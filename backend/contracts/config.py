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

# Silent-chunk gate: skip the SED model when the mono RMS of a window is below
# this threshold.  Empty rooms produce ~5e-4 RMS from mic noise; soft speech
# starts around 1e-3; conversation is ~2e-2.  0.002 is well above pure mic
# noise but still catches quiet door creaks, knocks, and faint cries — i.e.
# any sound a hearing-impaired user actually wants surfaced.
SILENCE_RMS_THRESHOLD: float = 0.002

# ---------------------------------------------------------------------------
# Alignment
# ---------------------------------------------------------------------------
ALIGNMENT_TIMEOUT_S: float = 0.2  # discard a window if its partner is late by this much

# ---------------------------------------------------------------------------
# Event grouping (sensitivity window)
# ---------------------------------------------------------------------------
# Detections of the same class within this gap are merged into one notification.
# 0.75 s = 1.5 hops at 0.5 s hop — bridges one missed window without
# accidentally merging two distinct events that are >= 1 s apart.
EVENT_MERGE_TOLERANCE_S: float = 0.75

# How often the periodic flusher polls for stale pending groups.
EVENT_GROUPER_FLUSH_INTERVAL_S: float = 0.5
