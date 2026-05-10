import { useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";

const LEGEND_ITEMS = [
  { src: "/img/alarm.jpg",       name: "Alarm" },
  { src: "/img/brokenglass.jpg", name: "Broken Glass" },
  { src: "/img/clap.jpg",        name: "Clap" },
  { src: "/img/cry.jpg",         name: "Crying" },
  { src: "/img/dog.jpg",         name: "Dog Barking" },
  { src: "/img/knock.jpg",       name: "Knock" },
  { src: "/img/metal.jpg",       name: "Metal Sound" },
  { src: "/img/ring.jpg",        name: "Phone Ringing" },
  { src: "/img/scream.jpg",      name: "Scream" },
  { src: "/img/doorbell.jpg",     name: "Doorbell" },
  { src: "/img/female.jpg",      name: "Female (You)" },
];

interface Props {
  open: boolean;
  onClose: () => void;
}

export default function LegendModal({ open, onClose }: Props) {
  const dialogRef = useRef<HTMLDivElement>(null);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        /* Backdrop — also acts as the flex centering layer */
        <motion.div
          key="legend-backdrop"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={onClose}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.35)",
            zIndex: 100,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
        >
          {/* Window — stopPropagation so clicks inside don't close */}
          <motion.div
            key="legend-window"
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label="Sound Legend"
            initial={{ opacity: 0, scale: 0.92 }}
            animate={{ opacity: 1, scale: 1 }}
            exit={{ opacity: 0, scale: 0.92 }}
            transition={{ type: "spring", stiffness: 340, damping: 30 }}
            onClick={(e) => e.stopPropagation()}
            style={{
              background: "#fff",
              borderRadius: 20,
              boxShadow:
                "rgba(0,0,0,0.04) 0 0 0 1px, rgba(0,0,0,0.14) 0 8px 32px, rgba(0,0,0,0.22) 0 20px 60px",
              width: "min(560px, 88vw)",
              maxHeight: "72vh",
              display: "flex",
              flexDirection: "column",
              overflow: "hidden",
              fontFamily: "'Child Writing', 'Inter', -apple-system, system-ui, sans-serif",
            }}
          >
            {/* Title bar */}
            <div
              style={{
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
                padding: "14px 20px",
                borderBottom: "1px solid #ebebeb",
                flexShrink: 0,
              }}
            >
              <span style={{ fontSize: 17, fontWeight: 700, color: "#111" }}>
                Sound Legend
              </span>
              <button
                onClick={onClose}
                style={{
                  fontSize: 18,
                  lineHeight: 1,
                  color: "#6a6a6a",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  padding: "4px 8px",
                  borderRadius: 8,
                }}
                aria-label="Close legend"
              >
                ✕
              </button>
            </div>

            {/* Grid of images */}
            <div
              style={{
                overflowY: "auto",
                padding: "16px 16px 20px",
                display: "grid",
                gridTemplateColumns: "repeat(auto-fill, minmax(100px, 1fr))",
                gap: 14,
              }}
            >
              {LEGEND_ITEMS.map(({ src, name }) => (
                <div
                  key={src}
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    alignItems: "center",
                    gap: 8,
                  }}
                >
                  <div
                    style={{
                      width: 88,
                      height: 88,
                      borderRadius: 14,
                      overflow: "hidden",
                      background: "#f5f5f5",
                      boxShadow: "rgba(0,0,0,0.06) 0 2px 8px, rgba(0,0,0,0.02) 0 0 0 1px",
                      flexShrink: 0,
                    }}
                  >
                    <img
                      src={src}
                      alt={name}
                      style={{ width: "100%", height: "100%", objectFit: "contain" }}
                    />
                  </div>
                  <span
                    style={{
                      fontSize: 13,
                      fontWeight: 600,
                      color: "#222",
                      textAlign: "center",
                      lineHeight: 1.3,
                    }}
                  >
                    {name}
                  </span>
                </div>
              ))}
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
