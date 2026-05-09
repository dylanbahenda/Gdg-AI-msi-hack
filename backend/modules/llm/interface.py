"""
LLM interface stub — to be implemented by the ML team.

Replace the body of LLMReasoner.reason() with the real local LLM inference.
Do NOT change the method signature or the import paths; the pipeline
depends on this exact interface.

NO external API calls are allowed. The model must run fully offline.
"""
from __future__ import annotations

from contracts.types import LLMInput, LLMOutput


class LLMReasoner:
    """Real LLM reasoner — fill in by ML team."""

    def __init__(self) -> None:
        # TODO: load the local LLM here (once at startup, not per call).
        raise NotImplementedError("LLMReasoner not yet implemented")

    def reason(self, input: LLMInput) -> LLMOutput:  # noqa: A002
        """
        Assess urgency and compose a short alert message.

        Constraints:
        - Must complete within 1000 ms on CPU.
        - message must be at most 80 characters.
        - priority must be one of "low" | "medium" | "high".
        - If the model returns malformed output, catch the error and return:
              LLMOutput(priority="medium",
                        message="Sound detected — could not assess urgency")
        - NO network calls. Fully local/offline.
        """
        raise NotImplementedError
