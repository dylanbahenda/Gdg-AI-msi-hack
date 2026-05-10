import { motion } from "framer-motion";
import { AlertNotification, Priority } from "../types/contracts";
import { soundEmoji, soundImage, soundLabel } from "../utils/soundMeta";

// Airbnb-adapted priority colors: Rausch for high
const PRIORITY_HEX: Record<Priority, string> = {
  high:   "#ff385c",
  medium: "#f97316",
  low:    "#16a34a",
};

const PRIORITY_BG: Record<Priority, string> = {
  high:   "bg-[#fff0f2]",
  medium: "bg-[#fff7ed]",
  low:    "bg-[#f0fdf4]",
};

const PRIORITY_LABEL: Record<Priority, string> = {
  high:   "text-[#ff385c]",
  medium: "text-[#ea6c00]",
  low:    "text-[#16a34a]",
};

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

interface Props {
  alert: AlertNotification;
  onClick: (a: AlertNotification) => void;
  showSpatial?: boolean;
}

export default function AlertCard({ alert, onClick, showSpatial = true }: Props) {
  const label = soundLabel(alert.sound_class);
  const priorityHex = PRIORITY_HEX[alert.priority];

  return (
    <motion.div
      initial={{ opacity: 0, y: -6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
      onClick={() => onClick(alert)}
      style={{
        border: `3px solid ${priorityHex}`,
        borderRadius: 16,
        boxShadow: `0 0 0 1px ${priorityHex}22, rgba(0,0,0,0.04) 0 2px 6px, rgba(0,0,0,0.08) 0 4px 8px`,
        fontFamily: "'Child Writing', 'Inter', -apple-system, system-ui, sans-serif",
      }}
      className="bg-white px-4 py-3.5 cursor-pointer hover:shadow-lg transition-shadow"
    >
      {/* Top row */}
      <div className="flex items-center gap-2">
        {/* Priority badge */}
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold uppercase tracking-wide ${PRIORITY_BG[alert.priority]} ${PRIORITY_LABEL[alert.priority]}`}>
          <span className="w-1.5 h-1.5 rounded-full" style={{ background: priorityHex }} />
          {alert.priority}
        </span>
        {/* Sound class image or emoji */}
        {soundImage(alert.sound_class) ? (
          <img src={soundImage(alert.sound_class)!} alt={soundLabel(alert.sound_class)} style={{ width: 28, height: 28, objectFit: "contain", borderRadius: 6 }} />
        ) : (
          <span className="text-[18px] leading-none" aria-hidden="true">{soundEmoji(alert.sound_class)}</span>
        )}
        <span className="text-[14px] font-medium text-[#222222] capitalize">{label}</span>
        {/* Timestamp */}
        <span className="text-[13px] text-[#6a6a6a] tabular-nums ml-auto font-mono">{formatTime(alert.timestamp)}</span>
      </div>

      {/* LLM message */}
      <p className="text-[14px] text-[#3f3f3f] mt-2 leading-[1.5]">{alert.message}</p>

      {/* Technical metadata */}
      <p className="text-[12px] text-[#6a6a6a] mt-1.5 font-mono">
        {showSpatial && (
          <>
            ↗ {alert.direction_of_arrival.toFixed(0)}°
            &nbsp;·&nbsp;
            {alert.distance_estimation.toFixed(1)} m
            &nbsp;·&nbsp;
          </>
        )}
        conf {(alert.sed_confidence * 100).toFixed(0)}%
        {alert.window_count ? (
          <>
            &nbsp;·&nbsp;
            {alert.window_count} win
          </>
        ) : null}
      </p>
    </motion.div>
  );
}
