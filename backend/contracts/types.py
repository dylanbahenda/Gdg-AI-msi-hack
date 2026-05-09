from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

SoundClass = Literal["clap", "baby_cry", "broken_glass", "doorbell", "metal_sound", "alarm"]
Priority = Literal["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Audio I/O (internal to pipeline — not shared with ML team)
# ---------------------------------------------------------------------------

@dataclass
class RawChunk:
    """A single sliding-window audio chunk produced by audio_io."""
    audio: np.ndarray   # float32, shape (WINDOW_SAMPLES,)
    sample_rate: int    # always 16000
    timestamp: float    # unix epoch of the START of this window
    window_id: int      # monotonically increasing, starts at 0


# ---------------------------------------------------------------------------
# SED — Sound Event Detection
# ---------------------------------------------------------------------------

@dataclass
class SEDInput:
    audio_chunk: np.ndarray   # float32, shape (n_samples,), range [-1.0, 1.0]
    sample_rate: int           # always 16000 Hz
    timestamp: float           # unix epoch of the START of this chunk
    window_id: int             # monotonically increasing chunk counter


@dataclass
class SEDOutput:
    window_id: int             # must match the input window_id
    timestamp: float           # echo from input
    sound_class: SoundClass    # top predicted class
    confidence: float          # 0.0 – 1.0
    detected: bool             # True if confidence >= SED_THRESHOLD


# ---------------------------------------------------------------------------
# DOA — Direction of Arrival
# ---------------------------------------------------------------------------

@dataclass
class DOAInput:
    audio_chunk: np.ndarray   # float32, shape (n_samples,) — same chunk as SED
    sample_rate: int           # always 16000 Hz
    timestamp: float           # unix epoch of the START of this chunk
    window_id: int             # same window_id as the paired SEDInput


@dataclass
class DOAOutput:
    window_id: int             # must match the input window_id
    timestamp: float           # echo from input
    direction_of_arrival: float   # 0–359.9°, clockwise from front
    distance_estimation: float    # estimated metres


# ---------------------------------------------------------------------------
# Temporal Alignment
# ---------------------------------------------------------------------------

@dataclass
class AlignedEvent:
    window_id: int
    timestamp: float           # from SEDOutput.timestamp
    sound_class: SoundClass
    sed_confidence: float
    doa_direction_of_arrival: float
    doa_distance_estimation: float


# ---------------------------------------------------------------------------
# LLM Reasoning Layer
# ---------------------------------------------------------------------------

@dataclass
class LLMInput:
    sound_class: SoundClass
    sed_confidence: float
    doa_direction_of_arrival: float
    doa_distance_estimation: float


@dataclass
class LLMOutput:
    priority: Priority    # "low" | "medium" | "high"
    message: str          # short human-facing alert, max 80 chars


# ---------------------------------------------------------------------------
# Final notification — emitted to the UI
# ---------------------------------------------------------------------------

@dataclass
class AlertNotification:
    timestamp: float
    sound_class: SoundClass
    direction_of_arrival: float   # degrees, 0–359.9
    distance_estimation: float    # metres
    sed_confidence: float         # 0.0–1.0
    priority: Priority
    message: str                  # max 80 chars
