
export type StatusType = "running" | "completed" | "error" | "cancelled" | "idle" | "active";

export interface StatusBadgeProps {
  status: StatusType | string;
  label?: string;
  className?: string;
}

export function StatusBadge({ status, label, className = "" }: StatusBadgeProps) {
  const norm = status.toLowerCase();

  const styles: Record<
    string,
    { dot: string; text: string; bg: string; border: string; defaultLabel: string }
  > = {
    running: {
      dot: "bg-amber-400 animate-pulse",
      text: "text-amber-300",
      bg: "bg-amber-950/40",
      border: "border-amber-800/60",
      defaultLabel: "Running",
    },
    completed: {
      dot: "bg-emerald-400",
      text: "text-emerald-300",
      bg: "bg-emerald-950/40",
      border: "border-emerald-800/60",
      defaultLabel: "Completed",
    },
    active: {
      dot: "bg-emerald-400",
      text: "text-emerald-300",
      bg: "bg-emerald-950/40",
      border: "border-emerald-800/60",
      defaultLabel: "Active",
    },
    error: {
      dot: "bg-red-400",
      text: "text-red-300",
      bg: "bg-red-950/40",
      border: "border-red-800/60",
      defaultLabel: "Failed",
    },
    cancelled: {
      dot: "bg-studio-400",
      text: "text-studio-400",
      bg: "bg-studio-800/40",
      border: "border-studio-700/60",
      defaultLabel: "Cancelled",
    },
    idle: {
      dot: "bg-studio-500",
      text: "text-studio-400",
      bg: "bg-studio-850",
      border: "border-studio-700/60",
      defaultLabel: "Idle",
    },
  };

  const current = styles[norm] || styles.idle;
  const displayLabel = label || current.defaultLabel;

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-2xs font-mono select-none border ${current.bg} ${current.border} ${current.text} ${className}`}
    >
      <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${current.dot}`} />
      <span>{displayLabel}</span>
    </span>
  );
}
