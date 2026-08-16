/**
 * Revenue OS API client — talks to the standalone Revenue OS API
 * (graxia/services/revenue_os_api), NOT the main backend.
 *
 * Base URL: VITE_REVENUE_OS_API_URL (default http://localhost:8001/api)
 * Admin key: VITE_REVENUE_OS_ADMIN_KEY or localStorage "revenue_os_admin_key"
 */
import axios from "axios";

const REVENUE_OS_BASE_URL = (
  import.meta.env.VITE_REVENUE_OS_API_URL || "http://localhost:8001/api"
).replace(/\/+$/, "");

export const revenueOsClient = axios.create({
  baseURL: REVENUE_OS_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// Attach admin key on every request (read at request time so the user can
// update it in Settings without a reload).
revenueOsClient.interceptors.request.use((config) => {
  const key =
    import.meta.env.VITE_REVENUE_OS_ADMIN_KEY ||
    localStorage.getItem("revenue_os_admin_key") ||
    "";
  if (key) {
    config.headers["X-Admin-Api-Key"] = key;
  }
  return config;
});

// ── Types (mirror graxia/packages/revenue_os/schemas_pkg/ceo_schemas.py) ──

export interface RevenueMetrics {
  today_cents: number;
  week_cents: number;
  month_cents: number;
  pending_orders: number;
  refunds_today: number;
}

export interface CampaignStats {
  active: number;
  paused: number;
  over_budget: number;
  needs_approval: number;
}

export interface ApprovalStats {
  pending_total: number;
  high_priority: number;
  expiring_soon: number;
  approved_today: number;
}

export interface IncidentStats {
  critical_open: number;
  high_open: number;
  total_open: number;
  resolved_today: number;
}

export interface AgentStats {
  pending_bwcp_messages: number;
  pending_outbox_events: number;
  failed_outbox_events: number;
  new_leads_today: number;
}

export interface CEODashboardSummary {
  generated_at: string;
  revenue: RevenueMetrics;
  campaigns: CampaignStats;
  approvals: ApprovalStats;
  incidents: IncidentStats;
  agent_activity: AgentStats;
}

export interface ApprovalItem {
  id: string;
  approval_type: string;
  title: string;
  priority: string;
  requested_by: string;
  created_at?: string;
  expires_at?: string;
}

export interface ApprovalQueue {
  pending: ApprovalItem[];
  total_pending: number;
}

export interface CriticalIncidents {
  critical: Array<{
    id: string;
    title: string;
    description?: string;
    severity: string;
    created_at?: string;
  }>;
  high: Array<{ id: string; title: string; severity: string; created_at?: string }>;
}

// ── API methods ──

export const revenueOsApi = {
  getSummary: async (): Promise<CEODashboardSummary> => {
    const { data } = await revenueOsClient.get("/ceo-dashboard/summary");
    return data;
  },
  getApprovalQueue: async (): Promise<ApprovalQueue> => {
    const { data } = await revenueOsClient.get("/ceo-dashboard/approvals");
    return data;
  },
  getCriticalIncidents: async (): Promise<CriticalIncidents> => {
    const { data } = await revenueOsClient.get("/ceo-dashboard/incidents");
    return data;
  },
  decideApproval: async (
    approvalId: string,
    decision: "approve" | "reject",
    note?: string,
  ): Promise<unknown> => {
    const { data } = await revenueOsClient.post(
      `/approvals/${approvalId}/decide`,
      { decision, note },
    );
    return data;
  },
};

export function formatBaht(cents: number): string {
  return `฿${(cents / 100).toLocaleString("th-TH", {
    maximumFractionDigits: 0,
  })}`;
}