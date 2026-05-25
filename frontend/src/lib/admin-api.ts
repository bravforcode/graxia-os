/**
 * Admin MCP client — JSON-RPC over HTTP for the local Operator UI.
 *
 * All calls go through the MCP JSON-RPC endpoint at POST /api/v1/mcp/.
 * Default org ID is the local dev placeholder.
 */
import axios, { type AxiosError } from "axios";

export const LOCAL_DEV_ORGANIZATION_ID = "00000000-0000-0000-0000-000000000001";

// ─── JSON-RPC helpers ────────────────────────────────────────────────────────

let jsonrpcId = 1;

async function jsonrpcCall<T = unknown>(
  method: string,
  params: Record<string, unknown> = {},
  orgId?: string,
): Promise<{ ok: boolean; data?: { items?: T[]; total?: number; [k: string]: unknown }; error?: { code: string; message: string }; meta?: Record<string, unknown> }> {
  const id = jsonrpcId++;
  const body = {
    jsonrpc: "2.0" as const,
    id,
    method,
    params: {
      ...params,
      organization_id: orgId || LOCAL_DEV_ORGANIZATION_ID,
    },
  };

  try {
    const { data: response } = await axios.post("/api/v1/mcp/", body);
    if (response?.error) {
      return { ok: false, error: response.error };
    }
    const result = response?.result || response;
    return { ok: true, data: result, meta: result?.meta };
  } catch (err) {
    const axiosErr = err as AxiosError<{ detail?: string }>;
    const detail = axiosErr.response?.data?.detail || axiosErr.message || "Request failed";
    return { ok: false, error: { code: "HTTP_ERROR", message: detail } };
  }
}

// ─── Tool types ──────────────────────────────────────────────────────────────

export interface MCPToolDefinition {
  name: string;
  description: string;
  risk_level: string;
  requires_approval: boolean;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  category?: string;
}

export interface MCPToolCallResponse {
  ok: boolean;
  data?: Record<string, unknown>;
  error?: { code: string; message: string };
  meta?: { request_id?: string; risk_level?: string; approval_request_id?: string; summary?: string };
}

export interface WorkflowDefinition {
  workflow_type: string;
  description: string;
  risk_level: string;
  allowed_tools: string[];
  blocked_tools: string[];
}

export interface WorkflowRunSummary {
  workflow_run_id: string;
  workflow_type: string;
  status: string;
  summary?: string;
  context_pack_ids: string[];
  approval_request_ids: string[];
  workspace_item_ids: string[];
  steps_completed: number;
  steps_failed: number;
}

export interface WorkflowRunDetail {
  workflow_run_id: string;
  organization_id: string;
  workflow_type: string;
  status: string;
  actor_type: string;
  actor_id: string | null;
  started_at: string;
  completed_at: string | null;
  current_step: string | null;
  context_pack_ids: string[];
  approval_request_ids: string[];
  workspace_item_ids: string[];
  tool_call_refs: { request_id: string; tool_name: string; risk_level: string; status: string; summary: string }[];
  output_summary: string | null;
  error_code: string | null;
  error_message: string | null;
  steps: {
    step_id: string;
    step_name: string;
    status: string;
    started_at: string | null;
    completed_at: string | null;
    tool_name: string | null;
    tool_result_summary: string | null;
    error_code: string | null;
  }[];
  metadata: Record<string, unknown>;
}

export interface WorkflowStatus {
  total_runs: number;
  completed: number;
  failed: number;
  latest_run_id: string | null;
}

export interface WorkflowPolicy {
  workflow_type: string;
  allowed_tools: string[];
  blocked_tools: string[];
  max_steps: number;
  token_budget: number;
  allow_real_external_calls: boolean;
  allow_customer_send: boolean;
  allow_publish: boolean;
}

export interface ApprovalRequestSummary {
  id: string;
  title: string;
  action_type: string;
  subject_type: string | null;
  subject_id: string | null;
  status: string;
  policy_class: string;
  requested_by: string | null;
  details: Record<string, unknown> | null;
  preview: Record<string, unknown> | null;
  created_at: string | null;
}

export interface ContextPack {
  context_pack_id: string;
  task_type: string;
  goal: string;
  token_budget: number;
  estimated_tokens: number;
  included_files: { path: string; size: number; estimated_tokens: number }[];
  content_mode: string;
  summaries: string[];
  diffs: { path: string; added: number; removed: number }[];
  constraints: string[];
  warnings: string[];
  excluded_file_count: number;
  secret_safety_status: string;
}

export interface FunnelAnalytics {
  revenue_summary?: Record<string, unknown>;
  orders_summary?: Record<string, unknown>;
  conversion_summary?: Record<string, unknown>;
  checkout_abandonment?: Record<string, unknown>;
  delivery_open_rate?: Record<string, unknown>;
  lead_captures?: Record<string, unknown>;
  pending_approvals?: number;
  recommendations?: string[];
}

export interface WorkspaceExportItem {
  id: string;
  type: "doc" | "sheet" | "email_draft" | "drive_file" | "calendar_plan";
  title: string;
  summary: string;
  status: string;
  is_mock: boolean;
  approval_required: boolean;
  created_at: string;
}

// ─── MCP Tool functions ──────────────────────────────────────────────────────

export async function listTools(orgId?: string): Promise<MCPToolDefinition[]> {
  const res = await jsonrpcCall<MCPToolDefinition>("tools/list", {}, orgId);
  if (!res.ok || !res.data) return [];
  const tools = res.data.tools || res.data.items || [];
  return tools as MCPToolDefinition[];
}

export async function callTool(
  name: string,
  arguments_: Record<string, unknown> = {},
  orgId?: string,
): Promise<MCPToolCallResponse> {
  const res = await jsonrpcCall("tools/call", { name, arguments: arguments_ }, orgId);
  if (!res.ok) {
    return {
      ok: false,
      error: res.error || { code: "UNKNOWN", message: "Tool call failed" },
    };
  }
  const resultData = res.data as Record<string, unknown> | undefined;
  return {
    ok: true,
    data: resultData,
    meta: res.meta as Record<string, unknown> | undefined,
  };
}

// ─── Workflow functions ──────────────────────────────────────────────────────

export async function listAgentWorkflows(orgId?: string): Promise<WorkflowDefinition[]> {
  const res = await jsonrpcCall<WorkflowDefinition>("tools/call", {
    name: "list_agent_workflows",
    arguments: {},
  }, orgId);
  if (!res.ok || !res.data) return [];
  return (res.data.items || []) as WorkflowDefinition[];
}

export async function runAgentWorkflow(
  workflowType: string,
  inputs: Record<string, unknown> = {},
  orgId?: string,
): Promise<WorkflowRunSummary | null> {
  const res = await jsonrpcCall("tools/call", {
    name: "run_agent_workflow",
    arguments: {
      workflow_type: workflowType,
      inputs,
    },
  }, orgId);
  if (!res.ok || !res.data) return null;
  return res.data as unknown as WorkflowRunSummary;
}

export async function getAgentWorkflowRun(
  runId: string,
  orgId?: string,
): Promise<WorkflowRunDetail | null> {
  const res = await jsonrpcCall("tools/call", {
    name: "get_agent_workflow_run",
    arguments: { workflow_run_id: runId },
  }, orgId);
  if (!res.ok || !res.data) return null;
  return (res.data.workflow_run || res.data) as unknown as WorkflowRunDetail;
}

export async function getAgentWorkflowStatus(orgId?: string): Promise<WorkflowStatus | null> {
  const res = await jsonrpcCall("tools/call", {
    name: "get_agent_workflow_status",
    arguments: {},
  }, orgId);
  if (!res.ok || !res.data) return null;
  return res.data as unknown as WorkflowStatus;
}

export async function getAgentWorkflowPolicy(
  workflowType: string,
  orgId?: string,
): Promise<WorkflowPolicy | null> {
  const res = await jsonrpcCall("tools/call", {
    name: "get_agent_workflow_policy",
    arguments: { workflow_type: workflowType },
  }, orgId);
  if (!res.ok || !res.data) return null;
  return res.data as unknown as WorkflowPolicy;
}

// ─── Context functions ───────────────────────────────────────────────────────

export async function buildContextPack(
  input: { task_type: string; goal: string; token_budget?: number; query?: string; must_preserve?: string[] },
  orgId?: string,
): Promise<Record<string, unknown> | null> {
  const res = await jsonrpcCall("tools/call", {
    name: "build_context_pack",
    arguments: input,
  }, orgId);
  if (!res.ok || !res.data) return null;
  return res.data;
}

export async function searchProjectContext(query: string, orgId?: string): Promise<Record<string, unknown> | null> {
  const res = await jsonrpcCall("tools/call", {
    name: "search_project_context",
    arguments: { query },
  }, orgId);
  if (!res.ok || !res.data) return null;
  return res.data;
}

export async function getProjectIndexSummary(orgId?: string): Promise<Record<string, unknown> | null> {
  const res = await jsonrpcCall("tools/call", {
    name: "get_project_index_summary",
    arguments: {},
  }, orgId);
  if (!res.ok || !res.data) return null;
  return res.data;
}

export async function getContextPack(contextPackId: string, orgId?: string): Promise<ContextPack | null> {
  const res = await jsonrpcCall("tools/call", {
    name: "get_context_pack",
    arguments: { context_pack_id: contextPackId },
  }, orgId);
  if (!res.ok || !res.data) return null;
  return res.data as unknown as ContextPack;
}

// ─── Funnel / Workspace / Approvals ──────────────────────────────────────────

export async function getFunnelAnalytics(orgId?: string): Promise<FunnelAnalytics | null> {
  // Use read-only funnel tools to gather analytics
  const [revenue, orders, conversion, abandonment, delivery] = await Promise.all([
    safeToolCall("get_revenue_summary", {}, orgId),
    safeToolCall("get_recent_orders", {}, orgId),
    safeToolCall("get_conversion_summary", {}, orgId),
    safeToolCall("get_checkout_abandonment", {}, orgId),
    safeToolCall("get_delivery_open_rate", {}, orgId),
  ]);
  return {
    revenue_summary: revenue?.ok ? (revenue.data as Record<string, unknown>) : undefined,
    orders_summary: orders?.ok ? (orders.data as Record<string, unknown>) : undefined,
    conversion_summary: conversion?.ok ? (conversion.data as Record<string, unknown>) : undefined,
    checkout_abandonment: abandonment?.ok ? (abandonment.data as Record<string, unknown>) : undefined,
    delivery_open_rate: delivery?.ok ? (delivery.data as Record<string, unknown>) : undefined,
  };
}

export async function getApprovals(
  params?: { status?: string; limit?: number; offset?: number },
  _orgId?: string,
): Promise<ApprovalRequestSummary[]> {
  try {
    const { default: api } = await import("./api");
    const result = await api.getApprovals(params);
    return (result.items || []) as unknown as ApprovalRequestSummary[];
  } catch {
    return [];
  }
}

export async function getApprovalById(id: string): Promise<ApprovalRequestSummary | null> {
  try {
    const approvals = await getApprovals({ limit: 200 });
    const found = approvals.find((a) => a.id === id);
    return found || null;
  } catch {
    return null;
  }
}

export async function approveApproval(id: string, note?: string): Promise<boolean> {
  try {
    const { default: api } = await import("./api");
    await api.approveApproval(id, note);
    return true;
  } catch {
    return false;
  }
}

export async function rejectApproval(id: string, note?: string): Promise<boolean> {
  try {
    const { default: api } = await import("./api");
    await api.rejectApproval(id, note);
    return true;
  } catch {
    return false;
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

async function safeToolCall(
  name: string,
  args: Record<string, unknown> = {},
  orgId?: string,
): Promise<MCPToolCallResponse> {
  return callTool(name, args, orgId);
}

export async function createWorkspaceDoc(
  docType: string,
  title: string,
  content: string,
  orgId?: string,
): Promise<MCPToolCallResponse> {
  return callTool("create_launch_doc", {
    doc_type: docType,
    title,
    content,
  }, orgId);
}

export async function createWorkspaceSheet(
  sheetType: string,
  rows: Record<string, unknown>[],
  orgId?: string,
): Promise<MCPToolCallResponse> {
  return callTool("export_revenue_summary_to_sheet", {
    sheet_type: sheetType,
    rows,
  }, orgId);
}

// ─── Redaction helpers ───────────────────────────────────────────────────────

const REDACTED_KEYS = [
  "secret", "token", "password", "key", "credential",
  "private", "authorization", "cookie", "stripe",
  "oauth", "database_url", "api_key", "access_key",
];

export function isRedactedKey(key: string): boolean {
  const lower = key.toLowerCase();
  return REDACTED_KEYS.some((rk) => lower.includes(rk));
}

export function redactValue(key: string, value: unknown): unknown {
  if (isRedactedKey(key)) {
    if (typeof value === "string" && value.length > 4) {
      return `${value.slice(0, 2)}****${value.slice(-2)}`;
    }
    return "***REDACTED***";
  }
  return value;
}

export function deepRedact(obj: unknown, depth = 0): unknown {
  if (depth > 10) return "[MAX_DEPTH]";
  if (obj === null || obj === undefined) return obj;
  if (typeof obj === "string") return obj;
  if (typeof obj === "number" || typeof obj === "boolean") return obj;
  if (Array.isArray(obj)) {
    return obj.map((item) => deepRedact(item, depth + 1));
  }
  if (typeof obj === "object") {
    const result: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(obj as Record<string, unknown>)) {
      result[k] = isRedactedKey(k) ? redactValue(k, v) : deepRedact(v, depth + 1);
    }
    return result;
  }
  return String(obj);
}
