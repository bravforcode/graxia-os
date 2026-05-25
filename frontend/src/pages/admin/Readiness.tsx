import { useState, useEffect } from "react";
import { CheckCircle2, XCircle, AlertTriangle, RefreshCw } from "lucide-react";
import { StatusBadge } from "@/components/admin/StatusBadge";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { listTools, getAgentWorkflowStatus, type MCPToolDefinition } from "@/lib/admin-api";

interface ReadinessCheck {
  key: string;
  label: string;
  status: "ready" | "not_ready";
  details: string;
}

export default function ReadinessPage() {
  const [loading, setLoading] = useState(true);
  const [checks, setChecks] = useState<ReadinessCheck[]>([]);
  const [tools, setTools] = useState<MCPToolDefinition[]>([]);

  useEffect(() => {
    loadReadiness();
  }, []);

  async function loadReadiness() {
    setLoading(true);
    const allTools = await listTools();
    setTools(allTools);
    await getAgentWorkflowStatus();

    const toolNames = allTools.map((t) => t.name);
    const hasFunnelTools = toolNames.some((n) => ["get_revenue_summary", "get_recent_orders", "get_conversion_summary", "get_checkout_abandonment", "get_delivery_open_rate"].includes(n));
    const hasWorkspaceTools = toolNames.some((n) => ["create_launch_doc", "export_revenue_summary_to_sheet", "create_launch_calendar_plan", "draft_customer_reply"].includes(n));
    const hasContextTools = toolNames.some((n) => ["build_context_pack", "search_project_context", "get_project_index_summary", "get_context_pack"].includes(n));
    const hasWorkflowTools = toolNames.some((n) => ["list_agent_workflows", "run_agent_workflow", "get_agent_workflow_run", "get_agent_workflow_status"].includes(n));
    const hasMCPReadonly = allTools.filter((t) => t.risk_level === "READ_ONLY").length >= 3;
    const hasMCPWrite = allTools.filter((t) => t.risk_level === "LOW_WRITE" || t.risk_level === "APPROVAL_REQUIRED").length >= 3;
    const hasUI = true; // This page IS the UI

    const items: ReadinessCheck[] = [
      { key: "LOCAL_FUNNEL_READY",        label: "Funnel Readiness",       status: hasFunnelTools ? "ready" : "not_ready", details: hasFunnelTools ? "Funnel tools registered" : "Missing funnel tools" },
      { key: "LOCAL_MCP_READONLY_READY",  label: "MCP Readonly",          status: hasMCPReadonly ? "ready" : "not_ready", details: `${allTools.filter((t) => t.risk_level === 'READ_ONLY').length} READ_ONLY tools` },
      { key: "LOCAL_MCP_WRITE_READY",     label: "MCP Write",             status: hasMCPWrite ? "ready" : "not_ready", details: `${allTools.filter((t) => t.risk_level === 'LOW_WRITE' || t.risk_level === 'APPROVAL_REQUIRED').length} write tools` },
      { key: "LOCAL_WORKSPACE_READY",     label: "Workspace Readiness",   status: hasWorkspaceTools ? "ready" : "not_ready", details: hasWorkspaceTools ? "Workspace tools registered" : "Missing workspace tools" },
      { key: "LOCAL_CONTEXT_READY",       label: "Context Readiness",     status: hasContextTools ? "ready" : "not_ready", details: hasContextTools ? "Context engine tools registered" : "Missing context tools" },
      { key: "LOCAL_WORKFLOW_READY",      label: "Workflow Readiness",    status: hasWorkflowTools ? "ready" : "not_ready", details: hasWorkflowTools ? "Workflow tools registered" : "Missing workflow tools" },
      { key: "LOCAL_UI_READY",            label: "UI Readiness",          status: "ready", details: "Operator UI is loaded and operational" },
      { key: "FULL_LOCAL_AGENT_READY",    label: "Full Agent Readiness",  status: hasFunnelTools && hasWorkspaceTools && hasContextTools && hasWorkflowTools && hasUI ? "ready" : "not_ready", details: "All local systems must be ready" },
    ];

    setChecks(items);
    setLoading(false);
  }

  const allReady = checks.every((c) => c.status === "ready");

  return (
    <div className="space-y-6">
      <PageHeader
        title="Readiness"
        description="Final local readiness checklist."
      />

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-white" />
        </div>
      )}

      {!loading && (
        <>
          {/* Overall status */}
          <div className={cn(
            "rounded-xl border p-4 flex items-center gap-3",
            allReady ? "border-emerald-500/20 bg-emerald-500/5" : "border-amber-500/20 bg-amber-500/5"
          )}>
            {allReady ? (
              <CheckCircle2 className="h-6 w-6 text-emerald-400 flex-shrink-0" />
            ) : (
              <AlertTriangle className="h-6 w-6 text-amber-400 flex-shrink-0" />
            )}
            <div>
              <div className={cn(
                "text-sm font-medium",
                allReady ? "text-emerald-400" : "text-amber-400"
              )}>
                {allReady ? "All local systems ready" : "Some systems not yet ready"}
              </div>
              <div className="text-xs text-zinc-500 mt-1">
                {checks.filter((c) => c.status === "ready").length}/{checks.length} checks passing
              </div>
            </div>
            <Button variant="outline" size="sm" onClick={loadReadiness} className="ml-auto" loading={loading}>
              <RefreshCw className="h-4 w-4" /> Re-check
            </Button>
          </div>

          {/* Readiness checks */}
          <Panel title="Local Readiness" eyebrow="STATUS">
            <div className="space-y-2">
              {checks.map((check) => (
                <div key={check.key} className="flex items-center gap-3 rounded-lg border border-zinc-800 bg-zinc-900/40 p-3">
                  <StatusBadge status={check.status} />
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-white">{check.label}</div>
                    <div className="text-xs text-zinc-500">{check.details}</div>
                  </div>
                  <span className="text-[10px] font-mono text-zinc-600">{check.key}</span>
                </div>
              ))}
            </div>
          </Panel>

          {/* Staging / Production blockers */}
          <Panel title="Staging &amp; Production" eyebrow="BLOCKERS">
            <div className="space-y-3">
              <div className="flex items-center gap-3 rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                <XCircle className="h-5 w-5 text-red-400 flex-shrink-0" />
                <div>
                  <div className="text-sm font-medium text-red-400">STAGING_READY: false</div>
                  <div className="text-xs text-zinc-500 mt-1">
                    Needs: real auth/org context, production-safe ApprovalRequest organization_id column,
                    rate limiting, monitoring/alerting, backups, real provider configs, staging smoke, deployment rollback
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3 rounded-lg border border-red-500/20 bg-red-500/5 p-3">
                <XCircle className="h-5 w-5 text-red-400 flex-shrink-0" />
                <div>
                  <div className="text-sm font-medium text-red-400">PRODUCTION_READY: false</div>
                  <div className="text-xs text-zinc-500 mt-1">
                    Needs: all staging requirements + production smoke, support/refund/policy pages,
                    deployment rollback tested, security audit, database backup verification
                  </div>
                </div>
              </div>
            </div>
          </Panel>

          {/* Tool summary */}
          {tools.length > 0 && (
            <Panel title="Registered Tools" eyebrow="MCP">
              <div className="text-xs text-zinc-400">
                {tools.length} tools registered across {
                  [...new Set(tools.map((t) => t.name?.split("_")[0] || "other"))].join(", ")
                } categories.
              </div>
              <div className="mt-2 flex flex-wrap gap-1">
                {tools.map((t) => (
                  <span key={t.name} className={cn(
                    "rounded px-1.5 py-0.5 text-[10px] font-mono",
                    t.risk_level === "DANGEROUS_BLOCKED" ? "bg-red-900/20 text-red-400" :
                    t.risk_level === "APPROVAL_REQUIRED" ? "bg-violet-900/20 text-violet-400" :
                    t.risk_level === "LOW_WRITE" ? "bg-amber-900/20 text-amber-400" :
                    "bg-blue-900/20 text-blue-400"
                  )}>
                    {t.name}
                  </span>
                ))}
              </div>
            </Panel>
          )}
        </>
      )}
    </div>
  );
}
