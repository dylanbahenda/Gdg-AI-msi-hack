from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np

SoundClass = Literal[
    "clap",
    "crying",
    "broken_glass",
    "doorbell",
    "metal_sound",
    "alarm",
    "dog",
    "scream",
    "knock",
    "phone",
]
Priority = Literal["low", "medium", "high"]


# ---------------------------------------------------------------------------
# Audio I/O (internal to pipeline — not shared with ML team)
# ---------------------------------------------------------------------------

@dataclass
class RawChunk:
    """A single sliding-window audio chunk produced by audio_io."""
    audio: np.ndarray         # float32, shape (WINDOW_SAMPLES,)  — channel 0 mono, for SED
    stereo_audio: np.ndarray  # float32, shape (WINDOW_SAMPLES, 2) — both channels, for DOA
    sample_rate: int          # always 16000
    timestamp: float          # unix epoch of the START of this window
    window_id: int            # monotonically increasing, starts at 0


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
    audio_chunk: np.ndarray   # float32, shape (n_samples, 2) — stereo, channels 0 and 1
    sample_rate: int           # always 16000 Hz
    timestamp: float           # unix epoch of the START of this chunk
    window_id: int             # same window_id as the paired SEDInput


@dataclass
class DOAOutput:
    window_id: int             # must match the input window_id
    timestamp: float           # echo from input
    direction_of_arrival: float   # 0–359.9°, clockwise from front
    distance_estimation: float    # estimated metres (class-agnostic best effort;
                                  # the orchestrator overrides this with the
                                  # class-conditional value once SED has run)
    # Raw measurements that let the orchestrator recompute distance once SED's
    # class is known. Defaulted for backward compatibility.
    event_rms: float = 0.0     # p95 RMS amplitude over the chunk
    coherence: float = 0.0     # GCC-PHAT peak height [-1, 1]


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
    timestamp: float              # start of the merged event
    sound_class: SoundClass
    direction_of_arrival: float   # degrees, 0–359.9 (confidence-weighted circular mean)
    distance_estimation: float    # metres (confidence-weighted mean)
    sed_confidence: float         # 0.0–1.0 (max across merged windows)
    priority: Priority
    message: str                  # max 80 chars
    duration_s: float = 0.0       # span of the merged event in seconds
    window_count: int = 1         # number of raw windows merged into this event
