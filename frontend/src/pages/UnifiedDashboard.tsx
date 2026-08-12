import { motion } from "framer-motion";
import type { LucideIcon } from "lucide-react";
import {
  Bell,
  Bot,
  Briefcase,
  CheckCircle,
  Cpu,
  Layers,
  LayoutDashboard,
  Mail,
  TrendingUp,
  Users,
  Search,
} from "lucide-react";
import { Suspense, lazy, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type SystemStats } from "../lib/api";
import { cn } from "../lib/utils";

const AgentCanvas = lazy(() => import("../components/canvas/AgentCanvas"));

// Animation Variants
const containerVariants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.05,
    },
  },
};

const itemVariants = {
  hidden: { y: 10, opacity: 0 },
  visible: {
    y: 0,
    opacity: 1,
  },
};

// --- Minimal UI Components ---

function MinimalCard({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <motion.div
      variants={itemVariants}
      className={cn(
        "bg-black border border-zinc-800 rounded-xl p-6",
        className,
      )}
    >
      {children}
    </motion.div>
  );
}

function StatItem({
  title,
  value,
  subtitle,
  trend,
  icon: Icon,
  trendUp,
}: {
  title: string;
  value: string | number;
  subtitle: string;
  trend?: string;
  icon: LucideIcon;
  trendUp?: boolean;
}) {
  return (
    <MinimalCard className="group flex flex-col justify-between space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm font-medium text-zinc-400">
          {title}
        </p>
        <Icon className="w-4 h-4 text-zinc-500" />
      </div>
      <div>
        <div className="text-2xl font-semibold text-white">
          {value}
        </div>
        <div className="flex items-center gap-2 mt-1">
          {trend && (
            <span
              className={cn(
                "text-xs font-medium",
                trendUp
                  ? "text-zinc-300"
                  : "text-zinc-500",
              )}
            >
              {trend}
            </span>
          )}
          <span className="text-xs text-zinc-500 truncate">
            {subtitle}
          </span>
        </div>
      </div>
    </MinimalCard>
  );
}

// Navigation items
const navItems = [
  { icon: LayoutDashboard, label: "Overview", id: "overview", href: "/" },
  { icon: TrendingUp, label: "Revenue", id: "revenue", href: "/ceo" },
  { icon: Users, label: "Leads", id: "leads", href: "/leads" },
  { icon: Mail, label: "Emails", id: "email", href: "/emails" },
  { icon: Briefcase, label: "Tasks", id: "tasks", href: "/tasks" },
  { icon: CheckCircle, label: "Approvals", id: "approvals", href: "/approvals" },
  { icon: Bot, label: "Agents", id: "agents", href: "/agents" },
];

export default function UnifiedDashboard() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("overview");
  const [stats, setStats] = useState<SystemStats | null>(null);

  const fetchStats = async () => {
    try {
      const data = await api.getSystemStats();
      setStats(data);
    } catch (error) {
      console.error("Failed to fetch system stats", error);
    }
  };

  useEffect(() => {
    fetchStats();
  }, []);

  return (
    <div className="min-h-screen bg-black text-zinc-100 font-sans selection:bg-white/30 selection:text-white">
      {/* Header */}
      <header className="border-b border-zinc-800 bg-black sticky top-0 z-50">
        <div className="max-w-[1200px] mx-auto px-6">
          <div className="flex items-center justify-between h-16">
            {/* Brand */}
            <div className="flex items-center gap-3 cursor-pointer" onClick={() => navigate('/')}>
              <div className="w-8 h-8 bg-white rounded-md flex items-center justify-center">
                <Layers className="w-5 h-5 text-black" />
              </div>
              <h1 className="font-semibold text-lg tracking-tight">Graxia</h1>
            </div>

            {/* Navigation */}
            <nav className="hidden lg:flex items-center gap-6">
              {navItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    setActiveTab(item.id);
                    navigate(item.href);
                  }}
                  className={cn(
                    "text-sm font-medium transition-colors",
                    activeTab === item.id
                      ? "text-white"
                      : "text-zinc-500 hover:text-zinc-300",
                  )}
                >
                  {item.label}
                </button>
              ))}
            </nav>

            {/* Actions */}
            <div className="flex items-center gap-4">
              <button
                className="text-zinc-400 hover:text-white transition-colors"
                aria-label="Notifications"
              >
                <Bell className="w-5 h-5" />
              </button>
              <div className="w-8 h-8 rounded-full bg-zinc-900 border border-zinc-800 flex items-center justify-center text-xs font-medium text-white">
                AD
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Grid */}
      <main className="max-w-[1200px] mx-auto px-6 py-8">
        <motion.div 
          initial="hidden"
          animate="visible"
          variants={containerVariants}
          className="space-y-8"
        >
          {/* Welcome Header */}
          <div>
            <h2 className="text-3xl font-semibold tracking-tight text-white">
              สวัสดี — Overview
            </h2>
            <p className="text-sm text-zinc-400 mt-1">
              Graxia Intelligence Dashboard
            </p>
          </div>

          {/* Key Metrics */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <StatItem
              title="Autonomous Actions"
              value={stats ? stats.ai_actions.toLocaleString() : "..."}
              subtitle={`${stats?.completed_24h || 0} Successful (24h)`}
              trend={`${stats?.success_rate || 0}%`}
              trendUp={(stats?.success_rate || 0) > 90}
              icon={Bot}
            />
            <StatItem
              title="Qualified Leads"
              value={stats ? stats.active_leads.toLocaleString() : "..."}
              subtitle={`${stats?.total_contacts || 0} Contacts in DB`}
              trend={`+${stats?.opportunities_found || 0}`}
              trendUp={true}
              icon={Users}
            />
            <StatItem
              title="Agent Outreach"
              value={stats ? stats.outreach_sent_24h.toLocaleString() : "..."}
              subtitle="Email + Telegram"
              icon={Mail}
            />
            <StatItem
              title="Compute Engine"
              value={stats?.active_ai_provider || "..."}
              subtitle={stats?.active_ai_model || "Scanning..."}
              icon={Cpu}
            />
          </div>

          {/* Orchestration Canvas Container */}
          <MinimalCard className="h-[600px] p-0 overflow-hidden relative">
             <div className="absolute top-4 left-4 z-10 flex items-center gap-2 px-3 py-1.5 bg-black border border-zinc-800 rounded-md shadow-sm">
               <Search className="w-3.5 h-3.5 text-zinc-500" />
               <span className="text-xs font-medium text-zinc-300">Agent Mesh</span>
             </div>
              <Suspense
                fallback={
                  <div className="w-full h-full flex items-center justify-center bg-black">
                    <p className="text-zinc-500 text-sm">
                      Loading...
                    </p>
                  </div>
                }
              >
                <AgentCanvas />
              </Suspense>
          </MinimalCard>
        </motion.div>
      </main>
    </div>
  );
}
