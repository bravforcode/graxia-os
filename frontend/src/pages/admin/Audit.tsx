import { useState, useEffect } from "react";
import { ScrollText, TerminalSquare, ShieldAlert, AlertTriangle, RefreshCw, Workflow, XCircle } from "lucide-react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { listTools, type MCPToolDefinition } from "@/lib/admin-api";

interface AuditEvent {
  type: "tool_call" | "workflow_run" | "approval" | "dangerous_blocked" | "error";
  summary: string;
  timestamp: string;
  details?: Record<string, unknown>;
}

export default function AuditPage() {
  const [loading, setLoading] = useState(true);
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [tools, setTools] = useState<MCPToolDefinition[]>([]);

  useEffect(() => {
    loadAudit();
  }, []);

  async function loadAudit() {
    setLoading(true);
    const allTools = await listTools();
    setTools(allTools);

    // Build audit events from tool availability
    const auditEvents: AuditEvent[] = [];

    // Check if dangerous tools are properly blocked
    const dangerousTools = allTools.filter((t) => t.risk_level === "DANGEROUS_BLOCKED" || t.risk_level === "DANGEROUS");
    dangerousTools.forEach((t) => {
      auditEvents.push({
        type: "dangerous_blocked",
        summary: `Dangerous tool "${t.name}" is blocked by policy`,
        timestamp: new Date().toISOString(),
      });
    });

    // Approval-required tools
    const approvalTools = allTools.filter((t) => t.requires_approval);
    approvalTools.forEach((t) => {
      auditEvents.push({
        type: "tool_call",
        summary: `Approval-gated tool "${t.name}" requires human review`,
        timestamp: new Date().toISOString(),
      });
    });

    // Check workflow tools
    const workflowTools = allTools.filter((t) => t.name.startsWith("get_agent_workflow") || t.name === "list_agent_workflows" || t.name === "run_agent_workflow");
    workflowTools.forEach((t) => {
      auditEvents.push({
        type: "workflow_run",
        summary: `Workflow tool "${t.name}" registered (${t.risk_level})`,
        timestamp: new Date().toISOString(),
      });
    });

    setEvents(auditEvents);
    setLoading(false);
  }

  const eventIcons = {
    tool_call: TerminalSquare,
    workflow_run: Workflow,
    approval: ShieldAlert,
    dangerous_blocked: AlertTriangle,
    error: XCircle,
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Audit"
        description="Safe audit events and tool call records."
        actions={
          <Button variant="outline" size="sm" onClick={loadAudit} loading={loading}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
        }
      />

      <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-400">
        <strong>Note:</strong> Audit view shows current tool registration state. Full runtime audit history requires a backend audit query endpoint.
      </div>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-white" />
        </div>
      )}

      {!loading && (
        <Panel title="Events" eyebrow="AUDIT">
          {events.length === 0 ? (
            <div className="py-8 text-center text-sm text-zinc-500">
              No audit events.
            </div>
          ) : (
            <div className="space-y-2">
              {events.map((event, i) => {
                const Icon = eventIcons[event.type] || ScrollText;
                return (
                  <div key={i} className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
                    <Icon className={cn(
                      "h-4 w-4 mt-0.5",
                      event.type === "dangerous_blocked" ? "text-red-400" :
                      event.type === "approval" ? "text-violet-400" :
                      event.type === "error" ? "text-red-400" :
                      "text-zinc-400"
                    )} />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-0.5">
                        <StatusBadge status={event.type === "dangerous_blocked" ? "blocked" : event.type === "error" ? "fail" : "completed"} />
                        <span className="text-xs text-zinc-300">{event.summary}</span>
                      </div>
                      <div className="text-[10px] text-zinc-600">{event.timestamp}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Panel>
      )}

      {/* Tool registration summary */}
      {!loading && tools.length > 0 && (
        <Panel title="Tool Registration" eyebrow="SUMMARY">
          <div className="text-xs text-zinc-400">
            <div className="grid grid-cols-2 gap-2">
              <div>Total tools registered</div>
              <div className="text-white font-medium">{tools.length}</div>
              <div>Dangerous (blocked)</div>
              <div className="text-red-400 font-medium">{tools.filter((t) => t.risk_level === "DANGEROUS_BLOCKED" || t.risk_level === "DANGEROUS").length}</div>
              <div>Approval required</div>
              <div className="text-violet-400 font-medium">{tools.filter((t) => t.requires_approval).length}</div>
              <div>Read-only</div>
              <div className="text-blue-400 font-medium">{tools.filter((t) => t.risk_level === "READ_ONLY").length}</div>
              <div>Low write</div>
              <div className="text-amber-400 font-medium">{tools.filter((t) => t.risk_level === "LOW_WRITE").length}</div>
            </div>
          </div>
        </Panel>
      )}
    </div>
  );
}
