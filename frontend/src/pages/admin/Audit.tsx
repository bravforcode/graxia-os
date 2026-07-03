import { useState, useEffect } from "react";
import { ScrollText, TerminalSquare, ShieldAlert, AlertTriangle, RefreshCw, Workflow, XCircle } from "lucide-react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { getRuntimeStatus, listBusinessEvents, listDeadLetters, listTools, type MCPToolDefinition } from "@/lib/admin-api";

interface AuditEvent {
  type: "tool_call" | "workflow_run" | "approval" | "dangerous_blocked" | "error" | "business_event" | "runtime_task";
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
    const [allTools, runtimeStatus, deadLetters, events] = await Promise.all([
      listTools(),
      getRuntimeStatus(),
      listDeadLetters(20),
      listBusinessEvents(),
    ]);
    setTools(allTools);

    const auditEvents: AuditEvent[] = [];

    const dangerousTools = allTools.filter((t) => t.risk_level === "DANGEROUS_BLOCKED" || t.risk_level === "DANGEROUS");
    dangerousTools.forEach((t) => {
      auditEvents.push({
        type: "dangerous_blocked",
        summary: `Dangerous tool "${t.name}" is blocked by policy`,
        timestamp: new Date().toISOString(),
      });
    });

    deadLetters.forEach((item) => {
      auditEvents.push({
        type: "error",
        summary: `Dead letter ${item.dead_letter_id.slice(0, 12)} recorded: ${item.reason}`,
        timestamp: new Date().toISOString(),
        details: {
          task_id: item.task_id,
          replay_count: item.replay_count,
        },
      });
    });

    events.slice(0, 20).forEach((event) => {
      auditEvents.push({
        type: "business_event",
        summary: `${event.event_type} → ${event.subject_type}:${event.subject_id}`,
        timestamp: new Date().toISOString(),
        details: {
          event_id: event.event_id,
          correlation_id: event.correlation_id,
        },
      });
    });

    if (runtimeStatus) {
      auditEvents.unshift({
        type: "runtime_task",
        summary: `Runtime snapshot: ${runtimeStatus.gateway_task_count} tasks, ${runtimeStatus.dead_letter_count} dead letters, ${runtimeStatus.business_event_count} events`,
        timestamp: new Date().toISOString(),
        details: runtimeStatus as unknown as Record<string, unknown>,
      });
    }

    setEvents(auditEvents);
    setLoading(false);
  }

  const eventIcons = {
    tool_call: TerminalSquare,
    workflow_run: Workflow,
    approval: ShieldAlert,
    dangerous_blocked: AlertTriangle,
    error: XCircle,
    business_event: ScrollText,
    runtime_task: Workflow,
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
        <strong>Note:</strong> Audit view shows current runtime evidence plus policy state. Full persisted audit history still depends on the backend audit query endpoint.
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
                      {event.details && (
                        <details className="mt-2">
                          <summary className="cursor-pointer text-[10px] text-zinc-500 hover:text-zinc-400">Details</summary>
                          <div className="mt-2 rounded-lg bg-black/40 p-2">
                            <pre className="overflow-auto text-[10px] text-zinc-500">{JSON.stringify(event.details, null, 2)}</pre>
                          </div>
                        </details>
                      )}
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
