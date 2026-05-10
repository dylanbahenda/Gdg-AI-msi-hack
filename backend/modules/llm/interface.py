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
        # 1. Initialize our memory cache
        self._cache: dict[str, str] = {}

    def reason(self, input: LLMInput) -> LLMOutput:  # noqa: A002
        """
        Assess urgency and compose a short alert message.

        Constraints:
        - Must complete within 1000 ms on CPU.
        - message must be at most 80 characters.
        - priority must be one of "low" | "medium" | "high".
        - If the model returns malformed output, catch the error and return fallback.
        - NO network calls. Fully local/offline.
        """
        priority = _PRIORITIES.get(input.sound_class, _FALLBACK_PRIORITY)

        # ---------------------------------------------------------
        # SMART CACHING LOGIC
        # ---------------------------------------------------------
        # Bucket the numbers so similar events trigger the cache!
        # Example: 42.1° becomes 45.0°, 3.2m becomes 3m. 
        # We IGNORE confidence in the cache key so it doesn't break the cache.
        dir_bucket = round(input.doa_direction_of_arrival / 45.0) * 45.0
        dist_bucket = round(input.doa_distance_estimation)
        
        cache_key = f"{input.sound_class}_{dir_bucket}_{dist_bucket}"

        if cache_key in self._cache:
            # INSTANT RETURN (0ms latency!)
            print(f"⚡[LLM Cache Hit]: {cache_key}")
            return LLMOutput(priority=priority, message=self._cache[cache_key])
        # ---------------------------------------------------------

        try:
            import ollama
            
            print(f"[LLM Cache Miss]: Generating new message for {cache_key}...")
            
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
                # 2. Limit CPU Threads to save resources for Audio/SED!
                options={
                    "num_thread": 2, 
                    "num_predict": 30 # Stop it from rambling endlessly
                }
            )
            message = response.message.content.strip()
            if not message:
                raise ValueError("empty LLM response")
            
            # Save the clean message to our cache before returning
            final_message = message[:80]
            self._cache[cache_key] = final_message

        except Exception as e:
            print(f"LLM Error: {e}")
            return LLMOutput(priority=_FALLBACK_PRIORITY, message=_FALLBACK_MESSAGE)

        return LLMOutput(priority=priority, message=final_message)