"""
Orchestrator — the main async loop that wires the whole pipeline together.

Flow:
    audio_io.start()
        │
        └─ Task A: _run_sed       — RawChunk → SEDOutput
                                    detected windows only → gate_queue
        │
        └─ Task B: _run_doa_gate  — (SEDOutput, RawChunk) → DOAOutput
                                    → LLMOutput → AlertNotification
                                    → event_bus.emit_alert()

DOA only runs when SED detects a sound event, saving compute on silent
windows and removing the need for temporal alignment bookkeeping.

IMPORTANT: this application is fully local.  No network calls of any kind
are made here or in any module it imports.
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

from contracts.config import (
    EVENT_GROUPER_FLUSH_INTERVAL_S,
    SILENCE_RMS_THRESHOLD,
    WINDOW_SIZE_S,
)
from contracts.types import (
    AlertNotification,
    AlignedEvent,
    DOAInput,
    DOAOutput,
    LLMInput,
    LLMOutput,
    RawChunk,
    SEDInput,
    SEDOutput,
)

# Real model stages. They are instantiated once at startup and reused for every
# live microphone window.
from modules.sed.interface import SEDModel
from modules.llm.interface import LLMReasoner

# DOA: real GCC-PHAT implementation — no mock needed.
from modules.doa.distance import compute_distance
from modules.doa.interface import DOAModel

from pipeline import audio_io, event_bus
from pipeline.event_grouper import EventGrouper, GroupedEvent

logger = logging.getLogger(__name__)

# Dedicated thread pool so SED, DOA, and LLM can run without starving each
# other.  max_workers=4 covers the three model stages with headroom.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="seld")


def _put_latest(queue: asyncio.Queue, item: object) -> None:
    """Insert item, dropping the oldest queued item if live processing is behind."""
    if queue.full():
        try:
            queue.get_nowait()
            queue.task_done()
        except asyncio.QueueEmpty:
            pass
    try:
        queue.put_nowait(item)
    except asyncio.QueueFull:
        pass


async def _run_sed(
    raw_queue: asyncio.Queue[RawChunk],
    gate_queue: asyncio.Queue[tuple[SEDOutput, RawChunk]],
    model: SEDModel,
    window_times: dict[int, float],
) -> None:
    """Run SED on every chunk; forward detected windows to gate_queue.

    Silent-chunk gate: skip the SED forward pass entirely when the mono RMS
    is below SILENCE_RMS_THRESHOLD. The RMS check costs ~10 µs while the
    model call costs ~100 ms, so this keeps CPU near zero in quiet rooms.
    """
    loop = asyncio.get_running_loop()
    while True:
        chunk = await raw_queue.get()
        window_times[chunk.window_id] = time.perf_counter()

        if float(np.sqrt(np.mean(chunk.audio ** 2))) < SILENCE_RMS_THRESHOLD:
            raw_queue.task_done()
            continue

        sed_input = SEDInput(
            audio_chunk=chunk.audio,
            sample_rate=chunk.sample_rate,
            timestamp=chunk.timestamp,
            window_id=chunk.window_id,
        )
        sed_output: SEDOutput = await loop.run_in_executor(
            _executor, model.detect, sed_input
        )
        if sed_output.detected:
            _put_latest(gate_queue, (sed_output, chunk))
        raw_queue.task_done()


async def _run_doa_gate(
    gate_queue: asyncio.Queue[tuple[SEDOutput, RawChunk]],
    doa_model: DOAModel,
    llm_reasoner: LLMReasoner,
    grouper: EventGrouper,
    window_times: dict[int, float],
) -> None:
    """
    For each SED-detected window:
      1. run DOA,
      2. emit a per-window AlignedEvent on the raw-events channel,
      3. feed it to the grouper; for any event the grouper finalises,
         run LLM and emit an AlertNotification.
    """
    loop = asyncio.get_running_loop()
    while True:
        sed_output, chunk = await gate_queue.get()

        doa_input = DOAInput(
            audio_chunk=chunk.stereo_audio,
            sample_rate=chunk.sample_rate,
            timestamp=chunk.timestamp,
            window_id=chunk.window_id,
        )
        doa_output: DOAOutput = await loop.run_in_executor(
            _executor, doa_model.estimate, doa_input
        )

        # Class-conditional distance: DOA's standalone estimate is class-agnostic
        # and would systematically miss for loud (scream) or quiet (clap) sources.
        # Now that SED's class is known, recompute using the per-class reference.
        distance_m = round(
            compute_distance(
                event_rms=doa_output.event_rms,
                coherence=doa_output.coherence,
                sound_class=sed_output.sound_class,
            ),
            2,
        )

        aligned = AlignedEvent(
            window_id=chunk.window_id,
            timestamp=sed_output.timestamp,
            sound_class=sed_output.sound_class,
            sed_confidence=sed_output.confidence,
            doa_direction_of_arrival=doa_output.direction_of_arrival,
            doa_distance_estimation=distance_m,
        )

        # Granular feed — every detected window. Drives the radar UI.
        event_bus.emit_raw_event(aligned)

        # Group same-class detections within the sensitivity window.
        for finalized in grouper.add(aligned):
            await _emit_alert_for_group(loop, llm_reasoner, finalized)

        start = window_times.pop(chunk.window_id, None)
        if start is not None:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "window %d | %s | latency %.1f ms",
                chunk.window_id, sed_output.sound_class, latency_ms,
            )
        gate_queue.task_done()


async def _flush_grouper_periodically(
    grouper: EventGrouper, llm_reasoner: LLMReasoner
) -> None:
    """Emit any pending groups whose last detection has aged past the tolerance."""
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(EVENT_GROUPER_FLUSH_INTERVAL_S)
        for finalized in grouper.flush_stale(now=time.time() - WINDOW_SIZE_S):
            await _emit_alert_for_group(loop, llm_reasoner, finalized)


async def _emit_alert_for_group(
    loop: asyncio.AbstractEventLoop,
    llm_reasoner: LLMReasoner,
    grouped: GroupedEvent,
) -> None:
    """Run LLM on a finalised group and emit one AlertNotification."""
    llm_input = LLMInput(
        sound_class=grouped.sound_class,
        sed_confidence=grouped.sed_confidence,
        doa_direction_of_arrival=grouped.direction_of_arrival,
        doa_distance_estimation=grouped.distance_estimation,
    )
    try:
        llm_output: LLMOutput = await loop.run_in_executor(
            _executor, llm_reasoner.reason, llm_input
        )
    except Exception:
        llm_output = LLMOutput(
            priority="medium",
            message="Sound detected — could not assess urgency",
        )

    event_bus.emit_alert(
        AlertNotification(
            timestamp=grouped.timestamp,
            sound_class=grouped.sound_class,
            direction_of_arrival=grouped.direction_of_arrival,
            distance_estimation=grouped.distance_estimation,
            sed_confidence=grouped.sed_confidence,
            priority=llm_output.priority,
            message=llm_output.message,
            duration_s=grouped.duration_s,
            window_count=grouped.window_count,
        )
    )


async def run() -> None:
    """
    Start the full pipeline and run until cancelled or interrupted.

    Model instances are created once at startup, never per-window.
    """
    event_bus.emit_status("loading", stage="models")
    sed_model = SEDModel()
    doa_model = DOAModel()
    llm_reasoner = LLMReasoner()
    grouper = EventGrouper()

    window_times: dict[int, float] = {}

    raw_queue: asyncio.Queue[RawChunk] = asyncio.Queue(maxsize=64)
    gate_queue: asyncio.Queue[tuple[SEDOutput, RawChunk]] = asyncio.Queue(maxsize=64)

    event_bus.emit_status("loading", stage="microphone")
    source_queue = await audio_io.start()
    event_bus.emit_status("ready")

    async def _relay() -> None:
        """Relay audio chunks from the mic source into the pipeline."""
        while True:
            chunk = await source_queue.get()
            _put_latest(raw_queue, chunk)
            source_queue.task_done()

    sed_task = asyncio.create_task(
        _run_sed(raw_queue, gate_queue, sed_model, window_times), name="sed"
    )
    doa_task = asyncio.create_task(
        _run_doa_gate(
            gate_queue, doa_model, llm_reasoner, grouper, window_times
        ),
        name="doa_gate",
    )
    flush_task = asyncio.create_task(
        _flush_grouper_periodically(grouper, llm_reasoner), name="flusher"
    )
    relay_task = asyncio.create_task(_relay(), name="relay")

    tasks = (relay_task, sed_task, doa_task, flush_task)
    try:
        await asyncio.gather(*tasks)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Pipeline interrupted — shutting down.")
        # Drain any remaining pending groups before exit.
        loop = asyncio.get_running_loop()
        for finalized in grouper.flush_all():
            await _emit_alert_for_group(loop, llm_reasoner, finalized)
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
