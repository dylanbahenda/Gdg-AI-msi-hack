"""
Entry point for the SELD pipeline.

Run directly for local testing:
    python main.py | jq .

When bundled in Tauri the binary is named `seld_pipeline` and Tauri launches
it as a sidecar.  All AlertNotification objects are written as newline-delimited
JSON to stdout — no network, no cloud, fully local.

Press Ctrl+C to stop.
"""
from __future__ import annotations

import asyncio
import logging
import sys

# Configure logging to stderr so it does not pollute the stdout JSON feed.
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

from pipeline.orchestrator import run


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
