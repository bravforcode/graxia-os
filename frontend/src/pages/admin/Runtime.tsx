import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, RefreshCw, RotateCcw, Workflow } from "lucide-react";
import { MetricCard } from "@/components/admin/MetricCard";
import { RiskBadge } from "@/components/admin/RiskBadge";
import { SafeJsonViewer } from "@/components/admin/SafeJsonViewer";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import {
  getRuntimeStatus,
  getTokenRoiSummary,
  listBusinessEvents,
  listDeadLetters,
  listRuntimeTasks,
  requestDeadLetterRequeue,
  type BusinessEventSummary,
  type DeadLetterSummary,
  type RuntimeStatus,
  type RuntimeTaskSummary,
  type TokenRoiSummary,
} from "@/lib/admin-api";

export default function RuntimePage() {
  const [loading, setLoading] = useState(true);
  const [requeueing, setRequeueing] = useState<string | null>(null);
  const [status, setStatus] = useState<RuntimeStatus | null>(null);
  const [tasks, setTasks] = useState<RuntimeTaskSummary[]>([]);
  const [deadLetters, setDeadLetters] = useState<DeadLetterSummary[]>([]);
  const [events, setEvents] = useState<BusinessEventSummary[]>([]);
  const [tokenRoi, setTokenRoi] = useState<TokenRoiSummary | null>(null);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    void load();
  }, []);

  async function load() {
    setLoading(true);
    setMessage(null);
    const [runtimeStatus, runtimeTasks, runtimeDeadLetters, runtimeEvents, roi] = await Promise.all([
      getRuntimeStatus(),
      listRuntimeTasks(12),
      listDeadLetters(12),
      listBusinessEvents(),
      getTokenRoiSummary(),
    ]);
    setStatus(runtimeStatus);
    setTasks(runtimeTasks);
    setDeadLetters(runtimeDeadLetters);
    setEvents(runtimeEvents.slice(0, 12));
    setTokenRoi(roi);
    setLoading(false);
  }

  async function handleRequestRequeue(deadLetterId: string) {
    setRequeueing(deadLetterId);
    const result = await requestDeadLetterRequeue(deadLetterId);
    setRequeueing(null);
    if (result.ok && result.meta?.approval_request_id) {
      setMessage({
        ok: true,
        text: `ApprovalRequest created: ${result.meta.approval_request_id as string}`,
      });
      await load();
      return;
    }
    setMessage({
      ok: false,
      text: result.error?.message || "Failed to create requeue approval request",
    });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="RUNTIME"
        title="Runtime Status"
        description="Gateway, worker, workflow, event, and dead-letter visibility for the current local runtime."
        actions={
          <Button variant="outline" size="sm" onClick={load} loading={loading}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
        }
      />

      {message && (
        <div
          className={cn(
            "rounded-lg px-3 py-2 text-xs",
            message.ok ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400",
          )}
        >
          {message.text}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4">
        <MetricCard title="Gateway Tasks" value={status?.gateway_task_count ?? 0} subtitle="Tracked by gateway" />
        <MetricCard title="Dead Letters" value={status?.dead_letter_count ?? 0} subtitle="Approval-gated requeue only" status={(status?.dead_letter_count ?? 0) > 0 ? "critical" : "neutral"} />
        <MetricCard title="Workflow Traces" value={status?.workflow_trace_count ?? 0} subtitle="Runtime orchestration traces" />
        <MetricCard title="Business Events" value={status?.business_event_count ?? 0} subtitle="Canonical runtime events" />
        <MetricCard title="Worker Caps" value={status?.worker_capability_count ?? 0} subtitle="Deterministic mock provider" />
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <Panel title="Runtime Summary" eyebrow="STATUS">
          {loading ? (
            <div className="flex items-center justify-center py-12">
              <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-white" />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 text-xs">
                <div className="text-zinc-500">Execution modes</div>
                <div className="text-right text-zinc-300">{status?.execution_modes?.join(", ") || "n/a"}</div>
                <div className="text-zinc-500">Worker capabilities</div>
                <div className="text-right text-zinc-300">{status?.worker_capability_count ?? 0}</div>
              </div>
              <div className="space-y-2">
                <div className="text-xs text-zinc-500">Capabilities</div>
                <div className="flex flex-wrap gap-1">
                  {(status?.worker_capabilities || []).map((capability) => (
                    <span key={capability} className="rounded bg-zinc-800 px-1.5 py-0.5 text-[10px] font-mono text-zinc-300">
                      {capability}
                    </span>
                  ))}
                </div>
              </div>
              <div className="rounded-lg border border-cyan-500/20 bg-cyan-500/5 p-3 text-xs text-cyan-300">
                Local/mock runtime only. Public/customer actions remain approval-gated.
              </div>
            </div>
          )}
        </Panel>

        <Panel title="Token ROI Baseline" eyebrow="CONTEXT">
          <div className="space-y-3 text-xs text-zinc-400">
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
              <div className="flex items-center justify-between gap-3">
                <span className="text-zinc-500">Net ROI</span>
                <span className={cn("font-medium", (tokenRoi?.net_roi ?? 0) >= 0 ? "text-emerald-400" : "text-red-400")}>
                  {tokenRoi?.net_roi ?? 0}
                </span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <span className="text-zinc-500">Retry cost</span>
                <span className="text-zinc-300">{tokenRoi?.retry_cost ?? 0}</span>
              </div>
              <div className="mt-2 flex items-center justify-between gap-3">
                <span className="text-zinc-500">Correction cost</span>
                <span className="text-zinc-300">{tokenRoi?.correction_cost ?? 0}</span>
              </div>
            </div>
            <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
              <div className="text-zinc-500">Recommendation</div>
              <div className="mt-1 text-zinc-200">{tokenRoi?.recommendation || "No ROI recommendation available."}</div>
            </div>
            <div className="text-[11px] text-zinc-600">
              Phase 11 shows runtime ROI evaluator baseline. Full token ROI dashboard lands in Phase 12.
            </div>
            <Link to="/admin/context-packs" className="inline-flex text-cyan-400 hover:text-cyan-300">
              Open Context Packs →
            </Link>
          </div>
        </Panel>

        <Panel title="Linked Surfaces" eyebrow="NAVIGATE">
          <div className="space-y-2 text-xs">
            <Link to="/admin/workflows" className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2 hover:border-zinc-700">
              <span className="text-zinc-300">Workflow Traces</span>
              <Workflow className="h-4 w-4 text-zinc-500" />
            </Link>
            <Link to="/admin/audit" className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2 hover:border-zinc-700">
              <span className="text-zinc-300">Audit Events</span>
              <AlertTriangle className="h-4 w-4 text-zinc-500" />
            </Link>
            <Link to="/admin/readiness" className="flex items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2 hover:border-zinc-700">
              <span className="text-zinc-300">Readiness Checks</span>
              <StatusBadge status="completed" />
            </Link>
          </div>
        </Panel>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <Panel title="Runtime Tasks" eyebrow="GATEWAY">
          <div className="space-y-2">
            {tasks.length === 0 ? (
              <div className="py-8 text-center text-sm text-zinc-500">No runtime tasks recorded.</div>
            ) : (
              tasks.map((task) => (
                <div key={task.task_id} className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={task.dead_lettered ? "blocked" : task.status === "failed" ? "fail" : task.status === "completed" ? "completed" : "running"} />
                    <span className="font-mono text-xs text-zinc-200">{task.task_id.slice(0, 12)}</span>
                    <RiskBadge riskLevel={task.risk_level} compact />
                  </div>
                  <div className="mt-2 grid grid-cols-2 gap-2 text-[11px] text-zinc-500">
                    <div>Target</div>
                    <div className="text-right text-zinc-300">{task.target}</div>
                    <div>Status</div>
                    <div className="text-right text-zinc-300">{task.status}</div>
                    <div>Correlation</div>
                    <div className="truncate text-right font-mono text-zinc-300">{task.correlation_id}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        </Panel>

        <Panel title="Dead Letters" eyebrow="APPROVAL">
          <div className="space-y-2">
            {deadLetters.length === 0 ? (
              <div className="py-8 text-center text-sm text-zinc-500">No dead letters.</div>
            ) : (
              deadLetters.map((item) => (
                <div key={item.dead_letter_id} className="rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-mono text-xs text-red-300">{item.dead_letter_id}</div>
                      <div className="mt-1 text-xs text-zinc-400">{item.reason}</div>
                    </div>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => handleRequestRequeue(item.dead_letter_id)}
                      loading={requeueing === item.dead_letter_id}
                      disabled={requeueing !== null}
                    >
                      <RotateCcw className="h-3 w-3" /> Request requeue
                    </Button>
                  </div>
                  <div className="mt-2 text-[11px] text-zinc-500">
                    task_id: <span className="font-mono text-zinc-300">{item.task_id}</span> · replay_count:{" "}
                    <span className="text-zinc-300">{item.replay_count}</span>
                  </div>
                </div>
              ))
            )}
          </div>
        </Panel>
      </div>

      <Panel title="Business Events" eyebrow="CANONICAL">
        {events.length === 0 ? (
          <div className="py-8 text-center text-sm text-zinc-500">No business events captured yet.</div>
        ) : (
          <div className="space-y-2">
            {events.map((event) => (
              <details key={event.event_id} className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
                <summary className="cursor-pointer list-none">
                  <div className="flex items-center gap-2">
                    <StatusBadge status="completed" />
                    <span className="font-mono text-xs text-zinc-200">{event.event_type}</span>
                    <span className="text-xs text-zinc-500">{event.subject_type}:{event.subject_id}</span>
                  </div>
                </summary>
                <div className="mt-3">
                  <SafeJsonViewer data={event} />
                </div>
              </details>
            ))}
          </div>
        )}
      </Panel>
    </div>
  );
}
