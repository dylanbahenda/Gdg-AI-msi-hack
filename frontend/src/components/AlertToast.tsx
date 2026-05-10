import { useEffect } from "react";
import { motion } from "framer-motion";
import { AlertNotification } from "../types/contracts";
import { soundEmoji, soundLabel } from "../utils/soundMeta";

const TOAST_DURATION_MS = 5000;

interface Props {
  alert: AlertNotification;
  onDismiss: () => void;
}

export default function AlertToast({ alert, onDismiss }: Props) {
  useEffect(() => {
    const t = setTimeout(onDismiss, TOAST_DURATION_MS);
    return () => clearTimeout(t);
  }, [onDismiss]);

  return (
    <motion.div
      initial={{ opacity: 0, x: -16 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: 16 }}
      transition={{ duration: 0.22, ease: "easeOut" }}
      style={{
        boxShadow:
          "rgba(0,0,0,0.03) 0 0 0 1px, rgba(0,0,0,0.08) 0 4px 16px, rgba(0,0,0,0.12) 0 8px 24px",
        fontFamily: "'Child Writing', 'Inter', -apple-system, system-ui, sans-serif",
        outline: "none",
      }}
      className="bg-white rounded-xl px-4 py-3 w-[272px]"
    >
      {/* Icon + name row */}
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-[22px] leading-none select-none" aria-hidden="true">
          {soundEmoji(alert.sound_class)}
        </span>
        <span className="text-[14px] font-semibold text-[#222222] capitalize leading-tight">
          {soundLabel(alert.sound_class)}
        </span>
      </div>

      {/* LLM message */}
      <p className="text-[13px] text-[#3f3f3f] leading-snug mb-2">
        {alert.message}
      </p>

      {/* Distance */}
      <p className="text-[11px] text-[#6a6a6a] font-mono">
        {alert.distance_estimation.toFixed(1)} m &middot; {alert.direction_of_arrival.toFixed(0)}&deg;
      </p>
    </motion.div>
  );
}
