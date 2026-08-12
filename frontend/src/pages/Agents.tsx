/**
 * Agents Management Page
 * จัดการ Agents ทั้งหมด - Identity, Social, Business
 */
import {
  Activity,
  MessageCircle,
  Plus,
  RefreshCw,
  Send,
  Settings,
  TrendingUp,
  Users,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { EmptyState } from "@/components/ui/empty-state";
import { MetricCard } from "@/components/ui/metric-card";
import { PageHeader } from "@/components/ui/page-header";
import { GlassCard } from "@/components/ui/glass-card";
import { StatusPill } from "@/components/ui/status-pill";

interface Agent {
  agent_id: string;
  agent_name: string;
  agent_type: string;
  bio: string;
  reputation_score: number;
  completed_tasks: number;
  success_rate: number;
  is_available: boolean;
  accounts: string[];
  capabilities: Array<{
    name: string;
    skill_level: number;
  }>;
}

interface Negotiation {
  id: string;
  initiator: string;
  responder: string;
  task: string;
  status: string;
  expires_at: string;
}

interface SocialStats {
  facebook?: {
    messages_received: number;
    messages_sent: number;
  } | null;
  line?: {
    messages_received: number;
    messages_sent: number;
  } | null;
}

const TABS = [
  { id: "all", label: "All Agents" },
  { id: "social", label: "Social" },
  { id: "business", label: "Business" },
  { id: "negotiations", label: "Negotiations" },
] as const;

type TabId = (typeof TABS)[number]["id"];

export default function AgentsPage() {
  const [agents, setAgents] = useState<Agent[]>([]);
  const [negotiations, setNegotiations] = useState<Negotiation[]>([]);
  const [socialStats, setSocialStats] = useState<SocialStats>({});
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<TabId>("all");
  const [createDialogOpen, setCreateDialogOpen] = useState(false);
  const [messageDialogOpen, setMessageDialogOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [newMessage, setNewMessage] = useState({ topic: "", content: "" });

  const [newAgent, setNewAgent] = useState({
    name: "",
    agent_type: "social",
    bio: "",
  });

  const API_BASE =
    import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";

  const fetchData = useCallback(async () => {
    try {
      const [agentsRes, negotiationsRes, statsRes] = await Promise.all([
        fetch(`${API_BASE}/agents/identities`),
        fetch(`${API_BASE}/agents/negotiations/active`),
        fetch(`${API_BASE}/agents/social/stats`),
      ]);

      if (agentsRes.ok) setAgents(await agentsRes.json());
      if (negotiationsRes.ok) {
        const negData = await negotiationsRes.json();
        setNegotiations(negData.negotiations || []);
      }
      if (statsRes.ok) setSocialStats(await statsRes.json());
    } catch (error) {
      console.error("Failed to fetch agent data:", error);
    } finally {
      setLoading(false);
    }
  }, [API_BASE]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  const createAgent = async () => {
    try {
      const res = await fetch(`${API_BASE}/agents/create`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(newAgent),
      });

      if (res.ok) {
        setCreateDialogOpen(false);
        setNewAgent({ name: "", agent_type: "social", bio: "" });
        fetchData();
      }
    } catch (error) {
      console.error("Failed to create agent:", error);
    }
  };

  const sendMessage = async () => {
    try {
      const res = await fetch(`${API_BASE}/agents/communicate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_agent: selectedAgent?.agent_name,
          topic: newMessage.topic,
          content: { message: newMessage.content },
          message_type: selectedAgent ? "direct" : "broadcast",
        }),
      });

      if (res.ok) {
        setMessageDialogOpen(false);
        setNewMessage({ topic: "", content: "" });
      }
    } catch (error) {
      console.error("Failed to send message:", error);
    }
  };

  const filteredAgents = agents.filter((agent) => {
    if (activeTab === "all") return true;
    return agent.agent_type === activeTab;
  });

  if (loading) {
    return (
      <div className="flex items-center justify-center h-screen">
        <motion.div
          animate={{ rotate: 360 }}
          transition={{ repeat: Infinity, duration: 1, ease: "linear" }}
        >
          <RefreshCw className="h-8 w-8 text-primary" />
        </motion.div>
      </div>
    );
  }

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        eyebrow="Agent Management"
        title={`จัดการ Agents (${agents.length})`}
        description="จัดการ Agents ทั้งหมดในระบบ - Social, Business และ Negotiations"
        actions={
          <div className="flex gap-2">
            <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              <Button
                variant="secondary"
                onClick={fetchData}
                icon={<RefreshCw className="h-4 w-4" />}
              >
                Refresh
              </Button>
            </motion.div>
            <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              <Button
                onClick={() => setCreateDialogOpen(true)}
                icon={<Plus className="h-4 w-4" />}
              >
                Create Agent
              </Button>
            </motion.div>
          </div>
        }
      />

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <MetricCard
          label="Total Agents"
          value={agents.length.toString()}
          helper={`${agents.filter((a) => a.is_available).length} available`}
          icon={Users}
        />
        <MetricCard
          label="Active Negotiations"
          value={negotiations.length.toString()}
          helper={`${negotiations.filter((n) => n.status === "pending").length} pending`}
          icon={Activity}
        />
        <MetricCard
          label="Facebook Messages"
          value={(socialStats.facebook?.messages_received || 0).toString()}
          helper={`${socialStats.facebook?.messages_sent || 0} sent`}
          icon={MessageCircle}
        />
        <MetricCard
          label="LINE Messages"
          value={(socialStats.line?.messages_received || 0).toString()}
          helper={`${socialStats.line?.messages_sent || 0} sent`}
          icon={Send}
        />
      </div>

      {/* Tabs */}
      <div className="flex gap-2 border-b border-white/10 relative">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`relative px-4 py-2 font-medium transition-colors ${
              activeTab === tab.id
                ? "text-primary"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {activeTab === tab.id && (
              <motion.div
                layoutId="activeTab"
                className="absolute left-0 right-0 bottom-[-1px] h-[2px] bg-primary"
                initial={false}
                transition={{ type: "spring", stiffness: 500, damping: 30 }}
              />
            )}
            {tab.label}
          </button>
        ))}
      </div>

      {/* Content */}
      {activeTab === "negotiations" ? (
        <motion.div layout className="space-y-4">
          <AnimatePresence mode="popLayout">
            {negotiations.length === 0 ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
              >
                <EmptyState message="No active negotiations" />
              </motion.div>
            ) : (
              negotiations.map((neg) => (
                <GlassCard
                  key={neg.id}
                  layout
                  initial={{ opacity: 0, y: 20 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -20 }}
                  intensity="low"
                  className="p-5"
                >
                  <div className="mb-4 flex items-start justify-between gap-4">
                    <div>
                      <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">
                        {neg.initiator} → {neg.responder}
                      </div>
                      <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
                        {neg.task}
                      </h2>
                    </div>
                  </div>
                  <div className="flex items-center justify-between">
                    <StatusPill
                      label={neg.status}
                      tone={neg.status === "pending" ? "warning" : "success"}
                    />
                    <span className="text-sm text-muted-foreground">
                      Expires: {new Date(neg.expires_at).toLocaleTimeString()}
                    </span>
                  </div>
                </GlassCard>
              ))
            )}
          </AnimatePresence>
        </motion.div>
      ) : (
        <motion.div layout className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <AnimatePresence mode="popLayout">
            {filteredAgents.length === 0 ? (
              <motion.div
                key="empty"
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0, scale: 0.9 }}
                className="col-span-full"
              >
                <EmptyState message={`No ${activeTab} agents found`} />
              </motion.div>
            ) : (
              filteredAgents.map((agent) => (
                <GlassCard
                  key={agent.agent_id}
                  layout
                  initial={{ opacity: 0, scale: 0.95 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.95 }}
                  intensity="medium"
                  className="p-5 flex flex-col"
                >
                  <div className="mb-4 flex items-start justify-between gap-4">
                    <div>
                      <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">
                        {agent.agent_type}
                      </div>
                      <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">
                        {agent.agent_name}
                      </h2>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusPill
                        label={agent.is_available ? "Available" : "Busy"}
                        tone={agent.is_available ? "success" : "warning"}
                        pulse={agent.is_available}
                      />
                    </div>
                  </div>

                  <div className="space-y-4 flex-1 flex flex-col">
                    <p className="text-sm text-muted-foreground flex-1">{agent.bio}</p>

                    <div className="flex items-center gap-4 text-sm bg-black/20 p-3 rounded-lg border border-white/5">
                      <div className="flex items-center gap-1">
                        <TrendingUp className="h-4 w-4 text-emerald-400" />
                        <span className="font-medium">{agent.success_rate.toFixed(1)}% success</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <Activity className="h-4 w-4 text-cyan-400" />
                        <span className="font-medium">{agent.completed_tasks} tasks</span>
                      </div>
                    </div>

                    <div className="flex flex-wrap gap-1.5">
                      {agent.capabilities.slice(0, 3).map((cap, idx) => (
                        <span
                          key={idx}
                          className="text-xs bg-white/5 border border-white/10 text-white/80 px-2 py-1 rounded-md"
                        >
                          {cap.name} <span className="opacity-50 ml-1">Lv.{cap.skill_level}</span>
                        </span>
                      ))}
                    </div>

                    <div className="flex gap-2 pt-4 mt-auto">
                      <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }} className="flex-1">
                        <Button
                          variant="secondary"
                          className="w-full"
                          onClick={() => {
                            setSelectedAgent(agent);
                            setMessageDialogOpen(true);
                          }}
                          icon={<Send className="h-4 w-4" />}
                        >
                          Message
                        </Button>
                      </motion.div>
                      <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
                        <Button
                          variant="ghost"
                          className="px-3"
                          icon={<Settings className="h-4 w-4" />}
                        />
                      </motion.div>
                    </div>
                  </div>
                </GlassCard>
              ))
            )}
          </AnimatePresence>
        </motion.div>
      )}

      {/* Create Agent Dialog */}
      <Dialog
        open={createDialogOpen}
        onClose={() => setCreateDialogOpen(false)}
        title="Create New Agent"
        footer={
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => setCreateDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button onClick={createAgent}>Create</Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Name</label>
            <input
              type="text"
              value={newAgent.name}
              onChange={(e) =>
                setNewAgent({ ...newAgent, name: e.target.value })
              }
              placeholder="e.g., Social Media Manager"
              className="input-field"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Type</label>
            <select
              value={newAgent.agent_type}
              onChange={(e) =>
                setNewAgent({ ...newAgent, agent_type: e.target.value })
              }
              className="input-field"
            >
              <option value="social">Social Media</option>
              <option value="business">Business</option>
              <option value="productivity">Productivity</option>
              <option value="creative">Creative</option>
            </select>
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Bio</label>
            <textarea
              value={newAgent.bio}
              onChange={(e) =>
                setNewAgent({ ...newAgent, bio: e.target.value })
              }
              placeholder="Agent's role and capabilities..."
              rows={3}
              className="input-field min-h-[5rem] resize-y"
            />
          </div>
        </div>
      </Dialog>

      {/* Message Dialog */}
      <Dialog
        open={messageDialogOpen}
        onClose={() => setMessageDialogOpen(false)}
        title={`Message ${selectedAgent?.agent_name || "All Agents"}`}
        footer={
          <div className="flex gap-2">
            <Button
              variant="secondary"
              onClick={() => setMessageDialogOpen(false)}
            >
              Cancel
            </Button>
            <Button onClick={sendMessage} icon={<Send className="h-4 w-4" />}>
              Send
            </Button>
          </div>
        }
      >
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Topic</label>
            <input
              type="text"
              value={newMessage.topic}
              onChange={(e) =>
                setNewMessage({ ...newMessage, topic: e.target.value })
              }
              placeholder="e.g., task_assignment"
              className="input-field"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">Message</label>
            <textarea
              value={newMessage.content}
              onChange={(e) =>
                setNewMessage({ ...newMessage, content: e.target.value })
              }
              placeholder="Enter your message..."
              rows={4}
              className="input-field min-h-[5rem] resize-y"
            />
          </div>
        </div>
      </Dialog>
    </div>
  );
}
