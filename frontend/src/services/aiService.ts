/**
 * AI Service - Frontend service for AI operations
 * Communicates with Graxia backend AI endpoints
 */

const API_URL = import.meta.env.VITE_API_URL || "http://localhost:8000";

function getAccessToken(): string | null {
  // Backend sets access_token as an httpOnly-or-readable cookie.
  // For non-httpOnly cookie access:
  const match = document.cookie.match(/(?:^|;\s*)access_token=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  model?: string;
  temperature?: number;
  stream?: boolean;
  use_vault?: boolean;
  use_skills?: boolean;
}

export interface ChatResponse {
  message: ChatMessage;
  model_used: string;
  tokens_used?: number;
  context_references?: string[];
}

export interface CodeRequest {
  prompt: string;
  language: string;
  context?: string;
  existing_code?: string;
  include_tests?: boolean;
  include_docs?: boolean;
}

export interface CodeResponse {
  code: string;
  language: string;
  explanation: string;
  tests?: string;
  documentation?: string;
  model_used: string;
  suggestions?: string[];
}

export interface VaultQueryRequest {
  query: string;
  search_type?: "semantic" | "keyword" | "graph";
  limit?: number;
  categories?: string[];
  tags?: string[];
}

export interface VaultFile {
  path: string;
  name: string;
  relevance_score: number;
  content_preview?: string;
  tags?: string[];
  last_modified?: string;
}

export interface VaultQueryResponse {
  query: string;
  total_results: number;
  files: VaultFile[];
  skills_suggested?: string[];
}

export interface SkillInfo {
  id: string;
  name: string;
  description: string;
  category: string;
  family: string;
  estimated_tokens: number;
}

export interface CodeExplanationResponse {
  explanation: string;
}

export interface VaultSearchResponse {
  results: VaultFile[];
}

export interface SkillsSearchResponse {
  skills: SkillInfo[];
}

export interface AgentStatus {
  agent: string;
  online: boolean;
  current_load: number;
  capabilities: string[];
  last_seen: string;
}

export interface AgentNetworkStatus {
  orchestrator: string;
  agents: AgentStatus[];
  messages_in_queue: number;
  recent_errors: string[];
}

export interface SystemStatus {
  recent_errors: string[];
}

export interface WebSocketMessage {
  type: string;
  id?: string;
  payload?: Record<string, unknown>;
  content?: string;
  error?: string;
}

export type WebSocketCallback = (data: WebSocketMessage) => void;

export class AIService {
  private baseUrl: string;
  private ws: WebSocket | null = null;
  private messageCallbacks: Map<string, WebSocketCallback> = new Map();

  constructor() {
    this.baseUrl = `${API_URL}/ai`;
  }

  private async fetch<T = unknown>(
    endpoint: string,
    options: RequestInit = {},
  ): Promise<T> {
    const token = getAccessToken();

    const response = await fetch(`${this.baseUrl}${endpoint}`, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(token && { Authorization: `Bearer ${token}` }),
        ...options.headers,
      },
    });

    if (!response.ok) {
      const error = await response
        .json()
        .catch(() => ({ detail: "Unknown error" }));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }

    return response.json();
  }

  // ═══════════════════════════════════════════════════════════════
  // Chat Operations
  // ═══════════════════════════════════════════════════════════════

  async chat(request: ChatRequest): Promise<ChatResponse> {
    return this.fetch("/chat", {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  async *streamChat(request: ChatRequest): AsyncGenerator<string> {
    const token = getAccessToken();

    const response = await fetch(`${this.baseUrl}/chat/stream`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...(token && { Authorization: `Bearer ${token}` }),
      },
      body: JSON.stringify(request),
    });

    if (!response.ok) {
      throw new Error("Failed to stream chat");
    }

    const reader = response.body?.getReader();
    if (!reader) throw new Error("No response body");

    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (data === "[DONE]") return;
          try {
            const parsed = JSON.parse(data);
            yield parsed.content;
          } catch {
            // JSON parse error for incomplete chunks - continue to next chunk
          }
        }
      }
    }
  }

  // ═══════════════════════════════════════════════════════════════
  // Code Operations
  // ═══════════════════════════════════════════════════════════════

  async generateCode(request: CodeRequest): Promise<CodeResponse> {
    return this.fetch("/code/generate", {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  async fixCode(
    code: string,
    errorMessage?: string,
    language: string = "python",
  ) {
    return this.fetch("/code/fix", {
      method: "POST",
      body: JSON.stringify({
        code,
        error_message: errorMessage,
        language,
      }),
    });
  }

  async explainCode(code: string, language?: string): Promise<string> {
    const response = await this.fetch<CodeExplanationResponse>(
      "/code/explain",
      {
        method: "POST",
        body: JSON.stringify({ code, language }),
      },
    );
    return response.explanation;
  }

  // ═══════════════════════════════════════════════════════════════
  // Vault Operations
  // ═══════════════════════════════════════════════════════════════

  async queryVault(request: VaultQueryRequest): Promise<VaultQueryResponse> {
    return this.fetch("/vault/query", {
      method: "POST",
      body: JSON.stringify(request),
    });
  }

  async getVaultFile(path: string): Promise<string> {
    const response = await fetch(
      `${this.baseUrl}/vault/file/${encodeURIComponent(path)}`,
      {
        headers: {
          Authorization: `Bearer ${getAccessToken() ?? ""}`,
        },
      },
    );
    const data = await response.json();
    return data.content;
  }

  async searchVault(query: string, limit: number = 10): Promise<VaultFile[]> {
    const response = await this.fetch<VaultSearchResponse>("/vault/search", {
      method: "POST",
      body: JSON.stringify({ query, limit }),
    });
    return response.results;
  }

  async getVaultStats() {
    return this.fetch("/vault/stats");
  }

  // ═══════════════════════════════════════════════════════════════
  // Skills Operations
  // ═══════════════════════════════════════════════════════════════

  async searchSkills(query: string, limit: number = 5): Promise<SkillInfo[]> {
    const response = await this.fetch<SkillsSearchResponse>("/skills/search", {
      method: "POST",
      body: JSON.stringify({ query, limit }),
    });
    return response.skills;
  }

  async loadSkill(skillId: string): Promise<Record<string, unknown>> {
    return this.fetch<Record<string, unknown>>("/skills/load", {
      method: "POST",
      body: JSON.stringify({ skill_id: skillId }),
    });
  }

  async getSkillCategories() {
    return this.fetch("/skills/categories");
  }

  // ═══════════════════════════════════════════════════════════════
  // Agent Operations
  // ═══════════════════════════════════════════════════════════════

  async getAgentStatus(): Promise<AgentNetworkStatus> {
    return this.fetch("/agent/status");
  }

  async delegateTask(agent: string, task: string, priority: string = "medium") {
    return this.fetch("/agent/delegate", {
      method: "POST",
      body: JSON.stringify({
        to_agent: agent,
        task,
        priority,
      }),
    });
  }

  async sendAgentCommand(agent: string, command: string) {
    return this.fetch(`/agent/${agent}/command`, {
      method: "POST",
      body: JSON.stringify({ command }),
    });
  }

  // ═══════════════════════════════════════════════════════════════
  // Auto-System Operations
  // ═══════════════════════════════════════════════════════════════

  async autoClassify(dryRun: boolean = true, maxFiles: number = 50) {
    return this.fetch("/auto/classify", {
      method: "POST",
      body: JSON.stringify({ dry_run: dryRun, max_files: maxFiles }),
    });
  }

  async autoLink(dryRun: boolean = true, limit: number = 100) {
    return this.fetch("/auto/link", {
      method: "POST",
      body: JSON.stringify({ dry_run: dryRun, limit }),
    });
  }

  async optimizeAll() {
    return this.fetch("/auto/optimize", {
      method: "POST",
    });
  }

  // ═══════════════════════════════════════════════════════════════
  // WebSocket Operations
  // ═══════════════════════════════════════════════════════════════

  connectWebSocket(): WebSocket {
    const wsUrl = `${API_URL.replace("http", "ws")}/ai/ws`;
    this.ws = new WebSocket(wsUrl);

    this.ws.onopen = () => {
      console.log("WebSocket connected");
    };

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const callback = this.messageCallbacks.get(data.request_id);
      if (callback) {
        callback(data);
        if (data.done) {
          this.messageCallbacks.delete(data.request_id);
        }
      }
    };

    this.ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };

    this.ws.onclose = () => {
      console.log("WebSocket disconnected");
      this.ws = null;
    };

    return this.ws;
  }

  sendWebSocketMessage(
    type: string,
    payload: Record<string, unknown>,
  ): Promise<WebSocketMessage> {
    return new Promise((resolve, reject) => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) {
        reject(new Error("WebSocket not connected"));
        return;
      }

      const id = Math.random().toString(36).substring(7);
      this.messageCallbacks.set(id, resolve);

      this.ws.send(
        JSON.stringify({
          type,
          id,
          payload,
        }),
      );

      // Timeout after 30 seconds
      setTimeout(() => {
        if (this.messageCallbacks.has(id)) {
          this.messageCallbacks.delete(id);
          reject(new Error("WebSocket timeout"));
        }
      }, 30000);
    });
  }

  disconnectWebSocket() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

// Export singleton instance
export const aiService = new AIService();

// React Hook
import { useCallback, useState } from "react";

export function useAIService() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const execute = useCallback(
    async <T>(fn: () => Promise<T>): Promise<T | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await fn();
        return result;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unknown error");
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  return { aiService, isLoading, error, execute };
}
