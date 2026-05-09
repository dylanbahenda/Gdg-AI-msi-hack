"""Run SEDDetector over a local audio file and print per-window results.

Usage:
    python scripts/try_clip.py <path_to_audio>
    python scripts/try_clip.py <path_to_audio> --hop 0.5 --window 1.0 --device cpu

Loads wav, flac, ogg, mp3, m4a, and most other formats via librosa (which
falls back to audioread/PyAV — no system ffmpeg required). Downmixes to mono,
resamples to 16 kHz, then slides a window of `--window` seconds with stride
`--hop` seconds. For each window, prints the top macro, its confidence, and
whether it cleared the detection threshold.
"""

import argparse
import sys
from pathlib import Path

import librosa
import numpy as np

from modules.sed.inference import SEDDetector
from contracts.types import SEDInput


_TARGET_SR = 16000


def load_audio_16k_mono(path: Path) -> np.ndarray:
    waveform, _ = librosa.load(str(path), sr=_TARGET_SR, mono=True)
    return waveform.astype(np.float32, copy=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio_path", type=Path)
    parser.add_argument("--window", type=float, default=1.0, help="window length in seconds")
    parser.add_argument("--hop", type=float, default=0.5, help="hop length in seconds")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--encoder", default="M2D", choices=["M2D", "BEATs", "ATST-F"])
    parser.add_argument("--threshold", type=float, default=0.1)
    parser.add_argument("--show-all", action="store_true", help="show all windows, not just detections")
    args = parser.parse_args()

    if not args.audio_path.exists():
        print(f"file not found: {args.audio_path}", file=sys.stderr)
        return 1

    print(f"Loading {args.audio_path}...")
    waveform = load_audio_16k_mono(args.audio_path)
    duration = len(waveform) / _TARGET_SR
    print(f"  duration: {duration:.2f}s, samples: {len(waveform)}")

    print(f"Loading SEDDetector(encoder={args.encoder!r}, device={args.device!r})...")
    detector = SEDDetector(
        encoder=args.encoder,
        device=args.device,
        detection_threshold=args.threshold,
    )

    window_samples = int(args.window * _TARGET_SR)
    hop_samples = int(args.hop * _TARGET_SR)

    print()
    print(f"{'window':>7} {'time':>8}  {'class':<14} {'conf':>6}  detected")
    print("-" * 50)

    window_id = 0
    n_detections = 0
    for start in range(0, len(waveform) - window_samples + 1, hop_samples):
        chunk = waveform[start : start + window_samples]
        timestamp = start / _TARGET_SR
        out = detector.detect(
            SEDInput(
                audio_chunk=chunk,
                sample_rate=_TARGET_SR,
                timestamp=timestamp,
                window_id=window_id,
            )
        )
        if out.detected:
            n_detections += 1

        if args.show_all or out.detected:
            marker = "*" if out.detected else " "
            print(
                f"{window_id:>7} {timestamp:>7.2f}s  "
                f"{out.sound_class:<14} {out.confidence:>6.3f}  {marker}"
            )

        window_id += 1

    print("-" * 50)
    print(f"total windows: {window_id}, detections: {n_detections}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
