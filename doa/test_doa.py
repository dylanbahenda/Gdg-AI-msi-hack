import os
import numpy as np
import soundfile as sf
from dataclasses import dataclass

# 1. Define the Data Contracts (from your Markdown interface)
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

# Import your engine
from doa_engine import DOAEngine

def test():
    wav_path = ("doa/test_audio.wav")
    
    print(f"Loading {wav_path}...")

    # Load audio (soundfile automatically returns float arrays between [-1.0, 1.0])
    audio_data, sample_rate = sf.read(wav_path)

    # --- Validation ---
    if audio_data.ndim == 1 or audio_data.shape[1] < 2:
        print("ERROR: test_audio.wav is Mono (1 channel).")
        print("DOA requires at least 2 channels (Stereo) to calculate time delays between mics.")
        return
    
    if sample_rate != 16000:
        print(f"WARNING: Sample rate is {sample_rate}Hz, but pipeline expects 16000Hz.")
        print("The math will still run, but distance/angle calculations might be slightly skewed.")

    # --- Simulate the Pipeline Chunking ---
    # The pipeline gives the engine 1-second chunks. Let's grab the first 1 second.
    chunk_length = min(sample_rate, len(audio_data)) 
    audio_chunk = audio_data[:chunk_length, :]

    print(f"Loaded audio chunk: shape {audio_chunk.shape}, peak amplitude {np.max(np.abs(audio_chunk)):.3f}")

    # 2. Create the strict input contract
    doa_input = DOAInput(
        audio_chunk=audio_chunk,
        sample_rate=sample_rate,
        timestamp=1700000000.0, # Fake unix timestamp
        window_id=0             # First window
    )

    # 3. Instantiate the Engine
    # (Assuming standard laptop mic distance is ~25cm = 0.25m)
    engine = DOAEngine(mic_distance_meters=0.25)
    
    print("\nProcessing through DOA Engine (with Coherence + Peak RMS logic)...")
    
    # 4. Run the main pipeline process
    # This automatically runs GCC-PHAT, extracts the angle & coherence, 
    # and calculates the smart distance.
    result = engine.process(doa_input)

    # 5. Print Results
    print("\n=== DOA OUTPUT ===")
    print(f"Window ID: {result.window_id}")
    
    # Direction formatting
    dir_str = "Center"
    if result.direction_of_arrival > 5.0:
        dir_str = "Right"
    elif result.direction_of_arrival < -5.0:
        dir_str = "Left"
        
    print(f"Direction: {result.direction_of_arrival:>6.1f}° ({dir_str})")
    print(f"Distance : {result.distance_estimation:>6.2f} meters")
    print("==================\n")

if __name__ == "__main__":
    test()