/**
 * Revenue OS v12 API Client
 * Enterprise-grade API integration with caching and error handling
 */
import axios, { AxiosError, AxiosInstance } from "axios";

// Types
export interface CEODashboardSummary {
  generated_at: string;
  revenue: {
    today_cents: number;
    week_cents: number;
    month_cents: number;
    pending_orders: number;
    refunds_today: number;
  };
  campaigns: {
    active: number;
    paused: number;
    over_budget: number;
    needs_approval: number;
  };
  approvals: {
    pending_total: number;
    high_priority: number;
    expiring_soon: number;
    approved_today: number;
  };
  incidents: {
    critical_open: number;
    high_open: number;
    total_open: number;
    resolved_today: number;
  };
  agent_activity: {
    pending_bwcp_messages: number;
    pending_outbox_events: number;
    failed_outbox_events: number;
    new_leads_today: number;
  };
}

export interface BWCPMessage {
  id: string;
  conversation_id: string;
  sender_agent: string;
  recipient_agent: string;
  message_type: string;
  belief?: string;
  will?: string;
  can?: Record<string, unknown>;
  plan?: Record<string, unknown>;
  campaign_id?: string;
  lead_id?: string;
  approval_id?: string;
  incident_id?: string;
  delivered: boolean;
  delivered_at?: string;
  read_at?: string;
  created_at: string;
}

export interface BWCPMessageList {
  items: BWCPMessage[];
  total: number;
  limit: number;
  offset: number;
}

export interface OutboxEvent {
  id: string;
  aggregate_type: string;
  aggregate_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  headers?: Record<string, unknown>;
  correlation_id?: string;
  processed: boolean;
  processed_at?: string;
  retry_count: number;
  last_error?: string;
  created_at: string;
}

export interface OutboxEventList {
  items: OutboxEvent[];
  total: number;
  limit: number;
  offset: number;
}

export interface OutboxStats {
  total: number;
  processed: number;
  unprocessed: number;
  failed: number;
  by_aggregate_type: Record<string, number>;
  by_event_type: Record<string, number>;
  avg_processing_seconds?: number;
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

export interface CriticalIncidentItem {
  id: string;
  title: string;
  description?: string;
  severity: string;
  created_at?: string;
  related_campaign_id?: string;
}

export interface CampaignPerformance {
  top_performers: Array<{
    id: string;
    name: string;
    revenue_cents: number;
    spent_cents: number;
    roas: number;
  }>;
  needs_attention: Array<{
    id: string;
    name: string;
    budget_cents: number;
    spent_cents: number;
    spend_percentage: number;
  }>;
}

// API Client Configuration
const API_BASE_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

class RevenueOSAPI {
  private client: AxiosInstance;

  constructor(apiKey: string) {
    this.client = axios.create({
      baseURL: `${API_BASE_URL}/api`,
      timeout: 30000,
      headers: {
        "Content-Type": "application/json",
        "X-API-Key": apiKey,
      },
    });

    // Response interceptor for error handling
    this.client.interceptors.response.use(
      (response) => response,
      (error: AxiosError) => {
        if (error.response?.status === 401) {
          // console.error('RevenueOS API: Unauthorized - Invalid API Key');
          window.dispatchEvent(new CustomEvent("revenue-os:auth-error"));
        }
        return Promise.reject(error);
      },
    );
  }

  // CEO Dashboard
  async getDashboardSummary(): Promise<CEODashboardSummary> {
    const response = await this.client.get<CEODashboardSummary>(
      "/ceo-dashboard/summary",
    );
    return response.data;
  }

  async getRevenueMetrics(days: number = 30): Promise<{
    period_days: number;
    daily_breakdown: Array<{
      date: string;
      revenue_cents: number;
      orders: number;
    }>;
    by_platform: Record<string, { revenue_cents: number; orders: number }>;
  }> {
    const response = await this.client.get("/ceo-dashboard/revenue", {
      params: { days },
    });
    return response.data;
  }

  async getCampaignPerformance(): Promise<CampaignPerformance> {
    const response = await this.client.get<CampaignPerformance>(
      "/ceo-dashboard/campaigns",
    );
    return response.data;
  }

  async getApprovalQueue(): Promise<{
    pending: ApprovalItem[];
    total_pending: number;
  }> {
    const response = await this.client.get("/ceo-dashboard/approvals");
    return response.data;
  }

  async getCriticalIncidents(): Promise<{
    critical: CriticalIncidentItem[];
    high: CriticalIncidentItem[];
  }> {
    const response = await this.client.get("/ceo-dashboard/incidents");
    return response.data;
  }

  // BWCP Messages
  async getBWCPInbox(
    recipientAgent: string,
    options?: { delivered?: boolean; limit?: number; offset?: number },
  ): Promise<BWCPMessageList> {
    const response = await this.client.get<BWCPMessageList>(
      `/bwcp/inbox/${recipientAgent}`,
      {
        params: options,
      },
    );
    return response.data;
  }

  async getBWCPConversation(conversationId: string): Promise<{
    conversation_id: string;
    messages: BWCPMessage[];
    message_count: number;
    participants: string[];
    started_at?: string;
    last_message_at?: string;
  }> {
    const response = await this.client.get(
      `/bwcp/conversation/${conversationId}`,
    );
    return response.data;
  }

  async getBWCPMessages(filters?: {
    sender_agent?: string;
    recipient_agent?: string;
    message_type?: string;
    delivered?: boolean;
    limit?: number;
    offset?: number;
  }): Promise<BWCPMessageList> {
    const response = await this.client.get<BWCPMessageList>("/bwcp/messages", {
      params: filters,
    });
    return response.data;
  }

  async getBWCPUnreadCount(recipientAgent: string): Promise<{
    recipient_agent: string;
    total_undelivered: number;
    by_type: Record<string, number>;
  }> {
    const response = await this.client.get(
      `/bwcp/unread-count/${recipientAgent}`,
    );
    return response.data;
  }

  async markBWCPMessageDelivered(messageId: string): Promise<BWCPMessage> {
    const response = await this.client.post<BWCPMessage>(
      `/bwcp/messages/${messageId}/delivered`,
    );
    return response.data;
  }

  async markBWCPMessageRead(messageId: string): Promise<BWCPMessage> {
    const response = await this.client.post<BWCPMessage>(
      `/bwcp/messages/${messageId}/read`,
    );
    return response.data;
  }

  async getBWCPStats(): Promise<{
    by_sender: Record<string, number>;
    by_recipient: Record<string, number>;
    by_type: Record<string, number>;
    total_undelivered: number;
  }> {
    const response = await this.client.get("/bwcp/stats");
    return response.data;
  }

  // Outbox Events
  async getOutboxEvents(filters?: {
    aggregate_type?: string;
    event_type?: string;
    processed?: boolean;
    retry_count_max?: number;
    limit?: number;
    offset?: number;
  }): Promise<OutboxEventList> {
    const response = await this.client.get<OutboxEventList>("/outbox/events", {
      params: filters,
    });
    return response.data;
  }

  async getOutboxEvent(eventId: string): Promise<OutboxEvent> {
    const response = await this.client.get<OutboxEvent>(
      `/outbox/events/${eventId}`,
    );
    return response.data;
  }

  async getOutboxStats(): Promise<OutboxStats> {
    const response = await this.client.get<OutboxStats>("/outbox/stats");
    return response.data;
  }

  async retryOutboxEvent(eventId: string): Promise<OutboxEvent> {
    const response = await this.client.post<OutboxEvent>(
      `/outbox/events/${eventId}/retry`,
    );
    return response.data;
  }

  async getFailedOutboxEvents(
    limit: number = 50,
    offset: number = 0,
  ): Promise<OutboxEventList> {
    const response = await this.client.get<OutboxEventList>("/outbox/failed", {
      params: { limit, offset },
    });
    return response.data;
  }

  async getPendingOutboxEvents(
    maxRetryCount: number = 2,
    limit: number = 50,
    offset: number = 0,
  ): Promise<OutboxEventList> {
    const response = await this.client.get<OutboxEventList>("/outbox/pending", {
      params: { max_retry_count: maxRetryCount, limit, offset },
    });
    return response.data;
  }

  async cleanupOldOutboxEvents(retentionDays: number = 30): Promise<{
    deleted_count: number;
    retention_days: number;
    cutoff_date: string;
  }> {
    const response = await this.client.post("/outbox/cleanup", null, {
      params: { retention_days: retentionDays },
    });
    return response.data;
  }
}

// Singleton instance
let apiInstance: RevenueOSAPI | null = null;

export function initializeRevenueOSAPI(apiKey: string): RevenueOSAPI {
  apiInstance = new RevenueOSAPI(apiKey);
  return apiInstance;
}

export function getRevenueOSAPI(): RevenueOSAPI {
  if (!apiInstance) {
    // TODO: replace with backend proxy endpoint — API key must stay server-side
    const apiKey = "";
    if (!apiKey) {
      // console.warn('RevenueOS API Key not configured');
    }
    return initializeRevenueOSAPI(apiKey);
  }
  return apiInstance;
}

export { RevenueOSAPI };
