# Frontend Plan — SELD Desktop UI
**Owner:** Pietro  
**Status:** Build against mock `AlertNotification` events  
**Stack:** Tauri 2 + React 18 + Tailwind CSS v3 + TypeScript

---

## Stack Overview

| Layer | Technology | Role |
|---|---|---|
| Desktop shell | Tauri 2 (Rust) | Native window, system tray, OS notifications |
| UI framework | React 18 + TypeScript | Component tree, state management |
| Styling | Tailwind CSS v3 | Utility-first styling |
| Python bridge | Tauri `sidecar` | Spawns the Python pipeline as a child process |
| IPC | Tauri Events (`emit` / `listen`) | Python → Rust → React event delivery |
| Canvas | HTML5 Canvas | Radar rendering |
| Animations | Framer Motion | Blip fade, card entrance, sweep animation |

---

## Project Structure

```
backend/
├── src-tauri/                    ← Rust/Tauri layer
│   ├── src/
│   │   └── main.rs               ← sidecar launch, IPC bridge
│   ├── tauri.conf.json
│   └── Cargo.toml
├── src/                          ← React app
│   ├── main.tsx
│   ├── App.tsx                   ← root layout + state
│   ├── components/
│   │   ├── RadarWidget.tsx        ← canvas radar
│   │   ├── AlertFeed.tsx          ← scrollable alert history
│   │   ├── AlertCard.tsx          ← single alert card
│   │   ├── HeaderBar.tsx          ← status + session counter
│   │   └── LastAlertBar.tsx       ← sticky bottom strip
│   ├── hooks/
│   │   ├── useAlertStream.ts      ← subscribes to Tauri events
│   │   └── useRadarBlip.ts        ← blip state + fade timer
│   ├── mock/
│   │   └── mockFeed.ts            ← emits fake AlertNotification on a timer
│   ├── types/
│   │   └── contracts.ts           ← AlertNotification TypeScript type
│   └── styles/
│       └── index.css              ← Tailwind directives + CSS vars
├── package.json
└── tailwind.config.ts
```

---

## 1. Shared Type — `AlertNotification`

Define once in `src/types/contracts.ts`. All components import from here.

```typescript
export type SoundClass =
  | "clap"
  | "baby_cry"
  | "broken_glass"
  | "doorbell"
  | "metal_sound"
  | "alarm";

export type Priority = "low" | "medium" | "high";

export interface AlertNotification {
  timestamp: number;               // unix epoch (seconds)
  sound_class: SoundClass;
  direction_of_arrival: number;    // 0–359.9°, clockwise from front (0° = forward)
  distance_estimation: number;     // metres
  sed_confidence: number;          // 0.0–1.0
  priority: Priority;
  message: string;                 // max 80 chars, from LLM
}
```

---

## 2. Python ↔ Tauri Bridge

The Python pipeline runs as a Tauri **sidecar** (a bundled child process). It writes `AlertNotification` objects as newline-delimited JSON to **stdout**. The Rust layer reads stdout and re-emits them as Tauri events into the React frontend.

### Python side (`pipeline/orchestrator.py`)
```python
import json, sys
from dataclasses import asdict

def emit_alert(notification: AlertNotification):
    print(json.dumps(asdict(notification)), flush=True)  # one JSON object per line
```

### Rust side (`src-tauri/src/main.rs`)
```rust
tauri::Builder::default()
    .setup(|app| {
        let handle = app.handle().clone();
        let (mut rx, _child) = app.shell()
            .sidecar("seld_pipeline")?
            .spawn()?;

        tauri::async_runtime::spawn(async move {
            while let Some(event) = rx.recv().await {
                if let CommandEvent::Stdout(line) = event {
                    let _ = handle.emit("alert", line);
                }
            }
        });
        Ok(())
    })
```

### React side — `src/hooks/useAlertStream.ts`
```typescript
import { listen } from "@tauri-apps/api/event";
import { useEffect, useState } from "react";
import { AlertNotification } from "../types/contracts";

export function useAlertStream() {
  const [alerts, setAlerts] = useState<AlertNotification[]>([]);

  useEffect(() => {
    const unlisten = listen<string>("alert", (event) => {
      const notification: AlertNotification = JSON.parse(event.payload);
      setAlerts((prev) => [notification, ...prev].slice(0, 50));
    });
    return () => { unlisten.then(fn => fn()); };
  }, []);

  return alerts;
}
```

---

## 3. Mock Feed (UI dev without Python running)

`src/mock/mockFeed.ts` — emits fake events on a timer. The UI is fully buildable and testable without the pipeline running at all.

```typescript
import { AlertNotification } from "../types/contracts";

const MOCK_EVENTS: AlertNotification[] = [
  { timestamp: 0, sound_class: "baby_cry",     direction_of_arrival: 45,  distance_estimation: 2.1, sed_confidence: 0.91, priority: "high",   message: "Baby cry detected — check immediately" },
  { timestamp: 0, sound_class: "doorbell",     direction_of_arrival: 315, distance_estimation: 4.5, sed_confidence: 0.78, priority: "low",    message: "Doorbell at 315°" },
  { timestamp: 0, sound_class: "broken_glass", direction_of_arrival: 180, distance_estimation: 1.2, sed_confidence: 0.85, priority: "high",   message: "Breaking glass detected — check area" },
  { timestamp: 0, sound_class: "alarm",        direction_of_arrival: 90,  distance_estimation: 3.0, sed_confidence: 0.95, priority: "high",   message: "Alarm sounding — take action" },
  { timestamp: 0, sound_class: "metal_sound",  direction_of_arrival: 270, distance_estimation: 2.8, sed_confidence: 0.70, priority: "medium", message: "Metal sound detected nearby" },
  { timestamp: 0, sound_class: "clap",         direction_of_arrival: 0,   distance_estimation: 1.5, sed_confidence: 0.65, priority: "low",    message: "Clap detected — possible noise" },
];

export function startMockFeed(onAlert: (n: AlertNotification) => void): () => void {
  let i = 0;
  const interval = setInterval(() => {
    onAlert({ ...MOCK_EVENTS[i % MOCK_EVENTS.length], timestamp: Date.now() / 1000 });
    i++;
  }, 3500);
  return () => clearInterval(interval);
}
```

**Swap pattern in `App.tsx`** — one env check, nothing else changes:
```typescript
const IS_MOCK = import.meta.env.DEV && !window.__TAURI__;

useEffect(() => {
  if (IS_MOCK) {
    return startMockFeed((n) => setAlerts(prev => [n, ...prev].slice(0, 50)));
  }
  // else: useAlertStream hook handles the Tauri listener
}, []);
```

---

## 4. Tailwind Config

```typescript
// tailwind.config.ts
export default {
  content: ["./src/**/*.{tsx,ts}"],
  theme: {
    extend: {
      colors: {
        radar: {
          bg:    "#060d06",
          ring:  "#0f1f0f",
          sweep: "#22c55e",
          grid:  "#112211",
          label: "#4a6a4a",
        },
        priority: {
          high:   "#ef4444",
          medium: "#f97316",
          low:    "#22c55e",
        },
      },
      fontFamily: {
        mono:    ["'JetBrains Mono'", "monospace"],
        display: ["'Space Mono'",     "monospace"],
      },
    },
  },
}
```

---

## 5. Component Specs

### 5.1 `RadarWidget.tsx`

Renders a circular radar on an HTML5 `<canvas>`. Animated with `requestAnimationFrame`.

**What it draws:**
- Dark circular face with 3 concentric distance rings (1m / 3m / 5m+) in `radar-ring` colour
- Four radial grid lines (N/E/S/W) with short text labels
- Rotating sweep line: a green arc that fades to transparent, full rotation every 3s
- A priority-coloured blip dot at the computed `(x, y)` for the latest alert
- Blip fades from opacity 1 → 0 over 4 seconds, disappears after

**Polar → Cartesian:**
```typescript
function polarToXY(
  directionDeg: number,
  distanceM: number,
  maxDistanceM: number,
  radiusPx: number,
  cx: number, cy: number
) {
  const r = Math.min(distanceM / maxDistanceM, 1) * radiusPx;
  const rad = ((directionDeg - 90) * Math.PI) / 180; // 0° = top
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}
```

**`useRadarBlip.ts` hook:**
```typescript
export function useRadarBlip(latestAlert: AlertNotification | null) {
  const [blip, setBlip] = useState<{ alert: AlertNotification; born: number } | null>(null);

  useEffect(() => {
    if (!latestAlert) return;
    setBlip({ alert: latestAlert, born: Date.now() });
  }, [latestAlert]);

  // Compute opacity in the animation loop: 1 - (elapsed / 4000)
  return blip;
}
```

**Props:**
```typescript
interface RadarWidgetProps {
  latestAlert: AlertNotification | null;
  size?: number; // default 320px
}
```

---

### 5.2 `AlertFeed.tsx` + `AlertCard.tsx`

Scrollable list, newest alert on top, max 50 entries kept in state.

**`AlertCard` visual layout:**
```
┌───────────────────────────────────────────────┐
│ ●  HIGH   baby_cry               12:04:33      │
│ Baby cry detected — check immediately          │
│ ↗ 45°  ·  2.1 m  ·  conf 91%                  │
└───────────────────────────────────────────────┘
```

- Priority dot: `w-2.5 h-2.5 rounded-full bg-priority-{priority}`
- Priority badge: `text-[10px] font-mono uppercase tracking-widest text-priority-{priority}`
- Sound class: `font-mono text-sm text-zinc-300`
- Timestamp: `text-xs text-zinc-500 tabular-nums ml-auto`
- Message: `text-sm text-white mt-1`
- Metadata row: `text-xs text-zinc-500 mt-1 font-mono`
- Card bg: `bg-zinc-900 border border-zinc-800 rounded-lg px-4 py-3`
- High-priority card: add `border-l-2 border-l-priority-high`

**Card entrance (Framer Motion):**
```tsx
<motion.div
  initial={{ opacity: 0, y: -6 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.18, ease: "easeOut" }}
>
```

**Clicking a card** calls `onCardClick(alert)` in the parent → re-plots that blip on the radar.

---

### 5.3 `HeaderBar.tsx`

```typescript
interface HeaderBarProps {
  status: "listening" | "detected" | "error";
  sessionCount: number;
}
```

- Left: `SELD` in `font-display font-bold` + `Monitor` in `font-display font-normal text-zinc-400`
- Centre: status pill — coloured dot + label
- Right: `{sessionCount} alerts` in `text-xs font-mono text-zinc-500`

Status pill behaviour:
- `listening` → zinc-500 dot, "Listening"
- `detected` → green-400 dot with `animate-pulse`, "Detected" — auto-reverts to `listening` after 2s
- `error` → red-500 dot, "Pipeline error"

---

### 5.4 `LastAlertBar.tsx`

Sticky strip pinned to the bottom of the window.

```typescript
interface LastAlertBarProps {
  alert: AlertNotification | null;
}
```

- Full-width, `border-t border-zinc-800`, `bg-zinc-950`
- Left accent border: `border-l-4 border-l-priority-{priority}`
- Content: `● [HIGH] Baby cry detected — check immediately · 12:04:33`
- All in `font-mono text-sm`
- No alert yet: `text-zinc-600 italic text-xs` — "No detections yet this session"

---

## 6. Root Layout — `App.tsx`

```tsx
<div className="h-screen w-screen bg-zinc-950 text-white flex flex-col overflow-hidden font-mono">

  <HeaderBar status={status} sessionCount={alerts.length} />

  <div className="flex flex-1 overflow-hidden">

    {/* Left column: Radar */}
    <div className="flex items-center justify-center w-[360px] shrink-0 border-r border-zinc-800 p-8">
      <RadarWidget latestAlert={alerts[0] ?? null} />
    </div>

    {/* Right column: Alert feed */}
    <div className="flex-1 overflow-y-auto p-4 space-y-2">
      <AlertFeed alerts={alerts} onCardClick={setReplayAlert} />
    </div>

  </div>

  <LastAlertBar alert={alerts[0] ?? null} />

</div>
```

---

## 7. Build Order

| Step | Task | Unblocks |
|---|---|---|
| 1 | Scaffold: `npm create tauri-app` with React + TypeScript + Tailwind | Everything |
| 2 | Write `contracts.ts` | All components |
| 3 | Write `mockFeed.ts`, wire into `App.tsx` with `IS_MOCK` flag | All UI work |
| 4 | Build `RadarWidget.tsx` — static rings + labels first, then blip, then sweep | Core visual |
| 5 | Build `AlertCard.tsx` + `AlertFeed.tsx` | Alert history |
| 6 | Build `HeaderBar.tsx` + `LastAlertBar.tsx` | Polish |
| 7 | Wire all state in `App.tsx`, full smoke test with mock data | Complete UI |
| 8 | Write `useAlertStream.ts` Tauri event hook | Python integration |
| 9 | Write Rust sidecar bridge in `main.rs` | Python integration |
| 10 | Connect to real Python pipeline, end-to-end test | Done |

---

## 8. OS Notifications (easy win, add at step 9)

When `priority === "high"`, fire a native OS notification via the Tauri notification plugin — works on both macOS and Windows:

```rust
app.notification()
    .builder()
    .title("SELD Alert")
    .body(&notification.message)
    .show()?;
```

No extra UI work needed.

---

## 9. Out of Scope (v1)

- Settings panel (threshold, confidence display)
- Persistent alert log to file
- System tray / background mode
- Multi-monitor support
- Sound / haptic feedback