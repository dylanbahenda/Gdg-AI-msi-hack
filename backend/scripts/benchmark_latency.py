"""Benchmark SEDDetector.detect() latency over N synthetic 1s chunks.

Usage:
    python scripts/benchmark_latency.py [--encoder M2D] [--device cpu] [--n 100]
"""

import argparse
import time

import numpy as np

from modules.sed.inference import SEDDetector
from contracts.types import SEDInput


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--encoder", default="M2D", choices=["M2D", "BEATs", "ATST-F"])
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=5)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    print(f"Loading SEDDetector(encoder={args.encoder!r}, device={args.device!r})...")
    detector = SEDDetector(encoder=args.encoder, device=args.device)

    rng = np.random.default_rng(args.seed)
    chunks = [
        rng.standard_normal(16000).astype(np.float32) * 0.1
        for _ in range(args.n + args.warmup)
    ]

    print(f"Warmup: {args.warmup} runs...")
    for i in range(args.warmup):
        detector.detect(
            SEDInput(
                audio_chunk=chunks[i],
                sample_rate=16000,
                timestamp=float(i),
                window_id=i,
            )
        )

    print(f"Measuring: {args.n} runs...")
    timings_ms: list[float] = []
    for i in range(args.warmup, args.warmup + args.n):
        t0 = time.perf_counter()
        detector.detect(
            SEDInput(
                audio_chunk=chunks[i],
                sample_rate=16000,
                timestamp=float(i),
                window_id=i,
            )
        )
        t1 = time.perf_counter()
        timings_ms.append((t1 - t0) * 1000.0)

    arr = np.array(timings_ms)
    p50 = float(np.percentile(arr, 50))
    p95 = float(np.percentile(arr, 95))
    p99 = float(np.percentile(arr, 99))

    print()
    print(f"=== {args.encoder} on {args.device}, n={args.n} ===")
    print(f"  mean: {arr.mean():7.1f} ms")
    print(f"  p50:  {p50:7.1f} ms")
    print(f"  p95:  {p95:7.1f} ms")
    print(f"  p99:  {p99:7.1f} ms")
    print(f"  min:  {arr.min():7.1f} ms")
    print(f"  max:  {arr.max():7.1f} ms")
    print()
    budget_ms = 500.0
    if p95 <= budget_ms:
        print(f"PASS: p95 within {budget_ms:.0f}ms CPU budget.")
    else:
        print(f"FAIL: p95 ({p95:.1f} ms) exceeds {budget_ms:.0f}ms budget.")


if __name__ == "__main__":
    main()
