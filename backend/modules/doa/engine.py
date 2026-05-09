"""
DOA Engine — GCC-PHAT based direction and distance estimator.

Stand-alone numerical core; has no dependency on backend contracts or any
framework.  The interface layer (interface.py) maps backend DOAInput/DOAOutput
contracts onto the public ``infer()`` method.
"""
from __future__ import annotations

import numpy as np


class DOAEngine:
    # Conservative default for typical laptop/USB stereo mic arrays.
    DEFAULT_MIC_DISTANCE = 0.15  # metres

    def __init__(self, mic_distance_meters: float | None = None) -> None:
        self.mic_distance = (
            mic_distance_meters
            if mic_distance_meters is not None
            else self.DEFAULT_MIC_DISTANCE
        )
        self.speed_of_sound = 343.0  # m/s

        # Expected p95 RMS amplitude for typical speech at 1 metre distance.
        # Tuned for standard laptop/USB microphone pre-amplification levels.
        self.ref_peak_at_1_meter = 0.2

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def infer(self, stereo: np.ndarray, sample_rate: int) -> tuple[float, float]:
        """
        Estimate direction and distance from one stereo audio window.

        Args:
            stereo:      float32 array, shape (n_samples, 2).
            sample_rate: samples per second (e.g. 16 000).

        Returns:
            (angle_deg, distance_m)
            angle_deg  — ±90°; negative = left, positive = right, 0 = centre.
            distance_m — estimated metres to the source.
        """
        if stereo.ndim < 2 or stereo.shape[1] < 2:
            return 0.0, 0.0

        ch_left = stereo[:, 0]
        ch_right = stereo[:, 1]
        angle_degrees, coherence_score = self._calculate_gcc_phat(
            ch_left, ch_right, sample_rate
        )
        distance_meters = self._estimate_distance(stereo, coherence_score)
        return angle_degrees, distance_meters

    @staticmethod
    def estimate_mic_distance(
        audio_chunks: list[np.ndarray],
        sample_rate: int,
        speed_of_sound: float = 343.0,
        silence_threshold: float = 0.01,
    ) -> float:
        """
        Estimate inter-microphone distance automatically from recorded audio.

        Algorithm: the physical mic spacing must be at least as large as the
        largest time-difference-of-arrival (TDOA) ever observed.  This method
        runs GCC-PHAT on every non-silent chunk, collects the peak delays, and
        uses the maximum to lower-bound d, adding 20 % headroom.

        Works best when the audio contains events from varied directions.
        Falls back to ``DEFAULT_MIC_DISTANCE`` when no usable signal is found.

        Args:
            audio_chunks:      list of stereo arrays, each shape (n_samples, 2).
            sample_rate:       samples per second.
            speed_of_sound:    m/s (default 343).
            silence_threshold: chunks whose channel-0 RMS is below this value
                               are skipped.

        Returns:
            Estimated mic spacing in metres, clamped to [0.12, 0.40].
        """
        max_delay_samples = 0
        # Search over a generous bound (up to 0.6 m worth of delay).
        search_bound_ref = int((0.6 / speed_of_sound) * sample_rate)

        for chunk in audio_chunks:
            if chunk.ndim < 2 or chunk.shape[1] < 2:
                continue
            ch0 = chunk[:, 0]
            if float(np.sqrt(np.mean(ch0 ** 2))) < silence_threshold:
                continue

            n = len(ch0)
            bound = min(search_bound_ref, n // 2 - 1)
            fft1 = np.fft.rfft(ch0)
            fft2 = np.fft.rfft(chunk[:, 1])
            R = fft1 * np.conj(fft2)
            R_phat = R / (np.abs(R) + 1e-15)
            cc = np.fft.irfft(R_phat, n=n)
            cc_valid = np.concatenate((cc[-bound:], cc[:bound + 1]))
            peak_idx = int(np.argmax(np.abs(cc_valid)))
            delay = abs(peak_idx - bound)
            if delay > max_delay_samples:
                max_delay_samples = delay

        if max_delay_samples == 0:
            return DOAEngine.DEFAULT_MIC_DISTANCE

        estimated = (max_delay_samples / sample_rate) * speed_of_sound * 1.2
        # Sanity clamp: realistic laptop/USB mic arrays are 12 cm – 40 cm.
        # 12 cm is the floor because near-centre-only recordings can severely
        # underestimate the true spacing.
        return float(np.clip(estimated, 0.12, 0.40))

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _calculate_gcc_phat(
        self, sig1: np.ndarray, sig2: np.ndarray, sr: int
    ) -> tuple[float, float]:
        """
        Generalised Cross-Correlation with Phase Transform.

        Returns:
            (angle_deg, coherence_score)
            angle_deg       — ±90° from arcsin of the normalised TDOA.
            coherence_score — GCC-PHAT peak height (higher = more direct path).
        """
        n = len(sig1)
        fft1 = np.fft.rfft(sig1)
        fft2 = np.fft.rfft(sig2)
        R = fft1 * np.conj(fft2)

        # Phase Transform: normalise magnitude, preserve phase only.
        R_phat = R / (np.abs(R) + 1e-15)
        cc = np.fft.irfft(R_phat, n=n)

        max_delay = int((self.mic_distance / self.speed_of_sound) * sr) + 1
        cc_valid = np.concatenate((cc[-max_delay:], cc[:max_delay + 1]))

        peak_idx = int(np.argmax(cc_valid))
        peak_value = float(cc_valid[peak_idx])

        # Sub-sample interpolation (parabolic fit around the peak).
        if 0 < peak_idx < len(cc_valid) - 1:
            alpha = cc_valid[peak_idx - 1]
            beta = cc_valid[peak_idx]
            gamma = cc_valid[peak_idx + 1]
            denom = alpha - 2 * beta + gamma
            if abs(denom) > 1e-10:
                peak_idx = peak_idx + 0.5 * (alpha - gamma) / denom

        delay_samples = peak_idx - max_delay
        tau = delay_samples / sr
        sin_theta = (tau * self.speed_of_sound) / self.mic_distance
        sin_theta = float(np.clip(sin_theta, -1.0, 1.0))

        angle_deg = float(np.degrees(np.arcsin(sin_theta)))
        return angle_deg, peak_value

    def _estimate_distance(self, audio: np.ndarray, coherence: float) -> float:
        """
        Estimate distance using peak RMS and mic coherence.

        Uses the inverse-square law: amplitude ∝ 1/d, so d ∝ ref/amplitude.
        A one-sided coherence penalty inflates the estimate for reverberant
        conditions (low coherence) without shrinking it for clean signals.
        """
        # Top 5 % of energy frames, ignoring silence gaps.
        peak_energy = np.percentile(audio ** 2, 95)
        event_rms = float(np.sqrt(peak_energy))

        if event_rms < 1e-5:
            return 20.0  # Near-silence → push to maximum range.

        base_distance = self.ref_peak_at_1_meter / event_rms

        # Coherence correction (one-sided: only ever increases distance).
        # High coherence → clean direct path → multiplier = 1.0.
        # Low coherence  → reverberant room  → multiplier > 1.0.
        coherence_multiplier = float(np.clip(0.12 / (coherence + 0.01), 1.0, 1.5))

        final_distance = base_distance * coherence_multiplier
        return float(np.clip(final_distance, 0.1, 20.0))
