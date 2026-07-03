/**
 * Revenue OS v12 WebSocket Client
 * Real-time updates for CEO Dashboard
 * Enterprise-grade WebSocket with automatic reconnection
 */

type WebSocketStatus = "connecting" | "connected" | "disconnected" | "error";

interface WSMessage {
  type: string;
  payload: unknown;
  timestamp: string;
}

interface BWCPMessageEvent {
  type: "bwcp_message";
  payload: {
    message_id: string;
    conversation_id: string;
    sender_agent: string;
    recipient_agent: string;
    message_type: string;
    belief?: string;
    will?: string;
    created_at: string;
  };
}

interface IncidentEvent {
  type: "incident_created";
  payload: {
    incident_id: string;
    title: string;
    severity: "low" | "medium" | "high" | "critical";
    description?: string;
    created_at: string;
  };
}

interface OutboxEvent {
  type: "outbox_processed";
  payload: {
    event_id: string;
    event_type: string;
    processed_at: string;
    retry_count: number;
  };
}

interface ApprovalEvent {
  type: "approval_required" | "approval_approved" | "approval_rejected";
  payload: {
    approval_id: string;
    approval_type: string;
    priority: string;
    requested_by?: string;
    reason?: string;
  };
}

type RevenueOSEvent =
  | BWCPMessageEvent
  | IncidentEvent
  | OutboxEvent
  | ApprovalEvent;

// Event handlers type
type EventHandler<T extends RevenueOSEvent = RevenueOSEvent> = (
  event: T,
) => void;

class RevenueOSWebSocket {
  private ws: WebSocket | null = null;
  private url: string;
  private status: WebSocketStatus = "disconnected";
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000; // Start with 1s, exponential backoff
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  private eventHandlers: Map<string, Set<EventHandler>> = new Map();
  private globalHandlers: Set<EventHandler> = new Set();

  constructor(url: string) {
    this.url = url;
  }

  // Connection Management
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      // console.log('RevenueOS WS: Already connected');
      return;
    }

    this.status = "connecting";
    this.emitStatusChange();

    try {
      // Connect without API key - authentication handled via backend proxy
      const wsUrl = new URL(this.url);

      this.ws = new WebSocket(wsUrl.toString());

      this.ws.onopen = this.handleOpen.bind(this);
      this.ws.onmessage = this.handleMessage.bind(this);
      this.ws.onclose = this.handleClose.bind(this);
      this.ws.onerror = this.handleError.bind(this);
    } catch (error) {
      // console.error('RevenueOS WS: Connection error', error);
      this.status = "error";
      this.emitStatusChange();
      this.scheduleReconnect();
    }
  }

  disconnect(): void {
    this.cleanup();
    this.status = "disconnected";
    this.emitStatusChange();
  }

  private cleanup(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }

    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      // console.error('RevenueOS WS: Max reconnection attempts reached');
      this.status = "error";
      this.emitStatusChange();
      return;
    }

    this.reconnectAttempts++;
    const delay = Math.min(
      this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1),
      30000, // Max 30s delay
    );

    // console.log(`RevenueOS WS: Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);

    this.reconnectTimeout = setTimeout(() => {
      this.connect();
    }, delay);
  }

  // WebSocket Event Handlers
  private handleOpen(): void {
    // console.log('RevenueOS WS: Connected');
    this.status = "connected";
    this.reconnectAttempts = 0;
    this.emitStatusChange();

    // Start heartbeat
    this.heartbeatInterval = setInterval(() => {
      this.send({ type: "ping", timestamp: new Date().toISOString() });
    }, 30000); // 30s heartbeat

    // Subscribe to all event types
    this.send({
      type: "subscribe",
      channels: ["bwcp", "incidents", "outbox", "approvals"],
    });
  }

  private handleMessage(event: MessageEvent): void {
    try {
      const data = JSON.parse(event.data) as WSMessage;

      // Handle pong
      if (data.type === "pong") return;

      // Emit to type-specific handlers
      const handlers = this.eventHandlers.get(data.type);
      if (handlers) {
        handlers.forEach((handler) => {
          try {
            handler(data as RevenueOSEvent);
          } catch (err) {
            // console.error(`RevenueOS WS: Handler error for ${data.type}`, err);
          }
        });
      }

      // Emit to global handlers
      this.globalHandlers.forEach((handler) => {
        try {
          handler(data as RevenueOSEvent);
        } catch (err) {
          // console.error('RevenueOS WS: Global handler error', err);
        }
      });

      // Emit custom DOM event for non-React consumers
      window.dispatchEvent(
        new CustomEvent("revenue-os:ws:message", {
          detail: data,
        }),
      );
    } catch (error) {
      // console.error('RevenueOS WS: Message parse error', error);
    }
  }

  private handleClose(event: CloseEvent): void {
    // console.log('RevenueOS WS: Closed', event.code, event.reason);
    this.cleanup();

    if (event.code !== 1000 && event.code !== 1001) {
      // Abnormal closure, attempt reconnect
      this.status = "disconnected";
      this.emitStatusChange();
      this.scheduleReconnect();
    } else {
      this.status = "disconnected";
      this.emitStatusChange();
    }
  }

  private handleError(error: Event): void {
    console.error("RevenueOS WS: Error", error);
    this.status = "error";
    this.emitStatusChange();
  }

  // Public API
  send(message: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(message));
    } else {
      console.warn("RevenueOS WS: Cannot send, not connected");
    }
  }

  // Event Subscription
  on<T extends RevenueOSEvent>(
    eventType: T["type"],
    handler: EventHandler<T>,
  ): () => void {
    if (!this.eventHandlers.has(eventType)) {
      this.eventHandlers.set(eventType, new Set());
    }
    this.eventHandlers.get(eventType)!.add(handler as EventHandler);

    // Return unsubscribe function
    return () => {
      this.eventHandlers.get(eventType)?.delete(handler as EventHandler);
    };
  }

  onAny(handler: EventHandler): () => void {
    this.globalHandlers.add(handler);
    return () => {
      this.globalHandlers.delete(handler);
    };
  }

  off<T extends RevenueOSEvent>(
    eventType: T["type"],
    handler: EventHandler<T>,
  ): void {
    this.eventHandlers.get(eventType)?.delete(handler as EventHandler);
  }

  // Status
  getStatus(): WebSocketStatus {
    return this.status;
  }

  isConnected(): boolean {
    return this.status === "connected";
  }

  private emitStatusChange(): void {
    window.dispatchEvent(
      new CustomEvent("revenue-os:ws:status", {
        detail: { status: this.status },
      }),
    );
  }

  // Convenience methods for common events
  onBWCPMessage(handler: (event: BWCPMessageEvent) => void): () => void {
    return this.on("bwcp_message", handler as EventHandler);
  }

  onIncident(handler: (event: IncidentEvent) => void): () => void {
    return this.on("incident_created", handler as EventHandler);
  }

  onOutboxProcessed(handler: (event: OutboxEvent) => void): () => void {
    return this.on("outbox_processed", handler as EventHandler);
  }

  onApproval(handler: (event: ApprovalEvent) => void): () => void {
    return this.on("approval_required", handler as EventHandler);
  }
}

// Singleton instance
let wsInstance: RevenueOSWebSocket | null = null;

export function initializeRevenueOSWebSocket(
  url?: string,
): RevenueOSWebSocket {
  const wsUrl =
    url || import.meta.env.VITE_WS_URL || "ws://localhost:8000/ws/revenue-os";

  wsInstance = new RevenueOSWebSocket(wsUrl);
  return wsInstance;
}

export function getRevenueOSWebSocket(): RevenueOSWebSocket {
  if (!wsInstance) {
    return initializeRevenueOSWebSocket();
  }
  return wsInstance;
}

export type {
  ApprovalEvent,
  BWCPMessageEvent,
  EventHandler,
  IncidentEvent,
  OutboxEvent,
  RevenueOSEvent,
  WebSocketStatus,
};

export { RevenueOSWebSocket };
