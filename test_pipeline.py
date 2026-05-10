#!/usr/bin/env python3
"""
Run the full SELD pipeline on a WAV file and print clean results.

Pipeline stages exercised end-to-end:
    SED → DOA → class-conditional distance → EventGrouper → LLM → AlertNotification

By default only grouped alerts are shown.  Pass ``--raw`` to also see one
line per per-window AlignedEvent (the radar / movement-tracking feed).

Usage:
    python test_pipeline.py path/to/audio.wav
    python test_pipeline.py path/to/audio.wav --raw
    python test_pipeline.py                         # uses built-in test file
"""
from __future__ import annotations

import logging
import sys
import time
import warnings
from pathlib import Path

import numpy as np

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

# ── paths ──────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / "backend"
sys.path.insert(0, str(BACKEND))

# Silence all third-party loggers; only our prints go to stdout.
logging.basicConfig(stream=sys.stderr, level=logging.CRITICAL)

# ── imports (after path setup) ─────────────────────────────────────────────
try:
    import soundfile as sf
except ModuleNotFoundError:
    sys.exit("Missing dependency: pip install soundfile")

try:
    from contracts.config import (
        HOP_SIZE_S,
        SAMPLE_RATE,
        SILENCE_RMS_THRESHOLD,
        WINDOW_SAMPLES,
    )
    from contracts.types import (
        AlignedEvent,
        DOAInput,
        LLMInput,
        SEDInput,
    )
    from modules.doa.distance import compute_distance
    from modules.doa.interface import DOAModel
    from pipeline.event_grouper import EventGrouper, GroupedEvent
except ModuleNotFoundError as e:
    sys.exit(f"Backend import error: {e}\nRun from the repo root.")


# ── model loaders (graceful fallbacks) ─────────────────────────────────────
def _load_sed():
    """Real SED if checkpoint + framework are available, else mock."""
    checkpoint = BACKEND / "resources" / "M2D_strong_1.pt"
    repo = BACKEND / "third_party" / "PretrainedSED"
    if checkpoint.exists() and repo.exists():
        from modules.sed.interface import SEDModel
        return SEDModel(), "real (M2D)"
    from modules.sed.mock import MockSEDModel
    return MockSEDModel(), "mock"


def _load_llm():
    """Real LLM via Ollama. If Ollama is unreachable at call time, the
    reasoner returns its own fallback message — there is no mock."""
    from modules.llm.interface import LLMReasoner
    return LLMReasoner(), "real (gemma3:1b via Ollama)"


# ── audio helpers ──────────────────────────────────────────────────────────
def _load_wav(path: Path) -> np.ndarray:
    audio, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if sr != SAMPLE_RATE:
        sys.exit(
            f"Sample rate mismatch: file={sr} Hz, pipeline expects {SAMPLE_RATE} Hz.\n"
            f"Resample first: sox {path} -r {SAMPLE_RATE} out.wav"
        )
    if audio.shape[1] == 1:
        print("  [warn] mono file — duplicating channel, DOA angle will be 0°", file=sys.stderr)
        audio = np.repeat(audio, 2, axis=1)
    elif audio.shape[1] > 2:
        audio = audio[:, :2]
    return audio  # (n_samples, 2) float32


def _windows(stereo: np.ndarray) -> list[tuple[int, np.ndarray]]:
    hop = int(HOP_SIZE_S * SAMPLE_RATE)
    out, wid = [], 0
    for start in range(0, max(stereo.shape[0], WINDOW_SAMPLES), hop):
        if start >= stereo.shape[0]:
            break
        chunk = stereo[start : start + WINDOW_SAMPLES]
        if chunk.shape[0] < WINDOW_SAMPLES:
            chunk = np.concatenate(
                [chunk, np.zeros((WINDOW_SAMPLES - chunk.shape[0], 2), dtype=np.float32)]
            )
        out.append((wid, chunk))
        wid += 1
    return out


# ── display ────────────────────────────────────────────────────────────────
_ICON = {"high": "🔴", "medium": "🟡", "low": "🟢"}
_W = 72


def _print_raw_event(ev: AlignedEvent) -> None:
    print(
        f"  raw  win {ev.window_id:>2}  ({ev.timestamp:>4.2f}s)  "
        f"{ev.sound_class:<13}  conf={ev.sed_confidence:>5.1%}  "
        f"dir={ev.doa_direction_of_arrival:>6.1f}°  "
        f"dist={ev.doa_distance_estimation:>5.2f}m"
    )


def _print_alert(idx: int, group: GroupedEvent, llm) -> None:
    icon = _ICON.get(llm.priority, "⚪")
    print(f"┌{'─' * (_W - 1)}")
    plural = "s" if group.window_count != 1 else ""
    print(
        f"│  Event #{idx}  │  t = {group.timestamp:.2f} s  "
        f"│  dur = {group.duration_s:.2f} s  │  n = {group.window_count} window{plural}"
    )
    print(f"├{'─' * (_W - 1)}")
    print(
        f"│  SED  ›  class = {group.sound_class:<16}  "
        f"confidence = {group.sed_confidence:.1%}"
    )
    print(
        f"│  DOA  ›  direction = {group.direction_of_arrival:>6.1f}°   "
        f"distance = {group.distance_estimation:.2f} m"
    )
    print(f"│  LLM  ›  {icon}  [{llm.priority.upper()}]  {llm.message}")
    print(f"└{'─' * (_W - 1)}")
    print()


# ── default file ───────────────────────────────────────────────────────────
DEFAULT_FILE = "test_audio.wav"


# ── main ───────────────────────────────────────────────────────────────────
def main() -> None:
    args = [a for a in sys.argv[1:] if a]
    show_raw = ("--raw" in args) or ("-r" in args)
    args = [a for a in args if a not in ("--raw", "-r")]

    if args:
        audio_path = Path(args[0])
    else:
        audio_path = BACKEND / "tests" / "assets" / DEFAULT_FILE

    if not audio_path.exists():
        sys.exit(f"File not found: {audio_path}")

    # ── header ────────────────────────────────────────────────────────────
    print()
    print("═" * _W)
    print("  SELD Pipeline Test")
    print(f"  File : {audio_path.name}")
    print("═" * _W)

    stereo = _load_wav(audio_path)
    duration_s = stereo.shape[0] / SAMPLE_RATE
    windows = _windows(stereo)

    sed_model, sed_label = _load_sed()
    doa_model = DOAModel()
    llm_reasoner, llm_label = _load_llm()
    grouper = EventGrouper()

    print(f"  Audio    : {duration_s:.2f} s  ({stereo.shape[0]} samples @ {SAMPLE_RATE} Hz)")
    print(f"  Windows  : {len(windows)}  ({WINDOW_SAMPLES} samples each, {HOP_SIZE_S} s hop)")
    print(f"  SED      : {sed_label}")
    print(f"  LLM      : {llm_label}")
    print(f"  Grouper  : merge tolerance {grouper.merge_tolerance_s} s")
    if show_raw:
        print("  Raw      : ON  (per-window AlignedEvent stream below)")
    print("─" * _W)
    print()

    detected_windows = 0
    alert_idx = 0
    t0 = time.perf_counter()

    def _emit_group(group: GroupedEvent) -> None:
        """Run LLM on a finalised group and print as an alert."""
        nonlocal alert_idx
        llm_out = llm_reasoner.reason(
            LLMInput(
                sound_class=group.sound_class,
                sed_confidence=group.sed_confidence,
                doa_direction_of_arrival=group.direction_of_arrival,
                doa_distance_estimation=group.distance_estimation,
            )
        )
        alert_idx += 1
        _print_alert(alert_idx, group, llm_out)

    # ── main loop ─────────────────────────────────────────────────────────
    silent_skipped = 0
    for window_id, stereo_window in windows:
        timestamp = window_id * HOP_SIZE_S
        mono = stereo_window[:, 0]

        # Silent-chunk gate: skip SED on quiet windows.
        if float(np.sqrt(np.mean(mono ** 2))) < SILENCE_RMS_THRESHOLD:
            silent_skipped += 1
            continue

        sed_out = sed_model.detect(
            SEDInput(
                audio_chunk=mono,
                sample_rate=SAMPLE_RATE,
                timestamp=timestamp,
                window_id=window_id,
            )
        )

        if not sed_out.detected:
            continue

        doa_out = doa_model.estimate(
            DOAInput(
                audio_chunk=stereo_window,
                sample_rate=SAMPLE_RATE,
                timestamp=timestamp,
                window_id=window_id,
            )
        )

        # Class-conditional distance (overrides DOA's class-agnostic estimate).
        distance_m = round(
            compute_distance(
                event_rms=doa_out.event_rms,
                coherence=doa_out.coherence,
                sound_class=sed_out.sound_class,
            ),
            2,
        )

        aligned = AlignedEvent(
            window_id=window_id,
            timestamp=timestamp,
            sound_class=sed_out.sound_class,
            sed_confidence=sed_out.confidence,
            doa_direction_of_arrival=doa_out.direction_of_arrival,
            doa_distance_estimation=distance_m,
        )

        if show_raw:
            _print_raw_event(aligned)
        detected_windows += 1

        for finalised in grouper.add(aligned):
            _emit_group(finalised)

    # Force-finalise any group still pending at the end of the file.
    for finalised in grouper.flush_all():
        _emit_group(finalised)

    elapsed_ms = (time.perf_counter() - t0) * 1000

    if alert_idx == 0:
        print("  No sound events detected.\n")

    print("═" * _W)
    print(f"  Silent-gated     : {silent_skipped}/{len(windows)} windows  (no SED call)")
    print(f"  Detected windows : {detected_windows}")
    print(f"  Grouped alerts   : {alert_idx}")
    print(
        f"  Elapsed          : {elapsed_ms:.0f} ms"
        f"   ({elapsed_ms / max(len(windows), 1):.1f} ms/window)"
    )
    print("═" * _W)
    print()


if __name__ == "__main__":
    main()
