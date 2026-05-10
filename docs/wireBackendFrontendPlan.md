## Wiring Plan: Backend → Tauri → Frontend

### How it works (already designed)

```
Microphone (sounddevice)
    → audio_io.py  (RawChunk queue)
    → orchestrator.py  (SED → DOA → LLM)
    → event_bus.py  (AlertNotification → stdout NDJSON, one line per alert)
    → lib.rs  (reads stdout, calls handle.emit("alert", line))
    → useAlertStream.ts  (listens to Tauri "alert" event, parses JSON)
    → App.tsx / components  (radar, feed, header)
```

The architecture is complete. What's missing is the **glue work** below.

---

### Step 1 — Swap the SED mock for the real model

In orchestrator.py, change the `MOCK SWAP` import:
```python
# FROM:
from modules.sed.mock import MockSEDModel as SEDModel
# TO:
from modules.sed.interface import SEDModel
```
Verify interface.py and inference.py load the `M2D_strong_1.pt` weight correctly before bundling.

---

### Step 2 — Bundle the Python backend as a Tauri sidecar binary

Tauri spawns the backend as a **child process** (not via network). The binary must exist at build time.

1. In backend, run PyInstaller:
   ```bash
   pip install pyinstaller
   pyinstaller --onefile --name seld-pipeline main.py \
     --add-data "resources/M2D_strong_1.pt:resources" \
     --add-data "../third_party/PretrainedSED:third_party/PretrainedSED"
   ```
2. Copy `backend/dist/seld-pipeline` → `frontend/src-tauri/binaries/seld-pipeline-aarch64-apple-darwin`  
   (Tauri 2 requires the **target triple** suffix; on Intel Mac it's `x86_64-apple-darwin`).

---

### Step 3 — Declare the sidecar in tauri.conf.json

Add one key to the `bundle` section in tauri.conf.json:
```json
"bundle": {
  ...existing keys...,
  "externalBin": ["binaries/seld-pipeline"]
}
```
This tells Tauri to include and code-sign the binary when building the `.app`.

---

### Step 4 — Add macOS microphone entitlement

The app bundle needs an entitlement or macOS will silently block the microphone.

1. Create `frontend/src-tauri/entitlements.macos.plist`:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" ...>
   <plist version="1.0"><dict>
     <key>com.apple.security.device.audio-input</key><true/>
   </dict></plist>
   ```
2. Reference it in tauri.conf.json under `bundle.macOS.entitlements`.

---

### Step 5 — Add Tauri `emit` feature to Cargo.toml

Cargo.toml currently has `tauri = { version = "2", features = [] }`. The `handle.emit()` call in lib.rs uses the `Emitter` trait. Confirm compilation succeeds; if not, add:
```toml
tauri = { version = "2", features = ["emit-all"] }
```

---

### Step 6 — Dev-mode smoke test

```bash
cd frontend
npm install
npm run tauri dev   # Rust compiles, React hot-reloads, mock feed shows in browser
```
At this point the frontend works with the mock. To test the real pipeline in dev mode, run the Python side manually in a second terminal:
```bash
cd backend && python main.py
```
and confirm JSON lines appear on stdout. Tauri dev mode won't spawn the sidecar automatically (no bundled binary yet), but the mock feed in App.tsx covers the UI.

---

### Step 7 — Production build

```bash
cd frontend
npm run tauri build
```
This produces a signed `.app` (macOS) containing: the React bundle, the Rust bridge, and the `seld-pipeline` binary. Double-clicking the app starts everything — no terminal needed.

---

### What's already done (no changes needed)

| Layer | Status |
|---|---|
| audio_io.py — real sounddevice mic capture | ✅ |
| event_bus.py — stdout NDJSON | ✅ |
| lib.rs — sidecar spawn + event re-emit | ✅ |
| useAlertStream.ts — Tauri event listener | ✅ |
| App.tsx — auto-switches mock ↔ real | ✅ |
| TypeScript types mirror Python contracts | ✅ |
| Capabilities (`shell:allow-spawn/execute/kill`) | ✅ |

The only real work is Steps 1–5: swap the mock, run PyInstaller, drop the binary in the right folder, and add two small config changes.

Similar code found with 1 license type