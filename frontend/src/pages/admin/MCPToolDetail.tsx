import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { ArrowLeft, Play, ShieldAlert, AlertTriangle } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { RiskBadge } from "@/components/admin/RiskBadge";
import { SafeJsonViewer } from "@/components/admin/SafeJsonViewer";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { listTools, callTool, type MCPToolDefinition, type MCPToolCallResponse } from "@/lib/admin-api";

const sampleInputs: Record<string, Record<string, unknown>> = {
  list_agent_workflows: {},
  run_agent_workflow: { workflow_type: "daily_funnel_brief", inputs: { date_range: "today" } },
  get_agent_workflow_run: { workflow_run_id: "wf_001" },
  get_agent_workflow_status: {},
  get_agent_workflow_policy: { workflow_type: "daily_funnel_brief" },
  build_context_pack: { task_type: "funnel_review", goal: "daily funnel brief" },
  search_project_context: { query: "production readiness" },
  get_revenue_summary: {},
  get_recent_orders: {},
  get_conversion_summary: {},
  get_checkout_abandonment: {},
  get_delivery_open_rate: {},
  get_pending_approvals: {},
};

export default function MCPToolDetail() {
  const { name } = useParams<{ name: string }>();
  const navigate = useNavigate();
  const [tool, setTool] = useState<MCPToolDefinition | null>(null);
  const [loading, setLoading] = useState(true);
  const [args, setArgs] = useState("{}");
  const [response, setResponse] = useState<MCPToolCallResponse | null>(null);
  const [running, setRunning] = useState(false);

  useEffect(() => {
    if (!name) return;
    setLoading(true);
    listTools().then((tools) => {
      const found = tools.find((t) => t.name === decodeURIComponent(name!));
      setTool(found || null);
      setLoading(false);
      // Set sample args
      const decodedName = decodeURIComponent(name!);
      if (sampleInputs[decodedName]) {
        setArgs(JSON.stringify(sampleInputs[decodedName], null, 2));
      }
    });
  }, [name]);

  const toolName = decodeURIComponent(name || "");
  const isDangerous = tool?.risk_level === "DANGEROUS" || tool?.risk_level === "DANGEROUS_BLOCKED";

  async function handleRun() {
    if (!tool) return;
    setRunning(true);
    setResponse(null);
    let parsed: Record<string, unknown> = {};
    try {
      parsed = JSON.parse(args);
    } catch {
      setResponse({ ok: false, error: { code: "INVALID_ARGS", message: "Invalid JSON arguments" } });
      setRunning(false);
      return;
    }
    const result = await callTool(tool.name, parsed);
    setResponse(result);
    setRunning(false);
  }

  if (loading) {
    return <div className="flex items-center justify-center py-12"><div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-white" /></div>;
  }

  if (!tool) {
    return (
      <div className="space-y-4">
        <Button variant="ghost" onClick={() => navigate("/admin/mcp-tools")}><ArrowLeft className="h-4 w-4" /> Back</Button>
        <div className="rounded-xl border border-dashed border-zinc-800 py-12 text-center text-sm text-zinc-500">Tool not found.</div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Button variant="ghost" size="sm" onClick={() => navigate("/admin/mcp-tools")}>
          <ArrowLeft className="h-4 w-4" /> Back
        </Button>
      </div>

      <PageHeader
        title={toolName}
        description={tool.description || ""}
        actions={<RiskBadge riskLevel={tool.risk_level} />}
      />

      {/* Safety warnings */}
      {isDangerous && (
        <div className="rounded-xl border border-red-500/20 bg-red-500/5 p-3 flex items-center gap-3">
          <ShieldAlert className="h-5 w-5 text-red-400 flex-shrink-0" />
          <span className="text-sm text-red-400 font-medium">DANGEROUS: This tool is blocked by policy. Run to confirm blocked response.</span>
        </div>
      )}

      {tool.requires_approval && (
        <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 p-3 flex items-center gap-3">
          <AlertTriangle className="h-5 w-5 text-violet-400 flex-shrink-0" />
          <span className="text-sm text-violet-400 font-medium">Requires approval — calling this tool will create an ApprovalRequest, not execute the action.</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Args */}
        <Panel title="Arguments" eyebrow="INPUT">
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="text-xs text-zinc-500 font-mono">{toolName}(args)</span>
              {!isDangerous && (
                <Button size="sm" onClick={handleRun} loading={running} disabled={running}>
                  <Play className="h-3 w-3" /> Run
                </Button>
              )}
            </div>
            <textarea
              value={args}
              onChange={(e) => setArgs(e.target.value)}
              className="w-full h-48 rounded-lg border border-zinc-800 bg-zinc-900 p-3 font-mono text-xs text-zinc-300 resize-none focus:outline-none focus:border-zinc-700"
            />
            {tool.input_schema && Object.keys(tool.input_schema).length > 0 && (
              <details>
                <summary className="text-xs text-zinc-500 cursor-pointer hover:text-zinc-300">Input schema</summary>
                <SafeJsonViewer data={tool.input_schema} initiallyExpanded={false} />
              </details>
            )}
          </div>
        </Panel>

        {/* Response */}
        <Panel title="Response" eyebrow="OUTPUT">
          {response ? (
            <div className="space-y-3">
              <div className={cn(
                "rounded-lg px-3 py-2 text-xs font-medium",
                response.ok ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
              )}>
                {response.ok ? "Success" : `Error: ${response.error?.code || "UNKNOWN"}`}
                {!response.ok && response.error?.message && ` — ${response.error.message}`}
              </div>
              {response.meta?.approval_request_id && (
                <div className="rounded-lg bg-violet-500/10 px-3 py-2 text-xs text-violet-400">
                  ApprovalRequest created: {response.meta.approval_request_id as string}
                </div>
              )}
              <SafeJsonViewer data={response.data || response.error} />
            </div>
          ) : (
            <div className="py-8 text-center text-sm text-zinc-500">
              Enter arguments and run the tool to see results.
            </div>
          )}
        </Panel>
      </div>
    </div>
  );
}
