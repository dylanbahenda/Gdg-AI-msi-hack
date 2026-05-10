# SELD Local Sound Event Detection

A local, offline SELD (Sound Event Localization and Detection) pipeline with live audio capture, sound class detection, direction-of-arrival estimation, and a Tauri/React frontend.

## Repository overview

This repository combines:

- `backend/`: Python pipeline for microphone capture, SED, DOA, grouping, and alert generation.
- `backend/modules/`: local implementations for SED, DOA, and LLM reasoning.
- `backend/contracts/`: shared dataclass contracts and pipeline configuration.
- `backend/pipeline/`: async audio routing, raw event emission, and per-window grouping.
- `frontend/`: Tauri + React + TypeScript UI that consumes alerts from the backend.
- `third_party/PretrainedSED/`: upstream PretrainedSED framework for the SED model.
- `resources/`: model checkpoint assets used by the pipeline.

## Core architecture

### Backend pipeline

The backend is a local Python process that runs entirely on-device.

1. `backend/main.py` is the CLI entrypoint.
2. `backend/pipeline/audio_io.py` opens the system microphone using `sounddevice`, buffers audio in a stereo ring buffer, and emits overlapping sliding windows as `RawChunk` objects.
3. `backend/pipeline/orchestrator.py` consumes raw windows with an async pipeline:
   - SED gate: skip quiet windows using RMS and run SED only on candidate windows.
   - DOA stage: estimate direction and distance for detected events.
   - Event grouping: merge consecutive same-class windows into a single alert.
   - LLM reasoning: add a human-facing alert message and priority.
4. `backend/pipeline/event_bus.py` writes machine-readable JSON lines to stdout. The Tauri sidecar reads this stdout stream and bridges it into the frontend.

### Model modules

- `backend/modules/sed/`: wraps the PretrainedSED framework and exposes `SEDModel.detect()`.
  - Uses `M2D` encoder by default.
  - Loads the downloaded `M2D_strong_1.pt` checkpoint from `resources/`.
  - Collapses frame-level multi-label probabilities into one top `SoundClass` and confidence per window.
- `backend/modules/doa/`: real GCC-PHAT direction-of-arrival engine.
  - Auto-calibrates microphone spacing during startup.
  - Returns a direction in degrees and class-agnostic distance-related measurements.
- `backend/modules/llm/`: local Ollama-backed alert text generator.
  - Maps sound class to deterministic priority.
  - Uses a cached, low-latency prompt to generate short user-facing messages.
  - Falls back safely if Ollama is unavailable.

### Frontend

The frontend is a Tauri + React app in `frontend/`.

- `frontend/src/hooks/useAlertStream.ts`: listens for `alert`, `raw_event`, and `system_info` events from the Tauri runtime.
- `frontend/src/App.tsx`: displays an alert feed, radar visualization, and message UI.
- The app supports a mock feed when running in the browser instead of inside Tauri.

## File structure summary

Key directories and files:

- `backend/main.py`: CLI entrypoint; live mic mode, file fallback, demo replay.
- `backend/pipeline/`: audio capture, orchestrator, event grouping, and offline file runner.
- `backend/contracts/`: typed dataclasses for SED, DOA, LLM, and final alerts.
- `backend/modules/sed/`: SED detector wrapper, ontology mapping, and model loader.
- `backend/modules/doa/`: DOA engine wrapper and distance estimation.
- `backend/modules/llm/`: local alert reasoning, priority mapping, and caching.
- `frontend/package.json`: app scripts, dependencies, and Tauri integration.
- `frontend/src/`: React UI components, hooks, and types.

## Setup

### 1. Python backend

From the repository root:

```bash
python -m venv .venv
.venv\Scripts\activate      # Windows
# or: source .venv/bin/activate  # macOS/Linux
pip install -e .[dev]
```

Install the PretrainedSED framework and ensure the checkpoint is available:

```bash
cd backend
bash scripts/setup_pretrainedsed.sh
```

If you cannot run the install script, place `M2D_strong_1.pt` manually into:

- `backend/resources/M2D_strong_1.pt`
- `resources/M2D_strong_1.pt`
- `frontend/resources/M2D_strong_1.pt`

### 2. Frontend

Install frontend dependencies:

```bash
cd frontend
npm install
```

### 3. Ollama (optional but recommended)

The local LLM alert generator expects a running Ollama server and the `gemma3:1b` model.
If Ollama is not installed, the backend will still run and emit fallback alert text.

## Running the app

### Live microphone mode

From the repo root:

```bash
cd frontend
npm run tauri dev
```

This launches the Tauri app and starts the backend process in live mic mode.

### Demo mode with replay file

Use environment variable `SELD_DEMO_FILE` to replay a test audio file:

```bash
cd frontend
set SELD_DEMO_FILE=../backend/tests/assets/test_audio.wav && npm run tauri dev
```

On macOS/Linux:

```bash
SELD_DEMO_FILE=../backend/tests/assets/test_audio.wav npm run tauri dev
```

### Backend-only file fallback

Run the backend on a local audio file without the UI:

```bash
cd backend
python main.py --file tests/assets/test_audio.wav
```

Or demo playback at live speed:

```bash
cd backend
python main.py --demo-file tests/assets/test_audio.wav
```

## Testing

Run backend tests from the repository root:

```bash
pytest
```

Fast tests only:

```bash
pytest -v -k 'not real'
```

## Important notes

- The system is designed to stay fully local. No external network requests are made by the audio pipeline itself.
- The frontend reads backend events through Tauri and does not talk directly to the Python process.
- The backend emits structured JSON lines on stdout so the Tauri sidecar can forward them reliably.
- `backend/pipeline/orchestrator.py` gates DOA and LLM work behind detected SED windows to save compute.

## Further documentation

- `docs/infernceclass.md`: SED class ontology and macro mapping.
- `backend/scripts/benchmark_latency.py`: pipeline latency benchmarking.
- `backend/scripts/test_doa.py`: DOA debugging and unit tests.
- `frontend/src/`: UI implementation and event handling.
