"""
CLI entry point for the SELD pipeline.

Default mode is real-time microphone input:
    python main.py

File input is retained only as a debug/fallback path:
    python main.py --file tests/assets/test_audio.wav

All events are written as newline-delimited JSON to stdout. Progress logs go to
stderr so stdout remains machine-readable.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Configure logging to stderr so it does not pollute the stdout JSON feed.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local SELD pipeline.")
    parser.add_argument(
        "--file",
        type=Path,
        help="Debug/fallback mode: process a 16 kHz audio file instead of the mic.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    try:
        if args.file is not None:
            from pipeline.file_runner import run_file

            run_file(args.file)
        else:
            from pipeline.orchestrator import run

            logging.getLogger(__name__).info("Starting live microphone mode.")
            asyncio.run(run())
    except Exception as exc:
        logging.getLogger(__name__).error("%s", exc)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
