import { useState, useEffect, useCallback } from "react";
import { AlertNotification } from "./types/contracts";
import { startMockFeed } from "./mock/mockFeed";
import { useAlertStream } from "./hooks/useAlertStream";
import RadarWidget from "./components/RadarWidget";
import AlertFeed from "./components/AlertFeed";
import HeaderBar from "./components/HeaderBar";
import LastAlertBar from "./components/LastAlertBar";

// Use mock feed when running in browser without Tauri (pure dev mode).
const IS_MOCK = !("__TAURI_INTERNALS__" in window);

function App() {
  const [alerts, setAlerts]           = useState<AlertNotification[]>([]);
  const [replayAlert, setReplayAlert] = useState<AlertNotification | null>(null);
  const [status, setStatus]           = useState<"listening" | "detected" | "error">("listening");

  const handleNewAlert = useCallback((n: AlertNotification) => {
    setAlerts((prev) => [n, ...prev].slice(0, 50));
    setReplayAlert(null);
    setStatus("detected");
    setTimeout(() => setStatus("listening"), 2000);
  }, []);

  // Mock feed (browser dev mode — no Tauri running).
  useEffect(() => {
    if (!IS_MOCK) return;
    return startMockFeed(handleNewAlert);
  }, [handleNewAlert]);

  // Real feed (inside Tauri sidecar).
  useAlertStream(IS_MOCK ? () => {} : handleNewAlert);

  // The alert shown on the radar: replayed card OR the newest real alert.
  const radarAlert = replayAlert ?? alerts[0] ?? null;

  return (
    <div className="h-screen w-screen bg-[#f7f7f7] flex flex-col overflow-hidden" style={{ fontFamily: "'Inter', -apple-system, system-ui, sans-serif", color: "#222222" }}>
      <HeaderBar status={status} sessionCount={alerts.length} />

      <div className="flex flex-1 overflow-hidden gap-0">
        {/* Left — Radar panel */}
        <div className="flex flex-col items-center justify-center w-[380px] shrink-0 border-r border-[#dddddd] bg-white p-6 gap-5">
          {/* Radar sits on its own dark surface */}
          <div
            className="rounded-2xl overflow-hidden"
            style={{ boxShadow: "rgba(0,0,0,0.02) 0 0 0 1px, rgba(0,0,0,0.06) 0 4px 12px, rgba(0,0,0,0.12) 0 8px 20px" }}
          >
            <RadarWidget latestAlert={radarAlert} size={300} />
          </div>

          {/* Latest blip summary */}
          {radarAlert ? (
            <div className="w-full rounded-xl bg-[#f7f7f7] border border-[#ebebeb] px-4 py-3">
              <p className="text-[12px] text-[#6a6a6a] font-mono text-center leading-relaxed">
                <span className="text-[#222222] font-medium capitalize">{radarAlert.sound_class.replace(/_/g, " ")}</span>
                &nbsp;·&nbsp;{radarAlert.direction_of_arrival.toFixed(0)}°
                &nbsp;·&nbsp;{radarAlert.distance_estimation.toFixed(1)} m
              </p>
            </div>
          ) : (
            <p className="text-[12px] text-[#6a6a6a] italic">Awaiting detections…</p>
          )}
        </div>

        {/* Right — Alert feed */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          <AlertFeed alerts={alerts} onCardClick={setReplayAlert} />
        </div>
      </div>

      <LastAlertBar alert={alerts[0] ?? null} />
    </div>
  );
}

export default App;
