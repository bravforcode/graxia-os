import { FileText, AlertTriangle, CheckCircle } from "lucide-react";
import { cn } from "@/lib/utils";

interface ContextPackData {
  context_pack_id?: string;
  task_type?: string;
  goal?: string;
  token_budget?: number;
  estimated_tokens?: number;
  included_files?: { path: string; size: number; estimated_tokens: number }[];
  warnings?: string[];
  excluded_file_count?: number;
  secret_safety_status?: string;
}

export function ContextPackSummary({ contextPack }: { contextPack: ContextPackData | null }) {
  if (!contextPack) {
    return <div className="text-sm text-zinc-500">No context pack data.</div>;
  }

  const files = contextPack.included_files || [];
  const warnings = contextPack.warnings || [];
  const tokenRatio = contextPack.token_budget && contextPack.estimated_tokens
    ? Math.round((contextPack.estimated_tokens / contextPack.token_budget) * 100)
    : 0;

  return (
    <div className="space-y-3">
      {/* Token gauge */}
      <div className="flex items-center gap-4">
        <div className="flex-1">
          <div className="flex justify-between text-xs text-zinc-400 mb-1">
            <span>Token usage</span>
            <span>{contextPack.estimated_tokens ?? "?"} / {contextPack.token_budget ?? "?"}</span>
          </div>
          <div className="h-2 rounded-full bg-zinc-800 overflow-hidden">
            <div
              className={cn(
                "h-full rounded-full transition-all",
                tokenRatio > 90 ? "bg-red-500" : tokenRatio > 70 ? "bg-amber-500" : "bg-emerald-500"
              )}
              style={{ width: `${Math.min(tokenRatio, 100)}%` }}
            />
          </div>
        </div>
        <span className={cn(
          "text-xs font-medium",
          tokenRatio > 90 ? "text-red-400" : tokenRatio > 70 ? "text-amber-400" : "text-emerald-400"
        )}>
          {tokenRatio}%
        </span>
      </div>

      {/* Metadata */}
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div className="text-zinc-500">Task type</div>
        <div className="text-zinc-300 font-mono">{contextPack.task_type || "-"}</div>
        <div className="text-zinc-500">Goal</div>
        <div className="text-zinc-300">{contextPack.goal || "-"}</div>
        <div className="text-zinc-500">Files included</div>
        <div className="text-zinc-300">{files.length}</div>
        <div className="text-zinc-500">Files excluded</div>
        <div className="text-zinc-300">{contextPack.excluded_file_count ?? 0}</div>
        <div className="text-zinc-500">Secret safety</div>
        <div className="text-zinc-300">
          <span className={cn(
            "inline-flex items-center gap-1",
            contextPack.secret_safety_status === "safe" ? "text-emerald-400" : "text-amber-400"
          )}>
            {contextPack.secret_safety_status === "safe" ? (
              <CheckCircle className="h-3 w-3" />
            ) : (
              <AlertTriangle className="h-3 w-3" />
            )}
            {contextPack.secret_safety_status || "unknown"}
          </span>
        </div>
      </div>

      {/* Files */}
      {files.length > 0 && (
        <div>
          <div className="text-xs font-medium text-zinc-400 mb-2 flex items-center gap-1">
            <FileText className="h-3 w-3" /> Included files
          </div>
          <div className="space-y-1 max-h-40 overflow-y-auto">
            {files.map((f, i) => (
              <div key={i} className="flex justify-between text-xs text-zinc-500 bg-zinc-800/30 rounded px-2 py-1">
                <span className="font-mono truncate">{f.path}</span>
                <span className="text-zinc-600 flex-shrink-0 ml-2">~{f.estimated_tokens}t</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Warnings */}
      {warnings.length > 0 && (
        <div>
          <div className="text-xs font-medium text-amber-400 mb-1 flex items-center gap-1">
            <AlertTriangle className="h-3 w-3" /> Warnings
          </div>
          <div className="space-y-1">
            {warnings.map((w, i) => (
              <div key={i} className="text-xs text-amber-400/80 bg-amber-500/5 rounded px-2 py-1">
                {w}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
