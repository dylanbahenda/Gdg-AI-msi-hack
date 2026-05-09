"""
SED interface stub — to be implemented by the ML team.

Replace the body of SEDModel.detect() with the real ReDimNet inference.
Do NOT change the method signature or the import paths; the pipeline
depends on this exact interface.
"""
from __future__ import annotations

from contracts.types import SEDInput, SEDOutput


class SEDModel:
    """Real SED model — fill in by ML team."""

    def __init__(self) -> None:
        # TODO: load model weights here (once at startup, not per call).
        raise NotImplementedError("SEDModel not yet implemented")

    def detect(self, input: SEDInput) -> SEDOutput:  # noqa: A002
        """
        Run inference on one audio window.

        Constraints:
        - Must complete within 500 ms on CPU.
        - Must echo window_id and timestamp from the input exactly.
        - Set detected=True only if confidence >= SED_THRESHOLD (0.6).
        """
        raise NotImplementedError
