"""
Test the SED→DOA pipeline against a real audio file.

Loads a WAV file, slices it into overlapping windows (matching the pipeline's
WINDOW_SAMPLES / HOP_SIZE_S settings), runs each window through SED and —
only when SED detects a sound — through the real GCC-PHAT DOA engine.

Usage:
    cd backend
    python3 scripts/test_with_audio_file.py tests/assets/test_audio.wav
    python3 scripts/test_with_audio_file.py /path/to/any/stereo_16k.wav

The script uses the REAL SEDDetector (requires M2D checkpoint) when the
checkpoint is present, and falls back to MockSEDModel automatically when it
is not, so the script works on every machine.

JSON AlertNotifications are written to stdout; progress logs go to stderr.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

# ── Path setup: run from inside backend/ ──────────────────────────────────
_BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_BACKEND))

from contracts.config import HOP_SIZE_S, SAMPLE_RATE, WINDOW_SAMPLES
from contracts.types import DOAInput, LLMInput, SEDInput
from modules.doa.interface import DOAModel
from modules.llm.mock import MockLLMReasoner

logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
log = logging.getLogger("file_test")


# ── Decide which SED model to use ────────────────────────────────────────

def _load_sed_model():
    checkpoint = _BACKEND / "resources" / "M2D_strong_1.pt"
    repo = _BACKEND / "third_party" / "PretrainedSED"
    if checkpoint.exists() and repo.exists():
        log.info("Using real SEDDetector (M2D checkpoint found).")
        from modules.sed.interface import SEDModel
        return SEDModel()
    log.warning("M2D checkpoint not found — falling back to MockSEDModel.")
    from modules.sed.mock import MockSEDModel
    return MockSEDModel()


# ── Audio loading ─────────────────────────────────────────────────────────

def load_stereo_16k(path: Path) -> np.ndarray:
    """
    Load a WAV file and return a float32 array of shape (n_samples, 2).

    - Mono files are duplicated to stereo.
    - Files with more than 2 channels are truncated to the first two.
    - Resampling is NOT performed — the file must be recorded at 16 kHz.
    """
    audio, sr = sf.read(str(path), dtype="float32", always_2d=True)

    if sr != SAMPLE_RATE:
        log.error(
            "Sample rate mismatch: file is %d Hz, pipeline expects %d Hz. "
            "Please resample the file first (e.g. sox input.wav -r 16000 out.wav).",
            sr, SAMPLE_RATE,
        )
        sys.exit(1)

    if audio.shape[1] == 1:
        log.warning("Mono file detected — duplicating channel for DOA (angle will be 0°).")
        audio = np.repeat(audio, 2, axis=1)
    elif audio.shape[1] > 2:
        log.warning("File has %d channels — using first two.", audio.shape[1])
        audio = audio[:, :2]

    return audio  # (n_samples, 2), float32


# ── Windowing ─────────────────────────────────────────────────────────────

def sliding_windows(stereo: np.ndarray) -> list[tuple[int, np.ndarray]]:
    """
    Yield (window_id, stereo_window) tuples from a stereo audio array.

    Windows are WINDOW_SAMPLES long with a HOP_SIZE_S hop.  The last
    partial window is zero-padded to full length.
    """
    hop = int(HOP_SIZE_S * SAMPLE_RATE)
    n_samples = stereo.shape[0]
    windows = []
    window_id = 0
    for start in range(0, max(n_samples, WINDOW_SAMPLES), hop):
        end = start + WINDOW_SAMPLES
        if start >= n_samples:
            break
        chunk = stereo[start:end]
        if chunk.shape[0] < WINDOW_SAMPLES:
            # Zero-pad the final partial window.
            pad = np.zeros((WINDOW_SAMPLES - chunk.shape[0], 2), dtype=np.float32)
            chunk = np.concatenate([chunk, pad], axis=0)
        windows.append((window_id, chunk))
        window_id += 1
    return windows


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        default = _BACKEND / "tests" / "assets" / "test_audio.wav"
        audio_path = default
        log.info("No path provided — using default: %s", audio_path)
    else:
        audio_path = Path(sys.argv[1])

    if not audio_path.exists():
        log.error("File not found: %s", audio_path)
        sys.exit(1)

    log.info("Loading audio: %s", audio_path)
    stereo = load_stereo_16k(audio_path)
    duration_s = stereo.shape[0] / SAMPLE_RATE
    log.info(
        "Loaded %.2f s of stereo audio (%d samples at %d Hz)",
        duration_s, stereo.shape[0], SAMPLE_RATE,
    )

    windows = sliding_windows(stereo)
    log.info(
        "Sliced into %d windows (%d samples each, %.1f s hop)",
        len(windows), WINDOW_SAMPLES, HOP_SIZE_S,
    )

    sed_model = _load_sed_model()
    doa_model = DOAModel()
    llm_reasoner = MockLLMReasoner()

    alerts_emitted = 0
    import time
    t0 = time.perf_counter()

    for window_id, stereo_window in windows:
        timestamp = window_id * HOP_SIZE_S   # synthetic timestamp
        mono = stereo_window[:, 0]

        # --- SED ---
        sed_input = SEDInput(
            audio_chunk=mono,
            sample_rate=SAMPLE_RATE,
            timestamp=timestamp,
            window_id=window_id,
        )
        sed_output = sed_model.detect(sed_input)

        log.debug(
            "window %3d | SED: %-13s conf=%.2f detected=%s",
            window_id, sed_output.sound_class, sed_output.confidence, sed_output.detected,
        )

        if not sed_output.detected:
            continue

        # --- DOA (only on detected windows) ---
        doa_input = DOAInput(
            audio_chunk=stereo_window,
            sample_rate=SAMPLE_RATE,
            timestamp=timestamp,
            window_id=window_id,
        )
        doa_output = doa_model.estimate(doa_input)

        # --- LLM ---
        llm_input = LLMInput(
            sound_class=sed_output.sound_class,
            sed_confidence=sed_output.confidence,
            doa_direction_of_arrival=doa_output.direction_of_arrival,
            doa_distance_estimation=doa_output.distance_estimation,
        )
        llm_output = llm_reasoner.reason(llm_input)

        alert = {
            "timestamp": timestamp,
            "sound_class": sed_output.sound_class,
            "direction_of_arrival": doa_output.direction_of_arrival,
            "distance_estimation": round(float(doa_output.distance_estimation), 3),
            "sed_confidence": round(sed_output.confidence, 4),
            "priority": llm_output.priority,
            "message": llm_output.message,
        }

        log.info(
            "ALERT window %3d | %-13s | conf=%.2f | dir=%5.1f° dist=%.2f m | %s",
            window_id,
            sed_output.sound_class,
            sed_output.confidence,
            doa_output.direction_of_arrival,
            doa_output.distance_estimation,
            llm_output.priority.upper(),
        )
        print(json.dumps(alert), flush=True)
        alerts_emitted += 1

    elapsed_ms = (time.perf_counter() - t0) * 1000
    log.info("─" * 60)
    log.info(
        "Processed %d windows in %.1f ms (%.2f ms/window)",
        len(windows), elapsed_ms, elapsed_ms / max(len(windows), 1),
    )
    log.info("Alerts emitted: %d", alerts_emitted)
    log.info("─" * 60)


if __name__ == "__main__":
    main()
