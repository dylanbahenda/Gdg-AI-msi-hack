"""
SED module — wraps the real SEDDetector behind the pipeline's interface.

The pipeline calls SEDModel().detect(input) and gets back a SEDOutput.
This file is the seam between the pipeline and the ML implementation.
"""
from __future__ import annotations

from contracts.types import SEDInput, SEDOutput
from modules.sed.inference import SEDDetector


class SEDModel:
    """Thin wrapper so the pipeline keeps calling detect() without change."""

    def __init__(self) -> None:
        self._detector = SEDDetector()

    def detect(self, input: SEDInput) -> SEDOutput:  # noqa: A002
        return self._detector.detect(input)
