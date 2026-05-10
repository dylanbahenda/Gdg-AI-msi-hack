"""
Offline fallback runner for debug audio files.

Live microphone input is the primary runtime path. This module keeps file input
available for development, demos without mic permission, and regression checks.
It uses the same model stages and JSON event bus as live mode.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from contracts.config import HOP_SIZE_S, SAMPLE_RATE, WINDOW_SAMPLES
from contracts.types import (
    AlertNotification,
    AlignedEvent,
    DOAInput,
    LLMInput,
    SEDInput,
)
from modules.doa.distance import compute_distance
from modules.doa.interface import DOAModel
from modules.llm.interface import LLMReasoner
from modules.sed.interface import SEDModel
from pipeline import event_bus
from pipeline.event_grouper import EventGrouper, GroupedEvent

logger = logging.getLogger(__name__)


def run_file(
    path: Path,
    *,
    realtime: bool = False,
    fake_spatial: bool = False,
) -> None:
    """Run the full SELD pipeline on one local audio file and emit JSON lines."""
    if not path.exists():
        raise FileNotFoundError(f"audio file not found: {path}")

    stereo = _load_stereo_16k(path)
    windows = list(_windows(stereo))
    duration_s = stereo.shape[0] / SAMPLE_RATE

    logger.info(
        "File %s: %s | %.2fs | %d windows",
        "demo replay" if realtime else "fallback",
        path,
        duration_s,
        len(windows),
    )

    sed_model = SEDModel()
    doa_model = DOAModel()
    llm_reasoner = LLMReasoner()
    grouper = EventGrouper()

    detected_windows = 0
    alerts = 0
    started = time.perf_counter()
    base_timestamp = time.time()

    def emit_group(grouped: GroupedEvent) -> None:
        nonlocal alerts
        llm_input = LLMInput(
            sound_class=grouped.sound_class,
            sed_confidence=grouped.sed_confidence,
            doa_direction_of_arrival=grouped.direction_of_arrival,
            doa_distance_estimation=grouped.distance_estimation,
        )
        try:
            llm_output = llm_reasoner.reason(llm_input)
        except Exception:
            from contracts.types import LLMOutput

            llm_output = LLMOutput(
                priority="medium",
                message="Sound detected - could not assess urgency",
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
        alerts += 1

    for window_id, stereo_window in windows:
        if realtime:
            target_time = started + window_id * HOP_SIZE_S
            sleep_s = target_time - time.perf_counter()
            if sleep_s > 0:
                time.sleep(sleep_s)
            timestamp = base_timestamp + window_id * HOP_SIZE_S
        else:
            timestamp = window_id * HOP_SIZE_S

        for grouped in grouper.flush_stale(now=timestamp):
            emit_group(grouped)

        sed_output = sed_model.detect(
            SEDInput(
                audio_chunk=stereo_window[:, 0],
                sample_rate=SAMPLE_RATE,
                timestamp=timestamp,
                window_id=window_id,
            )
        )

        if not sed_output.detected:
            continue

        doa_output = doa_model.estimate(
            DOAInput(
                audio_chunk=stereo_window,
                sample_rate=SAMPLE_RATE,
                timestamp=timestamp,
                window_id=window_id,
            )
        )
        if fake_spatial:
            direction, distance_m = _fake_spatial_values(
                sound_class=sed_output.sound_class,
                window_id=window_id,
            )
        else:
            direction = doa_output.direction_of_arrival
            distance_m = round(
                compute_distance(
                    event_rms=doa_output.event_rms,
                    coherence=doa_output.coherence,
                    sound_class=sed_output.sound_class,
                ),
                2,
            )
        aligned = AlignedEvent(
            window_id=window_id,
            timestamp=timestamp,
            sound_class=sed_output.sound_class,
            sed_confidence=sed_output.confidence,
            doa_direction_of_arrival=direction,
            doa_distance_estimation=distance_m,
        )
        event_bus.emit_raw_event(aligned)
        detected_windows += 1

        for grouped in grouper.add(aligned):
            emit_group(grouped)

    for grouped in grouper.flush_all():
        emit_group(grouped)

    elapsed_ms = (time.perf_counter() - started) * 1000
    logger.info(
        "File fallback complete: %d detected windows, %d alerts, %.1f ms",
        detected_windows,
        alerts,
        elapsed_ms,
    )


def _load_stereo_16k(path: Path) -> np.ndarray:
    audio, sr = sf.read(str(path), dtype="float32", always_2d=True)
    if sr != SAMPLE_RATE:
        raise ValueError(
            f"sample rate mismatch: file={sr} Hz, pipeline expects {SAMPLE_RATE} Hz"
        )
    if audio.shape[1] == 1:
        logger.warning("Mono file detected; duplicating channel for DOA.")
        audio = np.repeat(audio, 2, axis=1)
    elif audio.shape[1] > 2:
        logger.warning("File has %d channels; using first two.", audio.shape[1])
        audio = audio[:, :2]
    return audio


def _fake_spatial_values(sound_class: str, window_id: int) -> tuple[float, float]:
    """Stable demo-only DOA/distance values so file replay looks spatial."""
    base_direction = {
        "crying": 340.0,
        "scream": 25.0,
        "broken_glass": 285.0,
        "alarm": 90.0,
        "dog": 325.0,
        "clap": 350.0,
        "knock": 35.0,
        "doorbell": 315.0,
        "phone": 70.0,
        "metal_sound": 250.0,
    }.get(sound_class, 0.0)
    base_distance = {
        "crying": 1.8,
        "scream": 1.1,
        "broken_glass": 1.4,
        "alarm": 3.0,
        "dog": 1.5,
        "clap": 0.6,
        "knock": 0.9,
        "doorbell": 3.6,
        "phone": 2.2,
        "metal_sound": 1.7,
    }.get(sound_class, 2.0)

    direction_jitter = ((window_id * 17) % 31) - 15
    distance_jitter = (((window_id * 7) % 9) - 4) * 0.08
    direction = round((base_direction + direction_jitter) % 360, 1)
    distance = round(max(0.1, min(5.0, base_distance + distance_jitter)), 2)
    return direction, distance


def _windows(stereo: np.ndarray) -> list[tuple[int, np.ndarray]]:
    hop = int(HOP_SIZE_S * SAMPLE_RATE)
    out: list[tuple[int, np.ndarray]] = []
    starts = range(0, max(stereo.shape[0], WINDOW_SAMPLES), hop)
    for window_id, start in enumerate(starts):
        if start >= stereo.shape[0]:
            break
        chunk = stereo[start : start + WINDOW_SAMPLES]
        if chunk.shape[0] < WINDOW_SAMPLES:
            pad = np.zeros((WINDOW_SAMPLES - chunk.shape[0], 2), dtype=np.float32)
            chunk = np.concatenate([chunk, pad], axis=0)
        out.append((window_id, chunk))
    return out
