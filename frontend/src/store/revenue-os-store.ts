/**
 * Revenue OS v12 Zustand Store
 * Enterprise-grade state management for CEO Dashboard
 */
import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';
import type {
  CEODashboardSummary,
  BWCPMessage,
  OutboxEvent,
  OutboxStats,
  CampaignPerformance,
  CriticalIncidentItem,
  ApprovalItem,
} from '../lib/api/revenue-os';

// State Interfaces
interface RevenueOSState {
  // Dashboard Data
  dashboard: CEODashboardSummary | null;
  dashboardLoading: boolean;
  dashboardError: string | null;
  lastDashboardUpdate: number | null;

  // BWCP Messages
  bwcpMessages: BWCPMessage[];
  bwcpUnreadCounts: Record<string, number>;
  bwcpLoading: boolean;

  // Outbox Events
  outboxEvents: OutboxEvent[];
  outboxStats: OutboxStats | null;
  outboxLoading: boolean;

  // Campaigns
  campaignPerformance: CampaignPerformance | null;
  campaignsLoading: boolean;

  // Incidents
  criticalIncidents: CriticalIncidentItem[];
  highIncidents: CriticalIncidentItem[];
  incidentsLoading: boolean;

  // Approvals
  approvalQueue: ApprovalItem[];
  approvalsLoading: boolean;

  // Real-time Status
  wsConnected: boolean;
  wsStatus: 'connecting' | 'connected' | 'disconnected' | 'error';

  // Notifications
  notifications: Notification[];
  unreadNotifications: number;
}

interface Notification {
  id: string;
  type: 'incident' | 'approval' | 'bwcp' | 'outbox';
  title: string;
  message: string;
  severity?: 'low' | 'medium' | 'high' | 'critical';
  timestamp: string;
  read: boolean;
  data?: Record<string, unknown>;
}

// Actions Interface
interface RevenueOSActions {
  // Dashboard
  setDashboard: (dashboard: CEODashboardSummary) => void;
  setDashboardLoading: (loading: boolean) => void;
  setDashboardError: (error: string | null) => void;

  // BWCP
  setBWCPMessages: (messages: BWCPMessage[]) => void;
  addBWCPMessage: (message: BWCPMessage) => void;
  markBWCPDelivered: (messageId: string) => void;
  markBWCPRead: (messageId: string) => void;
  setBWCPUnreadCount: (agent: string, count: number) => void;
  setBWCPLoading: (loading: boolean) => void;

  // Outbox
  setOutboxEvents: (events: OutboxEvent[]) => void;
  setOutboxStats: (stats: OutboxStats) => void;
  updateOutboxEvent: (event: OutboxEvent) => void;
  setOutboxLoading: (loading: boolean) => void;

  // Campaigns
  setCampaignPerformance: (performance: CampaignPerformance) => void;
  setCampaignsLoading: (loading: boolean) => void;

  // Incidents
  setCriticalIncidents: (critical: CriticalIncidentItem[], high: CriticalIncidentItem[]) => void;
  addIncident: (incident: CriticalIncidentItem) => void;
  setIncidentsLoading: (loading: boolean) => void;

  // Approvals
  setApprovalQueue: (approvals: ApprovalItem[]) => void;
  addApproval: (approval: ApprovalItem) => void;
  removeApproval: (approvalId: string) => void;
  setApprovalsLoading: (loading: boolean) => void;

  // WebSocket
  setWSConnected: (connected: boolean) => void;
  setWSStatus: (status: RevenueOSState['wsStatus']) => void;

  // Notifications
  addNotification: (notification: Omit<Notification, 'id' | 'timestamp' | 'read'>) => void;
  markNotificationRead: (notificationId: string) => void;
  clearNotifications: () => void;
  dismissNotification: (notificationId: string) => void;

  // Reset
  reset: () => void;
}

// Initial State
const initialState: RevenueOSState = {
  dashboard: null,
  dashboardLoading: false,
  dashboardError: null,
  lastDashboardUpdate: null,

  bwcpMessages: [],
  bwcpUnreadCounts: {},
  bwcpLoading: false,

  outboxEvents: [],
  outboxStats: null,
  outboxLoading: false,

  campaignPerformance: null,
  campaignsLoading: false,

  criticalIncidents: [],
  highIncidents: [],
  incidentsLoading: false,

  approvalQueue: [],
  approvalsLoading: false,

  wsConnected: false,
  wsStatus: 'disconnected',

  notifications: [],
  unreadNotifications: 0,
};

// Store Creation
export const useRevenueOSStore = create<RevenueOSState & RevenueOSActions>()(
  devtools(
    persist(
      (set, get) => ({
        ...initialState,

        // Dashboard Actions
        setDashboard: (dashboard) =>
          set({
            dashboard,
            lastDashboardUpdate: Date.now(),
            dashboardError: null,
          }),

        setDashboardLoading: (loading) => set({ dashboardLoading: loading }),

        setDashboardError: (error) => set({ dashboardError: error }),

        // BWCP Actions
        setBWCPMessages: (messages) =>
          set({
            bwcpMessages: messages.sort(
              (a, b) =>
                new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
            ),
          }),

        addBWCPMessage: (message) =>
          set((state) => ({
            bwcpMessages: [message, ...state.bwcpMessages].slice(0, 100), // Keep last 100
            bwcpUnreadCounts: {
              ...state.bwcpUnreadCounts,
              [message.recipient_agent]:
                (state.bwcpUnreadCounts[message.recipient_agent] || 0) + 1,
            },
          })),

        markBWCPDelivered: (messageId) =>
          set((state) => ({
            bwcpMessages: state.bwcpMessages.map((m) =>
              m.id === messageId ? { ...m, delivered: true, delivered_at: new Date().toISOString() } : m
            ),
          })),

        markBWCPRead: (messageId) =>
          set((state) => ({
            bwcpMessages: state.bwcpMessages.map((m) =>
              m.id === messageId ? { ...m, read_at: new Date().toISOString() } : m
            ),
          })),

        setBWCPUnreadCount: (agent, count) =>
          set((state) => ({
            bwcpUnreadCounts: { ...state.bwcpUnreadCounts, [agent]: count },
          })),

        setBWCPLoading: (loading) => set({ bwcpLoading: loading }),

        // Outbox Actions
        setOutboxEvents: (events) =>
          set({
            outboxEvents: events.sort(
              (a, b) =>
                new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
            ),
          }),

        setOutboxStats: (stats) => set({ outboxStats: stats }),

        updateOutboxEvent: (event) =>
          set((state) => ({
            outboxEvents: state.outboxEvents.map((e) =>
              e.id === event.id ? event : e
            ),
          })),

        setOutboxLoading: (loading) => set({ outboxLoading: loading }),

        // Campaign Actions
        setCampaignPerformance: (performance) => set({ campaignPerformance: performance }),

        setCampaignsLoading: (loading) => set({ campaignsLoading: loading }),

        // Incident Actions
        setCriticalIncidents: (critical, high) =>
          set({ criticalIncidents: critical, highIncidents: high }),

        addIncident: (incident) =>
          set((state) => ({
            criticalIncidents:
              incident.severity === 'critical'
                ? [incident, ...state.criticalIncidents]
                : state.criticalIncidents,
            highIncidents:
              incident.severity === 'high'
                ? [incident, ...state.highIncidents]
                : state.highIncidents,
          })),

        setIncidentsLoading: (loading) => set({ incidentsLoading: loading }),

        // Approval Actions
        setApprovalQueue: (approvals) =>
          set({
            approvalQueue: approvals.sort(
              (a, b) => {
                const priorityOrder = { urgent: 0, high: 1, normal: 2, low: 3 };
                return priorityOrder[a.priority as keyof typeof priorityOrder] - priorityOrder[b.priority as keyof typeof priorityOrder];
              }
            ),
          }),

        addApproval: (approval) =>
          set((state) => ({
            approvalQueue: [approval, ...state.approvalQueue].sort(
              (a, b) => {
                const priorityOrder = { urgent: 0, high: 1, normal: 2, low: 3 };
                return priorityOrder[a.priority as keyof typeof priorityOrder] - priorityOrder[b.priority as keyof typeof priorityOrder];
              }
            ),
          })),

        removeApproval: (approvalId) =>
          set((state) => ({
            approvalQueue: state.approvalQueue.filter((a) => a.id !== approvalId),
          })),

        setApprovalsLoading: (loading) => set({ approvalsLoading: loading }),

        // WebSocket Actions
        setWSConnected: (connected) => set({ wsConnected: connected }),

        setWSStatus: (status) => set({ wsStatus: status, wsConnected: status === 'connected' }),

        // Notification Actions
        addNotification: (notification) =>
          set((state) => {
            const newNotification: Notification = {
              ...notification,
              id: `notif-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
              timestamp: new Date().toISOString(),
              read: false,
            };

            // Auto-dismiss after 10s for non-critical
            if (notification.severity !== 'critical') {
              setTimeout(() => {
                get().dismissNotification(newNotification.id);
              }, 10000);
            }

            return {
              notifications: [newNotification, ...state.notifications].slice(0, 50), // Keep last 50
              unreadNotifications: state.unreadNotifications + 1,
            };
          }),

        markNotificationRead: (notificationId) =>
          set((state) => ({
            notifications: state.notifications.map((n) =>
              n.id === notificationId ? { ...n, read: true } : n
            ),
            unreadNotifications: Math.max(0, state.unreadNotifications - 1),
          })),

        clearNotifications: () => set({ notifications: [], unreadNotifications: 0 }),

        dismissNotification: (notificationId) =>
          set((state) => ({
            notifications: state.notifications.filter((n) => n.id !== notificationId),
            unreadNotifications: state.notifications.find((n) => n.id === notificationId && !n.read)
              ? Math.max(0, state.unreadNotifications - 1)
              : state.unreadNotifications,
          })),

        // Reset
        reset: () => set(initialState),
      }),
      {
        name: 'revenue-os-store',
        partialize: (state) => ({
          // Only persist certain fields
          dashboard: state.dashboard,
          lastDashboardUpdate: state.lastDashboardUpdate,
          bwcpUnreadCounts: state.bwcpUnreadCounts,
        }),
      }
    ),
    { name: 'RevenueOSStore' }
  )
);

// Selectors
export const selectDashboardSummary = (state: ReturnType<typeof useRevenueOSStore.getState>) =>
  state.dashboard;

export const selectRevenueMetrics = (state: ReturnType<typeof useRevenueOSStore.getState>) =>
  state.dashboard?.revenue;

export const selectCampaignStats = (state: ReturnType<typeof useRevenueOSStore.getState>) =>
  state.dashboard?.campaigns;

export const selectApprovalStats = (state: ReturnType<typeof useRevenueOSStore.getState>) =>
  state.dashboard?.approvals;

export const selectIncidentStats = (state: ReturnType<typeof useRevenueOSStore.getState>) =>
  state.dashboard?.incidents;

export const selectAgentActivity = (state: ReturnType<typeof useRevenueOSStore.getState>) =>
  state.dashboard?.agent_activity;

export const selectCriticalAlerts = (state: ReturnType<typeof useRevenueOSStore.getState>) => {
  const alerts: Array<{ type: string; message: string; severity: string }> = [];

  if (state.dashboard?.incidents.critical_open ?? 0 > 0) {
    alerts.push({
      type: 'incident',
      message: `${state.dashboard?.incidents.critical_open} critical incidents open`,
      severity: 'critical',
    });
  }

  if (state.dashboard?.approvals.high_priority ?? 0 > 0) {
    alerts.push({
      type: 'approval',
      message: `${state.dashboard?.approvals.high_priority} high-priority approvals pending`,
      severity: 'high',
    });
  }

  if (state.dashboard?.campaigns.over_budget ?? 0 > 0) {
    alerts.push({
      type: 'campaign',
      message: `${state.dashboard?.campaigns.over_budget} campaigns over budget`,
      severity: 'medium',
    });
  }

  return alerts;
};
