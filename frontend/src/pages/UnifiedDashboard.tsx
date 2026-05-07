/**
 * Unified Dashboard - Graxia OS
 * Production Version (No Fake Data)
 */

import type { LucideIcon } from "lucide-react";
import {
  ArrowDownRight,
  ArrowUpRight,
  BarChart3,
  Bell,
  Bot,
  Briefcase,
  CheckCircle,
  Cpu,
  Layers,
  LayoutDashboard,
  Mail,
  RefreshCw,
  Server,
  Settings,
  TrendingUp,
  Users,
} from "lucide-react";
import { Suspense, lazy, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, type SystemStats } from "../lib/api";
import { cn } from "../lib/utils";

const AgentCanvas = lazy(() => import("../components/canvas/AgentCanvas"));

// Navigation items
const navItems = [
  { icon: LayoutDashboard, label: "ภาพรวม", id: "overview", href: "/" },
  { icon: TrendingUp, label: "Revenue OS", id: "revenue", href: "/ceo" },
  { icon: TrendingUp, label: "Quant OS", id: "trading", href: "/trading" },
  { icon: Users, label: "Leads & Contacts", id: "leads", href: "/leads" },
  { icon: Mail, label: "Email", id: "email", href: "/emails" },
  { icon: Briefcase, label: "Tasks", id: "tasks", href: "/tasks" },
  {
    icon: CheckCircle,
    label: "Approvals",
    id: "approvals",
    href: "/approvals",
  },
  { icon: BarChart3, label: "Analytics", id: "analytics", href: "/metrics" },
  { icon: Server, label: "System", id: "system", href: "/system" },
  { icon: Bot, label: "AI Agents", id: "agents", href: "/agents" },
  { icon: Settings, label: "Settings", id: "settings", href: "/settings" },
];

// Components
function Card({
  children,
  className,
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "bg-slate-800/50 border border-slate-700/50 rounded-xl p-6",
        className,
      )}
    >
      {children}
    </div>
  );
}

function StatCard({
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
    <Card className="hover:border-slate-600/50 transition-colors">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm text-slate-400">{title}</p>
          <h3 className="text-2xl font-bold text-slate-100 mt-1">{value}</h3>
          <p className="text-xs text-slate-500 mt-1">{subtitle}</p>
          {trend && (
            <div
              className={cn(
                "flex items-center gap-1 mt-2 text-xs",
                trendUp ? "text-emerald-400" : "text-rose-400",
              )}
            >
              {trendUp ? (
                <ArrowUpRight className="w-3 h-3" />
              ) : (
                <ArrowDownRight className="w-3 h-3" />
              )}
              {trend}
            </div>
          )}
        </div>
        <div className="p-3 bg-slate-700/50 rounded-lg">
          <Icon className="w-5 h-5 text-slate-400" />
        </div>
      </div>
    </Card>
  );
}

// Main Dashboard Component
export default function UnifiedDashboard() {
  const navigate = useNavigate();
  const [activeTab, setActiveTab] = useState("overview");
  const [stats, setStats] = useState<SystemStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [currentTime, setCurrentTime] = useState(new Date());

  const fetchStats = async () => {
    try {
      setLoading(true);
      const data = await api.getSystemStats();
      setStats(data);
    } catch (error) {
      console.error("Failed to fetch system stats", error);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    const timer = setInterval(() => setCurrentTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      {/* Header */}
      <header className="border-b border-slate-800 bg-slate-900/50 backdrop-blur-sm sticky top-0 z-50">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center justify-between h-16">
            {/* Logo */}
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-lg flex items-center justify-center">
                <Layers className="w-5 h-5 text-white" />
              </div>
              <div>
                <h1 className="font-bold text-lg">Graxia OS</h1>
                <p className="text-xs text-slate-400">Unified Dashboard</p>
              </div>
            </div>

            {/* Navigation */}
            <nav className="hidden md:flex items-center gap-1">
              {navItems.slice(0, 7).map((item) => (
                <button
                  key={item.id}
                  onClick={() => {
                    setActiveTab(item.id);
                    navigate(item.href);
                  }}
                  className={cn(
                    "flex items-center gap-2 px-3 py-2 rounded-lg text-sm transition-colors",
                    activeTab === item.id
                      ? "bg-slate-800 text-slate-100"
                      : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/50",
                  )}
                >
                  <item.icon className="w-4 h-4" />
                  <span className="hidden lg:inline">{item.label}</span>
                </button>
              ))}
            </nav>

            {/* Actions */}
            <div className="flex items-center gap-3">
              <button
                aria-label="Notifications"
                className="p-2 text-slate-400 hover:text-slate-200 transition-colors relative"
              >
                <Bell className="w-5 h-5" />
                <span className="absolute top-1 right-1 w-2 h-2 bg-rose-500 rounded-full" />
              </button>
              <button
                aria-label="Refresh"
                onClick={fetchStats}
                className={cn(
                  "p-2 text-slate-400 hover:text-slate-200 transition-colors",
                  loading && "animate-spin text-indigo-500",
                )}
              >
                <RefreshCw className="w-5 h-5" />
              </button>
              <div className="w-8 h-8 bg-slate-700 rounded-full flex items-center justify-center">
                <span className="text-sm font-medium">SYS</span>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Welcome */}
        <div className="mb-8">
          <h2 className="text-2xl font-bold text-slate-100">ระบบพร้อมใช้งาน</h2>
          <p className="text-slate-400 mt-1">
            {currentTime.toLocaleDateString("th-TH", {
              weekday: "long",
              year: "numeric",
              month: "long",
              day: "numeric",
              hour: "2-digit",
              minute: "2-digit",
            })}
            {" | Environment: "}
            {stats?.environment || "Loading..."}
          </p>
        </div>

        {/* Stats Grid - Real Data */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <StatCard
            title="Total AI Actions"
            value={stats ? stats.ai_actions.toLocaleString() : "..."}
            subtitle={`${stats?.completed_24h || 0} completed in 24h`}
            trend={`${stats?.success_rate || 0}% success rate`}
            trendUp={(stats?.success_rate || 0) > 90}
            icon={Bot}
          />
          <StatCard
            title="Active Leads"
            value={stats ? stats.active_leads.toLocaleString() : "..."}
            subtitle={`${stats?.total_contacts || 0} total contacts`}
            trend={`${stats?.opportunities_found || 0} opportunities`}
            trendUp={true}
            icon={Users}
          />
          <StatCard
            title="Outreach Sent"
            value={stats ? stats.outreach_sent_24h.toLocaleString() : "..."}
            subtitle="Last 24 hours"
            icon={Mail}
          />
          <StatCard
            title="AI Model Status"
            value={stats?.active_ai_provider || "..."}
            subtitle={stats?.active_ai_model || "Checking..."}
            icon={Cpu}
          />
        </div>

        {/* Agent Orchestration Canvas */}
        <div className="h-[calc(100vh-400px)] min-h-[500px] border border-slate-800 rounded-2xl overflow-hidden bg-slate-900 shadow-2xl relative">
          <Suspense
            fallback={
              <div className="w-full h-full flex items-center justify-center bg-slate-950">
                <div className="flex flex-col items-center gap-4">
                  <RefreshCw className="w-8 h-8 text-indigo-500 animate-spin" />
                  <p className="text-slate-400 font-medium animate-pulse">
                    Initializing Agent Canvas...
                  </p>
                </div>
              </div>
            }
          >
            <AgentCanvas />
          </Suspense>
        </div>
      </main>
    </div>
  );
}
