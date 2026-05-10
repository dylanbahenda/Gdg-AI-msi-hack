"""
DOA interface — real implementation using the GCC-PHAT engine.

The engine is automatically calibrated during the first
_CALIBRATION_CHUNKS windows (≈ 10 s at the default 0.5 s hop), after
which the mic-spacing estimate is locked.  The pipeline can therefore
start immediately with a sensible default and self-correct during
warm-up without any user configuration.
"""
from __future__ import annotations

import numpy as np

from contracts.types import DOAInput, DOAOutput
from modules.doa.distance import compute_distance
from modules.doa.engine import DOAEngine


class DOAModel:
    """Real DOA model backed by GCC-PHAT + inverse-square-law distance."""

    # Collect this many chunks before locking the mic-distance estimate.
    # At a 0.5 s hop that is ~10 s of warm-up audio.
    _CALIBRATION_CHUNKS: int = 20

    def __init__(self) -> None:
        # Start with the conservative default (0.15 m); will be updated once
        # enough chunks have been collected for automatic calibration.
        self._engine = DOAEngine(mic_distance_meters=None)
        self._calibration_buffer: list[np.ndarray] = []
        self._calibrated: bool = False

    def estimate(self, input: DOAInput) -> DOAOutput:  # noqa: A002
        """
        Estimate the direction and distance of the dominant sound source.

        Constraints:
        - Completes well within 200 ms on CPU (GCC-PHAT on a 16 000-sample
          window takes < 5 ms on a modern laptop).
        - Echoes window_id and timestamp from the input exactly.
        - direction_of_arrival: 0–359.9°, clockwise from front.
        - distance_estimation: metres (best-effort).
        """
        # --- Lazy mic-distance auto-calibration from live audio ---
        if not self._calibrated:
            self._calibration_buffer.append(input.audio_chunk)
            if len(self._calibration_buffer) >= self._CALIBRATION_CHUNKS:
                mic_d = DOAEngine.estimate_mic_distance(
                    self._calibration_buffer, input.sample_rate
                )
                self._engine = DOAEngine(mic_distance_meters=mic_d)
                self._calibrated = True
                self._calibration_buffer.clear()

        # --- Run GCC-PHAT inference ---
        angle_deg, event_rms, coherence = self._engine.infer(
            input.audio_chunk, input.sample_rate
        )

        # --- Map ±90° → 0–359.9° clockwise from front ---
        # Positive angle = right (0° – 90°), negative = left (270° – 359.9°).
        # Python's modulo handles the sign correctly:  (-30) % 360 == 330.
        # Guard against floating-point 360.0 rounding artefact.
        direction = round(float(angle_deg % 360), 1) % 360

        # Class-agnostic distance estimate. The alignment layer recomputes this
        # using the SED class once the two outputs are paired.
        distance_m = compute_distance(event_rms, coherence, sound_class=None)

        return DOAOutput(
            window_id=input.window_id,
            timestamp=input.timestamp,
            direction_of_arrival=direction,
            distance_estimation=round(distance_m, 2),
            event_rms=event_rms,
            coherence=coherence,
        )
