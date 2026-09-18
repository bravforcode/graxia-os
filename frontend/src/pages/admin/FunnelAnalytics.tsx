import { useState, useEffect } from "react";
import { RefreshCw } from "lucide-react";
import { MetricCard } from "@/components/admin/MetricCard";
import { PageHeader } from "@/components/ui/page-header";
import { Panel } from "@/components/ui/panel";
import { Button } from "@/components/ui/button";
import { getFunnelAnalytics, type FunnelAnalytics } from "@/lib/admin-api";

export default function FunnelAnalyticsPage() {
  const [loading, setLoading] = useState(true);
  const [analytics, setAnalytics] = useState<FunnelAnalytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadAnalytics();
  }, []);

  async function loadAnalytics() {
    setLoading(true);
    setError(null);
    const data = await getFunnelAnalytics();
    if (data) {
      setAnalytics(data);
    } else {
      setError("Could not load funnel analytics. Ensure the backend is running with funnel tools registered.");
    }
    setLoading(false);
  }

  // Helper to get a metric value from various funnel response shapes
  const getMetricValue = (obj: Record<string, unknown> | undefined, key: string): string | number => {
    if (!obj) return "-";
    const val = obj[key] ?? obj[`total_${key}`] ?? obj[`${key}_count`] ?? "-";
    if (typeof val === "number") return val;
    if (typeof val === "string") return val;
    return "-";
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Funnel Analytics"
        description="Local funnel metrics via MCP read-only tools."
        actions={
          <Button variant="outline" size="sm" onClick={loadAnalytics} loading={loading}>
            <RefreshCw className="h-4 w-4" /> Refresh
          </Button>
        }
      />

      {error && (
        <div className="rounded-xl border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-amber-400">
          {error}
        </div>
      )}

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="h-6 w-6 animate-spin rounded-full border-2 border-zinc-600 border-t-white" />
        </div>
      )}

      {!loading && analytics && (
        <div className="space-y-6">
          {/* Top metrics */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
            <MetricCard
              title="Revenue"
              value={getMetricValue(analytics.revenue_summary as Record<string, unknown> | undefined, "amount")}
              subtitle={getMetricValue(analytics.revenue_summary as Record<string, unknown> | undefined, "currency") as string || "USD"}
              status="up"
            />
            <MetricCard
              title="Orders"
              value={getMetricValue(analytics.orders_summary as Record<string, unknown> | undefined, "count")}
              subtitle="Recent orders"
              status="neutral"
            />
            <MetricCard
              title="Conversion"
              value={getMetricValue(analytics.conversion_summary as Record<string, unknown> | undefined, "rate")}
              subtitle="Conversion rate"
              status={Number(getMetricValue(analytics.conversion_summary as Record<string, unknown> | undefined, "rate")) > 2 ? "up" : "warning"}
            />
            <MetricCard
              title="Abandonment"
              value={getMetricValue(analytics.checkout_abandonment as Record<string, unknown> | undefined, "rate")}
              subtitle="Checkout drop-off"
              status={Number(getMetricValue(analytics.checkout_abandonment as Record<string, unknown> | undefined, "rate")) > 50 ? "critical" : "neutral"}
            />
            <MetricCard
              title="Delivery Open"
              value={getMetricValue(analytics.delivery_open_rate as Record<string, unknown> | undefined, "rate")}
              subtitle="Delivery open rate"
              status={Number(getMetricValue(analytics.delivery_open_rate as Record<string, unknown> | undefined, "rate")) > 50 ? "up" : "warning"}
            />
          </div>

          {/* Raw data panels */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            {analytics.revenue_summary && Object.keys(analytics.revenue_summary).length > 0 && (
              <Panel title="Revenue Summary" eyebrow="FUNNEL">
                <pre className="text-xs text-zinc-400 overflow-auto max-h-40">
                  {JSON.stringify(analytics.revenue_summary, null, 2)}
                </pre>
              </Panel>
            )}
            {analytics.orders_summary && Object.keys(analytics.orders_summary).length > 0 && (
              <Panel title="Orders Summary" eyebrow="FUNNEL">
                <pre className="text-xs text-zinc-400 overflow-auto max-h-40">
                  {JSON.stringify(analytics.orders_summary, null, 2)}
                </pre>
              </Panel>
            )}
          </div>

          {/* Source note */}
          <div className="text-xs text-zinc-500 text-center">
            Data sourced from MCP read-only funnel tools. No real Stripe or Google API calls.
          </div>
        </div>
      )}

      {!loading && !analytics && !error && (
        <div className="rounded-xl border border-dashed border-zinc-800 py-12 text-center text-sm text-zinc-500">
          No funnel data available.
        </div>
      )}
    </div>
  );
}
