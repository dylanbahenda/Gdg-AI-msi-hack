"""
Mock SED (Sound Event Detection) model.

Simulates realistic detections: fires roughly once every 3 seconds
(~every 6 windows at a 0.5 s hop), then is silent until the next cycle.
The ML team will drop-in replace this file with the real ReDimNet inference.
"""
from __future__ import annotations

import random
import time
from typing import get_args

from contracts.types import SEDInput, SEDOutput, SoundClass

# All valid sound classes pulled directly from the type alias so there is
# one single source of truth.
_SOUND_CLASSES: list[str] = list(get_args(SoundClass))

# How many windows between detections.  At 0.5 s/hop that is ~3 seconds.
_DETECTION_INTERVAL_WINDOWS: int = 6


class MockSEDModel:
    """
    Drop-in mock for the real SEDModel.

    Interface contract (the ML team must preserve this signature):
        def detect(self, input: SEDInput) -> SEDOutput
    """

    def __init__(self) -> None:
        self._window_counter: int = 0
        # Randomise the phase so that the first detection does not always
        # happen at window 0.
        self._next_detection_at: int = random.randint(
            2, _DETECTION_INTERVAL_WINDOWS
        )

    def detect(self, input: SEDInput) -> SEDOutput:  # noqa: A002
        self._window_counter += 1

        if self._window_counter >= self._next_detection_at:
            # Fire a detection.
            sound_class: SoundClass = random.choice(_SOUND_CLASSES)  # type: ignore[assignment]
            confidence = round(random.uniform(0.65, 0.99), 4)
            # Schedule the next detection.
            self._next_detection_at = (
                self._window_counter + _DETECTION_INTERVAL_WINDOWS
            )
            return SEDOutput(
                window_id=input.window_id,
                timestamp=input.timestamp,
                sound_class=sound_class,
                confidence=confidence,
                detected=True,
            )

        # Silent window.
        return SEDOutput(
            window_id=input.window_id,
            timestamp=input.timestamp,
            sound_class="clap",   # irrelevant — detected is False
            confidence=0.1,
            detected=False,
        )
