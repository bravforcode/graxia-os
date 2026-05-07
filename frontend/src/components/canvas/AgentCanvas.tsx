import {
  addEdge,
  applyEdgeChanges,
  applyNodeChanges,
  Background,
  Controls,
  Edge,
  Handle,
  Node,
  NodeMouseHandler,
  OnConnect,
  OnEdgesChange,
  OnNodesChange,
  Panel,
  Position,
  ReactFlow,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { Bot, Shield, Terminal, Zap } from "lucide-react";
import React, { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useGraxiaStream } from "../../hooks/useGraxiaStream";
import { cn } from "../../lib/utils";

// --- Types ---
interface AgentData extends Record<string, unknown> {
  label: string;
  status: "idle" | "thinking" | "active" | "blocked" | "waiting";
  agentId: string;
  lastMessage?: string;
}

// --- Custom Components ---

const AgentNode = React.memo(({ data }: { data: AgentData }) => {
  const statusConfig = {
    idle: { color: "border-zinc-800", icon: "text-zinc-500", label: "Idle" },
    thinking: { color: "border-[#8b5cf6]", icon: "text-[#8b5cf6]", label: "Thinking" },
    active: { color: "border-[#3b82f6]", icon: "text-[#3b82f6]", label: "Active" },
    blocked: { color: "border-red-500", icon: "text-red-500", label: "Blocked" },
    waiting: { color: "border-amber-500", icon: "text-amber-500", label: "Waiting for Human" },
  };

  const config = statusConfig[data.status] || statusConfig.idle;
  const isThinking = data.status === "thinking";

  return (
    <div
      className={cn(
        "px-4 py-3 shadow-xl rounded-xl border-2 transition-all duration-500 bg-[#0a0a0a] min-w-[220px]",
        config.color,
        (isThinking || data.status === 'active') && "shadow-lg"
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="w-2 h-2 !bg-zinc-700"
      />

      <div className="flex items-center gap-3">
        <div
          className={cn(
            "p-2 rounded-lg transition-colors bg-zinc-900/50",
            config.icon,
            isThinking && "animate-pulse"
          )}
        >
          {data.agentId.includes("security") ? (
            <Shield size={20} />
          ) : data.agentId.includes("orchestrator") ? (
            <Zap size={20} />
          ) : (
            <Bot size={20} />
          )}
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between">
            <div className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">
              Agent
            </div>
            <div className={cn("text-[8px] font-bold uppercase px-1.5 py-0.5 rounded bg-zinc-900", config.icon)}>
              {config.label}
            </div>
          </div>
          <div className="text-sm font-semibold text-zinc-100 truncate">
            {data.label}
          </div>
        </div>
      </div>

      {data.lastMessage && (
        <div className="mt-3 text-[10px] font-mono text-zinc-400 bg-black/40 p-2 rounded border border-zinc-800/50 line-clamp-2">
          {data.lastMessage}
        </div>
      )}

      {isThinking && (
        <div className="mt-2 flex items-center gap-2">
          <div className="flex gap-1">
            <span className="w-1 h-1 bg-[#8b5cf6] rounded-full animate-bounce [animation-delay:-0.3s]"></span>
            <span className="w-1 h-1 bg-[#8b5cf6] rounded-full animate-bounce [animation-delay:-0.15s]"></span>
            <span className="w-1 h-1 bg-[#8b5cf6] rounded-full animate-bounce"></span>
          </div>
          <span className="text-[10px] text-[#8b5cf6] font-medium">
            Generating response...
          </span>
        </div>
      )}

      <Handle
        type="source"
        position={Position.Bottom}
        className="w-2 h-2 !bg-zinc-700"
      />
    </div>
  );
});

AgentNode.displayName = "AgentNode";

const nodeTypes = {
  agent: AgentNode,
};

// --- Initial Data ---

const initialNodes: Node<AgentData>[] = [
  {
    id: "orchestrator",
    type: "agent",
    position: { x: 400, y: 50 },
    data: {
      label: "Graxia Orchestrator",
      status: "idle",
      agentId: "agent-orchestrator",
    },
  },
  {
    id: "backend",
    type: "agent",
    position: { x: 150, y: 250 },
    data: {
      label: "Backend Architect",
      status: "idle",
      agentId: "agent-backend",
    },
  },
  {
    id: "security",
    type: "agent",
    position: { x: 650, y: 250 },
    data: {
      label: "Security Guardian",
      status: "idle",
      agentId: "agent-security",
    },
  },
  {
    id: "ux-expert",
    type: "agent",
    position: { x: 400, y: 450 },
    data: { label: "UX Strategist", status: "idle", agentId: "agent-ux" },
  },
];

export const initialEdges: Edge[] = [
  {
    id: "e1-2",
    source: "orchestrator",
    target: "backend",
    animated: true,
    style: { stroke: "#4f46e5" },
  },
  {
    id: "e1-3",
    source: "orchestrator",
    target: "security",
    animated: true,
    style: { stroke: "#4f46e5" },
  },
  { id: "e2-4", source: "backend", target: "ux-expert", animated: false },
  { id: "e3-4", source: "security", target: "ux-expert", animated: false },
];

// --- Main Component ---

export const AgentCanvas = () => {
  const navigate = useNavigate();
  const [nodes, setNodes] = useState<Node<AgentData>[]>(initialNodes);
  const [edges, setEdges] = useState<Edge[]>(initialEdges);
  const { events, isConnected } = useGraxiaStream();

  const onNodesChange: OnNodesChange = useCallback(
    (changes) =>
      setNodes((nds) => applyNodeChanges(changes, nds) as Node<AgentData>[]),
    [],
  );

  const onEdgesChange: OnEdgesChange = useCallback(
    (changes) => setEdges((eds) => applyEdgeChanges(changes, eds)),
    [],
  );

  const onConnect: OnConnect = useCallback(
    (params) => setEdges((eds) => addEdge(params, eds)),
    [],
  );

  const onNodeClick: NodeMouseHandler = useCallback(
    (_, node) => {
      console.log("Opening control panel for:", node.data.label);
      navigate(`/agents?id=${node.data.agentId}`);
    },
    [navigate],
  );

  // Update nodes based on WebSocket events
  useEffect(() => {
    if (events.length > 0) {
      const latestEvent = events[0];
      if (latestEvent.agent_id) {
        setNodes((nds) =>
          nds.map((node) => {
            if (node.data.agentId === latestEvent.agent_id) {
              return {
                ...node,
                data: {
                  ...node.data,
                  status:
                    latestEvent.type === "thinking" ? "thinking" :
                    latestEvent.type === "blocked" ? "blocked" :
                    latestEvent.type === "waiting" ? "waiting" : "active",
                  lastMessage: latestEvent.message || node.data.lastMessage,
                },
              };
            }
            return node;
          }),
        );
      }
    }
  }, [events]);

  const defaultEdgeOptions = useMemo(
    () => ({
      style: { strokeWidth: 2, stroke: "#27272a" },
      type: "smoothstep",
    }),
    [],
  );

  return (
    <div className="w-full h-full bg-[#0a0a0a] relative">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onConnect={onConnect}
        onNodeClick={onNodeClick}
        nodeTypes={nodeTypes}
        defaultEdgeOptions={defaultEdgeOptions}
        fitView
        colorMode="dark"
      >
        <Background color="#18181b" gap={20} size={1} />
        <Controls className="!bg-[#18181b] !border-zinc-800 !fill-zinc-100" />

        <Panel position="top-right">
          <div className="flex items-center gap-3 px-4 py-2 bg-[#18181b]/80 backdrop-blur border border-zinc-800 rounded-full">
            <div
              className={cn(
                "w-2 h-2 rounded-full",
                isConnected ? "bg-emerald-500 animate-pulse" : "bg-rose-500",
              )}
            />
            <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
              {isConnected ? "Nexus Live" : "Nexus Offline"}
            </span>
          </div>
        </Panel>

        <Panel position="bottom-left" className="p-4 max-w-xs">
          <div className="bg-[#18181b]/80 backdrop-blur border border-zinc-800 rounded-xl p-4">
            <div className="flex items-center gap-2 mb-3">
              <Terminal size={14} className="text-[#3b82f6]" />
              <h3 className="text-xs font-bold text-zinc-200 uppercase tracking-tight">
                Nexus Intelligence Feed
              </h3>
            </div>
            <div className="space-y-2 max-h-40 overflow-y-auto pr-2 custom-scrollbar">
              {events.length === 0 ? (
                <p className="text-[10px] text-zinc-500 italic">
                  Monitoring neural pathways...
                </p>
              ) : (
                events.map((ev, i) => (
                  <div
                    key={i}
                    className="text-[10px] font-mono text-zinc-400 border-l border-zinc-800 pl-2 py-0.5"
                  >
                    <span className="text-[#3b82f6]">
                      [{ev.type.toUpperCase()}]
                    </span>{" "}
                    {ev.message}
                  </div>
                ))
              )}
            </div>
          </div>
        </Panel>
      </ReactFlow>

      {/* CSS for custom scrollbar */}
      <style>{`
        .custom-scrollbar::-webkit-scrollbar {
          width: 4px;
        }
        .custom-scrollbar::-webkit-scrollbar-track {
          background: transparent;
        }
        .custom-scrollbar::-webkit-scrollbar-thumb {
          background: #334155;
          border-radius: 10px;
        }
      `}</style>
    </div>
  );
};

export default React.memo(AgentCanvas);
