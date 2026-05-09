import numpy as np
from dataclasses import dataclass

@dataclass
class DOAInput:
    audio_chunk: np.ndarray   
    sample_rate: int          
    timestamp: float           
    window_id: int             

@dataclass
class DOAOutput:
    window_id: int             
    timestamp: float           
    direction_of_arrival: float 
    distance_estimation: float

class DOAEngine:
    def __init__(self, mic_distance_meters: float = 0.15):
        self.mic_distance = mic_distance_meters
        self.speed_of_sound = 343.0  # m/s
        
        # Calibration constants
        # 0.2 represents the expected 95th-percentile amplitude at 1 meter
        self.ref_peak_at_1_meter = 0.1  

    def process(self, input_data: DOAInput) -> DOAOutput:
        audio = input_data.audio_chunk
        
        # 1. Fallback/Validation
        if audio.ndim < 2 or audio.shape[1] < 2:
            return DOAOutput(input_data.window_id, input_data.timestamp, 0.0, 0.0)

        # 2. Extract Channels
        ch_left = audio[:, 0]
        ch_right = audio[:, 1]

        # 3. Direction of Arrival & Mic Coherence
        # We now extract both the angle and the coherence score from GCC-PHAT
        angle_degrees, coherence_score = self._calculate_gcc_phat(ch_left, ch_right, input_data.sample_rate)

        # 4. Smart Distance Estimation
        distance_meters = self._estimate_distance(audio, coherence_score)

        # 5. Return strict contract
        return DOAOutput(
            window_id=input_data.window_id,
            timestamp=input_data.timestamp,
            direction_of_arrival=angle_degrees,
            distance_estimation=distance_meters
        )

    def _calculate_gcc_phat(self, sig1: np.ndarray, sig2: np.ndarray, sr: int) -> tuple[float, float]:
        """Returns (Angle in degrees, Coherence Score)"""
        n = len(sig1)
        fft1 = np.fft.rfft(sig1)
        fft2 = np.fft.rfft(sig2)
        R = fft1 * np.conj(fft2)
        
        # Phase Transform
        R_phat = R / (np.abs(R) + 1e-15)
        cc = np.fft.irfft(R_phat, n=n)
        
        max_delay = int((self.mic_distance / self.speed_of_sound) * sr) + 1
        cc_valid = np.concatenate((cc[-max_delay:], cc[:max_delay + 1]))
        
        # The index of the peak gives us direction
        peak_idx = np.argmax(cc_valid)
        # The height of the peak gives us coherence (0.0 to ~1.0)
        peak_value = float(cc_valid[peak_idx]) 
        
        # Sub-sample interpolation
        if 0 < peak_idx < len(cc_valid) - 1:
            alpha = cc_valid[peak_idx - 1]
            beta = cc_valid[peak_idx]
            gamma = cc_valid[peak_idx + 1]
            shift = 0.5 * (alpha - gamma) / (alpha - 2 * beta + gamma)
            peak_idx = peak_idx + shift
            
        delay_samples = peak_idx - max_delay
        tau = delay_samples / sr
        sin_theta = (tau * self.speed_of_sound) / self.mic_distance
        sin_theta = np.clip(sin_theta, -1.0, 1.0)
        
        angle_deg = float(np.degrees(np.arcsin(sin_theta)))
        
        return angle_deg, peak_value

    def _estimate_distance(self, audio: np.ndarray, coherence: float) -> float:
        """
        Estimates distance using Peak RMS and Mic Coherence.
        """
        # 1. PEAK ENERGY (Top 5% loudest samples)
        # We square the audio to get energy, then find the 95th percentile.
        # This ignores the silent gaps in the audio chunk.
        peak_energy = np.percentile(audio**2, 95)
        event_rms = np.sqrt(peak_energy)
        
        if event_rms < 1e-5:
            return 10.0  # Absolute silence -> max distance

        # Base distance calculation based purely on loudness
        base_distance = self.ref_peak_at_1_meter / event_rms

        # 2. COHERENCE MULTIPLIER (Reverberation penalty)
        # High coherence (> 0.1) means direct path -> closer.
        # Low coherence (< 0.05) means highly reverberant -> further away.
        # We clamp the multiplier between 0.5x and 2.5x to prevent wild swings.
        coherence_multiplier = 0.1 / (coherence + 0.01)
        coherence_multiplier = np.clip(coherence_multiplier, 0.5, 2.5)

        # Apply multiplier
        final_distance = base_distance * coherence_multiplier

        # Clamp between 0.1m and 10.0m for sanity in the UI
        return float(np.clip(final_distance, 0.1, 10.0))