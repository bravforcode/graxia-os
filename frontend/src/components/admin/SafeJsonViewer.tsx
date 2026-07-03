import { useState } from "react";
import { ChevronRight, ChevronDown, Eye, EyeOff } from "lucide-react";
import { cn } from "@/lib/utils";
import { deepRedact, isRedactedKey } from "@/lib/admin-api";

interface SafeJsonViewerProps {
  data: unknown;
  initiallyExpanded?: boolean;
  maxDepth?: number;
  className?: string;
}

export function SafeJsonViewer({ data, maxDepth = 6, className }: SafeJsonViewerProps) {
  const [showRaw, setShowRaw] = useState(false);

  const displayData = showRaw ? data : deepRedact(data);

  return (
    <div className={cn("space-y-2", className)}>
      <div className="flex items-center gap-2">
        <button
          onClick={() => setShowRaw(!showRaw)}
          className={cn(
            "flex items-center gap-1.5 rounded px-2 py-1 text-xs font-medium transition-colors",
            showRaw
              ? "bg-red-500/10 text-red-400 hover:bg-red-500/20"
              : "bg-zinc-800 text-zinc-400 hover:bg-zinc-700"
          )}
        >
          {showRaw ? <EyeOff className="h-3 w-3" /> : <Eye className="h-3 w-3" />}
          {showRaw ? "Hide secrets" : "Show raw"}
        </button>
        {showRaw && (
          <span className="text-[10px] text-red-400 font-medium">
            ⚠ Secrets may be visible
          </span>
        )}
      </div>
      <div className="rounded-lg border border-zinc-800 bg-zinc-900/50 p-3 font-mono text-xs overflow-auto max-h-96">
        <JsonNode value={displayData} depth={0} maxDepth={maxDepth} path="" />
      </div>
    </div>
  );
}

function JsonNode({ value, depth, maxDepth, path }: { value: unknown; depth: number; maxDepth: number; path: string }) {
  const [expanded, setExpanded] = useState(depth < 2);

  if (depth > maxDepth) {
    return <span className="text-zinc-500">[MAX_DEPTH]</span>;
  }

  if (value === null) return <span className="text-zinc-500">null</span>;
  if (value === undefined) return <span className="text-zinc-500">undefined</span>;

  if (typeof value === "string") {
    const isRedacted = value.includes("***REDACTED***") || value.includes("****");
    return (
      <span className={cn(isRedacted ? "text-red-400" : "text-emerald-400")}>
        "{value}"
      </span>
    );
  }

  if (typeof value === "number") return <span className="text-blue-400">{value}</span>;
  if (typeof value === "boolean") return <span className="text-amber-400">{String(value)}</span>;

  if (Array.isArray(value)) {
    if (value.length === 0) return <span className="text-zinc-500">[]</span>;
    if (!expanded) {
      return (
        <span className="cursor-pointer text-zinc-300 hover:text-white" onClick={() => setExpanded(true)}>
          <ChevronRight className="inline h-3 w-3" /> [{value.length} items]
        </span>
      );
    }
    return (
      <div>
        <span className="cursor-pointer text-zinc-400 hover:text-white" onClick={() => setExpanded(false)}>
          <ChevronDown className="inline h-3 w-3" /> [{value.length}]
        </span>
        <div className="ml-4 border-l border-zinc-800 pl-3">
          {value.map((item, i) => (
            <div key={i}>
              <span className="text-zinc-600">{i}: </span>
              <JsonNode value={item} depth={depth + 1} maxDepth={maxDepth} path={`${path}[${i}]`} />
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    if (entries.length === 0) return <span className="text-zinc-500">{'{}'}</span>;
    if (!expanded) {
      return (
        <span className="cursor-pointer text-zinc-300 hover:text-white" onClick={() => setExpanded(true)}>
          <ChevronRight className="inline h-3 w-3" /> {'{'}...{'}'} ({entries.length} keys)
        </span>
      );
    }
    return (
      <div>
        <span className="cursor-pointer text-zinc-400 hover:text-white" onClick={() => setExpanded(false)}>
          <ChevronDown className="inline h-3 w-3" /> {'{ '}
        </span>
        <div className="ml-4 border-l border-zinc-800 pl-3">
          {entries.map(([k, v]) => {
            const redacted = isRedactedKey(k);
            return (
              <div key={k} className="leading-6">
                <span className={cn(redacted ? "text-red-400" : "text-purple-400")}>"{k}"</span>
                <span className="text-zinc-600">: </span>
                {redacted && typeof v === "string" && v.length > 0 ? (
                  <span className="text-red-400">"***REDACTED***"</span>
                ) : (
                  <JsonNode value={v} depth={depth + 1} maxDepth={maxDepth} path={`${path}.${k}`} />
                )}
              </div>
            );
          })}
        </div>
        <span className="text-zinc-400">{'} '}</span>
      </div>
    );
  }

  return <span>{String(value)}</span>;
}
