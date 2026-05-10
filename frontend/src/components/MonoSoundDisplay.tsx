import { motion, AnimatePresence } from "framer-motion";
import { AlertNotification, Priority } from "../types/contracts";
import { soundEmoji, soundLabel } from "../utils/soundMeta";

const PRIORITY_HEX: Record<Priority, string> = {
  high:   "#ff385c",
  medium: "#f97316",
  low:    "#16a34a",
};

interface Props {
  alert: AlertNotification | null;
}

export default function MonoSoundDisplay({ alert }: Props) {
  return (
    <div className="flex flex-col items-center justify-center w-full h-full gap-4">
      <div
        className="relative flex items-center justify-center rounded-2xl bg-white"
        style={{
          width: 260,
          height: 260,
          boxShadow: "rgba(0,0,0,0.02) 0 0 0 1px, rgba(0,0,0,0.06) 0 4px 12px, rgba(0,0,0,0.12) 0 8px 20px",
          border: alert ? `3px solid ${PRIORITY_HEX[alert.priority]}` : "3px solid #dddddd",
          transition: "border-color 0.3s ease",
        }}
      >
        <AnimatePresence mode="wait">
          {alert ? (
            <motion.div
              key={alert.sound_class + alert.timestamp}
              initial={{ opacity: 0, scale: 0.7 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.7 }}
              transition={{ duration: 0.22, ease: "easeOut" }}
              className="flex flex-col items-center gap-3"
            >
              <span className="text-[72px] leading-none select-none" aria-hidden="true">
                {soundEmoji(alert.sound_class)}
              </span>
              <span className="text-[16px] font-semibold text-[#222222] capitalize tracking-tight">
                {soundLabel(alert.sound_class)}
              </span>
              <span
                className="text-[12px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-full"
                style={{
                  color: PRIORITY_HEX[alert.priority],
                  background: `${PRIORITY_HEX[alert.priority]}18`,
                }}
              >
                {alert.priority}
              </span>
            </motion.div>
          ) : (
            <motion.div
              key="idle"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center gap-2"
            >
              <span className="text-[48px] leading-none select-none opacity-25" aria-hidden="true">🎙</span>
              <span className="text-[13px] text-[#6a6a6a] italic">Awaiting detections…</span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* Pulsing ring when active */}
        {alert && (
          <motion.span
            key={`ring-${alert.timestamp}`}
            className="absolute inset-0 rounded-2xl pointer-events-none"
            style={{ border: `3px solid ${PRIORITY_HEX[alert.priority]}` }}
            initial={{ opacity: 0.6, scale: 1 }}
            animate={{ opacity: 0, scale: 1.08 }}
            transition={{ duration: 0.7, ease: "easeOut" }}
          />
        )}
      </div>

      {/* LLM message below the square */}
      <AnimatePresence mode="wait">
        {alert && (
          <motion.p
            key={`msg-${alert.timestamp}`}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="text-[13px] text-[#3f3f3f] text-center leading-snug max-w-[260px]"
          >
            {alert.message}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}
