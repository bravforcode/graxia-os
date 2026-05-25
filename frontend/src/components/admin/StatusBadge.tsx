import { cn } from "@/lib/utils";

type StatusType =
  | "ready" | "not_ready"
  | "pass" | "fail"
  | "pending" | "running"
  | "completed" | "blocked"
  | "approval_required" | "mock"
  | "skipped"
  | "live" | "offline"
  | string;

const statusConfig: Record<string, { bg: string; text: string; dot: string; label: string }> = {
  ready:             { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400", label: "Ready" },
  not_ready:         { bg: "bg-red-500/10",     text: "text-red-400",    dot: "bg-red-400",    label: "Not Ready" },
  pass:              { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400", label: "Pass" },
  fail:              { bg: "bg-red-500/10",     text: "text-red-400",    dot: "bg-red-400",    label: "Fail" },
  pending:           { bg: "bg-amber-500/10",   text: "text-amber-400",  dot: "bg-amber-400",  label: "Pending" },
  running:           { bg: "bg-blue-500/10",    text: "text-blue-400",   dot: "bg-blue-400",   label: "Running" },
  completed:         { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400", label: "Completed" },
  blocked:           { bg: "bg-red-500/10",     text: "text-red-400",    dot: "bg-red-400",    label: "Blocked" },
  approval_required: { bg: "bg-violet-500/10",  text: "text-violet-400", dot: "bg-violet-400", label: "Approval Required" },
  mock:              { bg: "bg-cyan-500/10",    text: "text-cyan-400",   dot: "bg-cyan-400",   label: "Mock" },
  skipped:           { bg: "bg-zinc-500/10",    text: "text-zinc-400",   dot: "bg-zinc-400",   label: "Skipped" },
  live:              { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400", label: "Live" },
  offline:           { bg: "bg-zinc-500/10",    text: "text-zinc-400",   dot: "bg-zinc-400",   label: "Offline" },
  approved:          { bg: "bg-emerald-500/10", text: "text-emerald-400", dot: "bg-emerald-400", label: "Approved" },
  rejected:          { bg: "bg-red-500/10",     text: "text-red-400",    dot: "bg-red-400",    label: "Rejected" },
};

export function StatusBadge({ status, pulse }: { status: StatusType; pulse?: boolean }) {
  const config = statusConfig[status] || { bg: "bg-zinc-500/10", text: "text-zinc-400", dot: "bg-zinc-400", label: status };
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium", config.bg, config.text)}>
      <span className={cn("h-1.5 w-1.5 rounded-full", config.dot, pulse && "animate-pulse")} />
      {config.label}
    </span>
  );
}

export function IndicatorDot({ status, pulse }: { status: StatusType; pulse?: boolean }) {
  const config = statusConfig[status] || { dot: "bg-zinc-400" };
  return <span className={cn("inline-block h-2 w-2 rounded-full", config.dot, pulse && "animate-pulse")} />;
}
