#!/usr/bin/env python3
"""
Run the full SELD pipeline on a WAV file and print clean results.

Usage:
    python test_pipeline.py path/to/audio.wav
    python test_pipeline.py                      # uses built-in test file
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

# Silence all third-party loggers; only our prints go to stdout
logging.basicConfig(stream=sys.stderr, level=logging.CRITICAL)

# ── imports (after path setup) ─────────────────────────────────────────────
try:
    import soundfile as sf
except ModuleNotFoundError:
    sys.exit("Missing dependency: pip install soundfile")

try:
    from contracts.config import HOP_SIZE_S, SAMPLE_RATE, WINDOW_SAMPLES
    from contracts.types import DOAInput, LLMInput, SEDInput
    from modules.doa.interface import DOAModel
    from modules.llm.interface import LLMReasoner
except ModuleNotFoundError as e:
    sys.exit(f"Backend import error: {e}\nRun from the repo root.")


# ── model loader ───────────────────────────────────────────────────────────
def _load_sed():
    checkpoint = BACKEND / "resources" / "M2D_strong_1.pt"
    repo = BACKEND / "third_party" / "PretrainedSED"
    if checkpoint.exists() and repo.exists():
        from modules.sed.interface import SEDModel
        return SEDModel(), "real (M2D)"
    from modules.sed.mock import MockSEDModel
    return MockSEDModel(), "mock"


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
_W = 68


def _print_alert(window_id, timestamp, sed, doa, llm) -> None:
    icon = _ICON.get(llm.priority, "⚪")
    print(f"┌{'─' * (_W - 1)}")
    print(f"│  Window {window_id:>2}  │  t = {timestamp:.2f} s")
    print(f"├{'─' * (_W - 1)}")
    print(f"│  SED  ›  class = {sed.sound_class:<16}  confidence = {sed.confidence:.1%}")
    print(f"│  DOA  ›  direction = {doa.direction_of_arrival:>6.1f}°   distance = {doa.distance_estimation:.2f} m")
    print(f"│  LLM  ›  {icon}  [{llm.priority.upper()}]  {llm.message}")
    print(f"└{'─' * (_W - 1)}")
    print()


# ── main ───────────────────────────────────────────────────────────────────
def main() -> None:
    if len(sys.argv) >= 2:
        audio_path = Path(sys.argv[1])
    else:
        audio_path = BACKEND / "tests" / "assets" / "test_shout_1.wav"

    if not audio_path.exists():
        sys.exit(f"File not found: {audio_path}")

    # ── header ────────────────────────────────────────────────────────────
    print()
    print("═" * _W)
    print(f"  SELD Pipeline Test")
    print(f"  File : {audio_path.name}")
    print("═" * _W)

    stereo = _load_wav(audio_path)
    duration_s = stereo.shape[0] / SAMPLE_RATE
    windows = _windows(stereo)

    sed_model, sed_label = _load_sed()
    doa_model = DOAModel()
    llm_reasoner = LLMReasoner()

    print(f"  Audio    : {duration_s:.2f} s  ({stereo.shape[0]} samples @ {SAMPLE_RATE} Hz)")
    print(f"  Windows  : {len(windows)}  ({WINDOW_SAMPLES} samples each, {HOP_SIZE_S} s hop)")
    print(f"  SED      : {sed_label}")
    print(f"  LLM      : gemma3:1b  (via Ollama)")
    print("─" * _W)
    print()

    alerts = 0
    t0 = time.perf_counter()

    for window_id, stereo_window in windows:
        timestamp = window_id * HOP_SIZE_S
        mono = stereo_window[:, 0]

        sed_out = sed_model.detect(
            SEDInput(audio_chunk=mono, sample_rate=SAMPLE_RATE,
                     timestamp=timestamp, window_id=window_id)
        )

        if not sed_out.detected:
            continue

        doa_out = doa_model.estimate(
            DOAInput(audio_chunk=stereo_window, sample_rate=SAMPLE_RATE,
                     timestamp=timestamp, window_id=window_id)
        )

        llm_out = llm_reasoner.reason(
            LLMInput(
                sound_class=sed_out.sound_class,
                sed_confidence=sed_out.confidence,
                doa_direction_of_arrival=doa_out.direction_of_arrival,
                doa_distance_estimation=doa_out.distance_estimation,
            )
        )

        _print_alert(window_id, timestamp, sed_out, doa_out, llm_out)
        alerts += 1

    elapsed_ms = (time.perf_counter() - t0) * 1000

    if alerts == 0:
        print("  No sound events detected.\n")

    print("═" * _W)
    print(f"  Alerts   : {alerts}")
    print(f"  Elapsed  : {elapsed_ms:.0f} ms   ({elapsed_ms / max(len(windows), 1):.1f} ms/window)")
    print("═" * _W)
    print()


if __name__ == "__main__":
    main()
