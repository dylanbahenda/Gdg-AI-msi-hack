import { useEffect, useRef } from "react";
import { AlertNotification, Priority } from "../types/contracts";

// ── Constants ────────────────────────────────────────────────────────────────
const MAX_DIST_M   = 5;       // metres — full-radius distance
const BLIP_TTL_MS  = 4000;    // blip fades over 4 seconds
const SWEEP_RPM_MS = 3000;    // full rotation every 3 seconds
const TRAIL_STEPS  = 24;      // sweep-trail arc segments
const TRAIL_ARC    = Math.PI / 2; // 90° sweep trail

const COLORS = {
  bg:           "#060d06",
  ring:         "#0f1f0f",
  grid:         "#1a2f1a",
  border:       "#1a3a1a",
  label:        "#4a6a4a",
  sweep:        "#22c55e",
  priorityHigh:   "#ef4444",
  priorityMedium: "#f97316",
  priorityLow:    "#22c55e",
} as const;

const PRIORITY_COLOR: Record<Priority, string> = {
  high:   COLORS.priorityHigh,
  medium: COLORS.priorityMedium,
  low:    COLORS.priorityLow,
};

// ── Helpers ──────────────────────────────────────────────────────────────────
function polarToXY(
  dirDeg: number,
  distM: number,
  radiusPx: number,
  cx: number,
  cy: number,
) {
  const r   = Math.min(distM / MAX_DIST_M, 1) * radiusPx;
  const rad = ((dirDeg - 90) * Math.PI) / 180; // 0° = top (North)
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

// ── Types ────────────────────────────────────────────────────────────────────
interface Blip {
  alert: AlertNotification;
  born:  number; // performance.now()
}

interface Props {
  latestAlert: AlertNotification | null;
  size?: number;
}

// ── Component ────────────────────────────────────────────────────────────────
export default function RadarWidget({ latestAlert, size = 320 }: Props) {
  const canvasRef    = useRef<HTMLCanvasElement>(null);
  const blipsRef     = useRef<Blip[]>([]);
  const sweepRef     = useRef(0);       // radians
  const lastTimeRef  = useRef<number | null>(null);
  const rafRef       = useRef<number>(0);

  // Add a new blip whenever latestAlert changes.
  useEffect(() => {
    if (!latestAlert) return;
    blipsRef.current.push({ alert: latestAlert, born: performance.now() });
  }, [latestAlert]);

  // Animation loop — runs independently of React renders.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const dpr    = window.devicePixelRatio ?? 1;
    canvas.width  = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width  = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.scale(dpr, dpr);

    const cx     = size / 2;
    const cy     = size / 2;
    const radius = size / 2 - 16;

    function draw(now: number) {
      const dt = lastTimeRef.current == null ? 0 : now - lastTimeRef.current;
      lastTimeRef.current = now;

      // Advance sweep
      sweepRef.current = (sweepRef.current + (2 * Math.PI * dt) / SWEEP_RPM_MS) % (2 * Math.PI);

      // Evict expired blips
      blipsRef.current = blipsRef.current.filter((b) => now - b.born < BLIP_TTL_MS);

      // ── Clear ─────────────────────────────────────────────────────────────
      ctx!.clearRect(0, 0, size, size);

      // ── Clip to circle ────────────────────────────────────────────────────
      ctx!.save();
      ctx!.beginPath();
      ctx!.arc(cx, cy, radius, 0, 2 * Math.PI);
      ctx!.clip();

      // Background
      ctx!.fillStyle = COLORS.bg;
      ctx!.fillRect(0, 0, size, size);

      // Grid lines (N / E / S / W)
      for (let i = 0; i < 4; i++) {
        const a = (i * Math.PI) / 2;
        ctx!.beginPath();
        ctx!.moveTo(cx, cy);
        ctx!.lineTo(cx + radius * Math.cos(a), cy + radius * Math.sin(a));
        ctx!.strokeStyle = COLORS.grid;
        ctx!.lineWidth   = 1;
        ctx!.stroke();
      }

      // Concentric rings at 1 m, 3 m, 5 m (= full radius)
      for (const dist of [1, 3, 5]) {
        const r = (dist / MAX_DIST_M) * radius;
        ctx!.beginPath();
        ctx!.arc(cx, cy, r, 0, 2 * Math.PI);
        ctx!.strokeStyle = COLORS.ring;
        ctx!.lineWidth   = 1;
        ctx!.stroke();
      }

      // Distance labels
      ctx!.fillStyle   = COLORS.label;
      ctx!.font        = "9px monospace";
      ctx!.textAlign   = "left";
      ctx!.textBaseline = "middle";
      for (const [dist, label] of [[1, "1m"], [3, "3m"], [5, "5m"]] as const) {
        const r = (dist / MAX_DIST_M) * radius;
        ctx!.fillText(label, cx + 3, cy - r + 2);
      }

      // Cardinal labels
      ctx!.font         = "10px monospace";
      ctx!.textAlign    = "center";
      ctx!.textBaseline = "middle";
      ctx!.fillStyle    = COLORS.label;
      const cardinals: [string, number, number][] = [
        ["N",  0,            -(radius - 12)],
        ["E",  radius - 12,  0             ],
        ["S",  0,             radius - 12  ],
        ["W", -(radius - 12), 0            ],
      ];
      for (const [lbl, dx, dy] of cardinals) {
        ctx!.fillText(lbl, cx + dx, cy + dy);
      }

      // ── Sweep trail ───────────────────────────────────────────────────────
      const sweep = sweepRef.current;
      for (let i = 0; i < TRAIL_STEPS; i++) {
        const t      = i / TRAIL_STEPS;
        const startA = sweep - TRAIL_ARC + t * TRAIL_ARC;
        const endA   = sweep - TRAIL_ARC + (t + 1) * TRAIL_ARC;
        ctx!.beginPath();
        ctx!.moveTo(cx, cy);
        ctx!.arc(cx, cy, radius, startA, endA);
        ctx!.closePath();
        ctx!.fillStyle = `rgba(34,197,94,${(t * 0.22).toFixed(3)})`;
        ctx!.fill();
      }

      // Sweep line
      ctx!.beginPath();
      ctx!.moveTo(cx, cy);
      ctx!.lineTo(cx + radius * Math.cos(sweep), cy + radius * Math.sin(sweep));
      ctx!.strokeStyle = "rgba(34,197,94,0.9)";
      ctx!.lineWidth   = 2;
      ctx!.stroke();

      ctx!.restore(); // remove circle clip

      // ── Outer border ──────────────────────────────────────────────────────
      ctx!.beginPath();
      ctx!.arc(cx, cy, radius, 0, 2 * Math.PI);
      ctx!.strokeStyle = COLORS.border;
      ctx!.lineWidth   = 2;
      ctx!.stroke();

      // ── Blips ─────────────────────────────────────────────────────────────
      for (const { alert, born } of blipsRef.current) {
        const age     = now - born;
        const opacity = Math.max(0, 1 - age / BLIP_TTL_MS);
        if (opacity <= 0) continue;

        const { x, y } = polarToXY(
          alert.direction_of_arrival,
          alert.distance_estimation,
          radius,
          cx,
          cy,
        );
        const color = PRIORITY_COLOR[alert.priority];

        // Outer glow
        ctx!.save();
        ctx!.globalAlpha = opacity * 0.35;
        ctx!.beginPath();
        ctx!.arc(x, y, 11, 0, 2 * Math.PI);
        ctx!.fillStyle = color;
        ctx!.fill();
        ctx!.restore();

        // Core dot
        ctx!.save();
        ctx!.globalAlpha = opacity;
        ctx!.beginPath();
        ctx!.arc(x, y, 5, 0, 2 * Math.PI);
        ctx!.fillStyle = color;
        ctx!.fill();
        ctx!.restore();

        // Label (sound class, direction)
        if (opacity > 0.4) {
          const label = `${alert.sound_class.replace("_", " ")} ${alert.direction_of_arrival.toFixed(0)}°`;
          ctx!.save();
          ctx!.globalAlpha  = opacity;
          ctx!.font         = "9px monospace";
          ctx!.fillStyle    = color;
          ctx!.textAlign    = "center";
          ctx!.textBaseline = "bottom";
          ctx!.fillText(label, x, y - 8);
          ctx!.restore();
        }
      }

      rafRef.current = requestAnimationFrame(draw);
    }

    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [size]);

  return (
    <canvas
      ref={canvasRef}
      className="rounded-full"
      style={{ imageRendering: "pixelated" }}
    />
  );
}
