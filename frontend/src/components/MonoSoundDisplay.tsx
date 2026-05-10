import { motion, AnimatePresence } from "framer-motion";
import { AlertNotification, Priority } from "../types/contracts";
import { soundEmoji, soundImage } from "../utils/soundMeta";

const PRIORITY_HEX: Record<Priority, string> = {
  high:   "#ff385c",
  medium: "#f97316",
  low:    "#16a34a",
};

interface Props {
  alert: AlertNotification | null;
  avatarSrc?: string;
}

export default function MonoSoundDisplay({ alert, avatarSrc }: Props) {
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
              className="flex flex-col items-center"
            >
              {soundImage(alert.sound_class) ? (
                <img
                  src={soundImage(alert.sound_class)!}
                  alt={alert.sound_class}
                  className="select-none"
                  style={{ width: 220, height: 220, objectFit: "contain", borderRadius: 16 }}
                />
              ) : (
                <span className="text-[100px] leading-none select-none" aria-hidden="true">
                  {soundEmoji(alert.sound_class)}
                </span>
              )}
            </motion.div>
          ) : (
            <motion.div
              key="idle"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex flex-col items-center gap-2"
            >
              {avatarSrc ? (
                <img
                  src={avatarSrc}
                  alt="you"
                  className="select-none"
                  style={{ width: 120, height: 120, objectFit: "cover", borderRadius: "50%", opacity: 0.7 }}
                />
              ) : (
                <span className="text-[48px] leading-none select-none opacity-25" aria-hidden="true">🎙</span>
              )}
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

      {/* ── Single latest message below the square ── */}
      <AnimatePresence mode="wait">
        {alert?.message && (
          <motion.p
            key={alert.timestamp}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -6 }}
            transition={{ duration: 0.22, ease: "easeOut" }}
            style={{
              maxWidth: 300,
              textAlign: "center",
              fontSize: 15,
              lineHeight: 1.5,
              color: "#3f3f3f",
              fontFamily: "'Child Writing', 'Inter', -apple-system, system-ui, sans-serif",
            }}
          >
            {alert.message}
          </motion.p>
        )}
      </AnimatePresence>
    </div>
  );
}
