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


@dataclass(frozen=True)
class SEDInput:
    audio_chunk: np.ndarray
    sample_rate: int
    timestamp: float
    window_id: int


@dataclass(frozen=True)
class SEDOutput:
    window_id: int
    timestamp: float
    sound_class: SoundClass
    confidence: float
    detected: bool
