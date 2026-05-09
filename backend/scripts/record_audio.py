import sounddevice as sd # type: ignore
from scipy.io.wavfile import write

fs = 16000  # Baseline requirement
seconds = 5 
print("Recording...")
# Capture stereo (2 channels)
recording = sd.rec(int(seconds * fs), samplerate=fs, channels=2)
sd.wait() 
write('doa/test_audio.wav', fs, recording)
print("Recording saved as test_audio.wav")