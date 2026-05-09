# Backend Plan — SELD Pipeline
**Owner:** Pietro  
**Status:** Build against mocks (ML modules not ready)  
**Stack:** Python, asyncio, sounddevice

---

## What You Own

```
Audio I/O → Sliding Window → [MockSED | MockDOA] → Temporal Alignment → LLM Input → [MockLLM] → Event Bus → UI
```

Everything except the internals of the three ML/LLM modules. You build the skeleton they will plug into.

---

## Module Breakdown

### 1. `contracts/` — Shared Types (do this first)

Create the single source of truth for all dataclasses. Every other module imports from here.

**`contracts/types.py`**
```python
from dataclasses import dataclass
from typing import Literal

SoundClass = Literal["clap", "baby_cry", "broken_glass", "doorbell", "metal_sound", "alarm"]
Priority   = Literal["low", "medium", "high"]

@dataclass
class SEDInput:
    audio_chunk: "np.ndarray"  # float32, shape (n_samples,)
    sample_rate: int
    timestamp: float
    window_id: int

@dataclass
class SEDOutput:
    window_id: int
    timestamp: float
    sound_class: SoundClass
    confidence: float
    detected: bool

@dataclass
class DOAInput:
    audio_chunk: "np.ndarray"
    sample_rate: int
    timestamp: float
    window_id: int

@dataclass
class DOAOutput:
    window_id: int
    timestamp: float
    direction_of_arrival: float   # 0–359.9°, clockwise from front
    distance_estimation: float    # estimated metres

@dataclass
class AlignedEvent:
    window_id: int
    timestamp: float
    sound_class: SoundClass
    sed_confidence: float
    doa_direction_of_arrival: float
    doa_distance_estimation: float

@dataclass
class LLMInput:
    sound_class: SoundClass
    sed_confidence: float
    doa_direction_of_arrival: float
    doa_distance_estimation: float

@dataclass
class LLMOutput:
    priority: Priority
    message: str
```

**`contracts/config.py`**
```python
SAMPLE_RATE          = 16000   # Hz
WINDOW_SIZE_S        = 1.0     # seconds
HOP_SIZE_S           = 0.5     # seconds
WINDOW_SAMPLES       = 16000   # SAMPLE_RATE * WINDOW_SIZE_S
SED_THRESHOLD        = 0.6
ALIGNMENT_TIMEOUT_S  = 0.2
```

---

### 2. `modules/sed/mock.py` — Mock SED

Emits a realistic random detection roughly every 3 seconds. All other windows return `detected=False`.

**Behaviour:**
- Maintain an internal counter. Every ~6 windows (3s at 0.5s hop), pick a random `SoundClass` and a confidence between 0.65–0.99, set `detected=True`.
- All other windows: `confidence=0.1`, `detected=False`, `sound_class="clap"` (irrelevant since detected=False).
- Echo back `window_id` and `timestamp` exactly from input.

**Interface to match (ML team will replace this file):**
```python
class MockSEDModel:
    def detect(self, input: SEDInput) -> SEDOutput: ...
```

---

### 3. `modules/doa/mock.py` — Mock DOA

Returns a plausible direction and distance for every window.

**Behaviour:**
- `direction_of_arrival`: random float in [0, 360)
- `distance_estimation`: random float in [0.5, 5.0] metres
- Echo `window_id` and `timestamp` from input.

**Interface to match:**
```python
class MockDOAModel:
    def estimate(self, input: DOAInput) -> DOAOutput: ...
```

---

### 4. `modules/llm/mock.py` — Mock LLM

Returns hardcoded priority + message keyed by `sound_class`. No inference, instant response.

**Behaviour:**
```python
MOCK_RESPONSES = {
    "baby_cry":      ("high",   "Baby cry detected — check immediately"),
    "alarm":         ("high",   "Alarm sounding — take action"),
    "broken_glass":  ("high",   "Breaking glass detected — check area"),
    "metal_sound":   ("medium", "Metal sound detected nearby"),
    "doorbell":      ("low",    "Doorbell at {direction:.0f}°"),
    "clap":          ("low",    "Clap detected — possible noise"),
}
```

For `doorbell`, interpolate `doa_direction_of_arrival` into the message string.

**Interface to match:**
```python
class MockLLMReasoner:
    def reason(self, input: LLMInput) -> LLMOutput: ...
```

---

### 5. `pipeline/audio_io.py` — Mic Input + Sliding Window

Captures audio from the default mic and emits overlapping chunks.

**Responsibilities:**
- Open mic stream with `sounddevice` at 16000 Hz, mono, float32.
- Buffer incoming samples into a ring buffer.
- Every `HOP_SIZE_S` (0.5s), slice a `WINDOW_SAMPLES` (16000) window and put it on an async queue.
- Attach `window_id` (incrementing int) and `timestamp` (time of window start) to each chunk.
- Expose: `async def start() -> asyncio.Queue[RawChunk]`

**`RawChunk`** (internal, not a contract type):
```python
@dataclass
class RawChunk:
    audio: np.ndarray   # float32, shape (16000,)
    sample_rate: int    # 16000
    timestamp: float
    window_id: int
```

---

### 6. `pipeline/alignment.py` — Temporal Alignment

Receives `SEDOutput` and `DOAOutput` from parallel tasks, pairs them by `window_id`, and emits `AlignedEvent`.

**Algorithm:**
1. Maintain two dicts: `pending_sed: dict[int, SEDOutput]` and `pending_doa: dict[int, DOAOutput]`.
2. When either output arrives, store it. If the partner for that `window_id` is already present → pair them immediately.
3. If a partner doesn't arrive within `ALIGNMENT_TIMEOUT_S` (200ms) → discard both sides for that window.
4. Only emit `AlignedEvent` if `SEDOutput.detected == True`. Silently drop windows where `detected=False`.
5. Clean up stale entries older than the timeout on every iteration.

**Interface:**
```python
async def run_alignment(
    sed_queue: asyncio.Queue[SEDOutput],
    doa_queue: asyncio.Queue[DOAOutput],
    out_queue: asyncio.Queue[AlignedEvent]
) -> None: ...
```

---

### 7. `pipeline/orchestrator.py` — Main Async Loop

Wires everything together. This is the entry point.

**Flow:**
```
audio_io.start()
    │
    ├─ Task A: for each RawChunk → SEDModel.detect() → sed_queue
    ├─ Task B: for each RawChunk → DOAModel.estimate() → doa_queue
    └─ Task C: alignment.run_alignment(sed_queue, doa_queue, aligned_queue)
                    │
                    └─ for each AlignedEvent → LLMReasoner.reason() → emit to UI
```

**Swap point:** The three model instantiation lines are the only place that changes when mocks are replaced by real models:
```python
# Dev (mock)
from modules.sed.mock import MockSEDModel as SEDModel
from modules.doa.mock import MockDOAModel as DOAModel
from modules.llm.mock import MockLLMReasoner as LLMReasoner

# Production (real)
# from modules.sed.interface import SEDModel
# from modules.doa.interface import DOAModel
# from modules.llm.interface import LLMReasoner
```

**UI bridge:** The orchestrator puts `LLMOutput + AlignedEvent` onto a shared event object (or callback) that the UI layer subscribes to. Define a combined notification type:
```python
@dataclass
class AlertNotification:
    timestamp: float
    sound_class: SoundClass
    direction_of_arrival: float
    distance_estimation: float
    sed_confidence: float
    priority: Priority
    message: str
```

---

### 8. `pipeline/event_bus.py` — UI Bridge

Decouples the async pipeline from the UI framework (Electron/PyQt/Tkinter — TBD).

**For PyQt/Tkinter:** Use a `queue.Queue` (thread-safe). UI polls it on a timer.  
**For Electron (Python ↔ JS bridge):** Write `AlertNotification` as a JSON line to stdout. Electron reads it via a child process pipe.

Expose a single function:
```python
def emit_alert(notification: AlertNotification) -> None: ...
```

The orchestrator calls this; the UI layer reads it. They never import each other.

---

## File Structure

```
backend/
├── contracts/
│   ├── types.py
│   └── config.py
├── modules/
│   ├── sed/
│   │   ├── interface.py      ← ML team fills this
│   │   └── mock.py           ← you build this
│   ├── doa/
│   │   ├── interface.py      ← ML team fills this
│   │   └── mock.py           ← you build this
│   └── llm/
│       ├── interface.py      ← ML team fills this
│       └── mock.py           ← you build this
├── pipeline/
│   ├── audio_io.py
│   ├── alignment.py
│   ├── orchestrator.py
│   └── event_bus.py
└── ui/                       ← see frontend plan
```

---

## Build Order

| Step | Task | Unblocks |
|------|------|----------|
| 1 | Write `contracts/types.py` and `contracts/config.py` | Everything |
| 2 | Write all three mock modules | Orchestrator dev |
| 3 | Write `audio_io.py` (can use silence/sine-wave in tests) | Orchestrator dev |
| 4 | Write `alignment.py` + unit tests | End-to-end loop |
| 5 | Write `orchestrator.py` wiring mocks together | UI integration |
| 6 | Write `event_bus.py` with chosen UI bridge method | UI integration |
| 7 | Smoke test: full pipeline emitting mock alerts to stdout | UI dev can start |
| 8 | Swap in real ML modules one at a time | ML team handoff |

---

## Testing Approach

- **`alignment.py`**: Unit test the pairing logic with synthetic SEDOutput/DOAOutput objects. Test timeout, test missing partner, test `detected=False` filtering.
- **`audio_io.py`**: Test with a prerecorded WAV file injected in place of the live mic.
- **Full pipeline smoke test**: Run orchestrator with all mocks, assert `AlertNotification` objects appear in the event bus at the expected rate (~1 every 3s).
- No GPU required for any of this. Everything runs on CPU with mocks.