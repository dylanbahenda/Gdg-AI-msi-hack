"""
DOA interface stub — to be implemented by the ML team.

Replace the body of DOAModel.estimate() with the real DOA inference.
Do NOT change the method signature or the import paths; the pipeline
depends on this exact interface.
"""
from __future__ import annotations

from contracts.types import DOAInput, DOAOutput


class DOAModel:
    """Real DOA model — fill in by ML team."""

    def __init__(self) -> None:
        # TODO: load model weights here (once at startup, not per call).
        raise NotImplementedError("DOAModel not yet implemented")

    def estimate(self, input: DOAInput) -> DOAOutput:  # noqa: A002
        """
        Estimate the direction of the dominant sound source.

        Constraints:
        - Must complete within 200 ms on CPU (runs in parallel with SED).
        - Must echo window_id and timestamp from the input exactly.
        - direction_of_arrival: 0–359.9°, clockwise from front.
        - distance_estimation: metres (best-effort).
        """
        raise NotImplementedError
