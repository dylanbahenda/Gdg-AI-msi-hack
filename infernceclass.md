# SELD System — Inference Interface Contracts


## 1. Shared Data Types


```python
from dataclasses import dataclass
from typing import Literal

SoundClass = Literal[
    "clap",
    "baby_cry",
    "broken_glass",
    "doorbell",
    "metal_sound",
    "alarm"
]

Priority = Literal["low", "medium", "high"] #LLM defines it
```

---

## 2. SED — Sound Event Detection

**Owner:** ML team  
**Model:** ReDimNet 
**Task:** Given a raw audio chunk, return what sound was detected and how confident.

### Input

```python
@dataclass
class SEDInput:
    audio_chunk: np.ndarray   # shape: (n_samples,), dtype: float32, range: [-1.0, 1.0]
    sample_rate: int           # always 16000 Hz
    timestamp: float           # unix epoch of the START of this chunk (seconds)
    window_id: int             # monotonically increasing chunk counter (0, 1, 2, ...)
```

### Output

```python
@dataclass
class SEDOutput:
    window_id: int             # must match the input window_id
    timestamp: float           # unix epoch of the START of this chunk (echo from input)
    sound_class: SoundClass    # top predicted class
    confidence: float          # 0.0 – 1.0, probability of top class
    detected: bool             # True if confidence >= configured threshold (default: 0.6)
```

### Notes

- Processing must complete within **500ms on CPU** (1s window target).
- Model must be loaded once at startup, not per call.

### Mock Behaviour

```python
# Returns a random detection every ~3 seconds
```

---

## 3. DOA — Direction of Arrival

**Owner:** ML team  
**Task:** Given the same audio chunk as SED, estimate the horizontal angle (azimuth) of the dominant sound source.

### Input

```python
@dataclass
class DOAInput:
    audio_chunk: np.ndarray   # shape: (n_samples,), dtype: float32 — same chunk as SED
    sample_rate: int           # always 16000 Hz
    timestamp: float           # unix epoch of the START of this chunk
    window_id: int             # same window_id as the paired SEDInput
```

> **Note:** In v1, a laptop multichannel mic is available.

### Output

```python
@dataclass
class DOAOutput:
    window_id: int             # must match the input window_id
    timestamp: float           # unix epoch of the START of this chunk (echo from input)
    direction_of_arrival: float 
    distance_estimation: float
```

### Notes

- Must produce output within **200ms** (runs in parallel with SED, not after).

### Mock Behaviour

```python
# Returns mock data.
```

---

## 4. Temporal Alignment

**Owner:** Backend/pipeline team (this is Pietro)  
**Task:** Pair one SEDOutput and one DOAOutput that share the same `window_id` into a single aligned event. Discard unmatched or non-detected outputs.

### Logic

```python
@dataclass
class AlignedEvent:
    window_id: int
    timestamp: float           # from SEDOutput.timestamp
    sound_class: SoundClass
    sed_confidence: float
    doa_direction_of_arrival: float 
    doa_distance_estimation: float

```

**Alignment rules:**
1. Match SED and DOA outputs by `window_id`.
2. Only forward if `SEDOutput.detected == True`.
3. If either module's output is missing within a **200ms timeout**, drop the window entirely.

---

## 5. LLM Reasoning Layer

**Owner:** ML team  
**Task:** Given an aligned sound event, assess urgency and compose a short human-readable alert message.

### Input

```python
@dataclass
class LLMInput:
    sound_class: SoundClass
    sed_confidence: float
    doa_direction_of_arrival: float 
    doa_distance_estimation: float
```

### Output

```python
@dataclass
class LLMOutput:
    priority: Priority         # "low" | "medium" | "high"
    message: str               # short human-facing alert, max 80 chars
```

### Prompt Contract (for ML team)

The LLM must be prompted with a structured input and return a structured JSON response. The UI/backend team depends on this exact JSON shape.

**System prompt (fixed):**
```
You are a sound alert assistant. You receive a detected sound event and must assess its urgency.
Always respond with valid JSON only. No explanation. No markdown.
```

**User prompt template:**
```
Sound detected: {sound_class}
Confidence: {sed_confidence:.0%}
Direction: {direction_degrees:.0f}° (clockwise from front){" [direction unavailable]" if not doa_available else ""}

Respond with JSON:
{
  "priority": "low" | "medium" | "high",
  "message": "<short alert for the user, max 80 chars>"
}
```

**Expected raw LLM output:**
```json
{
  "priority": "high",
  "message": "Baby cry detected behind you — check immediately"
}
```

### Priority Guidelines (for ML team to encode in system prompt)

| Sound | Default Priority | Notes |
|---|---|---|
| `baby_cry` | high | Always high regardless of confidence |
| `alarm` | high | Always high |
| `broken_glass` | high | Security risk |
| `doorbell` | low | Informational |
| `clap` | low | May be noise |
| `metal_sound` | medium | Context-dependent |
| `unknown` | — | Should never reach LLM (filtered by SED threshold) |

### Notes

- Total LLM round-trip must complete within **1000ms on CPU**.
- If the model returns malformed JSON, the pipeline must catch the error and emit a fallback: `{priority: "medium", message: "Sound detected — could not assess urgency"}`.
- The LLM must run fully offline — no API calls.

### Mock Behaviour

```python
# Returns hardcoded responses keyed by sound_class:
# baby_cry → high / "Baby cry detected — check immediately"
# doorbell → low / "Doorbell detected at {direction}°"
# etc.
```


## 9. Versioning & Change Process

- This document is the **source of truth** for all inter-module interfaces.
- Any change to a dataclass field (name, type, or removal) requires **team agreement and a version bump**.
- Additive fields (new optional fields) are allowed with a minor bump and must have a default value.
- Breaking changes (rename, remove, type change) require a major bump and migration notice.