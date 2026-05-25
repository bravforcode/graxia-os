import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import {
  Activity, ShieldCheck, Workflow, FileText, BarChart3,
  Play, ExternalLink, TerminalSquare, Database
} from "lucide-react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { MetricCard } from "@/components/admin/MetricCard";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { cn } from "@/lib/utils";
import { getAgentWorkflowStatus, runAgentWorkflow, type WorkflowStatus } from "@/lib/admin-api";

const readinessItems = [
  { key: "LOCAL_FUNNEL_READY",        label: "Funnel" },
  { key: "LOCAL_MCP_READONLY_READY",  label: "MCP Readonly" },
  { key: "LOCAL_MCP_WRITE_READY",     label: "MCP Write" },
  { key: "LOCAL_WORKSPACE_READY",     label: "Workspace" },
  { key: "LOCAL_CONTEXT_READY",       label: "Context" },
  { key: "LOCAL_WORKFLOW_READY",      label: "Workflows" },
  { key: "LOCAL_UI_READY",            label: "UI" },
  { key: "FULL_LOCAL_AGENT_READY",    label: "Full Agent" },
];

const quickActions = [
  { label: "Run Daily Funnel Brief",   workflow: "daily_funnel_brief",    icon: BarChart3,  description: "Daily operating brief for the funnel" },
  { label: "Run Launch Plan Builder",  workflow: "launch_plan_builder",   icon: FileText,   description: "Create a launch plan for a digital product" },
  { label: "Run Weekly Revenue Review",workflow: "weekly_revenue_review", icon: Activity,   description: "Weekly founder-style revenue review" },
];

const statusLinks = [
  { label: "Approval Inbox",    path: "/admin/approvals",     icon: ShieldCheck,   count: "pending" },
  { label: "MCP Tools",        path: "/admin/mcp-tools",     icon: TerminalSquare, count: "all" },
  { label: "Workflows",        path: "/admin/workflows",     icon: Workflow,       count: "all" },
  { label: "Context Packs",    path: "/admin/context-packs", icon: Database,       count: "all" },
];

export default function AgentControl() {
  const navigate = useNavigate();
  const [wfStatus, setWfStatus] = useState<WorkflowStatus | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [runResult, setRunResult] = useState<{ type: string; ok: boolean; msg: string } | null>(null);

  useEffect(() => {
    getAgentWorkflowStatus().then(setWfStatus);
  }, []);

  async function handleQuickAction(workflow: string, label: string) {
    setRunning(workflow);
    setRunResult(null);
    const result = await runAgentWorkflow(workflow, { date_range: "today" });
    setRunning(null);
    if (result) {
      setRunResult({ type: workflow, ok: true, msg: `${label}: ${result.status} (${result.steps_completed} steps)` });
      // Refresh status
      getAgentWorkflowStatus().then(setWfStatus);
    } else {
      setRunResult({ type: workflow, ok: false, msg: `${label}: failed to run` });
    }
  }

  return (
    <div className="space-y-6">
      {/* Safety Banner */}
      <div className="rounded-xl border border-cyan-500/20 bg-cyan-500/5 p-3 flex items-center gap-3">
        <TerminalSquare className="h-5 w-5 text-cyan-400 flex-shrink-0" />
        <div className="flex-1">
          <div className="flex items-center gap-3 text-xs">
            <span className="text-cyan-400 font-medium">Mode: Local / Mock / Approval-Gated</span>
            <span className="text-zinc-600">|</span>
            <span className="text-zinc-500">External calls: Disabled</span>
            <span className="text-zinc-600">|</span>
            <span className="text-zinc-500">Real email: Disabled</span>
            <span className="text-zinc-600">|</span>
            <span className="text-zinc-500">Real Google: Disabled</span>
            <span className="text-zinc-600">|</span>
            <span className="text-amber-400 font-medium">Production: Not Ready</span>
          </div>
        </div>
      </div>

      <PageHeader
        title="Agent Control"
        description="Executive command center for local-safe agent operations."
      />

      {/* Readiness Status */}
      <Panel title="System Readiness" eyebrow="STATUS">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          {readinessItems.map((item) => (
            <div key={item.key} className="flex items-center gap-2 rounded-lg bg-zinc-800/40 px-3 py-2">
              <StatusBadge status={item.key.includes("READY") ? "ready" : "not_ready"} />
              <span className="text-xs text-zinc-400">{item.label}</span>
            </div>
          ))}
        </div>
      </Panel>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard title="Workflow Runs" value={wfStatus?.total_runs ?? 0} subtitle="Total runs" />
        <MetricCard title="Completed" value={wfStatus?.completed ?? 0} subtitle="Successful runs" status="up" />
        <MetricCard title="Failed" value={wfStatus?.failed ?? 0} subtitle="Failed runs" status={wfStatus?.failed ? "critical" : "neutral"} />
      </div>

      {/* Quick Actions */}
      <Panel title="Safe Actions" eyebrow="QUICK RUN">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {quickActions.map((action) => (
            <button
              key={action.workflow}
              onClick={() => handleQuickAction(action.workflow, action.label)}
              disabled={running !== null}
              className={cn(
                "rounded-xl border border-zinc-800 bg-zinc-900/40 p-4 text-left transition-all hover:border-zinc-700 hover:bg-zinc-900/80",
                running === action.workflow && "animate-pulse border-blue-500/50"
              )}
            >
              <div className="flex items-center gap-2 mb-2">
                <action.icon className="h-4 w-4 text-blue-400" />
                <span className="text-sm font-medium text-white">{action.label}</span>
              </div>
              <p className="text-xs text-zinc-500">{action.description}</p>
              {running === action.workflow ? (
                <div className="mt-2 text-xs text-blue-400">Running...</div>
              ) : (
                <div className="mt-2 flex items-center gap-1 text-xs text-zinc-400">
                  <Play className="h-3 w-3" /> Run
                </div>
              )}
            </button>
          ))}
        </div>
        {runResult && (
          <div className={cn(
            "mt-3 rounded-lg px-3 py-2 text-xs",
            runResult.ok ? "bg-emerald-500/10 text-emerald-400" : "bg-red-500/10 text-red-400"
          )}>
            {runResult.msg}
          </div>
        )}
      </Panel>

      {/* Quick Links */}
      <Panel title="Quick Links" eyebrow="NAVIGATE">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {statusLinks.map((link) => (
            <button
              key={link.path}
              onClick={() => navigate(link.path)}
              className="flex items-center gap-3 rounded-xl border border-zinc-800 bg-zinc-900/40 p-3 text-left transition-all hover:border-zinc-700 hover:bg-zinc-900/80"
            >
              <link.icon className="h-5 w-5 text-zinc-400" />
              <div>
                <div className="text-sm font-medium text-white">{link.label}</div>
                <div className="text-xs text-zinc-500">{link.count}</div>
              </div>
              <ExternalLink className="h-3 w-3 text-zinc-600 ml-auto" />
            </button>
          ))}
        </div>
      </Panel>
    </div>
  );
}
