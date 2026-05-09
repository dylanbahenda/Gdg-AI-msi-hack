"""
Mock DOA (Direction of Arrival) model.

Returns a plausible random direction and distance for every window.
The ML team will replace this file with the real DOA inference.
"""
from __future__ import annotations

import random

from contracts.types import DOAInput, DOAOutput


class MockDOAModel:
    """
    Drop-in mock for the real DOAModel.

    Interface contract (the ML team must preserve this signature):
        def estimate(self, input: DOAInput) -> DOAOutput
    """

    def estimate(self, input: DOAInput) -> DOAOutput:  # noqa: A002
        return DOAOutput(
            window_id=input.window_id,
            timestamp=input.timestamp,
            direction_of_arrival=round(random.uniform(0.0, 359.9), 1),
            distance_estimation=round(random.uniform(0.5, 5.0), 2),
        )
