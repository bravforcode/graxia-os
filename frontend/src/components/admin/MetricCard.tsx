import { cn } from "@/lib/utils";

interface MetricCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  status?: "up" | "down" | "neutral" | "warning" | "critical";
  className?: string;
}

const statusColors: Record<string, { border: string; dot: string }> = {
  up:       { border: "border-emerald-500/30", dot: "bg-emerald-400" },
  down:     { border: "border-red-500/30",     dot: "bg-red-400" },
  neutral:  { border: "border-zinc-700",       dot: "bg-zinc-400" },
  warning:  { border: "border-amber-500/30",   dot: "bg-amber-400" },
  critical: { border: "border-red-500/50",     dot: "bg-red-400" },
};

export function MetricCard({ title, value, subtitle, status, className }: MetricCardProps) {
  const colors = statusColors[status || "neutral"];
  return (
    <div className={cn(
      "rounded-xl border bg-zinc-900/60 p-4 backdrop-blur-sm transition-colors hover:bg-zinc-900/80",
      colors.border,
      className
    )}>
      <div className="flex items-center justify-between mb-1">
        <span className="text-xs font-medium text-zinc-400 uppercase tracking-wider">{title}</span>
        {status && <span className={cn("h-2 w-2 rounded-full", colors.dot)} />}
      </div>
      <div className="text-2xl font-semibold text-white tracking-tight">{value}</div>
      {subtitle && <div className="mt-1 text-xs text-zinc-500">{subtitle}</div>}
    </div>
  );
}
