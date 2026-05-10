import { useState, useEffect, useCallback, useMemo, useRef } from "react";
import { AnimatePresence } from "framer-motion";
import { AlertNotification, RawEvent, SystemInfo } from "./types/contracts";
import { startMockFeed } from "./mock/mockFeed";
import { useAlertStream } from "./hooks/useAlertStream";
import RadarWidget, { RadarDetection } from "./components/RadarWidget";
import MonoSoundDisplay from "./components/MonoSoundDisplay";
import AlertToast from "./components/AlertToast";

// Use mock feed when running in browser without Tauri (pure dev mode).
const IS_MOCK = !("__TAURI_INTERNALS__" in window);

interface Toast {
  id: string;
  alert: AlertNotification;
}

function App() {
  const [alerts, setAlerts]       = useState<AlertNotification[]>([]);
  const [rawEvents, setRawEvents] = useState<RawEvent[]>([]);
  const [toasts, setToasts]       = useState<Toast[]>([]);
  const [isMono, setIsMono]       = useState(false);
  const toastCountRef             = useRef(0);

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const handleNewAlert = useCallback((n: AlertNotification) => {
    setAlerts((prev) => [n, ...prev].slice(0, 50));
    const id = `toast-${toastCountRef.current++}`;
    setToasts((prev) => [...prev, { id, alert: n }]);
  }, []);

  const handleRawEvent = useCallback((n: RawEvent) => {
    setRawEvents((prev) => [n, ...prev].slice(0, 80));
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
    return [...grouped, ...raw];
  }, [alerts, rawEvents]);

  return (
    <div
      className="h-screen w-screen flex items-center overflow-visible"
      style={{
        background: "#f7f7f7",
        fontFamily: "'Child Writing', 'Inter', -apple-system, system-ui, sans-serif",
        paddingLeft: 10,
      }}
    >
      <div className="relative">
        {/* Persistent radar (stereo) or square (mono) */}
        {isMono ? (
          <MonoSoundDisplay alert={alerts[0] ?? null} />
        ) : (
          <div
            className="relative rounded-full overflow-hidden bg-white"
            style={{
              boxShadow:
                "rgba(0,0,0,0.02) 0 0 0 1px, rgba(0,0,0,0.06) 0 4px 12px, rgba(0,0,0,0.12) 0 8px 20px",
            }}
          >
            <RadarWidget detections={radarDetections} size={440} />
          </div>
        )}

        {/* Toast notifications — pop out to the right of the radar */}
        <div
          className="absolute top-0 left-full ml-5 flex flex-col gap-3 pointer-events-none"
          style={{ minWidth: 272 }}
        >
          <AnimatePresence initial={false}>
            {toasts.map((toast) => (
              <div key={toast.id} className="pointer-events-auto">
                <AlertToast
                  alert={toast.alert}
                  onDismiss={() => dismissToast(toast.id)}
                />
              </div>
            ))}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

export default App;


