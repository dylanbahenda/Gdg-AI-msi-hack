import { AlertNotification, Priority } from "../types/contracts";
import { soundEmoji } from "../utils/soundMeta";

const PRIORITY_HEX: Record<Priority, string> = {
  high:   "#ff385c",
  medium: "#f97316",
  low:    "#16a34a",
};

function formatTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString("en-GB", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

interface Props {
  alert: AlertNotification | null;
}

export default function LastAlertBar({ alert }: Props) {
  if (!alert) {
    return (
      <footer className="border-t border-[#ebebeb] bg-white px-6 py-3 shrink-0">
        <span className="text-[13px] text-[#6a6a6a] italic">No detections yet this session</span>
      </footer>
    );
  }

  const hex = PRIORITY_HEX[alert.priority];

  return (
    <footer
      className="border-t border-[#ebebeb] bg-white px-6 py-3 shrink-0"
      style={{ borderLeft: `4px solid ${hex}` }}
    >
      <div className="flex items-center gap-2">
        <span
          className="text-[12px] font-bold uppercase tracking-wide"
          style={{ color: hex }}
        >
          ● {alert.priority}
        </span>
        <span className="text-[16px] leading-none" aria-hidden="true">{soundEmoji(alert.sound_class)}</span>
        <span className="text-[13px] text-[#3f3f3f] truncate">{alert.message}</span>
        <span className="text-[12px] text-[#6a6a6a] font-mono ml-auto shrink-0">· {formatTime(alert.timestamp)}</span>
      </div>
    </footer>
  );
}
