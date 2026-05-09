type Status = "listening" | "detected" | "error";

const STATUS_LABEL: Record<Status, string> = {
  listening: "Listening",
  detected:  "Detected",
  error:     "Pipeline error",
};

// Pill background / text combinations per status
const STATUS_PILL: Record<Status, string> = {
  listening: "bg-[#f7f7f7] text-[#6a6a6a] border border-[#dddddd]",
  detected:  "bg-[#ff385c] text-white border border-[#ff385c]",
  error:     "bg-red-50 text-red-600 border border-red-200",
};

const STATUS_DOT: Record<Status, string> = {
  listening: "bg-[#6a6a6a]",
  detected:  "bg-white animate-pulse",
  error:     "bg-red-500",
};

interface Props {
  status: Status;
  sessionCount: number;
}

export default function HeaderBar({ status, sessionCount }: Props) {
  return (
    <header className="flex items-center px-6 py-0 h-16 border-b border-[#dddddd] bg-white shrink-0">
      {/* Left — wordmark */}
      <div className="flex items-center gap-1.5">
        {/* Rausch orb — brand moment */}
        <span className="w-7 h-7 rounded-full bg-[#ff385c] flex items-center justify-center shrink-0">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M3 18v-6a9 9 0 0 1 18 0v6" />
            <path d="M21 19a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2v-3a2 2 0 0 1 2-2h3zM3 19a2 2 0 0 0 2 2h1a2 2 0 0 0 2-2v-3a2 2 0 0 0-2-2H3z" />
          </svg>
        </span>
        <span className="font-semibold text-[#222222] text-[15px] tracking-tight">SELD</span>
        <span className="font-normal text-[#6a6a6a] text-[15px]">Monitor</span>
      </div>

      {/* Centre — status pill */}
      <div className="mx-auto">
        <span className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-[13px] font-medium ${STATUS_PILL[status]}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[status]}`} />
          {STATUS_LABEL[status]}
        </span>
      </div>

      {/* Right — session counter */}
      <span className="text-[13px] text-[#6a6a6a] tabular-nums">
        {sessionCount} alert{sessionCount !== 1 ? "s" : ""}
      </span>
    </header>
  );
}
