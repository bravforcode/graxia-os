import { cn } from "@/lib/utils";
import { StatusBadge } from "./StatusBadge";

interface Step {
  step_id: string;
  step_name: string;
  status: string;
  started_at: string | null;
  completed_at: string | null;
  tool_name: string | null;
  tool_result_summary: string | null;
  error_code: string | null;
  input_refs?: string[];
  output_refs?: string[];
  metadata?: Record<string, unknown>;
}

export function WorkflowRunTimeline({ steps }: { steps: Step[] }) {
  if (!steps || steps.length === 0) {
    return <div className="text-sm text-zinc-500 py-4">No steps recorded.</div>;
  }

  return (
    <div className="space-y-0">
      {steps.map((step, i) => (
        <div key={step.step_id} className="relative flex gap-4 pb-6 last:pb-0">
          {/* Vertical line */}
          {i < steps.length - 1 && (
            <div className="absolute left-[11px] top-6 bottom-0 w-px bg-zinc-800" />
          )}

          {/* Dot */}
          <div className="relative flex-shrink-0 mt-1.5">
            <div className={cn(
              "h-3 w-3 rounded-full border-2",
              step.status === "completed" ? "border-emerald-500 bg-emerald-500/20" :
              step.status === "failed" ? "border-red-500 bg-red-500/20" :
              step.status === "running" ? "border-blue-500 bg-blue-500/20 animate-pulse" :
              step.status === "skipped" ? "border-zinc-600 bg-zinc-600/20" :
              "border-zinc-600 bg-zinc-800"
            )} />
          </div>

          {/* Content */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-sm font-medium text-white">{step.step_name}</span>
              <StatusBadge status={step.status} />
            </div>

            {step.tool_name && (
              <div className="text-xs text-zinc-500 mb-1">
                Tool: <span className="font-mono text-zinc-400">{step.tool_name}</span>
              </div>
            )}

            {step.tool_result_summary && (
              <div className="text-xs text-zinc-400 bg-zinc-800/50 rounded px-2 py-1 mt-1">
                {step.tool_result_summary}
              </div>
            )}

            {step.error_code && (
              <div className="text-xs text-red-400 bg-red-500/10 rounded px-2 py-1 mt-1">
                [{step.error_code}] {String(step.metadata?.error ?? '') || step.tool_result_summary}
              </div>
            )}

            {step.started_at && (
              <div className="text-[10px] text-zinc-600 mt-1">
                {step.started_at}
                {step.completed_at && ` → ${step.completed_at}`}
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}
