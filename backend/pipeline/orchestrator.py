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

Swapping mocks for real models:
    Change the import lines marked MOCK SWAP below — nothing else changes.

IMPORTANT: this application is fully local.  No network calls of any kind
are made here or in any module it imports.
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor

from contracts.types import (
    AlertNotification,
    DOAInput,
    DOAOutput,
    LLMInput,
    LLMOutput,
    RawChunk,
    SEDInput,
    SEDOutput,
)

# ── MOCK SWAP ────────────────────────────────────────────────────────────────
# SED: swap MockSEDModel → SEDModel (from modules.sed.interface) when ready.
from modules.sed.mock import MockSEDModel as SEDModel
from modules.llm.interface import LLMReasoner

# DOA: real GCC-PHAT implementation — no mock needed.
from modules.doa.interface import DOAModel
# ─────────────────────────────────────────────────────────────────────────────

from pipeline import audio_io, event_bus

logger = logging.getLogger(__name__)

# Dedicated thread pool so SED, DOA, and LLM can run without starving each
# other.  max_workers=4 covers the three model stages with headroom.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="seld")


async def _run_sed(
    raw_queue: asyncio.Queue[RawChunk],
    gate_queue: asyncio.Queue[tuple[SEDOutput, RawChunk]],
    model: SEDModel,
    window_times: dict[int, float],
) -> None:
    """Run SED on every chunk; forward detected windows to gate_queue."""
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
        sed_output: SEDOutput = await loop.run_in_executor(
            _executor, model.detect, sed_input
        )
        if sed_output.detected:
            await gate_queue.put((sed_output, chunk))
        raw_queue.task_done()


async def _run_doa_gate(
    gate_queue: asyncio.Queue[tuple[SEDOutput, RawChunk]],
    doa_model: DOAModel,
    llm_reasoner: LLMReasoner,
    window_times: dict[int, float],
) -> None:
    """For each SED-detected window: run DOA, reason with LLM, emit alert."""
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

        llm_input = LLMInput(
            sound_class=sed_output.sound_class,
            sed_confidence=sed_output.confidence,
            doa_direction_of_arrival=doa_output.direction_of_arrival,
            doa_distance_estimation=doa_output.distance_estimation,
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

        notification = AlertNotification(
            timestamp=sed_output.timestamp,
            sound_class=sed_output.sound_class,
            direction_of_arrival=doa_output.direction_of_arrival,
            distance_estimation=doa_output.distance_estimation,
            sed_confidence=sed_output.confidence,
            priority=llm_output.priority,
            message=llm_output.message,
        )

        start = window_times.pop(chunk.window_id, None)
        if start is not None:
            latency_ms = (time.perf_counter() - start) * 1000
            logger.debug(
                "window %d | %s | latency %.1f ms",
                chunk.window_id, sed_output.sound_class, latency_ms,
            )
        event_bus.emit_alert(notification)
        gate_queue.task_done()


async def run() -> None:
    """
    Start the full pipeline and run until cancelled or interrupted.

    Model instances are created once at startup, never per-window.
    """
    sed_model = SEDModel()
    doa_model = DOAModel()
    llm_reasoner = LLMReasoner()

    window_times: dict[int, float] = {}

    raw_queue: asyncio.Queue[RawChunk] = asyncio.Queue(maxsize=64)
    gate_queue: asyncio.Queue[tuple[SEDOutput, RawChunk]] = asyncio.Queue(maxsize=64)

    source_queue = await audio_io.start()

    async def _relay() -> None:
        """Relay audio chunks from the mic source into the pipeline."""
        while True:
            chunk = await source_queue.get()
            await raw_queue.put(chunk)
            source_queue.task_done()

    sed_task = asyncio.create_task(
        _run_sed(raw_queue, gate_queue, sed_model, window_times), name="sed"
    )
    doa_task = asyncio.create_task(
        _run_doa_gate(gate_queue, doa_model, llm_reasoner, window_times), name="doa_gate"
    )
    relay_task = asyncio.create_task(_relay(), name="relay")

    try:
        await asyncio.gather(relay_task, sed_task, doa_task)
    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Pipeline interrupted — shutting down.")
        for t in (relay_task, sed_task, doa_task):
            t.cancel()
        await asyncio.gather(relay_task, sed_task, doa_task, return_exceptions=True)


