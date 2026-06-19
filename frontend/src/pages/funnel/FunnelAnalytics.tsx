import { useEffect, useState } from "react";
import { 
  TrendingUp, 
  Eye, 
  Users, 
  ShoppingBag, 
  Activity, 
  DollarSign, 
  ArrowLeft,
  Calendar,
  Layers,
  Sparkles,
  AlertTriangle,
  AlertCircle,
  Info,
  CheckCircle2,
  HeartPulse
} from "lucide-react";
import { Link } from "react-router-dom";
import { funnelApi, type FunnelAnalyticsSummary, type FunnelDailyAnalytics } from "../../api/funnel";
import { client } from "../../lib/api";

interface AIRecommendation {
  id: string;
  title: string;
  description: string;
  action: string;
  priority: "critical" | "high" | "medium" | "low";
  category: string;
  impact_estimate: string;
  effort: string;
  metric_trigger: string;
  metric_value?: number;
  metric_benchmark?: number;
}

interface HealthScore {
  overall: number;
  conversion: number;
  traffic: number;
  revenue: number;
  delivery: number;
  label: string;
  summary: string;
}

interface AIRecommendationsResponse {
  health_score: HealthScore;
  recommendations: AIRecommendation[];
  total_recommendations: number;
  analysis_period_days: number;
}

export default function FunnelAnalytics() {
  const [summary, setSummary] = useState<FunnelAnalyticsSummary | null>(null);
  const [dailyData, setDailyData] = useState<FunnelDailyAnalytics[]>([]);
  const [aiData, setAiData] = useState<AIRecommendationsResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [aiLoading, setAiLoading] = useState(false);
  const [dateRange, setDateRange] = useState("30");

  useEffect(() => {
    fetchAnalytics();
  }, [dateRange]);

  const fetchAnalytics = async () => {
    try {
      setLoading(true);
      const [sum, daily] = await Promise.all([
        funnelApi.getAnalyticsSummary(),
        funnelApi.getDailyAnalytics()
      ]);
      setSummary(sum);
      setDailyData(daily);
    } catch (err) {
      console.error("Failed to load analytics dashboard data", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchAIRecommendations = async () => {
    try {
      setAiLoading(true);
      const { data } = await client.get<AIRecommendationsResponse>(
        `/funnel/ai/recommendations?days_back=${dateRange}`
      );
      setAiData(data);
    } catch (err) {
      console.error("Failed to load AI recommendations", err);
    } finally {
      setAiLoading(false);
    }
  };

  const priorityConfig = {
    critical: { color: "text-red-400", bg: "bg-red-500/10", border: "border-red-500/30", Icon: AlertTriangle, label: "Critical" },
    high:     { color: "text-orange-400", bg: "bg-orange-500/10", border: "border-orange-500/30", Icon: AlertCircle, label: "High" },
    medium:   { color: "text-amber-400", bg: "bg-amber-500/10", border: "border-amber-500/30", Icon: Info, label: "Medium" },
    low:      { color: "text-emerald-400", bg: "bg-emerald-500/10", border: "border-emerald-500/30", Icon: CheckCircle2, label: "Low" },
  };

  const healthColor = (score: number) => {
    if (score >= 80) return "text-emerald-400";
    if (score >= 60) return "text-indigo-400";
    if (score >= 35) return "text-amber-400";
    return "text-red-400";
  };

  if (loading) {
    return (
      <div className="p-20 text-center text-slate-400">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-4" />
        Aggregating funnel conversion databases...
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Link 
              to="/products"
              className="p-1.5 bg-slate-900 border border-slate-800 hover:border-slate-700 text-slate-400 hover:text-slate-200 rounded-lg transition-colors"
            >
              <ArrowLeft size={16} />
            </Link>
            <h1 className="text-2xl font-bold text-slate-100 flex items-center gap-2">
              <Activity className="text-indigo-400 w-7 h-7" />
              Funnel Conversion Analytics
            </h1>
          </div>
          <p className="text-sm text-slate-400 mt-1 pl-9">
            Monitor real-time visitor traffic views, leads capture rates, payment drop-offs, and daily revenue completions.
          </p>
        </div>

        {/* Date Filters */}
        <div className="flex items-center gap-2 self-end md:self-auto">
          <Calendar className="text-slate-500 w-4 h-4" />
          <select
            value={dateRange}
            onChange={(e) => setDateRange(e.target.value)}
            className="bg-slate-900/60 border border-slate-800 focus:border-indigo-500 text-slate-300 px-3.5 py-2 rounded-xl text-xs outline-none transition-colors"
          >
            <option value="7">Last 7 Days</option>
            <option value="30">Last 30 Days</option>
            <option value="90">Last 90 Days</option>
          </select>
        </div>
      </div>

      {/* Analytics Summary Panels */}
      {summary && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Net Revenue</p>
                  <h3 className="text-2xl font-extrabold text-slate-100 mt-2">
                    {summary.total_revenue.toLocaleString()} THB
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">
                    AOV: {summary.average_order_value.toFixed(2)} THB
                  </p>
                </div>
                <div className="p-3 bg-emerald-500/10 rounded-xl text-emerald-400">
                  <DollarSign size={20} />
                </div>
              </div>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Total Visitors</p>
                  <h3 className="text-2xl font-extrabold text-slate-100 mt-2">
                    {summary.unique_visitors.toLocaleString()}
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Total views: {summary.views.toLocaleString()}
                  </p>
                </div>
                <div className="p-3 bg-indigo-500/10 rounded-xl text-indigo-400">
                  <Eye size={20} />
                </div>
              </div>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Subscribers / Leads</p>
                  <h3 className="text-2xl font-extrabold text-slate-100 mt-2">
                    {summary.leads.toLocaleString()}
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Opt-in rate: {summary.lead_conversion_rate.toFixed(1)}%
                  </p>
                </div>
                <div className="p-3 bg-purple-500/10 rounded-xl text-purple-400">
                  <Users size={20} />
                </div>
              </div>
            </div>

            <div className="bg-slate-900/50 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <div className="flex items-start justify-between">
                <div>
                  <p className="text-xs text-slate-400 uppercase tracking-wider font-semibold">Paid Sales Orders</p>
                  <h3 className="text-2xl font-extrabold text-slate-100 mt-2">
                    {summary.sales_count.toLocaleString()}
                  </h3>
                  <p className="text-xs text-slate-500 mt-1">
                    Checkout conversions: {summary.checkout_to_purchase_rate.toFixed(1)}%
                  </p>
                </div>
                <div className="p-3 bg-cyan-500/10 rounded-xl text-cyan-400">
                  <ShoppingBag size={20} />
                </div>
              </div>
            </div>
          </div>

          {/* Funnel Step Leakage Visualizer */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            
            {/* Funnel Step chart (5 Columns) */}
            <div className="lg:col-span-5 bg-slate-900/40 border border-slate-800/80 rounded-3xl p-6 shadow-xl backdrop-blur-xl space-y-6">
              <div className="border-b border-slate-850 pb-4">
                <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                  <Layers size={16} className="text-indigo-400" />
                  Conversion Pipeline
                </h3>
                <p className="text-[10px] text-slate-400 mt-0.5">Visualize where customer traffic drops off.</p>
              </div>

              {/* Steps rendering */}
              <div className="space-y-4 pt-2">
                
                {/* Step 1: Views */}
                <div className="space-y-1.5">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-semibold text-slate-200">1. Landing Page Views</span>
                    <span className="font-mono font-bold text-slate-400">{summary.views} (100.0%)</span>
                  </div>
                  <div className="w-full bg-slate-950/60 h-2.5 rounded-full overflow-hidden border border-slate-850">
                    <div className="h-full bg-indigo-500 rounded-full" style={{ width: "100%" }} />
                  </div>
                </div>

                {/* Step 2: Leads captured */}
                <div className="space-y-1.5">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-semibold text-slate-200">2. Free Leads (Sample Opt-in)</span>
                    <span className="font-mono font-bold text-indigo-300">
                      {summary.leads} ({summary.lead_conversion_rate.toFixed(1)}%)
                    </span>
                  </div>
                  <div className="w-full bg-slate-950/60 h-2.5 rounded-full overflow-hidden border border-slate-850">
                    <div 
                      className="h-full bg-gradient-to-r from-indigo-500 to-purple-500 rounded-full" 
                      style={{ width: `${Math.min(100, Math.max(0, summary.lead_conversion_rate))}%` }} 
                    />
                  </div>
                </div>

                {/* Step 3: Checkout Starts */}
                <div className="space-y-1.5">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-semibold text-slate-200">3. Checkout Starts</span>
                    <span className="font-mono font-bold text-amber-300">
                      {summary.checkout_starts} ({summary.checkout_rate.toFixed(1)}%)
                    </span>
                  </div>
                  <div className="w-full bg-slate-950/60 h-2.5 rounded-full overflow-hidden border border-slate-850">
                    <div 
                      className="h-full bg-amber-500 rounded-full" 
                      style={{ width: `${Math.min(100, Math.max(0, summary.checkout_rate))}%` }} 
                    />
                  </div>
                </div>

                {/* Step 4: Purchases */}
                <div className="space-y-1.5">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-semibold text-slate-200">4. Paid Purchases</span>
                    <span className="font-mono font-bold text-emerald-300">
                      {summary.purchases} ({summary.purchase_conversion_rate.toFixed(1)}%)
                    </span>
                  </div>
                  <div className="w-full bg-slate-950/60 h-2.5 rounded-full overflow-hidden border border-slate-850">
                    <div 
                      className="h-full bg-emerald-500 rounded-full" 
                      style={{ width: `${Math.min(100, Math.max(0, summary.purchase_conversion_rate))}%` }} 
                    />
                  </div>
                </div>

                {/* Step 5: Deliveries Opened */}
                <div className="space-y-1.5">
                  <div className="flex justify-between items-center text-xs">
                    <span className="font-semibold text-slate-200">5. Secure Deliveries Downloaded</span>
                    <span className="font-mono font-bold text-cyan-300">
                      {summary.delivery_opened}
                    </span>
                  </div>
                  <div className="w-full bg-slate-950/60 h-2.5 rounded-full overflow-hidden border border-slate-850">
                    <div 
                      className="h-full bg-cyan-400 rounded-full" 
                      style={{ 
                        width: `${summary.purchases > 0 
                          ? Math.min(100, Math.max(0, (summary.delivery_opened / summary.purchases) * 100)) 
                          : 0}%` 
                      }} 
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* Daily logs (7 Columns) */}
            <div className="lg:col-span-7 bg-slate-900/40 border border-slate-800/80 rounded-3xl p-6 shadow-xl backdrop-blur-xl space-y-4">
              <div className="border-b border-slate-850 pb-4 flex justify-between items-center">
                <div>
                  <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                    <TrendingUp size={16} className="text-indigo-400" />
                    Daily Operations Ledger
                  </h3>
                  <p className="text-[10px] text-slate-400 mt-0.5">Chronological record of visitor actions & receipts.</p>
                </div>
              </div>

              {dailyData.length === 0 ? (
                <div className="p-16 text-center text-slate-500 text-xs">
                  No operational records found in selected database range.
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-slate-850 text-slate-400 font-semibold uppercase tracking-wider bg-slate-950/10">
                        <th className="px-4 py-2.5">Date</th>
                        <th className="px-4 py-2.5">Views</th>
                        <th className="px-4 py-2.5">Leads</th>
                        <th className="px-4 py-2.5">Orders</th>
                        <th className="px-4 py-2.5 text-right">Revenue</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-850/50">
                      {dailyData.map((d, index) => (
                        <tr key={index} className="hover:bg-slate-950/15 transition-colors">
                          <td className="px-4 py-3 font-semibold text-slate-300 font-mono">{d.date}</td>
                          <td className="px-4 py-3 text-slate-400 font-mono">{d.views}</td>
                          <td className="px-4 py-3 text-indigo-300 font-mono">+{d.leads}</td>
                          <td className="px-4 py-3 text-emerald-300 font-mono">+{d.purchases}</td>
                          <td className="px-4 py-3 text-slate-200 font-mono font-semibold text-right">
                            {parseFloat(d.revenue.toString()).toFixed(2)} THB
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

          </div>
        </>
      )}

      {/* AI Funnel Recommendations Panel */}
      <div className="bg-slate-900/40 border border-slate-800/80 rounded-3xl p-6 shadow-xl backdrop-blur-xl">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Sparkles size={16} className="text-indigo-400" />
              AI Funnel Recommendations
            </h3>
            <p className="text-[10px] text-slate-400 mt-0.5">Analyzes your funnel data and surfaces prioritized growth actions.</p>
          </div>
          {!aiData && (
            <button
              id="btn-get-ai-recommendations"
              onClick={fetchAIRecommendations}
              disabled={aiLoading}
              className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs font-semibold rounded-xl transition-colors"
            >
              {aiLoading ? (
                <span className="w-3 h-3 border border-white border-t-transparent rounded-full animate-spin" />
              ) : (
                <Sparkles size={13} />
              )}
              {aiLoading ? "Analyzing..." : "Get AI Recommendations"}
            </button>
          )}
          {aiData && (
            <button
              onClick={fetchAIRecommendations}
              disabled={aiLoading}
              className="text-xs text-slate-400 hover:text-slate-200 transition-colors"
            >
              {aiLoading ? "Refreshing..." : "↻ Refresh"}
            </button>
          )}
        </div>

        {!aiData && !aiLoading && (
          <div className="p-10 text-center text-slate-500 text-xs border border-dashed border-slate-800 rounded-2xl">
            <Sparkles size={28} className="mx-auto mb-3 opacity-30" />
            Click "Get AI Recommendations" to analyze your funnel and surface prioritized growth actions.
          </div>
        )}

        {aiLoading && (
          <div className="p-10 text-center text-slate-400 text-xs">
            <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mx-auto mb-3" />
            Analyzing {dateRange}-day funnel data...
          </div>
        )}

        {aiData && !aiLoading && (
          <div className="space-y-5">
            {/* Health Score Row */}
            <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
              {([
                { label: "Overall", value: aiData.health_score.overall },
                { label: "Conversion", value: aiData.health_score.conversion },
                { label: "Traffic", value: aiData.health_score.traffic },
                { label: "Revenue", value: aiData.health_score.revenue },
                { label: "Delivery", value: aiData.health_score.delivery },
              ] as const).map(({ label, value }) => (
                <div key={label} className="bg-slate-950/50 border border-slate-800 rounded-2xl p-3 text-center">
                  <p className="text-[10px] text-slate-500 uppercase tracking-wider mb-1">{label}</p>
                  <p className={`text-2xl font-extrabold ${healthColor(value)}`}>{value}</p>
                  <div className="mt-1.5 h-1 bg-slate-800 rounded-full overflow-hidden">
                    <div className={`h-full rounded-full ${value >= 80 ? 'bg-emerald-500' : value >= 60 ? 'bg-indigo-500' : value >= 35 ? 'bg-amber-500' : 'bg-red-500'}`} style={{ width: `${value}%` }} />
                  </div>
                </div>
              ))}
            </div>

            <div className="flex items-start gap-2 p-3 bg-slate-950/30 border border-slate-800/60 rounded-xl text-xs">
              <HeartPulse size={14} className={`mt-0.5 shrink-0 ${healthColor(aiData.health_score.overall)}`} />
              <div>
                <span className={`font-bold ${healthColor(aiData.health_score.overall)}`}>{aiData.health_score.label}: </span>
                <span className="text-slate-400">{aiData.health_score.summary}</span>
              </div>
            </div>

            {/* Recommendations List */}
            {aiData.recommendations.length === 0 ? (
              <div className="p-8 text-center text-slate-500 text-xs">
                <CheckCircle2 size={24} className="mx-auto mb-2 text-emerald-500" />
                No critical issues found — your funnel is healthy!
              </div>
            ) : (
              <div className="space-y-3">
                {aiData.recommendations.map((rec) => {
                  const cfg = priorityConfig[rec.priority];
                  const RecIcon = cfg.Icon;
                  return (
                    <div key={rec.id} className={`border ${cfg.border} ${cfg.bg} rounded-2xl p-4 space-y-2`}>
                      <div className="flex items-start gap-3">
                        <RecIcon size={15} className={`${cfg.color} mt-0.5 shrink-0`} />
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-xs font-bold text-slate-100">{rec.title}</span>
                            <span className={`text-[9px] px-1.5 py-0.5 rounded font-semibold uppercase ${cfg.bg} ${cfg.color} border ${cfg.border}`}>
                              {cfg.label}
                            </span>
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 uppercase">
                              {rec.category}
                            </span>
                            <span className="text-[9px] text-slate-500">effort: {rec.effort}</span>
                          </div>
                          <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">{rec.description}</p>
                          <div className="mt-2 p-2.5 bg-slate-950/50 border border-slate-800/50 rounded-lg">
                            <p className="text-[11px] text-slate-200">
                              <span className="font-semibold text-indigo-400">→ Action: </span>{rec.action}
                            </p>
                          </div>
                          <p className="text-[10px] text-emerald-400/70 mt-1.5">💡 {rec.impact_estimate}</p>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            <p className="text-[10px] text-slate-600 text-right">
              Analysis period: last {aiData.analysis_period_days} days · {aiData.total_recommendations} recommendation(s)
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
