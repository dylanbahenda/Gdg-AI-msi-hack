"""
Event Bus — decouples the async pipeline from whatever UI layer is running.

The orchestrator calls emit_alert() with an AlertNotification.  The event bus
serialises it as a single JSON line and writes it to stdout.  The Tauri sidecar
reads stdout line-by-line and forwards each line as a Tauri event into React.

Why stdout?
  - Zero dependencies on any GUI toolkit.
  - Tauri sidecar model requires exactly this: child process writes to stdout,
    Rust reads it, re-emits to the frontend via Tauri events.
  - Fully local — nothing leaves the machine.

For local Python-only testing, redirect stdout or pipe it anywhere you like:
    python main.py | jq .
"""
from __future__ import annotations

import json
import sys
from dataclasses import asdict

from contracts.types import AlertNotification, AlignedEvent


def emit_alert(notification: AlertNotification) -> None:
    """
    Serialise an AlertNotification as a single JSON line to stdout.

    Channel: ``{"channel": "alert", ...AlertNotification fields...}``.

    flush=True is critical: without it Python buffers stdout and the Tauri
    sidecar may never see the line until the buffer is full.
    """
    _emit("alert", notification)


def emit_raw_event(event: AlignedEvent) -> None:
    """
    Serialise a single per-window AlignedEvent as a JSON line.

    This is the granular feed: every detected window goes through here, even
    if the grouper later merges it into a single AlertNotification. The radar
    UI (and any movement / heat-map view) consumes this stream.

    Channel: ``{"channel": "raw_event", ...AlignedEvent fields...}``.
    """
    _emit("raw_event", event)


def emit_status(state: str, **details: object) -> None:
    """
    Emit a backend status line — used by the UI to know the pipeline is alive.

    Without this, in a silent room, no events fire and the UI sits waiting
    forever on stdout. Sending a 'ready' status as soon as models are loaded
    confirms the backend is online and listening.

    Channel: ``{"channel": "status", "state": ..., ...details}``.
    """
    payload = {"channel": "status", "state": state, **details}
    payload = _make_json_safe(payload)
    print(json.dumps(payload), flush=True)


def _emit(channel: str, payload_obj: object) -> None:
    payload = {"channel": channel, **asdict(payload_obj)}  # type: ignore[arg-type]
    payload = _make_json_safe(payload)
    print(json.dumps(payload), flush=True)


def _make_json_safe(obj: object) -> object:
    """Recursively convert numpy scalars to native Python types."""
    if isinstance(obj, dict):
        return {k: _make_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_make_json_safe(v) for v in obj]
    # numpy float32 / float64 / int32 etc. all have an item() method.
    if hasattr(obj, "item"):
        return obj.item()  # type: ignore[union-attr]
    return obj
