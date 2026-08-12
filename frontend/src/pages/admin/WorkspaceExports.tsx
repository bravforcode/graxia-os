import { useState } from "react";
import { FileText, Sheet, Mail, Calendar, HardDrive } from "lucide-react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { cn } from "@/lib/utils";
import { callTool } from "@/lib/admin-api";

const workspaceActions = [
  { label: "Create Launch Doc",     tool: "create_launch_doc",               icon: FileText,  params: { doc_type: "launch_plan", title: "New Launch Plan", content: "# Launch Plan\n\nSummary:\n\nLead magnet:\n\nContent plan:\n\nOutreach plan:" } },
  { label: "Export to Sheet",       tool: "export_revenue_summary_to_sheet",  icon: Sheet,     params: { sheet_type: "revenue_summary" } },
  { label: "Create Calendar Plan",  tool: "create_launch_calendar_plan",      icon: Calendar,  params: { launch_date: "2026-06-01", pre_launch_days: 7 } },
  { label: "Draft Customer Reply",  tool: "draft_customer_reply",            icon: Mail,      params: { thread_id: "thread-0", draft_text: "Thank you for reaching out! Here's what I can help with..." } },
];

export default function WorkspaceExports() {
  const [running, setRunning] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, { ok: boolean; data?: unknown; error?: { code: string; message: string } }>>({});


  async function handleAction(action: typeof workspaceActions[0]) {
    setRunning(action.label);
    const res = await callTool(action.tool, action.params);
    setResults((prev) => ({ ...prev, [action.label]: res }));
    setRunning(null);
  }

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-3 flex items-center gap-3">
        <HardDrive className="h-5 w-5 text-cyan-400 flex-shrink-0" />
        <div className="text-xs text-cyan-400 font-medium">
          MOCK — no real Google API calls. All items are local-only mock outputs.
        </div>
      </div>

      <PageHeader
        title="Workspace Exports"
        description="View mock Workspace outputs."
      />

      {/* Action buttons */}
      <Panel title="Create Workspace Items" eyebrow="ACTIONS">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {workspaceActions.map((action) => {
            const Icon = action.icon;
            const result = results[action.label];
            return (
              <button
                key={action.label}
                onClick={() => handleAction(action)}
                disabled={running !== null}
                className={cn(
                  "rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 text-left transition-all hover:border-zinc-700 hover:bg-zinc-900/80",
                  running === action.label && "animate-pulse border-blue-500/50"
                )}
              >
                <div className="flex items-center gap-2 mb-2">
                  <Icon className="h-4 w-4 text-cyan-400" />
                  <span className="text-sm font-medium text-white">{action.label}</span>
                </div>
                <div className="text-xs text-zinc-500">via MCP tool</div>
                {result && (
                  <div className={cn(
                    "mt-2 rounded px-2 py-1 text-[10px]",
                    result.ok ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
                  )}>
                    {result.ok ? "Created" : `Error: ${result.error?.code}`}
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </Panel>

      {/* Results */}
      {Object.keys(results).length > 0 && (
        <Panel title="Results" eyebrow="OUTPUT">
          <div className="space-y-3">
            {Object.entries(results).map(([label, res]) => (
              <div key={label} className={cn(
                "rounded-lg border p-3",
                res.ok ? "border-emerald-500/20 bg-emerald-500/5" : "border-red-500/20 bg-red-500/5"
              )}>
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-sm font-medium text-white">{label}</span>
                  <StatusBadge status={res.ok ? "completed" : "fail"} />
                  <span className="text-[10px] text-cyan-400 ml-auto">MOCK</span>
                </div>
                {res.data ? (
                  <pre className="text-xs text-zinc-400 mt-1 overflow-auto max-h-20">
                    {JSON.stringify(res.data, null, 2)}
                  </pre>
                ) : null}
                {!res.ok && res.error && (
                  <div className="text-xs text-red-400 mt-1">[{res.error.code}] {res.error.message}</div>
                )}
              </div>
            ))}
          </div>
        </Panel>
      )}

      {/* Empty state */}
      {Object.keys(results).length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-800 py-12 text-center text-sm text-zinc-500">
          No workspace exports yet. Use the action buttons above to create mock workspace items.
        </div>
      )}
    </div>
  );
}
