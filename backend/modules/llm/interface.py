"""
Local LLM reasoning module.

This implementation keeps the pipeline fully offline by calling a local
Ollama model. The human-facing description comes from the model, while the
priority is hardcoded from the detected sound class.
"""
from __future__ import annotations

from contracts.types import LLMInput, LLMOutput

_PRIORITIES: dict[str, str] = {
    "baby_cry": "high",
    "crying": "high",
    "alarm": "high",
    "broken_glass": "high",
    "metal_sound": "medium",
    "doorbell": "low",
    "clap": "low",
}

_FALLBACK_PRIORITY = "medium"
_FALLBACK_MESSAGE = "Sound detected — could not assess urgency"

_SYSTEM_PROMPT = (
    "You are an assistant for hearing-impaired users. "
    "You receive a sound classification label detected by a microphone. "
    "Respond with one single, clear, friendly sentence describing what is likely happening around the user. "
    "Never say 'I' or explain yourself. Just describe the situation directly. "
    "Keep the answer under 80 characters."
)


class LLMReasoner:
    """Local Ollama-backed reasoner for alert generation."""

    def __init__(self) -> None:
        self._model = "gemma3:1b"

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
        priority = _PRIORITIES.get(input.sound_class, _FALLBACK_PRIORITY)

        try:
            import ollama

            response = ollama.chat(
                model=self._model,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": (
                            f"label: {input.sound_class}; "
                            f"confidence: {input.sed_confidence:.2f}; "
                            f"direction: {input.doa_direction_of_arrival:.1f}; "
                            f"distance: {input.doa_distance_estimation:.1f}"
                        ),
                    },
                ],
            )
            message = response.message.content.strip()
            if not message:
                raise ValueError("empty LLM response")
        except Exception:
            return LLMOutput(priority=_FALLBACK_PRIORITY, message=_FALLBACK_MESSAGE)

        return LLMOutput(priority=priority, message=message[:80])
