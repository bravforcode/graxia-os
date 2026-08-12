import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { ArrowLeft, ExternalLink } from "lucide-react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { WorkflowRunTimeline } from "@/components/admin/WorkflowRunTimeline";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { getAgentWorkflowRun, type WorkflowRunDetail } from "@/lib/admin-api";

export default function WorkflowRunDetailPage() {
  const { run_id } = useParams<{ run_id: string }>();
  const navigate = useNavigate();
  const [run, setRun] = useState<WorkflowRunDetail | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!run_id) return;
    setLoading(true);
    getAgentWorkflowRun(run_id).then((result) => {
      setRun(result);
      setLoading(false);
    });
  }, [run_id]);

  if (loading) {
    return <div className="flex items-center justify-center py-12"><div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-white" /></div>;
  }

  if (!run) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/admin/workflows")}><ArrowLeft className="h-4 w-4" /> Back</Button>
        <div className="rounded-xl border border-dashed border-zinc-800 py-12 text-center text-sm text-zinc-500">Run not found.</div>
      </div>
    );
  }

  const steps = run.steps || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate("/admin/workflows")}>
          <ArrowLeft className="h-4 w-4" /> Back
        </Button>
      </div>

      <PageHeader
        title={run.workflow_type}
        description={`Run ${run.workflow_run_id.slice(0, 12)}...`}
        actions={<StatusBadge status={run.status} pulse={run.status === "running"} />}
      />

      {/* Summary */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div className="rounded-lg bg-zinc-900/60 border border-zinc-800 p-3">
          <div className="text-xs text-zinc-500">Status</div>
          <div className="text-sm font-medium text-white mt-1">{run.status}</div>
        </div>
        <div className="rounded-lg bg-zinc-900/60 border border-zinc-800 p-3">
          <div className="text-xs text-zinc-500">Steps</div>
          <div className="text-sm font-medium text-white mt-1">{steps.length}</div>
        </div>
        <div className="rounded-lg bg-zinc-900/60 border border-zinc-800 p-3">
          <div className="text-xs text-zinc-500">Context Packs</div>
          <div className="text-sm font-medium text-white mt-1">{run.context_pack_ids?.length || 0}</div>
        </div>
        <div className="rounded-lg bg-zinc-900/60 border border-zinc-800 p-3">
          <div className="text-xs text-zinc-500">Approval Requests</div>
          <div className="text-sm font-medium text-white mt-1">{run.approval_request_ids?.length || 0}</div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Timeline */}
        <div className="lg:col-span-2">
          <Panel title="Steps Timeline" eyebrow="EXECUTION">
            <WorkflowRunTimeline steps={steps} />
          </Panel>
        </div>

        {/* Sidebar */}
        <div className="space-y-4">
          {/* Output summary */}
          {run.output_summary && (
            <Panel title="Output Summary" eyebrow="RESULT">
              <p className="text-sm text-zinc-300">{run.output_summary}</p>
            </Panel>
          )}

          {/* Errors */}
          {run.error_code && (
            <Panel title="Error" eyebrow="FAILURE">
              <div className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">
                <div className="font-medium">[{run.error_code}]</div>
                {run.error_message && <div className="mt-1">{run.error_message}</div>}
              </div>
            </Panel>
          )}

          {/* References */}
          <Panel title="References" eyebrow="REFS">
            <div className="space-y-2 text-xs">
              {run.context_pack_ids && run.context_pack_ids.length > 0 && (
                <div>
                  <div className="text-zinc-500 mb-1">Context Packs</div>
                  {run.context_pack_ids.map((id) => (
                    <button
                      key={id}
                      onClick={() => navigate(`/admin/context-packs/${id}`)}
                      className="flex items-center gap-1 text-blue-400 hover:text-blue-300 font-mono"
                    >
                      {id.slice(0, 16)}... <ExternalLink className="h-3 w-3" />
                    </button>
                  ))}
                </div>
              )}
              {run.approval_request_ids && run.approval_request_ids.length > 0 && (
                <div>
                  <div className="text-zinc-500 mb-1">Approval Requests</div>
                  {run.approval_request_ids.map((id) => (
                    <button
                      key={id}
                      onClick={() => navigate(`/admin/approvals/${id}`)}
                      className="flex items-center gap-1 text-violet-400 hover:text-violet-300 font-mono"
                    >
                      {id.slice(0, 16)}... <ExternalLink className="h-3 w-3" />
                    </button>
                  ))}
                </div>
              )}
              {run.workspace_item_ids && run.workspace_item_ids.length > 0 && (
                <div>
                  <div className="text-zinc-500 mb-1">Workspace Items</div>
                  {run.workspace_item_ids.map((id) => (
                    <div key={id} className="font-mono text-zinc-400">{id}</div>
                  ))}
                </div>
              )}
            </div>
          </Panel>

          {/* Tool calls */}
          {run.tool_call_refs && run.tool_call_refs.length > 0 && (
            <Panel title="Tool Calls" eyebrow="MCP">
              <div className="space-y-2">
                {run.tool_call_refs.map((ref, i) => (
                  <div key={i} className="rounded-lg bg-zinc-800/40 px-2 py-1.5">
                    <div className="flex items-center gap-2 text-xs">
                      <span className="font-mono text-zinc-300">{ref.tool_name}</span>
                      <StatusBadge status={ref.status} />
                    </div>
                    <div className="text-[10px] text-zinc-500 mt-0.5">{ref.summary}</div>
                  </div>
                ))}
              </div>
            </Panel>
          )}
        </div>
      </div>
    </div>
  );
}
