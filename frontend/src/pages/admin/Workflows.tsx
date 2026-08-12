import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { Workflow, Play, RefreshCw } from "lucide-react";
import { RiskBadge } from "@/components/admin/RiskBadge";
import { PageHeader } from "@/components/ui/page-header";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { listAgentWorkflows, runAgentWorkflow, getAgentWorkflowStatus, type WorkflowDefinition, type WorkflowStatus, type WorkflowRunSummary } from "@/lib/admin-api";

export default function WorkflowsPage() {
  const navigate = useNavigate();
  const [workflows, setWorkflows] = useState<WorkflowDefinition[]>([]);
  const [wfStatus, setWfStatus] = useState<WorkflowStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState<string | null>(null);
  const [lastRun, setLastRun] = useState<{ type: string; result: WorkflowRunSummary | null } | null>(null);

  useEffect(() => {
    load();
  }, []);

  async function load() {
    setLoading(true);
    const [wfs, status] = await Promise.all([
      listAgentWorkflows(),
      getAgentWorkflowStatus(),
    ]);
    setWorkflows(wfs);
    setWfStatus(status);
    setLoading(false);
  }

  async function handleRun(wfType: string) {
    setRunning(wfType);
    setLastRun(null);
    const result = await runAgentWorkflow(wfType, { date_range: "today" });
    setRunning(null);
    setLastRun({ type: wfType, result });
    load();
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Workflows"
        description="Run local-safe agent workflows."
        actions={
          <Button variant="outline" size="sm" onClick={load} loading={loading}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
        }
      />

      {/* Workflow status summary */}
      {wfStatus && (
        <div className="flex items-center gap-4 text-xs">
          <span className="text-zinc-500">Total runs: <span className="text-zinc-300 font-medium">{wfStatus.total_runs}</span></span>
          <span className="text-zinc-500">Completed: <span className="text-emerald-400 font-medium">{wfStatus.completed}</span></span>
          <span className="text-zinc-500">Failed: <span className={cn("font-medium", wfStatus.failed > 0 ? "text-red-400" : "text-zinc-300")}>{wfStatus.failed}</span></span>
          {wfStatus.latest_run_id && (
            <button
              onClick={() => navigate(`/admin/workflows/${wfStatus.latest_run_id}`)}
              className="text-blue-400 hover:text-blue-300 underline"
            >
              Latest run
            </button>
          )}
        </div>
      )}

      {/* Last run result */}
      {lastRun && lastRun.result && (
        <div className={cn(
          "rounded-lg px-3 py-2 text-xs",
          lastRun.result.status === "completed" ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
        )}>
          <strong>{lastRun.type}:</strong> {lastRun.result.status} ({lastRun.result.steps_completed} steps completed, {lastRun.result.steps_failed} failed)
          <button
            onClick={() => navigate(`/admin/workflows/${lastRun.result!.workflow_run_id}`)}
            className="ml-2 underline hover:no-underline"
          >
            View run
          </button>
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-white" />
        </div>
      )}

      {!loading && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          {workflows.map((wf) => (
            <div key={wf.workflow_type} className="rounded-xl border border-zinc-800 bg-zinc-900/40 p-4">
              <div className="flex items-start justify-between gap-3 mb-2">
                <div>
                  <div className="flex items-center gap-2 mb-1">
                    <Workflow className="h-4 w-4 text-blue-400" />
                    <span className="text-sm font-medium text-white font-mono">{wf.workflow_type}</span>
                    <RiskBadge riskLevel={wf.risk_level} compact />
                  </div>
                  <p className="text-xs text-zinc-500">{wf.description}</p>
                </div>
              </div>

              <div className="flex items-center gap-2 mt-3">
                <Button
                  size="sm"
                  onClick={() => handleRun(wf.workflow_type)}
                  loading={running === wf.workflow_type}
                  disabled={running !== null}
                >
                  <Play className="h-3 w-3" /> Run
                </Button>
              </div>

              {/* Allowed/blocked tools */}
              <details className="mt-3">
                <summary className="text-xs text-zinc-500 cursor-pointer hover:text-zinc-400">Tools ({wf.allowed_tools?.length || 0} allowed, {wf.blocked_tools?.length || 0} blocked)</summary>
                <div className="mt-2 space-y-1">
                  {wf.allowed_tools && wf.allowed_tools.length > 0 && (
                    <div className="text-xs">
                      <span className="text-emerald-500">Allowed:</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {wf.allowed_tools.map((t) => <span key={t} className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-zinc-400">{t}</span>)}
                      </div>
                    </div>
                  )}
                  {wf.blocked_tools && wf.blocked_tools.length > 0 && (
                    <div className="text-xs">
                      <span className="text-red-500">Blocked:</span>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {wf.blocked_tools.map((t) => <span key={t} className="rounded bg-red-900/20 px-1.5 py-0.5 font-mono text-red-400">{t}</span>)}
                      </div>
                    </div>
                  )}
                </div>
              </details>
            </div>
          ))}
        </div>
      )}

      {!loading && workflows.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-800 py-12 text-center text-sm text-zinc-500">
          No workflows available. Ensure the backend is running and MCP tools are registered.
        </div>
      )}
    </div>
  );
}
