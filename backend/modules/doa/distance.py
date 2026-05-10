"""
Distance computation — class-conditional, source-loudness-aware.

The DOA engine measures `event_rms` (peak energy of the chunk) and `coherence`
(GCC-PHAT peak height), but cannot turn those into metres without knowing how
loud the source is at the reference distance.  That depends on the sound class:
a clap and a whisper at 1 m have very different RMS values.

This module owns the class → expected-RMS-at-1-m table and the formula that
combines it with the engine's measurements.  It is called from:
  - alignment.py — once SED's class is paired with DOA's event_rms,
                   the *correct* distance is computed and overrides the
                   class-agnostic estimate that DOA produced standalone.
  - doa/interface.py — for a best-effort estimate when DOA runs alone.
"""
from __future__ import annotations

import numpy as np

from contracts.types import SoundClass


# Expected p95 RMS amplitude of a typical event of each class at 1 m, recorded
# through a standard laptop/USB mic chain.  Two values are empirically
# calibrated; the rest are placeholder estimates ranked by relative loudness.
# Re-calibrate per-class with one known-distance recording each.
#
# Calibration math: d = ref / rms, so ref = expected_rms_at_1m.
#   clap @ 10 cm  measured rms = 0.040  ⇒  at 1 m ≈ 0.040 × 0.10 = 0.004
#   shout @ 3.5 m measured rms = 0.270  ⇒  at 1 m ≈ 0.270 × 3.50 ≈ 1.00
REF_PEAK_BY_CLASS: dict[SoundClass, float] = {
    "clap":         0.004,  # calibrated  (single hand clap — brief transient)
    "knock":        0.005,  # placeholder (similar transient profile to clap)
    "metal_sound":  0.010,  # placeholder (sharp transient)
    "broken_glass": 0.020,  # placeholder (transient + crackle tail)
    "phone":        0.050,  # placeholder (moderate sustained tone)
    "doorbell":     0.050,  # placeholder (moderate sustained tone)
    "crying":       0.100,  # placeholder (continuous moderate-loud)
    "dog":          0.150,  # placeholder (loud transient bark)
    "alarm":        0.500,  # placeholder (designed-loud sustained)
    "scream":       1.000,  # calibrated  (sustained loud vocalisation)
}

# Used when the sound class is unknown (e.g. DOA running standalone).
DEFAULT_REF_PEAK: float = 0.05

# Distance-clamp bounds — return 0.1 m for very loud events, 20 m max.
_MIN_DISTANCE_M: float = 0.1
_MAX_DISTANCE_M: float = 20.0


def compute_distance(
    event_rms: float,
    coherence: float,
    sound_class: SoundClass | None = None,
) -> float:
    """
    Convert per-chunk event_rms + coherence into an absolute distance estimate.

    Args:
        event_rms:   p95 RMS amplitude over the chunk (from DOAEngine.infer).
        coherence:   GCC-PHAT peak height [-1, 1] — high = clean direct path.
        sound_class: SED class. If None, uses DEFAULT_REF_PEAK.

    Returns:
        Distance in metres, clamped to [0.1, 20.0].

    Model: amplitude ∝ 1/d (free-field point source) ⇒ d = ref / rms.
    A one-sided coherence penalty inflates the estimate in reverberant
    conditions (low coherence) but never shrinks it for clean signals.
    """
    if event_rms < 1e-5:
        return _MAX_DISTANCE_M  # near-silence → push to maximum range

    ref = (
        REF_PEAK_BY_CLASS.get(sound_class, DEFAULT_REF_PEAK)
        if sound_class is not None
        else DEFAULT_REF_PEAK
    )

    base_distance = ref / event_rms
    coherence_multiplier = float(np.clip(0.12 / (coherence + 0.01), 1.0, 1.5))
    final_distance = base_distance * coherence_multiplier
    return float(np.clip(final_distance, _MIN_DISTANCE_M, _MAX_DISTANCE_M))
