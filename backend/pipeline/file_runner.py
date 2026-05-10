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


def run_file(path: Path) -> None:
    """Run the full SELD pipeline on one local audio file and emit JSON lines."""
    if not path.exists():
        raise FileNotFoundError(f"audio file not found: {path}")

    stereo = _load_stereo_16k(path)
    windows = list(_windows(stereo))
    duration_s = stereo.shape[0] / SAMPLE_RATE

    logger.info(
        "File fallback: %s | %.2fs | %d windows",
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
        timestamp = window_id * HOP_SIZE_S
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
            doa_direction_of_arrival=doa_output.direction_of_arrival,
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
