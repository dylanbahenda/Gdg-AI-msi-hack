import { useState, useEffect, useCallback, useMemo } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { AlertNotification, Priority, RawEvent, SystemInfo } from "./types/contracts";
import { startMockFeed } from "./mock/mockFeed";
import { useAlertStream } from "./hooks/useAlertStream";
import RadarWidget, { RadarDetection } from "./components/RadarWidget";
import MonoSoundDisplay from "./components/MonoSoundDisplay";
import AlertFeed from "./components/AlertFeed";
import LegendModal from "./components/LegendModal";
import { soundLabel } from "./utils/soundMeta";

const IS_MOCK = !("__TAURI_INTERNALS__" in window);

const PRIORITY_HEX: Record<Priority, string> = {
  high:   "#ff385c",
  medium: "#f97316",
  low:    "#16a34a",
};

type Gender = "female" | "male";

const AVATAR: Record<Gender, string> = {
  female: "/img/female.jpg",
  male:   "/img/boy.jpg",
};

function App() {
  const [alerts, setAlerts]             = useState<AlertNotification[]>([]);
  const [rawEvents, setRawEvents]       = useState<RawEvent[]>([]);
  const [isMono, setIsMono]             = useState(false);
  const [gender, setGender]             = useState<Gender>("female");
  const [showMessages, setShowMessages] = useState(false);
  const [showLegend, setShowLegend]     = useState(false);

  const avatarSrc = AVATAR[gender];

  const handleNewAlert = useCallback((n: AlertNotification) => {
    setAlerts((prev) => [n, ...prev].slice(0, 50));
  }, []);

  const handleRawEvent = useCallback((n: RawEvent) => {
    setRawEvents((prev) => [n, ...prev].slice(0, 80));
  }, []);

  const handleSystemInfo = useCallback((info: SystemInfo) => {
    setIsMono(info.mono_fallback);
  }, []);

  useEffect(() => {
    if (!IS_MOCK) return;
    return startMockFeed(handleNewAlert);
  }, [handleNewAlert]);

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
    const grouped: RadarDetection[] = alerts.slice(0, 18).map((alert) => ({
      id: `alert-${alert.timestamp}-${alert.sound_class}`,
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
      className="h-screen w-screen flex flex-col overflow-hidden relative"
      style={{
        background: "#f7f7f7",
        fontFamily: "'Child Writing', 'Inter', -apple-system, system-ui, sans-serif",
      }}
    >
      {/* ── Header bar ─────────────────────────────────────────── */}
      <div className="flex items-center justify-between px-4 py-2 flex-shrink-0">

        {/* Top-left: character selector */}
        <div className="flex items-center gap-2">
          {(["female", "male"] as Gender[]).map((g) => (
            <button
              key={g}
              onClick={() => setGender(g)}
              title={g === "female" ? "Female" : "Male"}
              style={{
                width: 42,
                height: 42,
                borderRadius: "50%",
                overflow: "hidden",
                border: gender === g ? "3px solid #ff385c" : "3px solid transparent",
                boxShadow: gender === g
                  ? "0 0 0 1px #ff385c, rgba(0,0,0,0.12) 0 4px 12px"
                  : "rgba(0,0,0,0.10) 0 2px 8px",
                opacity: gender === g ? 1 : 0.45,
                transition: "all 0.2s ease",
                padding: 0,
                cursor: "pointer",
                background: "none",
              }}
            >
              <img
                src={AVATAR[g]}
                alt={g}
                style={{ width: "100%", height: "100%", objectFit: "cover", display: "block" }}
              />
            </button>
          ))}
        </div>

        {/* Top-right: messages button */}
        <button
          onClick={() => setShowMessages(true)}
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            padding: "6px 14px",
            borderRadius: 999,
            background: "#fff",
            border: "none",
            cursor: "pointer",
            fontSize: 13,
            fontWeight: 500,
            color: "#222",
            boxShadow: "rgba(0,0,0,0.06) 0 2px 8px, rgba(0,0,0,0.02) 0 0 0 1px",
          }}
        >
          <span>💬</span>
          <span>Messages</span>
          {alerts.length > 0 && (
            <span
              style={{
                background: "#ff385c",
                color: "#fff",
                borderRadius: 999,
                fontSize: 11,
                fontFamily: "monospace",
                width: 20,
                height: 20,
                minWidth: 20,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              {alerts.length > 99 ? "99" : alerts.length}
            </span>
          )}
        </button>
      </div>

      {/* ── Main content ───────────────────────────────────────── */}
      <div
        className="flex-1 flex items-center justify-center overflow-visible"
        style={{ paddingLeft: 10 }}
      >
        <div className="relative">
          {isMono ? (
            <MonoSoundDisplay alert={alerts[0] ?? null} avatarSrc={avatarSrc} />
          ) : (
            <div className="flex flex-col items-center gap-4">
              <div
                className="relative rounded-full overflow-hidden bg-white"
                style={{
                  boxShadow:
                    "rgba(0,0,0,0.02) 0 0 0 1px, rgba(0,0,0,0.06) 0 4px 12px, rgba(0,0,0,0.12) 0 8px 20px",
                }}
              >
                <RadarWidget detections={radarDetections} size={400} avatarSrc={avatarSrc} />
              </div>
              <AnimatePresence mode="wait">
                {alerts[0] && (
                  <motion.p
                    key={alerts[0].timestamp}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: -6 }}
                    transition={{ duration: 0.22, ease: "easeOut" }}
                    style={{
                      maxWidth: 380,
                      textAlign: "center",
                      fontSize: 15,
                      lineHeight: 1.5,
                      color: "#3f3f3f",
                      fontFamily: "'Child Writing', 'Inter', -apple-system, system-ui, sans-serif",
                    }}
                  >
                    <span style={{ color: PRIORITY_HEX[alerts[0].priority], fontWeight: 700 }}>
                      {soundLabel(alerts[0].sound_class)}
                    </span>
                    {alerts[0].message && `: ${alerts[0].message}`}
                  </motion.p>
                )}
              </AnimatePresence>
            </div>
          )}

        </div>
      </div>

      {/* Toasts removed — latest message shown below the main square */}

      {/* ── Legend button (fixed bottom-left) ───────────────── */}
      <button
        onClick={() => setShowLegend(true)}
        style={{
          position: "fixed",
          bottom: 18,
          left: 18,
          padding: "7px 16px",
          borderRadius: 999,
          background: "#fff",
          border: "none",
          cursor: "pointer",
          fontSize: 13,
          fontWeight: 600,
          color: "#222",
          boxShadow: "rgba(0,0,0,0.06) 0 2px 8px, rgba(0,0,0,0.02) 0 0 0 1px",
          zIndex: 40,
          fontFamily: "'Child Writing', 'Inter', -apple-system, system-ui, sans-serif",
        }}
      >
        Legend
      </button>

      {/* ── Legend modal ────────────────────────────────────────── */}
      <LegendModal open={showLegend} onClose={() => setShowLegend(false)} />

      {/* ── Messages panel (slides in from right) ──────────────── */}
      <AnimatePresence>
        {showMessages && (
          <motion.div
            initial={{ x: "100%" }}
            animate={{ x: 0 }}
            exit={{ x: "100%" }}
            transition={{ type: "spring", stiffness: 320, damping: 32 }}
            style={{
              position: "fixed",
              top: 0,
              right: 0,
              bottom: 0,
              width: 320,
              display: "flex",
              flexDirection: "column",
              background: "#f7f7f7",
              boxShadow: "-4px 0 24px rgba(0,0,0,0.12)",
              zIndex: 50,
            }}
          >
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "12px 16px",
                borderBottom: "1px solid #ebebeb",
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: 16, fontWeight: 600, color: "#222" }}>Messages</span>
              <button
                onClick={() => setShowMessages(false)}
                style={{
                  fontSize: 20,
                  lineHeight: 1,
                  color: "#6a6a6a",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                }}
              >
                ✕
              </button>
            </div>
            <div style={{ flex: 1, overflowY: "auto", padding: 16 }}>
              <AlertFeed alerts={alerts} onCardClick={() => {}} showSpatial={!isMono} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export default App;
