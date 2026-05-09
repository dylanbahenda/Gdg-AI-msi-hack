"""
Mock LLM Reasoning module.

Returns hardcoded priority + message keyed by sound_class.
No model, no network, no inference — instant, deterministic response.
The ML team will replace this file with the real local LLM inference.
"""
from __future__ import annotations

from contracts.types import LLMInput, LLMOutput, Priority, SoundClass

# (priority, message_template) — {direction} is substituted for doorbell.
_MOCK_RESPONSES: dict[str, tuple[Priority, str]] = {
    "baby_cry":      ("high",   "Baby cry detected — check immediately"),
    "alarm":         ("high",   "Alarm sounding — take action"),
    "broken_glass":  ("high",   "Breaking glass detected — check area"),
    "metal_sound":   ("medium", "Metal sound detected nearby"),
    "doorbell":      ("low",    "Doorbell at {direction:.0f}°"),
    "clap":          ("low",    "Clap detected — possible noise"),
}

# Fallback for any class not explicitly listed (future-proofing).
_FALLBACK: tuple[Priority, str] = ("medium", "Sound detected — could not assess urgency")


class MockLLMReasoner:
    """
    Drop-in mock for the real LLMReasoner.

    Interface contract (the ML team must preserve this signature):
        def reason(self, input: LLMInput) -> LLMOutput
    """

    def reason(self, input: LLMInput) -> LLMOutput:  # noqa: A002
        priority, template = _MOCK_RESPONSES.get(input.sound_class, _FALLBACK)
        message = template.format(direction=input.doa_direction_of_arrival)
        # Enforce the 80-char contract so the mock behaves like the real LLM.
        message = message[:80]
        return LLMOutput(priority=priority, message=message)
