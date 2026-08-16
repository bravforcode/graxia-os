/**
 * RevenueOSDashboard — CEO dashboard for the standalone Revenue OS API.
 * Shows revenue, campaigns, approvals, incidents, and agent activity.
 * Admin key: set via VITE_REVENUE_OS_ADMIN_KEY or localStorage
 * "revenue_os_admin_key" (Settings page).
 */
import { motion } from "framer-motion";
import {
  AlertTriangle,
  Bot,
  CheckCircle2,
  Clock,
  DollarSign,
  RefreshCw,
  ShieldCheck,
  ShoppingCart,
  Target,
  TrendingUp,
  XCircle,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import {
  formatBaht,
  revenueOsApi,
  type CEODashboardSummary,
} from "../lib/revenueOsApi";
import { cn } from "../lib/utils";

const containerVariants = {
  hidden: { opacity: 0 },
  visible: { opacity: 1, transition: { staggerChildren: 0.05 } },
};

const itemVariants = {
  hidden: { y: 10, opacity: 0 },
  visible: { y: 0, opacity: 1 },
};

function StatCard({
  label,
  value,
  sub,
  icon: Icon,
  accent,
}: {
  label: string;
  value: string;
  sub?: string;
  icon: React.ElementType;
  accent: string;
}) {
  return (
    <motion.div
      variants={itemVariants}
      className="bg-black border border-zinc-800 rounded-xl p-5"
    >
      <div className="flex items-center justify-between">
        <span className="text-xs text-zinc-500 uppercase tracking-wider">
          {label}
        </span>
        <Icon size={16} className={accent} />
      </div>
      <div className="mt-2 text-2xl font-semibold text-zinc-100">{value}</div>
      {sub && <div className="mt-1 text-xs text-zinc-500">{sub}</div>}
    </motion.div>
  );
}

export default function RevenueOSDashboard() {
  const [summary, setSummary] = useState<CEODashboardSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await revenueOsApi.getSummary();
      setSummary(data);
    } catch (err) {
      const detail =
        (err as { response?: { status?: number } }).response?.status === 401
          ? "Unauthorized — set the Revenue OS admin key (VITE_REVENUE_OS_ADMIN_KEY or localStorage 'revenue_os_admin_key')."
          : "Cannot reach Revenue OS API. Is it running? (docker compose -f docker-compose.revenue-os.yml up -d)";
      setError(detail);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const r = summary?.revenue;
  const c = summary?.campaigns;
  const a = summary?.approvals;
  const i = summary?.incidents;
  const ag = summary?.agent_activity;

  return (
    <motion.div
      variants={containerVariants}
      initial="hidden"
      animate="visible"
      className="p-6 space-y-6"
    >
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100">
            Revenue OS — CEO Dashboard
          </h1>
          <p className="text-sm text-zinc-500">
            Autonomous commerce operations ·{" "}
            {summary
              ? `updated ${new Date(summary.generated_at).toLocaleTimeString("th-TH")}`
              : "no data"}
          </p>
        </div>
        <button
          onClick={() => void load()}
          className="flex items-center gap-2 px-3 py-2 rounded-lg border border-zinc-800 text-sm text-zinc-300 hover:bg-zinc-900"
        >
          <RefreshCw size={14} className={loading ? "animate-spin" : ""} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="flex items-start gap-3 rounded-xl border border-red-900/50 bg-red-950/30 p-4 text-sm text-red-300">
          <AlertTriangle size={16} className="mt-0.5 shrink-0" />
          <div>
            <div className="font-medium">Revenue OS API unavailable</div>
            <div className="mt-1 text-red-400/80">{error}</div>
          </div>
        </div>
      )}

      {loading && !summary && (
        <div className="text-sm text-zinc-500">Loading Revenue OS summary…</div>
      )}

      {summary && (
        <>
          {/* Revenue */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              label="Today"
              value={formatBaht(r?.today_cents ?? 0)}
              icon={TrendingUp}
              accent="text-emerald-400"
            />
            <StatCard
              label="This Week"
              value={formatBaht(r?.week_cents ?? 0)}
              icon={DollarSign}
              accent="text-emerald-400"
            />
            <StatCard
              label="This Month"
              value={formatBaht(r?.month_cents ?? 0)}
              icon={DollarSign}
              accent="text-emerald-400"
            />
            <StatCard
              label="Pending Orders"
              value={String(r?.pending_orders ?? 0)}
              sub={`refunds today: ${r?.refunds_today ?? 0}`}
              icon={ShoppingCart}
              accent="text-amber-400"
            />
          </div>

          {/* Operations */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
            <StatCard
              label="Active Campaigns"
              value={String(c?.active ?? 0)}
              sub={`${c?.over_budget ?? 0} over budget · ${c?.needs_approval ?? 0} need approval`}
              icon={Target}
              accent="text-sky-400"
            />
            <StatCard
              label="Pending Approvals"
              value={String(a?.pending_total ?? 0)}
              sub={`${a?.high_priority ?? 0} high priority · ${a?.expiring_soon ?? 0} expiring soon`}
              icon={ShieldCheck}
              accent="text-violet-400"
            />
            <StatCard
              label="Open Incidents"
              value={String(i?.total_open ?? 0)}
              sub={`${i?.critical_open ?? 0} critical · ${i?.high_open ?? 0} high`}
              icon={AlertTriangle}
              accent={i?.critical_open ? "text-red-400" : "text-amber-400"}
            />
            <StatCard
              label="Agent Activity"
              value={String(ag?.new_leads_today ?? 0)}
              sub={`${ag?.pending_bwcp_messages ?? 0} messages · ${ag?.failed_outbox_events ?? 0} outbox failures`}
              icon={Bot}
              accent="text-cyan-400"
            />
          </div>

          {/* Approvals quick actions */}
          <motion.div
            variants={itemVariants}
            className="bg-black border border-zinc-800 rounded-xl p-5"
          >
            <div className="flex items-center gap-2 mb-3">
              <ShieldCheck size={16} className="text-violet-400" />
              <h2 className="text-sm font-medium text-zinc-200">
                Approval Queue
              </h2>
            </div>
            {a?.pending_total === 0 ? (
              <div className="flex items-center gap-2 text-sm text-zinc-500">
                <CheckCircle2 size={14} className="text-emerald-400" />
                No pending approvals — agents are within policy.
              </div>
            ) : (
              <div className="text-sm text-zinc-400">
                {a?.pending_total} items waiting for CEO decision — open the{" "}
                <a
                  href="/ceo/approvals.html"
                  target="_blank"
                  rel="noreferrer"
                  className="text-violet-400 underline hover:text-violet-300"
                >
                  CEO Console
                </a>{" "}
                or approve via Telegram.
              </div>
            )}
          </motion.div>

          {/* Incidents */}
          <motion.div
            variants={itemVariants}
            className="bg-black border border-zinc-800 rounded-xl p-5"
          >
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle size={16} className="text-amber-400" />
              <h2 className="text-sm font-medium text-zinc-200">Incidents</h2>
            </div>
            {i?.total_open === 0 ? (
              <div className="flex items-center gap-2 text-sm text-zinc-500">
                <CheckCircle2 size={14} className="text-emerald-400" />
                All clear — {i?.resolved_today ?? 0} resolved today.
              </div>
            ) : (
              <div className="flex items-center gap-2 text-sm text-amber-300">
                <Clock size={14} />
                {i?.total_open} open incidents ({i?.critical_open} critical) —{" "}
                {i?.resolved_today ?? 0} resolved today.
              </div>
            )}
          </motion.div>

          {/* Agent activity */}
          <motion.div
            variants={itemVariants}
            className="bg-black border border-zinc-800 rounded-xl p-5"
          >
            <div className="flex items-center gap-2 mb-3">
              <Bot size={16} className="text-cyan-400" />
              <h2 className="text-sm font-medium text-zinc-200">
                Agent Activity
              </h2>
            </div>
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 text-sm">
              <div className="text-zinc-400">
                <span className="text-zinc-500">New leads today: </span>
                <span className="text-zinc-200">{ag?.new_leads_today ?? 0}</span>
              </div>
              <div className="text-zinc-400">
                <span className="text-zinc-500">BWCP messages: </span>
                <span className="text-zinc-200">
                  {ag?.pending_bwcp_messages ?? 0}
                </span>
              </div>
              <div className="text-zinc-400">
                <span className="text-zinc-500">Outbox pending: </span>
                <span className="text-zinc-200">
                  {ag?.pending_outbox_events ?? 0}
                </span>
              </div>
              <div
                className={cn(
                  "text-zinc-400",
                  (ag?.failed_outbox_events ?? 0) > 0 && "text-red-400",
                )}
              >
                <span className="text-zinc-500">Outbox failed: </span>
                <span className="text-zinc-200">
                  {ag?.failed_outbox_events ?? 0}
                </span>
              </div>
            </div>
          </motion.div>

          {/* Escalation status */}
          <motion.div
            variants={itemVariants}
            className="flex items-center gap-2 text-xs text-zinc-600"
          >
            <XCircle size={12} />
            Policy-gated autonomy: agents never exceed configured caps without
            CEO approval.
          </motion.div>
        </>
      )}
    </motion.div>
  );
}