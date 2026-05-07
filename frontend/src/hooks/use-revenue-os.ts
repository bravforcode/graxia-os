/**
 * Revenue OS v12 React Query Hooks
 * Enterprise-grade data fetching with caching and real-time updates
 */
import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationOptions,
  type UseQueryOptions,
} from "@tanstack/react-query";
import { useEffect } from "react";
import {
  getRevenueOSAPI,
  type BWCPMessage,
  type CEODashboardSummary,
  type OutboxEvent,
} from "../lib/api/revenue-os";
import type {
  ApprovalEvent,
  BWCPMessageEvent,
  IncidentEvent,
} from "../lib/websocket/revenue-os-ws";
import { getRevenueOSWebSocket } from "../lib/websocket/revenue-os-ws";
import { useRevenueOSStore } from "../store/revenue-os-store";

// API Instance
const api = getRevenueOSAPI();

// Query Keys
export const revenueOSKeys = {
  all: ["revenue-os"] as const,
  dashboard: () => [...revenueOSKeys.all, "dashboard"] as const,
  revenue: (days: number) => [...revenueOSKeys.all, "revenue", days] as const,
  campaigns: () => [...revenueOSKeys.all, "campaigns"] as const,
  approvals: () => [...revenueOSKeys.all, "approvals"] as const,
  incidents: () => [...revenueOSKeys.all, "incidents"] as const,
  bwcp: {
    all: () => [...revenueOSKeys.all, "bwcp"] as const,
    inbox: (agent: string) =>
      [...revenueOSKeys.bwcp.all(), "inbox", agent] as const,
    conversation: (id: string) =>
      [...revenueOSKeys.bwcp.all(), "conversation", id] as const,
    messages: () => [...revenueOSKeys.bwcp.all(), "messages"] as const,
    stats: () => [...revenueOSKeys.bwcp.all(), "stats"] as const,
  },
  outbox: {
    all: () => [...revenueOSKeys.all, "outbox"] as const,
    events: () => [...revenueOSKeys.outbox.all(), "events"] as const,
    stats: () => [...revenueOSKeys.outbox.all(), "stats"] as const,
    pending: () => [...revenueOSKeys.outbox.all(), "pending"] as const,
    failed: () => [...revenueOSKeys.outbox.all(), "failed"] as const,
  },
};

// ==========================================
// CEO Dashboard Hooks
// ==========================================

export function useDashboardSummary(
  options?: UseQueryOptions<CEODashboardSummary>,
) {
  const setDashboard = useRevenueOSStore((state) => state.setDashboard);
  const setDashboardLoading = useRevenueOSStore(
    (state) => state.setDashboardLoading,
  );

  return useQuery({
    queryKey: revenueOSKeys.dashboard(),
    queryFn: async () => {
      setDashboardLoading(true);
      try {
        const data = await api.getDashboardSummary();
        setDashboard(data);
        return data;
      } finally {
        setDashboardLoading(false);
      }
    },
    refetchInterval: 30000, // Refetch every 30s
    staleTime: 15000, // Consider stale after 15s
    ...options,
  });
}

export function useRevenueMetrics(
  days: number = 30,
  options?: UseQueryOptions,
) {
  return useQuery({
    queryKey: revenueOSKeys.revenue(days),
    queryFn: () => api.getRevenueMetrics(days),
    staleTime: 60000, // 1 minute
    ...options,
  });
}

export function useCampaignPerformance(options?: UseQueryOptions) {
  const setCampaignPerformance = useRevenueOSStore(
    (state) => state.setCampaignPerformance,
  );
  const setCampaignsLoading = useRevenueOSStore(
    (state) => state.setCampaignsLoading,
  );

  return useQuery({
    queryKey: revenueOSKeys.campaigns(),
    queryFn: async () => {
      setCampaignsLoading(true);
      try {
        const data = await api.getCampaignPerformance();
        setCampaignPerformance(data);
        return data;
      } finally {
        setCampaignsLoading(false);
      }
    },
    refetchInterval: 60000, // Refetch every minute
    ...options,
  });
}

export function useApprovalQueue(options?: UseQueryOptions) {
  const setApprovalQueue = useRevenueOSStore((state) => state.setApprovalQueue);
  const setApprovalsLoading = useRevenueOSStore(
    (state) => state.setApprovalsLoading,
  );

  return useQuery({
    queryKey: revenueOSKeys.approvals(),
    queryFn: async () => {
      setApprovalsLoading(true);
      try {
        const data = await api.getApprovalQueue();
        setApprovalQueue(data.pending);
        return data;
      } finally {
        setApprovalsLoading(false);
      }
    },
    refetchInterval: 15000, // Refetch every 15s for approvals
    ...options,
  });
}

export function useCriticalIncidents(options?: UseQueryOptions) {
  const setCriticalIncidents = useRevenueOSStore(
    (state) => state.setCriticalIncidents,
  );
  const setIncidentsLoading = useRevenueOSStore(
    (state) => state.setIncidentsLoading,
  );

  return useQuery({
    queryKey: revenueOSKeys.incidents(),
    queryFn: async () => {
      setIncidentsLoading(true);
      try {
        const data = await api.getCriticalIncidents();
        setCriticalIncidents(data.critical, data.high);
        return data;
      } finally {
        setIncidentsLoading(false);
      }
    },
    refetchInterval: 10000, // Refetch every 10s for incidents
    ...options,
  });
}

// ==========================================
// BWCP Hooks
// ==========================================

export function useBWCPInbox(
  recipientAgent: string,
  options?: { delivered?: boolean; limit?: number },
) {
  const setBWCPMessages = useRevenueOSStore((state) => state.setBWCPMessages);
  const setBWCPLoading = useRevenueOSStore((state) => state.setBWCPLoading);

  return useQuery({
    queryKey: revenueOSKeys.bwcp.inbox(recipientAgent),
    queryFn: async () => {
      setBWCPLoading(true);
      try {
        const data = await api.getBWCPInbox(recipientAgent, options);
        setBWCPMessages(data.items);
        return data;
      } finally {
        setBWCPLoading(false);
      }
    },
    enabled: !!recipientAgent,
    refetchInterval: 10000,
  });
}

export function useBWCPConversation(
  conversationId: string,
  options?: UseQueryOptions,
) {
  return useQuery({
    queryKey: revenueOSKeys.bwcp.conversation(conversationId),
    queryFn: () => api.getBWCPConversation(conversationId),
    enabled: !!conversationId,
    ...options,
  });
}

export function useBWCPStats(options?: UseQueryOptions) {
  return useQuery({
    queryKey: revenueOSKeys.bwcp.stats(),
    queryFn: () => api.getBWCPStats(),
    refetchInterval: 30000,
    ...options,
  });
}

export function useMarkBWCPDelivered(
  options?: UseMutationOptions<BWCPMessage, Error, string>,
) {
  const queryClient = useQueryClient();
  const markBWCPDelivered = useRevenueOSStore(
    (state) => state.markBWCPDelivered,
  );

  return useMutation({
    mutationFn: (messageId: string) => api.markBWCPMessageDelivered(messageId),
    onSuccess: (data) => {
      markBWCPDelivered(data.id);
      queryClient.invalidateQueries({ queryKey: revenueOSKeys.bwcp.all() });
    },
    ...options,
  });
}

export function useMarkBWCPRead(
  options?: UseMutationOptions<BWCPMessage, Error, string>,
) {
  const queryClient = useQueryClient();
  const markBWCPRead = useRevenueOSStore((state) => state.markBWCPRead);

  return useMutation({
    mutationFn: (messageId: string) => api.markBWCPMessageRead(messageId),
    onSuccess: (data) => {
      markBWCPRead(data.id);
      queryClient.invalidateQueries({ queryKey: revenueOSKeys.bwcp.all() });
    },
    ...options,
  });
}

// ==========================================
// Outbox Hooks
// ==========================================

export function useOutboxEvents(
  filters?: {
    processed?: boolean;
    aggregate_type?: string;
    limit?: number;
  },
  options?: UseQueryOptions,
) {
  const setOutboxEvents = useRevenueOSStore((state) => state.setOutboxEvents);
  const setOutboxLoading = useRevenueOSStore((state) => state.setOutboxLoading);

  return useQuery({
    queryKey: revenueOSKeys.outbox.events(),
    queryFn: async () => {
      setOutboxLoading(true);
      try {
        const data = await api.getOutboxEvents(filters);
        setOutboxEvents(data.items);
        return data;
      } finally {
        setOutboxLoading(false);
      }
    },
    refetchInterval: 30000,
    ...options,
  });
}

export function useOutboxStats(options?: UseQueryOptions) {
  const setOutboxStats = useRevenueOSStore((state) => state.setOutboxStats);

  return useQuery({
    queryKey: revenueOSKeys.outbox.stats(),
    queryFn: async () => {
      const data = await api.getOutboxStats();
      setOutboxStats(data);
      return data;
    },
    refetchInterval: 30000,
    ...options,
  });
}

export function useOutboxPending(options?: UseQueryOptions) {
  return useQuery({
    queryKey: revenueOSKeys.outbox.pending(),
    queryFn: () => api.getPendingOutboxEvents(),
    refetchInterval: 15000,
    ...options,
  });
}

export function useOutboxFailed(options?: UseQueryOptions) {
  return useQuery({
    queryKey: revenueOSKeys.outbox.failed(),
    queryFn: () => api.getFailedOutboxEvents(),
    refetchInterval: 60000,
    ...options,
  });
}

export function useRetryOutboxEvent(
  options?: UseMutationOptions<OutboxEvent, Error, string>,
) {
  const queryClient = useQueryClient();
  const updateOutboxEvent = useRevenueOSStore(
    (state) => state.updateOutboxEvent,
  );

  return useMutation({
    mutationFn: (eventId: string) => api.retryOutboxEvent(eventId),
    onSuccess: (data) => {
      updateOutboxEvent(data);
      queryClient.invalidateQueries({ queryKey: revenueOSKeys.outbox.all() });
    },
    ...options,
  });
}

// ==========================================
// WebSocket Hook
// ==========================================

export function useRevenueOSWebSocket() {
  const setWSStatus = useRevenueOSStore((state) => state.setWSStatus);
  const setWSConnected = useRevenueOSStore((state) => state.setWSConnected);
  const addNotification = useRevenueOSStore((state) => state.addNotification);
  const addBWCPMessage = useRevenueOSStore((state) => state.addBWCPMessage);
  const addIncident = useRevenueOSStore((state) => state.addIncident);
  const addApproval = useRevenueOSStore((state) => state.addApproval);
  const queryClient = useQueryClient();

  useEffect(() => {
    const ws = getRevenueOSWebSocket();

    // Connect to WebSocket
    ws.connect();

    // Handle status changes
    const handleStatusChange = (event: CustomEvent) => {
      setWSStatus(event.detail.status);
      setWSConnected(event.detail.status === "connected");
    };

    window.addEventListener(
      "revenue-os:ws:status",
      handleStatusChange as EventListener,
    );

    // Subscribe to events
    const unsubscribeBWCP = ws.onBWCPMessage((event: BWCPMessageEvent) => {
      addBWCPMessage({
        id: event.payload.message_id,
        conversation_id: event.payload.conversation_id,
        sender_agent: event.payload.sender_agent,
        recipient_agent: event.payload.recipient_agent,
        message_type: event.payload.message_type,
        belief: event.payload.belief,
        will: event.payload.will,
        delivered: false,
        created_at: event.payload.created_at,
      });
      addNotification({
        type: "bwcp",
        title: "New BWCP Message",
        message: `${event.payload.sender_agent} → ${event.payload.recipient_agent}`,
        severity: "low",
        data: event.payload,
      });
      queryClient.invalidateQueries({ queryKey: revenueOSKeys.bwcp.all() });
    });

    const unsubscribeIncident = ws.onIncident((event: IncidentEvent) => {
      addIncident({
        id: event.payload.incident_id,
        title: event.payload.title,
        severity: event.payload.severity,
        created_at: event.payload.created_at,
      });
      addNotification({
        type: "incident",
        title: "Incident Created",
        message: event.payload.title,
        severity: event.payload.severity,
        data: event.payload,
      });
      queryClient.invalidateQueries({ queryKey: revenueOSKeys.incidents() });
    });

    const unsubscribeOutbox = ws.onOutboxProcessed(() => {
      queryClient.invalidateQueries({ queryKey: revenueOSKeys.outbox.all() });
    });

    const unsubscribeApproval = ws.onApproval((event: ApprovalEvent) => {
      if (event.type === "approval_required") {
        addApproval({
          id: event.payload.approval_id,
          title: event.payload.approval_type,
          approval_type: event.payload.approval_type,
          priority: event.payload.priority,
          requested_by: event.payload.requested_by || "Unknown",
        });
        addNotification({
          type: "approval",
          title: "Approval Required",
          message: `${event.payload.approval_type} (${event.payload.priority} priority)`,
          severity:
            event.payload.priority === "urgent"
              ? "critical"
              : event.payload.priority === "high"
                ? "high"
                : "medium",
          data: event.payload,
        });
        queryClient.invalidateQueries({ queryKey: revenueOSKeys.approvals() });
      }
    });

    // Cleanup
    return () => {
      window.removeEventListener(
        "revenue-os:ws:status",
        handleStatusChange as EventListener,
      );
      unsubscribeBWCP();
      unsubscribeIncident();
      unsubscribeOutbox();
      unsubscribeApproval();
      ws.disconnect();
    };
  }, [
    setWSStatus,
    setWSConnected,
    addNotification,
    addBWCPMessage,
    addIncident,
    addApproval,
    queryClient,
  ]);
}

// ==========================================
// Combined Dashboard Hook
// ==========================================

export function useCEODashboard() {
  const dashboard = useRevenueOSStore((state) => state.dashboard);
  const dashboardLoading = useRevenueOSStore((state) => state.dashboardLoading);
  const notifications = useRevenueOSStore((state) => state.notifications);
  const unreadNotifications = useRevenueOSStore(
    (state) => state.unreadNotifications,
  );
  const wsConnected = useRevenueOSStore((state) => state.wsConnected);

  // Fetch all dashboard data
  const { isLoading: isDashboardLoading } = useDashboardSummary();
  const { isLoading: isCampaignsLoading } = useCampaignPerformance();
  const { isLoading: isApprovalsLoading } = useApprovalQueue();
  const { isLoading: isIncidentsLoading } = useCriticalIncidents();

  // Connect WebSocket
  useRevenueOSWebSocket();

  const isLoading =
    dashboardLoading ||
    isDashboardLoading ||
    isCampaignsLoading ||
    isApprovalsLoading ||
    isIncidentsLoading;

  return {
    dashboard,
    isLoading,
    wsConnected,
    notifications,
    unreadNotifications,
  };
}
