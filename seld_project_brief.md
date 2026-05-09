# Project: Spatial SELD + LLM Alert System (Local-Only)

## Overview

A fully local application that continuously listens to ambient audio, detects and classifies sound events, estimates their spatial origin, and uses a local LLM to assess priority and notify the user. No internet connection required — works in airplane mode.

---

## Target Users

- Deaf or hearing-impaired people
- Parents monitoring children
- Remote workers in meetings (background awareness)
- Gamers needing environmental awareness

---

## Core Pipeline

```
Mic Input → SED → DOA → Temporal Alignment → LLM Reasoning → User Notification
```

### 1. Sound Event Detection (SED)

- **Model:** ReDimNet
- **Task:** classify what the sound is
- **Target classes:** clap, baby cry, broken glass, doorbell, metal sounds, alarms
- Runs fully on-device

### 2. Direction of Arrival (DOA)

- **Model:** TBD
- **Task:** estimate *where* the sound comes from
- **Base version:** radar-like directional display using laptop mic

### 3. Temporal Alignment

- SED and DOA run in parallel on the same sliding window chunks
- Their outputs are aligned by timeframe before being passed downstream: only SED detections and DOA estimates that fall within the same time window are paired and forwarded together
- This ensures the LLM always receives a coherent `{sound_class, direction}` pair, not mismatched outputs from different moments

### 4. LLM Reasoning Layer

- **Model:** TBD
- **Task:** interpret detected sound + direction → classify urgency → compose a short user-facing message
- **Example outputs:**
  - `"Doorbell detected, front-left — low urgency"`
  - `"Baby cry detected — high urgency, please check"`

---

## Must-Have Features (MVP Scope)

| Feature | Description |
|---|---|
| Fully local | No API calls, works offline/airplane mode |
| Sound event detection | Classify events from mic stream in real time |
| Spatial detection | Show direction of sound source (radar UI) |
| Temporal alignment | SED and DOA outputs matched by time window before LLM |
| LLM alert | Short priority message sent to user |
| Base mic support | Laptop built-in microphone only |

---

## Tech Stack

| Component | Candidate |
|---|---|
| SED | ReDimNet or PANNs |
| DOA | TBD |
| LLM | TBD |
| Audio I/O | `sounddevice` or `pyaudio` |
| UI | Electron or Python GUI (Tkinter/PyQt) with radar view |
| Orchestration | Python async pipeline |

---

## Architecture Notes for Agents

- **Modularity:** each stage (SED, DOA, Alignment, LLM) should be an independent module with a clean interface, swappable independently
- **Latency budget:** aim for end-to-end < 2s on CPU; < 500ms if GPU available
- **Sliding window:** process audio in overlapping chunks (e.g. 1s window, 0.5s hop)
- **Confidence threshold:** SED should only forward detections above a configurable threshold to avoid LLM spam
- **LLM prompt design:** keep the prompt minimal and structured — pass `{sound_class, direction_degrees, confidence}` and ask for `{priority: low/medium/high, message: string}`

---

## Out of Scope (v1)

- Bluetooth multi-mic array
- Room map / floor plan integration
- Person name detection
