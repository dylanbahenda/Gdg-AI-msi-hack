"""
Diagnostic script — runs the real DOA engine against a stereo WAV file and
prints the estimated direction and distance.

Usage (from the backend/ directory):
    python scripts/test_doa.py [path/to/stereo.wav]

Defaults to tests/assets/test_audio.wav when no path is given.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

# Allow running from repo root or from backend/
_HERE = Path(__file__).resolve().parent.parent   # backend/
sys.path.insert(0, str(_HERE))

from modules.doa.engine import DOAEngine


def main(wav_path: Path) -> None:
    print(f"Loading {wav_path}...")
    audio_data, sample_rate = sf.read(wav_path)

    # Validation
    if audio_data.ndim == 1 or audio_data.shape[1] < 2:
        print("ERROR: file is mono. DOA requires stereo (≥ 2 channels).")
        sys.exit(1)

    if sample_rate != 16000:
        print(f"WARNING: sample rate is {sample_rate} Hz; pipeline expects 16000 Hz.")

    # 1.0 s window, 0.5 s hop (matches SED's try_clip.py)
    chunk_length = sample_rate
    hop_length = sample_rate // 2
    chunks = [
        audio_data[start:start + chunk_length, :]
        for start in range(0, len(audio_data) - chunk_length + 1, hop_length)
    ]

    # Auto-estimate mic distance
    mic_d = DOAEngine.estimate_mic_distance(chunks, sample_rate)
    print(f"Auto-estimated mic distance: {mic_d * 100:.1f} cm")

    # Select the chunk with the highest peak amplitude (event onset, not noise)
    best_idx, best_chunk = max(
        enumerate(chunks), key=lambda ic: float(np.max(np.abs(ic[1])))
    )
    print(
        f"Using chunk {best_idx}  "
        f"peak={float(np.max(np.abs(best_chunk))):.4f}  "
        f"p95_rms={float(np.sqrt(np.percentile(best_chunk ** 2, 95))):.4f}"
    )

    engine = DOAEngine(mic_distance_meters=mic_d)
    angle_deg, distance_m = engine.infer(best_chunk, sample_rate)

    # Map to 0–359.9° convention (same as DOAModel)
    direction = round(angle_deg % 360, 1) % 360

    print()
    print("=== DOA OUTPUT ===")
    if direction <= 5.0 or direction >= 355.0:
        dir_str = "Center"
    elif direction < 180:
        dir_str = "Right"
    else:
        dir_str = "Left"
    print(f"Direction: {direction:>6.1f}°  ({dir_str})")
    print(f"Distance : {distance_m:>6.2f} m")
    print("==================")

    print("\nAll chunks:")
    for i, c in enumerate(chunks):
        a, d = engine.infer(c, sample_rate)
        peak = float(np.max(np.abs(c)))
        t = i * hop_length / sample_rate
        print(f"  chunk {i} ({t:>4.2f}s): peak={peak:.4f}  angle={a:+.1f}°  dist={d:.2f} m")


if __name__ == "__main__":
    default = Path(__file__).resolve().parent.parent / "tests" / "assets" / "test_audio.wav"
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else default
    main(path)
