"""
Pipeline integration test — exercises the SED→DOA pipeline end-to-end
without a microphone.

Synthetic stereo audio (white noise with slight channel asymmetry) is fed
through MockSEDModel and the real GCC-PHAT DOAModel.  When SED detects a
sound event the DOA angle and distance are computed from the same audio
window and an AlertNotification is emitted to stdout as JSON.

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
from contracts.config import EVENT_GROUPER_FLUSH_INTERVAL_S, SILENCE_RMS_THRESHOLD
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
from modules.doa.distance import compute_distance
from modules.doa.interface import DOAModel
from modules.llm.mock import MockLLMReasoner
from modules.sed.mock import MockSEDModel
from pipeline import event_bus
from pipeline.event_grouper import EventGrouper, GroupedEvent

# Same dedicated executor as the production orchestrator.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="seld_test")


async def _synthetic_audio_producer(
    raw_queue: asyncio.Queue[RawChunk],
    num_windows: int,
    window_start_times: dict[int, float],
) -> None:
    """
    Emit `num_windows` synthetic stereo RawChunks at the real hop rate.

    Audio is white noise in [-1, 1] with a slight amplitude difference
    between channels — this gives GCC-PHAT a non-trivial signal to work with.
    """
    log = logging.getLogger("producer")
    for window_id in range(num_windows):
        mono = np.random.uniform(-1.0, 1.0, WINDOW_SAMPLES).astype(np.float32)
        # Small amplitude offset between channels simulates a sound source
        # slightly off-centre, so DOA can estimate a non-zero angle.
        stereo = np.stack([mono, mono * 0.85], axis=1)
        chunk = RawChunk(
            audio=mono,
            stereo_audio=stereo,
            sample_rate=SAMPLE_RATE,
            timestamp=time.time(),
            window_id=window_id,
        )
        window_start_times[window_id] = time.perf_counter()
        await raw_queue.put(chunk)
        log.debug("Emitted window %d", window_id)
        await asyncio.sleep(HOP_SIZE_S)   # real-time pacing

    log.info("All %d windows produced.", num_windows)


async def _run_sed(
    raw_queue: asyncio.Queue[RawChunk],
    gate_queue: asyncio.Queue[tuple[SEDOutput, RawChunk]],
    model: MockSEDModel,
) -> None:
    """Run SED on every chunk; forward detected windows to gate_queue.

    Silent-chunk gate: skip the SED model call when mono RMS is below
    SILENCE_RMS_THRESHOLD — keeps the test honest under quiet inputs.
    """
    loop = asyncio.get_running_loop()
    while True:
        chunk = await raw_queue.get()

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
            await gate_queue.put((sed_output, chunk))
        raw_queue.task_done()


async def _run_doa_gate(
    gate_queue: asyncio.Queue[tuple[SEDOutput, RawChunk]],
    doa_model: DOAModel,
    llm_reasoner: MockLLMReasoner,
    grouper: EventGrouper,
    alert_count: list[int],
    latencies_ms: list[float],
    window_start_times: dict[int, float],
) -> None:
    """
    For each SED-detected window: run DOA, emit raw event, feed grouper.
    The grouper finalises events; LLM runs once per finalised group.
    """
    loop = asyncio.get_running_loop()
    log = logging.getLogger("doa_gate")
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

        # Class-conditional distance: see orchestrator.py for rationale.
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
        event_bus.emit_raw_event(aligned)
        log.info(
            "raw window %-3d | %-13s | conf=%.2f | dir=%5.1f° dist=%.2fm",
            chunk.window_id,
            sed_output.sound_class,
            sed_output.confidence,
            doa_output.direction_of_arrival,
            distance_m,
        )

        for finalized in grouper.add(aligned):
            await _emit_alert_for_group(loop, llm_reasoner, finalized, alert_count, log)

        start = window_start_times.pop(chunk.window_id, None)
        if start is not None:
            latencies_ms.append((time.perf_counter() - start) * 1000)

        gate_queue.task_done()


async def _flush_grouper_periodically(
    grouper: EventGrouper,
    llm_reasoner: MockLLMReasoner,
    alert_count: list[int],
) -> None:
    log = logging.getLogger("flusher")
    loop = asyncio.get_running_loop()
    while True:
        await asyncio.sleep(EVENT_GROUPER_FLUSH_INTERVAL_S)
        for finalized in grouper.flush_stale(now=time.time()):
            await _emit_alert_for_group(loop, llm_reasoner, finalized, alert_count, log)


async def _emit_alert_for_group(
    loop: asyncio.AbstractEventLoop,
    llm_reasoner: MockLLMReasoner,
    grouped: GroupedEvent,
    alert_count: list[int],
    log: logging.Logger,
) -> None:
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

    notification = AlertNotification(
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
    event_bus.emit_alert(notification)
    alert_count[0] += 1
    log.info(
        "ALERT  | %-13s | conf=%.2f | dir=%5.1f° dist=%.2fm | dur=%.2fs | n=%d | %s",
        grouped.sound_class,
        grouped.sed_confidence,
        grouped.direction_of_arrival,
        grouped.distance_estimation,
        grouped.duration_s,
        grouped.window_count,
        llm_output.priority,
    )


async def run_test(num_windows: int = 30) -> None:
    """
    Run the SED-gated DOA pipeline for `num_windows` synthetic audio windows.

    At 0.5 s/hop that is 15 seconds of simulated audio, which should
    produce ~5 AlertNotification events (one every ~3 s from the mock SED).
    """
    sed_model = MockSEDModel()
    doa_model = DOAModel()
    llm_reasoner = MockLLMReasoner()
    grouper = EventGrouper()

    raw_queue: asyncio.Queue[RawChunk] = asyncio.Queue(maxsize=64)
    gate_queue: asyncio.Queue[tuple[SEDOutput, RawChunk]] = asyncio.Queue(maxsize=64)

    alert_count: list[int] = [0]
    latencies_ms: list[float] = []
    window_start_times: dict[int, float] = {}

    log = logging.getLogger("test")
    log.info(
        "Starting SED→DOA pipeline — %d windows at %.1f s/hop = %.0f s simulated audio",
        num_windows, HOP_SIZE_S, num_windows * HOP_SIZE_S,
    )
    log.info("SED: mock (fires ~every 6 windows).  DOA: real GCC-PHAT.")
    log.info("Expecting ~%d alerts.  JSON output on stdout.", num_windows // 6)

    producer_task = asyncio.create_task(
        _synthetic_audio_producer(raw_queue, num_windows, window_start_times),
        name="producer",
    )
    sed_task = asyncio.create_task(
        _run_sed(raw_queue, gate_queue, sed_model), name="sed"
    )
    doa_task = asyncio.create_task(
        _run_doa_gate(
            gate_queue, doa_model, llm_reasoner, grouper,
            alert_count, latencies_ms, window_start_times,
        ),
        name="doa_gate",
    )
    flush_task = asyncio.create_task(
        _flush_grouper_periodically(grouper, llm_reasoner, alert_count),
        name="flusher",
    )

    await producer_task
    log.info("Producer done — draining pipeline…")
    # Give the grouper enough time to age out final pending events.
    await asyncio.sleep(EVENT_GROUPER_FLUSH_INTERVAL_S * 3)

    # Flush anything still pending at shutdown.
    loop = asyncio.get_running_loop()
    for finalized in grouper.flush_all():
        await _emit_alert_for_group(loop, llm_reasoner, finalized, alert_count, log)

    for t in (sed_task, doa_task, flush_task):
        t.cancel()
    await asyncio.gather(sed_task, doa_task, flush_task, return_exceptions=True)

    # ── Summary ────────────────────────────────────────────────────────────
    log.info("─" * 60)
    log.info("Test complete.  Total alerts emitted: %d", alert_count[0])
    if latencies_ms:
        log.info(
            "End-to-end latency (chunk-in → alert-out):"
            "  min=%.1f ms  avg=%.1f ms  max=%.1f ms",
            min(latencies_ms),
            sum(latencies_ms) / len(latencies_ms),
            max(latencies_ms),
        )
    log.info("─" * 60)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    try:
        asyncio.run(run_test(num_windows=n))
    except KeyboardInterrupt:
        pass
