/**
 * Dashboard Helper Components
 * Shared UI components for dashboard views
 */

import type { LucideIcon } from "lucide-react";
import { ChevronRight } from "lucide-react";
import { cn } from "../../lib/utils";

// Card component (local definition for dashboard helpers)
function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "bg-slate-900/50 border border-slate-800 rounded-xl",
        className,
      )}
    >
      {children}
    </div>
  );
}

export function AgentStatusCard({
  name,
  role,
  status,
  tasks,
}: {
  name: string;
  role: string;
  status: string;
  tasks: number;
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-4">
        <div
          className={cn(
            "w-10 h-10 rounded-full flex items-center justify-center",
            status === "active"
              ? "bg-emerald-500/20 text-emerald-400"
              : "bg-slate-700/50 text-slate-400",
          )}
        >
          <span className="text-lg">{status === "active" ? "●" : "○"}</span>
        </div>
        <div className="flex-1">
          <h4 className="font-medium text-slate-200">{name}</h4>
          <p className="text-sm text-slate-500">{role}</p>
        </div>
        <div className="text-right">
          <span
            className={cn(
              "text-sm font-medium",
              status === "active" ? "text-emerald-400" : "text-slate-400",
            )}
          >
            {status === "active" ? "ทำงาน" : "หยุด"}
          </span>
          <p className="text-xs text-slate-500 mt-1">{tasks} งาน</p>
        </div>
      </div>
    </Card>
  );
}

export function QuickAction({
  icon: Icon,
  label,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-3 p-3 bg-slate-800/50 hover:bg-slate-700/50 border border-slate-700/50 rounded-lg transition-colors text-left"
    >
      <Icon className="w-4 h-4 text-slate-400" />
      <span className="text-sm text-slate-300">{label}</span>
      <ChevronRight className="w-4 h-4 text-slate-500 ml-auto" />
    </button>
  );
}

export function SystemHealthItem({
  label,
  status,
  value,
}: {
  label: string;
  status: "good" | "warning" | "error";
  value: string;
}) {
  return (
    <div className="flex items-center justify-between py-2">
      <span className="text-sm text-slate-400">{label}</span>
      <div className="flex items-center gap-2">
        <span
          className={cn(
            "w-2 h-2 rounded-full",
            status === "good"
              ? "bg-emerald-500"
              : status === "warning"
                ? "bg-amber-500"
                : "bg-rose-500",
          )}
        />
        <span className="text-sm text-slate-300">{value}</span>
      </div>
    </div>
  );
}
