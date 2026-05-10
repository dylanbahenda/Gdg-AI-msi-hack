import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";

export default function MonoBanner() {
  const [dismissed, setDismissed] = useState(false);

  return (
    <AnimatePresence>
      {!dismissed && (
        <motion.div
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          transition={{ duration: 0.25, ease: "easeOut" }}
          className="flex items-start gap-3 px-5 py-3 bg-[#fff7ed] border-b border-[#fed7aa]"
        >
          <span className="text-[18px] shrink-0 mt-0.5" aria-hidden="true">🎙</span>
          <div className="flex-1 min-w-0">
            <p className="text-[13px] font-semibold text-[#9a3412]">
              Mono microphone detected — spatial positioning unavailable
            </p>
            <p className="text-[12px] text-[#c2410c] mt-0.5 leading-snug">
              Only a single-channel mic was found. Sound detection works normally, but direction and distance cannot be estimated.
              Connect a stereo microphone or audio interface for full spatial awareness.
            </p>
          </div>
          <button
            onClick={() => setDismissed(true)}
            aria-label="Dismiss"
            className="shrink-0 mt-0.5 text-[#c2410c] hover:text-[#9a3412] transition-colors text-[16px] leading-none font-light"
          >
            ✕
          </button>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
