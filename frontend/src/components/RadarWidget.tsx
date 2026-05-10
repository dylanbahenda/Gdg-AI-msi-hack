import { useEffect, useRef } from "react";
import { Priority, SoundClass } from "../types/contracts";
import { SOUND_IMAGE } from "../utils/soundMeta";

const MIN_R_FRAC = 0.35;  // inner band boundary (fraction of radar radius)
const MAX_R_FRAC = 0.82;  // outer band boundary (fraction of radar radius)
const BLIP_TTL_MS = 9000;
const SWEEP_PERIOD_MS = 7200;       // one full revolution of the sweep line
const TRAIL_STEPS = 20;
const TRAIL_ARC = Math.PI / 2;

// Cosmetic stretch: incoming DOA is ±90° (front semicircle is all 2-mic
// GCC-PHAT can deliver). We multiply by this factor so the dots fill more
// of the visible disk; what's left over (≈80° around the rear) is a
// graphical placeholder that the user reads as "the back of the radar".
const STRETCH_FACTOR = 70 / 45;

const COLORS = {
  bg: "#ffffff",
  ring: "#e5e7eb",
  grid: "#d1d5db",
  border: "#cbd5e1",
  label: "#64748b",
  sweep: "#0ea5e9",
  text: "#111827",
  muted: "#64748b",
  callout: "rgba(255,255,255,0.92)",
  priorityHigh: "#ff385c",
  priorityMedium: "#f97316",
  priorityLow: "#16a34a",
} as const;

const PRIORITY_COLOR: Record<Priority, string> = {
  high: COLORS.priorityHigh,
  medium: COLORS.priorityMedium,
  low: COLORS.priorityLow,
};

export interface RadarDetection {
  id: string;
  timestamp: number;
  sound_class: SoundClass;
  direction_of_arrival: number;
  distance_estimation: number;
  sed_confidence: number;
  priority?: Priority;
  message?: string;
}

interface Blip {
  detection: RadarDetection;
  born: number;
  randomR: number; // fraction of radar radius, randomised at spawn
}

interface Props {
  detections: RadarDetection[];
  size?: number;
  avatarSrc?: string;
}

function stretchDeg(measuredDeg: number): number {
  return measuredDeg * STRETCH_FACTOR;
}

function polarToXY(
  displayDeg: number,
  rFrac: number,
  radiusPx: number,
  cx: number,
  cy: number,
) {
  const r = rFrac * radiusPx;
  // 0° = top (front), +90° = right, -90° = left, ±180° = back.
  const rad = ((displayDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

export default function RadarWidget({ detections, size = 320, avatarSrc }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const blipsRef = useRef<Blip[]>([]);
  const seenRef = useRef<Set<string>>(new Set());
  const sweepRef = useRef(0);
  const lastTimeRef = useRef<number | null>(null);
  const rafRef = useRef<number>(0);
  const avatarImgRef = useRef<HTMLImageElement | null>(null);
  const ringFallbackImgRef = useRef<HTMLImageElement | null>(null);
  const soundImgCacheRef = useRef<Map<SoundClass, HTMLImageElement>>(new Map());

  // Preload all sound class images once
  useEffect(() => {
    const cache = soundImgCacheRef.current;
    for (const [sc, src] of Object.entries(SOUND_IMAGE) as [SoundClass, string | null][]) {
      if (!src) continue;
      const img = new window.Image();
      img.src = src;
      img.onload = () => { cache.set(sc, img); };
    }
  }, []);

  // Load avatar image into a ref so the draw loop can use it without re-mounting
  useEffect(() => {
    if (!avatarSrc) { avatarImgRef.current = null; return; }
    const img = new window.Image();
    img.src = avatarSrc;
    img.onload = () => { avatarImgRef.current = img; };
  }, [avatarSrc]);

  // Load ring fallback image for events without a specific image
  useEffect(() => {
    const img = new window.Image();
    img.src = "/img/ring.jpg";
    img.onload = () => { ringFallbackImgRef.current = img; };
  }, []);

  useEffect(() => {
    for (const detection of detections) {
      if (seenRef.current.has(detection.id)) {
        blipsRef.current = blipsRef.current.map((blip: Blip) =>
          blip.detection.id === detection.id ? { ...blip, detection } : blip,
        );
        continue;
      }
      seenRef.current.add(detection.id);
      const randomR = MIN_R_FRAC + Math.random() * (MAX_R_FRAC - MIN_R_FRAC);
      blipsRef.current.push({ detection, born: performance.now(), randomR });
    }
  }, [detections]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const drawCtx = ctx;

    const dpr = window.devicePixelRatio ?? 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    const cx = size / 2;
    const cy = size / 2;
    const radius = size / 2 - 18;
    const TWO_PI = Math.PI * 2;

    function draw(now: number) {
      const ctx = drawCtx;
      const dt = lastTimeRef.current == null ? 0 : now - lastTimeRef.current;
      lastTimeRef.current = now;
      sweepRef.current = (sweepRef.current + (TWO_PI * dt) / SWEEP_PERIOD_MS) % TWO_PI;
      blipsRef.current = blipsRef.current.filter((b: Blip) => now - b.born < BLIP_TTL_MS);

      ctx.clearRect(0, 0, size, size);

      // Full disk background
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, TWO_PI);
      ctx.fillStyle = COLORS.bg;
      ctx.fill();

      // Clip everything to the disk for clean edges
      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, TWO_PI);
      ctx.clip();

      // 4 cardinal radials (full diameters through centre)
      ctx.beginPath();
      ctx.moveTo(cx - radius, cy);
      ctx.lineTo(cx + radius, cy);
      ctx.moveTo(cx, cy - radius);
      ctx.lineTo(cx, cy + radius);
      ctx.strokeStyle = COLORS.grid;
      ctx.lineWidth = 1;
      ctx.stroke();

      // 4 diagonals (45° spokes in all four quadrants)
      const d45 = radius * Math.cos(Math.PI / 4);
      ctx.beginPath();
      ctx.moveTo(cx - d45, cy - d45);
      ctx.lineTo(cx + d45, cy + d45);
      ctx.moveTo(cx - d45, cy + d45);
      ctx.lineTo(cx + d45, cy - d45);
      ctx.strokeStyle = COLORS.grid;
      ctx.lineWidth = 1;
      ctx.stroke();

      // Concentric range rings
      for (const frac of [MIN_R_FRAC, MAX_R_FRAC]) {
        const r = frac * radius;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, TWO_PI);
        ctx.strokeStyle = COLORS.ring;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      // Sweep trail — full revolution
      const sweep = sweepRef.current;
      for (let i = 0; i < TRAIL_STEPS; i++) {
        const t = i / TRAIL_STEPS;
        const startA = sweep - TRAIL_ARC + t * TRAIL_ARC;
        const endA = sweep - TRAIL_ARC + (t + 1) * TRAIL_ARC;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.arc(cx, cy, radius, startA, endA);
        ctx.closePath();
        ctx.fillStyle = `rgba(14,165,233,${(t * 0.1).toFixed(3)})`;
        ctx.fill();
      }

      // Sweep line
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + radius * Math.cos(sweep), cy + radius * Math.sin(sweep));
      ctx.strokeStyle = "rgba(14,165,233,0.72)";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.restore();

      // Outer ring border
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, TWO_PI);
      ctx.strokeStyle = COLORS.border;
      ctx.lineWidth = 2;
      ctx.stroke();

      // Cardinal labels — placed just inside the rim so they read on a normal radar.
      ctx.fillStyle = COLORS.label;
      ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("FRONT", cx, cy - radius + 12);
      ctx.fillText("BACK",  cx, cy + radius - 12);
      ctx.fillText("R",     cx + radius - 14, cy);
      ctx.fillText("L",     cx - radius + 14, cy);

      // ── Avatar at center (below blips) ────────────────────────
      const avatarImg = avatarImgRef.current;
      if (avatarImg) {
        const r = 32;
        ctx.save();
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, TWO_PI);
        ctx.clip();
        ctx.drawImage(avatarImg, cx - r, cy - r, r * 2, r * 2);
        ctx.restore();
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, TWO_PI);
        ctx.strokeStyle = "rgba(255,255,255,0.95)";
        ctx.lineWidth = 3;
        ctx.stroke();
      }

      for (const { detection, born, randomR } of blipsRef.current) {
        const age = now - born;
        const opacity = Math.max(0, 1 - age / BLIP_TTL_MS);
        if (opacity <= 0) continue;

        const { x, y } = polarToXY(
          stretchDeg(detection.direction_of_arrival),
          randomR,
          radius,
          cx,
          cy,
        );
        const color = detection.priority ? PRIORITY_COLOR[detection.priority] : COLORS.sweep;

        ctx.save();
        ctx.globalAlpha = opacity * 0.22;
        ctx.beginPath();
        ctx.arc(x, y, 18, 0, TWO_PI);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.restore();

        const soundImg = soundImgCacheRef.current.get(detection.sound_class);
        const blipR = soundImg ? 13 : 9;
        if (soundImg) {
          ctx.save();
          ctx.globalAlpha = opacity;
          ctx.beginPath();
          ctx.arc(x, y, blipR, 0, TWO_PI);
          ctx.clip();
          ctx.drawImage(soundImg, x - blipR, y - blipR, blipR * 2, blipR * 2);
          ctx.restore();
        } else {
          const fallbackImg = ringFallbackImgRef.current;
          ctx.save();
          ctx.globalAlpha = opacity;
          ctx.beginPath();
          ctx.arc(x, y, blipR, 0, TWO_PI);
          ctx.clip();
          if (fallbackImg) {
            ctx.drawImage(fallbackImg, x - blipR, y - blipR, blipR * 2, blipR * 2);
          } else {
            ctx.fillStyle = "#ffffff";
            ctx.fill();
          }
          ctx.restore();
        }
        ctx.save();
        ctx.globalAlpha = opacity;
        ctx.beginPath();
        ctx.arc(x, y, blipR, 0, TWO_PI);
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.stroke();
        ctx.restore();
      }

      rafRef.current = requestAnimationFrame(draw);
    }

    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [size]);

  return (
    <canvas
      ref={canvasRef}
      style={{ imageRendering: "auto" }}
    />
  );
}
