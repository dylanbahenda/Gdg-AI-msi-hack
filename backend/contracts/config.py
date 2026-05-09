# ---------------------------------------------------------------------------
# Audio settings
# ---------------------------------------------------------------------------
SAMPLE_RATE: int = 16000        # Hz — microphone sample rate
WINDOW_SIZE_S: float = 1.0      # seconds — length of each analysis window
HOP_SIZE_S: float = 0.5         # seconds — step between consecutive windows
WINDOW_SAMPLES: int = 16000     # SAMPLE_RATE * WINDOW_SIZE_S

# ---------------------------------------------------------------------------
# Detection thresholds
# ---------------------------------------------------------------------------
SED_THRESHOLD: float = 0.6      # minimum confidence to treat a window as "detected"

# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------
ALIGNMENT_TIMEOUT_S: float = 0.2  # discard a window if its partner is late by this much
