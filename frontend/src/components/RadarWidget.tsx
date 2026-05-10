import { useEffect, useRef } from "react";
import { Priority, SoundClass } from "../types/contracts";
import { soundEmoji, soundLabel } from "../utils/soundMeta";

const MAX_DIST_M = 5;
const BLIP_TTL_MS = 9000;
const SWEEP_RPM_MS = 3600;
const TRAIL_STEPS = 20;
const TRAIL_ARC = Math.PI / 2;

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
}

interface Props {
  detections: RadarDetection[];
  size?: number;
}

function polarToXY(
  dirDeg: number,
  distM: number,
  radiusPx: number,
  cx: number,
  cy: number,
) {
  const r = Math.min(distM / MAX_DIST_M, 1) * radiusPx;
  const rad = ((dirDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function roundedRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  const radius = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + radius, y);
  ctx.arcTo(x + w, y, x + w, y + h, radius);
  ctx.arcTo(x + w, y + h, x, y + h, radius);
  ctx.arcTo(x, y + h, x, y, radius);
  ctx.arcTo(x, y, x + w, y, radius);
  ctx.closePath();
}

function truncateText(
  ctx: CanvasRenderingContext2D,
  text: string,
  maxWidth: number,
) {
  if (ctx.measureText(text).width <= maxWidth) return text;
  let out = text;
  while (out.length > 3 && ctx.measureText(`${out}...`).width > maxWidth) {
    out = out.slice(0, -1);
  }
  return `${out}...`;
}

function drawCallout(
  ctx: CanvasRenderingContext2D,
  detection: RadarDetection,
  x: number,
  y: number,
  opacity: number,
  color: string,
  size: number,
) {
  const emoji = soundEmoji(detection.sound_class);
  const title = detection.message ?? soundLabel(detection.sound_class);
  const meta = `${detection.direction_of_arrival.toFixed(0)}° · ${detection.distance_estimation.toFixed(1)}m`;
  const boxW = Math.min(190, size - 34);
  const boxH = 50;
  const left = Math.max(12, Math.min(size - boxW - 12, x + 12));
  const top = Math.max(12, Math.min(size - boxH - 12, y - boxH - 10));

  ctx.save();
  ctx.globalAlpha = opacity;

  roundedRect(ctx, left, top, boxW, boxH, 8);
  ctx.fillStyle = COLORS.callout;
  ctx.fill();
  ctx.lineWidth = 1;
  ctx.strokeStyle = color;
  ctx.stroke();

  ctx.font = "20px system-ui, Apple Color Emoji, Segoe UI Emoji";
  ctx.textAlign = "left";
  ctx.textBaseline = "middle";
  ctx.fillText(emoji, left + 10, top + 25);

  ctx.font = "600 11px Inter, system-ui, sans-serif";
  ctx.fillStyle = COLORS.text;
  ctx.fillText(truncateText(ctx, title, boxW - 48), left + 38, top + 20);

  ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
  ctx.fillStyle = COLORS.muted;
  ctx.fillText(meta, left + 38, top + 34);

  ctx.restore();
}

export default function RadarWidget({ detections, size = 320 }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const blipsRef = useRef<Blip[]>([]);
  const seenRef = useRef<Set<string>>(new Set());
  const sweepRef = useRef(0);
  const lastTimeRef = useRef<number | null>(null);
  const rafRef = useRef<number>(0);

  useEffect(() => {
    for (const detection of detections) {
      if (seenRef.current.has(detection.id)) {
        blipsRef.current = blipsRef.current.map((blip) =>
          blip.detection.id === detection.id ? { ...blip, detection } : blip,
        );
        continue;
      }
      seenRef.current.add(detection.id);
      blipsRef.current.push({ detection, born: performance.now() });
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

    function draw(now: number) {
      const ctx = drawCtx;
      const dt = lastTimeRef.current == null ? 0 : now - lastTimeRef.current;
      lastTimeRef.current = now;
      sweepRef.current = (sweepRef.current + (2 * Math.PI * dt) / SWEEP_RPM_MS) % (2 * Math.PI);
      blipsRef.current = blipsRef.current.filter((b) => now - b.born < BLIP_TTL_MS);

      ctx.clearRect(0, 0, size, size);
      ctx.fillStyle = COLORS.bg;
      ctx.fillRect(0, 0, size, size);

      ctx.save();
      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
      ctx.clip();

      for (let i = 0; i < 4; i++) {
        const a = (i * Math.PI) / 2;
        ctx.beginPath();
        ctx.moveTo(cx, cy);
        ctx.lineTo(cx + radius * Math.cos(a), cy + radius * Math.sin(a));
        ctx.strokeStyle = COLORS.grid;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

      for (const dist of [1, 3, 5]) {
        const r = (dist / MAX_DIST_M) * radius;
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, 2 * Math.PI);
        ctx.strokeStyle = COLORS.ring;
        ctx.lineWidth = 1;
        ctx.stroke();
      }

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

      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + radius * Math.cos(sweep), cy + radius * Math.sin(sweep));
      ctx.strokeStyle = "rgba(14,165,233,0.72)";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.restore();

      ctx.beginPath();
      ctx.arc(cx, cy, radius, 0, 2 * Math.PI);
      ctx.strokeStyle = COLORS.border;
      ctx.lineWidth = 2;
      ctx.stroke();

      ctx.fillStyle = COLORS.label;
      ctx.font = "10px ui-monospace, SFMono-Regular, Menlo, monospace";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText("FRONT", cx, cy - radius + 14);
      ctx.fillText("R", cx + radius - 14, cy);
      ctx.fillText("L", cx - radius + 14, cy);
      ctx.fillText("BACK", cx, cy + radius - 14);

      for (const { detection, born } of blipsRef.current) {
        const age = now - born;
        const opacity = Math.max(0, 1 - age / BLIP_TTL_MS);
        if (opacity <= 0) continue;

        const { x, y } = polarToXY(
          detection.direction_of_arrival,
          detection.distance_estimation,
          radius,
          cx,
          cy,
        );
        const color = detection.priority ? PRIORITY_COLOR[detection.priority] : COLORS.sweep;

        ctx.save();
        ctx.globalAlpha = opacity * 0.22;
        ctx.beginPath();
        ctx.arc(x, y, 18, 0, 2 * Math.PI);
        ctx.fillStyle = color;
        ctx.fill();
        ctx.restore();

        ctx.save();
        ctx.globalAlpha = opacity;
        ctx.beginPath();
        ctx.arc(x, y, 9, 0, 2 * Math.PI);
        ctx.fillStyle = "#ffffff";
        ctx.fill();
        ctx.lineWidth = 2;
        ctx.strokeStyle = color;
        ctx.stroke();
        ctx.font = "18px system-ui, Apple Color Emoji, Segoe UI Emoji";
        ctx.textAlign = "center";
        ctx.textBaseline = "middle";
        ctx.fillText(soundEmoji(detection.sound_class), x, y + 0.5);
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
      className="rounded-full bg-white"
      style={{ imageRendering: "auto" }}
    />
  );
}
