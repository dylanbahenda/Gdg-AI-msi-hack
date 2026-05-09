"""
Pipeline integration test — runs the full mock pipeline without a microphone.

Instead of opening the mic, this script generates synthetic RawChunk objects
at the configured hop rate and feeds them directly into the orchestrator
queues.  Everything else (SED mock, DOA mock, alignment, LLM mock, event bus)
runs exactly as it would in production.

Usage:
    cd backend
    python3 test_pipeline.py            # 30 windows (~15 s simulated)
    python3 test_pipeline.py 60         # 60 windows (~30 s simulated)

Output: one AlertNotification JSON line per detected event on stdout,
        latency stats on stderr at the end.

No network, no API, no cloud — 100% local.
"""
from __future__ import annotations

import asyncio
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np

# ---------------------------------------------------------------------------
# Logging goes to stderr so it does not pollute the JSON stdout feed.
# ---------------------------------------------------------------------------
logging.basicConfig(
    stream=sys.stderr,
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

from contracts.config import HOP_SIZE_S, SAMPLE_RATE, WINDOW_SAMPLES
from contracts.types import (
    AlignedEvent,
    AlertNotification,
    DOAInput,
    LLMInput,
    LLMOutput,
    RawChunk,
    SEDInput,
)
from modules.doa.mock import MockDOAModel
from modules.llm.mock import MockLLMReasoner
from modules.sed.mock import MockSEDModel
from pipeline import alignment, event_bus

# Same dedicated executor as the production orchestrator.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="seld_test")


async def _synthetic_audio_producer(
    sed_raw: asyncio.Queue[RawChunk],
    doa_raw: asyncio.Queue[RawChunk],
    num_windows: int,
    window_start_times: dict[int, float],
) -> None:
    """
    Emit `num_windows` synthetic RawChunks at the real hop rate.

    Audio is white noise in [-1, 1] — shape and dtype match what the real mic
    produces, so the mocks receive correctly-shaped arrays.
    """
    log = logging.getLogger("producer")
    for window_id in range(num_windows):
        audio = np.random.uniform(-1.0, 1.0, WINDOW_SAMPLES).astype(np.float32)
        chunk = RawChunk(
            audio=audio,
            sample_rate=SAMPLE_RATE,
            timestamp=time.time(),
            window_id=window_id,
        )
        # Record the exact moment this chunk enters the pipeline.
        window_start_times[window_id] = time.perf_counter()

        # Fan-out: both SED and DOA get the same chunk reference.
        await sed_raw.put(chunk)
        await doa_raw.put(chunk)

        log.debug("Emitted window %d", window_id)
        await asyncio.sleep(HOP_SIZE_S)   # real-time pacing

    log.info("All %d windows produced.", num_windows)


async def _run_sed(
    raw_queue: asyncio.Queue[RawChunk],
    sed_queue: asyncio.Queue,
    model: MockSEDModel,
) -> None:
    loop = asyncio.get_running_loop()
    while True:
        chunk = await raw_queue.get()
        sed_input = SEDInput(
            audio_chunk=chunk.audio,
            sample_rate=chunk.sample_rate,
            timestamp=chunk.timestamp,
            window_id=chunk.window_id,
        )
        result = await loop.run_in_executor(_executor, model.detect, sed_input)
        await sed_queue.put(result)
        raw_queue.task_done()


async def _run_doa(
    raw_queue: asyncio.Queue[RawChunk],
    doa_queue: asyncio.Queue,
    model: MockDOAModel,
) -> None:
    loop = asyncio.get_running_loop()
    while True:
        chunk = await raw_queue.get()
        doa_input = DOAInput(
            audio_chunk=chunk.audio,
            sample_rate=chunk.sample_rate,
            timestamp=chunk.timestamp,
            window_id=chunk.window_id,
        )
        result = await loop.run_in_executor(_executor, model.estimate, doa_input)
        await doa_queue.put(result)
        raw_queue.task_done()


async def _run_llm(
    aligned_queue: asyncio.Queue[AlignedEvent],
    reasoner: MockLLMReasoner,
    alert_count: list[int],
    latencies_ms: list[float],
    window_start_times: dict[int, float],
) -> None:
    loop = asyncio.get_running_loop()
    log = logging.getLogger("llm")
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

        # Measure end-to-end latency for this window.
        start = window_start_times.pop(event.window_id, None)
        if start is not None:
            latency_ms = (time.perf_counter() - start) * 1000
            latencies_ms.append(latency_ms)
            log.info(
                "window %-3d | %-13s | priority=%-6s | latency=%.2f ms",
                event.window_id, event.sound_class, llm_output.priority, latency_ms,
            )

        event_bus.emit_alert(notification)
        alert_count[0] += 1
        aligned_queue.task_done()


async def run_test(num_windows: int = 30) -> None:
    """
    Run the mock pipeline for `num_windows` windows.

    At 0.5 s/hop that is 15 seconds of simulated audio, which should
    produce ~5 AlertNotification events (one every ~3 s).
    """
    sed_model = MockSEDModel()
    doa_model = MockDOAModel()
    llm_reasoner = MockLLMReasoner()

    sed_raw: asyncio.Queue[RawChunk] = asyncio.Queue(maxsize=64)
    doa_raw: asyncio.Queue[RawChunk] = asyncio.Queue(maxsize=64)
    sed_queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    doa_queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    aligned_queue: asyncio.Queue[AlignedEvent] = asyncio.Queue(maxsize=64)

    alert_count: list[int] = [0]
    latencies_ms: list[float] = []
    window_start_times: dict[int, float] = {}

    log = logging.getLogger("test")
    log.info(
        "Starting mock pipeline — %d windows at %.1f s/hop = %.0f s simulated audio",
        num_windows, HOP_SIZE_S, num_windows * HOP_SIZE_S,
    )
    log.info("Expecting ~%d alerts.  JSON output on stdout.", num_windows // 6)

    producer_task = asyncio.create_task(
        _synthetic_audio_producer(sed_raw, doa_raw, num_windows, window_start_times),
        name="producer",
    )
    sed_task   = asyncio.create_task(_run_sed(sed_raw,  sed_queue,  sed_model),  name="sed")
    doa_task   = asyncio.create_task(_run_doa(doa_raw,  doa_queue,  doa_model),  name="doa")
    align_task = asyncio.create_task(
        alignment.run_alignment(sed_queue, doa_queue, aligned_queue), name="alignment",
    )
    llm_task   = asyncio.create_task(
        _run_llm(aligned_queue, llm_reasoner, alert_count, latencies_ms, window_start_times),
        name="llm",
    )

    await producer_task
    log.info("Producer done — draining pipeline…")
    await asyncio.sleep(1.0)   # give alignment its 200 ms timeout budget to flush

    for t in (sed_task, doa_task, align_task, llm_task):
        t.cancel()
    await asyncio.gather(sed_task, doa_task, align_task, llm_task, return_exceptions=True)

    # ── Latency summary ────────────────────────────────────────────────────
    log.info("─" * 55)
    log.info("Test complete.  Total alerts emitted: %d", alert_count[0])
    if latencies_ms:
        log.info(
            "End-to-end latency (chunk-in → alert-out):  "
            "min=%.2f ms  avg=%.2f ms  max=%.2f ms",
            min(latencies_ms),
            sum(latencies_ms) / len(latencies_ms),
            max(latencies_ms),
        )
    log.info("─" * 55)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    try:
        asyncio.run(run_test(num_windows=n))
    except KeyboardInterrupt:
        pass
