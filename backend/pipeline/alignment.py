"""
Temporal Alignment — pairs SEDOutput and DOAOutput by window_id.

Rules (from infernceclass.md and BackendPlan.md):
  1. Match SED and DOA outputs by window_id.
  2. Only forward if SEDOutput.detected == True.
  3. If either output is missing within ALIGNMENT_TIMEOUT_S, drop the window.

Design: two concurrent consumer coroutines share a pair of plain dicts.
Because asyncio is single-threaded, dict access between `await` points is
atomically safe — no locks needed.  This avoids the overhead of recreating
asyncio.Future objects on every loop iteration that the asyncio.wait approach
requires.
"""
from __future__ import annotations

import asyncio
import time

from contracts.config import ALIGNMENT_TIMEOUT_S
from contracts.types import AlignedEvent, DOAOutput, SEDOutput
from modules.doa.distance import compute_distance


async def run_alignment(
    sed_queue: asyncio.Queue[SEDOutput],
    doa_queue: asyncio.Queue[DOAOutput],
    out_queue: asyncio.Queue[AlignedEvent],
) -> None:
    """
    Continuously read from sed_queue and doa_queue, pair by window_id,
    and put AlignedEvent objects onto out_queue.

    This coroutine runs forever; cancel it to stop the pipeline.
    """
    # Shared state — safe because asyncio is cooperative (single-threaded).
    pending_sed: dict[int, tuple[SEDOutput, float]] = {}
    pending_doa: dict[int, tuple[DOAOutput, float]] = {}

    def _build_event(sed_out: SEDOutput, doa_out: DOAOutput) -> AlignedEvent:
        # Recompute distance using the SED class — DOA's standalone estimate is
        # class-agnostic and would systematically miss for loud (scream) or
        # quiet (whisper) source types.
        distance = compute_distance(
            event_rms=doa_out.event_rms,
            coherence=doa_out.coherence,
            sound_class=sed_out.sound_class,
        )
        return AlignedEvent(
            window_id=sed_out.window_id,
            timestamp=sed_out.timestamp,
            sound_class=sed_out.sound_class,
            sed_confidence=sed_out.confidence,
            doa_direction_of_arrival=doa_out.direction_of_arrival,
            doa_distance_estimation=round(distance, 2),
        )

    async def _consume_sed() -> None:
        while True:
            sed_out = await sed_queue.get()
            # Drop silent windows immediately — nothing to align.
            if not sed_out.detected:
                continue
            wid = sed_out.window_id
            if wid in pending_doa:
                doa_out, _ = pending_doa.pop(wid)
                await out_queue.put(_build_event(sed_out, doa_out))
            else:
                pending_sed[wid] = (sed_out, time.monotonic())

    async def _consume_doa() -> None:
        while True:
            doa_out = await doa_queue.get()
            wid = doa_out.window_id
            if wid in pending_sed:
                sed_out, _ = pending_sed.pop(wid)
                await out_queue.put(_build_event(sed_out, doa_out))
            else:
                pending_doa[wid] = (doa_out, time.monotonic())

    async def _cleanup_stale() -> None:
        """Periodically evict entries that waited longer than the timeout."""
        while True:
            await asyncio.sleep(ALIGNMENT_TIMEOUT_S)
            cutoff = time.monotonic() - ALIGNMENT_TIMEOUT_S
            for wid in [w for w, (_, t) in pending_sed.items() if t < cutoff]:
                del pending_sed[wid]
            for wid in [w for w, (_, t) in pending_doa.items() if t < cutoff]:
                del pending_doa[wid]

    await asyncio.gather(_consume_sed(), _consume_doa(), _cleanup_stale())
