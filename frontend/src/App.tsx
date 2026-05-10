import { useState, useEffect, useCallback, useMemo } from "react";
import { AlertNotification, RawEvent, SystemInfo } from "./types/contracts";
import { startMockFeed } from "./mock/mockFeed";
import { useAlertStream } from "./hooks/useAlertStream";
import RadarWidget, { RadarDetection } from "./components/RadarWidget";
import AlertFeed from "./components/AlertFeed";
import HeaderBar from "./components/HeaderBar";
import LastAlertBar from "./components/LastAlertBar";
import MonoSoundDisplay from "./components/MonoSoundDisplay";
import MonoBanner from "./components/MonoBanner";
import { soundEmoji } from "./utils/soundMeta";

// Use mock feed when running in browser without Tauri (pure dev mode).
const IS_MOCK = !("__TAURI_INTERNALS__" in window);

function App() {
  const [alerts, setAlerts]           = useState<AlertNotification[]>([]);
  const [rawEvents, setRawEvents]     = useState<RawEvent[]>([]);
  const [replayAlert, setReplayAlert] = useState<AlertNotification | null>(null);
  const [status, setStatus]           = useState<"listening" | "detected" | "error">("listening");
  const [isMono, setIsMono]           = useState(false);

  const handleNewAlert = useCallback((n: AlertNotification) => {
    setAlerts((prev) => [n, ...prev].slice(0, 50));
    setReplayAlert(null);
    setStatus("detected");
    setTimeout(() => setStatus("listening"), 2000);
  }, []);

  const handleRawEvent = useCallback((n: RawEvent) => {
    setRawEvents((prev) => [n, ...prev].slice(0, 80));
    setStatus("detected");
    setTimeout(() => setStatus("listening"), 800);
  }, []);

  const handleSystemInfo = useCallback((info: SystemInfo) => {
    setIsMono(info.mono_fallback);
  }, []);

  // Mock feed (browser dev mode — no Tauri running).
  useEffect(() => {
    if (!IS_MOCK) return;
    return startMockFeed(handleNewAlert);
  }, [handleNewAlert]);

  // Real feed (inside Tauri sidecar).
  useAlertStream(
    IS_MOCK ? () => {} : handleNewAlert,
    IS_MOCK ? () => {} : handleRawEvent,
    IS_MOCK ? () => {} : handleSystemInfo,
  );

  // The alert shown on the radar: replayed card OR the newest real alert.
  const radarAlert = replayAlert ?? alerts[0] ?? null;
  const radarDetections = useMemo<RadarDetection[]>(() => {
    const raw: RadarDetection[] = rawEvents.slice(0, 30).map((event) => ({
      id: `raw-${event.window_id}`,
      timestamp: event.timestamp,
      sound_class: event.sound_class,
      direction_of_arrival: event.doa_direction_of_arrival,
      distance_estimation: event.doa_distance_estimation,
      sed_confidence: event.sed_confidence,
    }));
    const grouped: RadarDetection[] = alerts.slice(0, 18).map((alert, index) => ({
      id: `alert-${alert.timestamp}-${alert.sound_class}-${index}`,
      timestamp: alert.timestamp,
      sound_class: alert.sound_class,
      direction_of_arrival: alert.direction_of_arrival,
      distance_estimation: alert.distance_estimation,
      sed_confidence: alert.sed_confidence,
      priority: alert.priority,
      message: alert.message,
    }));
    const replay = replayAlert
      ? [{
          id: `replay-${replayAlert.timestamp}-${replayAlert.sound_class}`,
          timestamp: replayAlert.timestamp,
          sound_class: replayAlert.sound_class,
          direction_of_arrival: replayAlert.direction_of_arrival,
          distance_estimation: replayAlert.distance_estimation,
          sed_confidence: replayAlert.sed_confidence,
          priority: replayAlert.priority,
          message: replayAlert.message,
        }]
      : [];
    return [...replay, ...grouped, ...raw];
  }, [alerts, rawEvents, replayAlert]);

  return (
    <div className="h-screen w-screen bg-[#f7f7f7] flex flex-col overflow-hidden" style={{ fontFamily: "'Inter', -apple-system, system-ui, sans-serif", color: "#222222" }}>
      <HeaderBar status={status} sessionCount={alerts.length} />

      {/* Mono-mode startup banner */}
      {isMono && <MonoBanner />}

      <div className="flex flex-1 overflow-hidden gap-0">
        {/* Left panel — Radar (stereo) or Mono sound display */}
        <div className="flex flex-col items-center justify-center w-[400px] shrink-0 border-r border-[#dddddd] bg-white p-6 gap-5">
          {isMono ? (
            <MonoSoundDisplay alert={replayAlert ?? alerts[0] ?? null} />
          ) : (
            <>
              <div
                className="rounded-full overflow-hidden bg-white"
                style={{ boxShadow: "rgba(0,0,0,0.02) 0 0 0 1px, rgba(0,0,0,0.06) 0 4px 12px, rgba(0,0,0,0.12) 0 8px 20px" }}
              >
                <RadarWidget detections={radarDetections} size={330} />
              </div>

              {/* Latest blip summary */}
              {radarAlert ? (
                <div className="w-full rounded-xl bg-[#f7f7f7] border border-[#ebebeb] px-4 py-3">
                  <p className="text-[12px] text-[#6a6a6a] font-mono text-center leading-relaxed">
                    <span className="text-[16px] align-middle mr-1" aria-hidden="true">{soundEmoji(radarAlert.sound_class)}</span>
                    <span className="text-[#222222] font-medium capitalize">{radarAlert.sound_class.replace(/_/g, " ")}</span>
                    &nbsp;·&nbsp;{radarAlert.direction_of_arrival.toFixed(0)}°
                    &nbsp;·&nbsp;{radarAlert.distance_estimation.toFixed(1)} m
                  </p>
                  <p className="text-[13px] text-[#3f3f3f] text-center mt-1 leading-snug">{radarAlert.message}</p>
                </div>
              ) : (
                <p className="text-[12px] text-[#6a6a6a] italic">Awaiting detections…</p>
              )}
            </>
          )}
        </div>

        {/* Right — Alert feed */}
        <div className="flex-1 overflow-y-auto p-5 space-y-3">
          <AlertFeed alerts={alerts} onCardClick={setReplayAlert} showSpatial={!isMono} />
        </div>
      </div>

      <LastAlertBar alert={alerts[0] ?? null} />
    </div>
  );
}

export default App;
