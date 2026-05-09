"""
Orchestrator — the main async loop that wires the whole pipeline together.

Flow:
    audio_io.start()
        │
        ├─ Task A: for each RawChunk → SEDModel.detect()  → sed_queue
        ├─ Task B: for each RawChunk → DOAModel.estimate() → doa_queue
        └─ Task C: alignment.run_alignment(sed_queue, doa_queue, aligned_queue)
                        │
                        └─ for each AlignedEvent → LLMReasoner.reason()
                                                 → AlertNotification
                                                 → event_bus.emit_alert()

Swapping mocks for real models:
    Change the three import lines below (marked MOCK SWAP) — nothing else
    in the pipeline needs to change.

IMPORTANT: this application is fully local.  No network calls of any kind
are made here or in any module it imports.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from contracts.types import (
    AlignedEvent,
    AlertNotification,
    DOAInput,
    LLMInput,
    RawChunk,
    SEDInput,
)

# ── MOCK SWAP ────────────────────────────────────────────────────────────────
# Dev (mock): comment these three lines out when the real models are ready.
from modules.sed.mock import MockSEDModel as SEDModel  # noqa: E402
from modules.doa.mock import MockDOAModel as DOAModel  # noqa: E402
from modules.llm.mock import MockLLMReasoner as LLMReasoner  # noqa: E402

# Production (real): uncomment these three lines and remove the mock imports.
# from modules.sed.interface import SEDModel
# from modules.doa.interface import DOAModel
# from modules.llm.interface import LLMReasoner
# ─────────────────────────────────────────────────────────────────────────────

from pipeline import audio_io, alignment, event_bus

logger = logging.getLogger(__name__)

# Dedicated thread pool: at minimum one thread per CPU-bound model (SED, DOA,
# LLM) so they can run in parallel without starving each other.  The default
# executor shares threads with everything else in the process.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="seld")


async def _run_sed(
    raw_queue: asyncio.Queue[RawChunk],
    sed_queue: asyncio.Queue,
    model: SEDModel,
    window_times: dict[int, float],
) -> None:
    """Task A — feed every audio chunk through the SED model."""
    loop = asyncio.get_running_loop()
    while True:
        chunk = await raw_queue.get()
        window_times[chunk.window_id] = time.perf_counter()
        sed_input = SEDInput(
            audio_chunk=chunk.audio,
            sample_rate=chunk.sample_rate,
            timestamp=chunk.timestamp,
            window_id=chunk.window_id,
        )
        # Run blocking inference in the dedicated thread pool.
        sed_output = await loop.run_in_executor(_executor, model.detect, sed_input)
        await sed_queue.put(sed_output)
        raw_queue.task_done()


async def _run_doa(
    raw_queue: asyncio.Queue[RawChunk],
    doa_queue: asyncio.Queue,
    model: DOAModel,
) -> None:
    """Task B — feed every audio chunk through the DOA model."""
    loop = asyncio.get_running_loop()
    while True:
        chunk = await raw_queue.get()
        doa_input = DOAInput(
            audio_chunk=chunk.audio,
            sample_rate=chunk.sample_rate,
            timestamp=chunk.timestamp,
            window_id=chunk.window_id,
        )
        doa_output = await loop.run_in_executor(_executor, model.estimate, doa_input)
        await doa_queue.put(doa_output)
        raw_queue.task_done()


async def _run_llm(
    aligned_queue: asyncio.Queue[AlignedEvent],
    reasoner: LLMReasoner,
    window_times: dict[int, float],
) -> None:
    """Consume AlignedEvents, run LLM reasoning, emit AlertNotifications."""
    loop = asyncio.get_running_loop()
    while True:
        event = await aligned_queue.get()
        llm_input = LLMInput(
            sound_class=event.sound_class,
            sed_confidence=event.sed_confidence,
            doa_direction_of_arrival=event.doa_direction_of_arrival,
            doa_distance_estimation=event.doa_distance_estimation,
        )
        try:
            llm_output = await loop.run_in_executor(_executor, reasoner.reason, llm_input)
        except Exception:
            from contracts.types import LLMOutput
            llm_output = LLMOutput(
                priority="medium",
                message="Sound detected — could not assess urgency",
            )

        notification = AlertNotification(
            timestamp=event.timestamp,
            sound_class=event.sound_class,
            direction_of_arrival=event.doa_direction_of_arrival,
            distance_estimation=event.doa_distance_estimation,
            sed_confidence=event.sed_confidence,
            priority=llm_output.priority,
            message=llm_output.message,
        )
        # Log end-to-end latency for this window.
        start = window_times.pop(event.window_id, None)
        if start is not None:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "window %d | %s | latency %.1f ms",
                event.window_id, event.sound_class, latency_ms,
            )
        event_bus.emit_alert(notification)
        aligned_queue.task_done()


async def run() -> None:
    """
    Start the full pipeline and run until cancelled or interrupted.

    The three model instances are created here — once at startup,
    never per-window.
    """
    sed_model = SEDModel()
    doa_model = DOAModel()
    llm_reasoner = LLMReasoner()

    # Shared latency tracker: window_id → perf_counter() when chunk first entered pipeline.
    window_times: dict[int, float] = {}

    # Bounded queues prevent unbounded memory growth if a stage falls behind.
    sed_queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    doa_queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    aligned_queue: asyncio.Queue[AlignedEvent] = asyncio.Queue(maxsize=64)
    sed_raw_queue: asyncio.Queue[RawChunk] = asyncio.Queue(maxsize=64)
    doa_raw_queue: asyncio.Queue[RawChunk] = asyncio.Queue(maxsize=64)

    source_queue = await audio_io.start()

    async def _fan_out() -> None:
        """Copy each RawChunk from the mic source to both SED and DOA queues."""
        while True:
            chunk = await source_queue.get()
            for q in (sed_raw_queue, doa_raw_queue):
                try:
                    q.put_nowait(chunk)
                except asyncio.QueueFull:
                    logger.warning("Queue full for window %d — dropping chunk", chunk.window_id)
            source_queue.task_done()

    tasks = [
        asyncio.create_task(_fan_out(), name="fan_out"),
        asyncio.create_task(_run_sed(sed_raw_queue, sed_queue, sed_model, window_times), name="sed"),
        asyncio.create_task(_run_doa(doa_raw_queue, doa_queue, doa_model), name="doa"),
        asyncio.create_task(
            alignment.run_alignment(sed_queue, doa_queue, aligned_queue),
            name="alignment",
        ),
        asyncio.create_task(_run_llm(aligned_queue, llm_reasoner, window_times), name="llm"),
    ]

    logger.info("SELD pipeline started (mock mode)")
    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        logger.info("Pipeline shutting down")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
