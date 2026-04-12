import { useQuery } from '@tanstack/react-query'
import { AlertTriangle, CalendarDays, DollarSign, RefreshCw, TrendingUp, Wallet } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { MetricCard } from '@/components/ui/MetricCard'
import { PageHeader } from '@/components/ui/PageHeader'
import { Panel } from '@/components/ui/Panel'
import { StatusPill } from '@/components/ui/StatusPill'
import { api } from '@/lib/api'
import { formatCurrency } from '@/lib/utils'

function percentageTone(percentage: number) {
  if (percentage >= 90) {
    return 'danger' as const
  }
  if (percentage >= 70) {
    return 'warning' as const
  }
  return 'success' as const
}

export default function Costs() {
  const { data: summary, refetch: refetchSummary } = useQuery({
    queryKey: ['costs-summary'],
    queryFn: api.getCostsSummary,
  })

  const { data: usage, refetch: refetchUsage } = useQuery({
    queryKey: ['costs-usage'],
    queryFn: () => api.getCostsUsage({ days: 30 }),
  })

  const { data: forecast, refetch: refetchForecast } = useQuery({
    queryKey: ['costs-forecast'],
    queryFn: api.getCostsForecast,
  })

  async function refreshAll() {
    await Promise.all([refetchSummary(), refetchUsage(), refetchForecast()])
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Budget guardrails"
        title="Cost monitoring"
        description="Track LLM spend, monthly forecast, and platform-level usage before the system burns through budget."
        actions={
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => void refreshAll()}>
            Refresh
          </Button>
        }
      />

      {summary ? (
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Today"
            value={formatCurrency(summary.today.cost_usd, 'USD')}
            helper={`${summary.today.percentage.toFixed(0)}% of ${formatCurrency(summary.today.budget_usd, 'USD')}`}
            icon={CalendarDays}
            accent="cyan"
          />
          <MetricCard
            label="This week"
            value={formatCurrency(summary.week.cost_usd, 'USD')}
            helper={`${summary.week.percentage.toFixed(0)}% of ${formatCurrency(summary.week.budget_usd, 'USD')}`}
            icon={DollarSign}
            accent="blue"
          />
          <MetricCard
            label="This month"
            value={formatCurrency(summary.month.cost_usd, 'USD')}
            helper={`${summary.month.percentage.toFixed(0)}% of ${formatCurrency(summary.month.budget_usd, 'USD')}`}
            icon={Wallet}
            accent="orange"
          />
          <MetricCard
            label="Requests"
            value={String(usage?.total_requests ?? 0)}
            helper={usage ? `Average ${formatCurrency(usage.avg_cost_per_request, 'USD')} per request` : 'No usage yet.'}
            icon={TrendingUp}
            accent="green"
          />
        </section>
      ) : null}

      {forecast ? (
        <Panel
          eyebrow="Forecast"
          title="Monthly outlook"
          actions={<StatusPill label={forecast.over_budget ? 'Over budget' : 'Within budget'} tone={forecast.over_budget ? 'danger' : 'success'} />}
        >
          <div className="grid gap-4 lg:grid-cols-4">
            <BudgetValue label="Current cost" value={formatCurrency(forecast.current_cost, 'USD')} />
            <BudgetValue label="Forecasted cost" value={formatCurrency(forecast.forecasted_cost, 'USD')} />
            <BudgetValue label="Daily average" value={formatCurrency(forecast.daily_average, 'USD')} />
            <BudgetValue label="Budget" value={formatCurrency(forecast.budget, 'USD')} />
          </div>

          {forecast.over_budget ? (
            <div className="mt-4 rounded-2xl border border-[rgba(239,95,86,0.2)] bg-[rgba(239,95,86,0.08)] px-4 py-4 text-sm text-[var(--color-accent-red)]">
              <div className="flex items-center gap-2">
                <AlertTriangle size={16} />
                Forecast exceeds budget by {formatCurrency(forecast.forecasted_cost - forecast.budget, 'USD')}.
              </div>
            </div>
          ) : null}
        </Panel>
      ) : null}

      {summary ? (
        <Panel eyebrow="Budget windows" title="Consumption by period">
          <div className="grid gap-4 lg:grid-cols-3">
            {[
              ['Today', summary.today.cost_usd, summary.today.budget_usd, summary.today.percentage],
              ['This week', summary.week.cost_usd, summary.week.budget_usd, summary.week.percentage],
              ['This month', summary.month.cost_usd, summary.month.budget_usd, summary.month.percentage],
            ].map(([label, cost, budget, percentage]) => (
              <div key={label} className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5">
                <div className="flex items-center justify-between">
                  <div className="text-sm text-[var(--color-text-secondary)]">{label}</div>
                  <StatusPill label={`${Number(percentage).toFixed(0)}%`} tone={percentageTone(Number(percentage))} />
                </div>
                <div className="mt-4 text-2xl font-semibold text-[var(--color-text-primary)]">
                  {formatCurrency(Number(cost), 'USD')}
                </div>
                <div className="mt-2 text-sm text-[var(--color-text-tertiary)]">
                  of {formatCurrency(Number(budget), 'USD')}
                </div>
                <div className="mt-4 h-2 overflow-hidden rounded-full bg-[var(--color-bg-tertiary)]">
                  <div
                    className="h-full rounded-full bg-[var(--color-accent-cyan)] transition-all"
                    style={{ width: `${Math.min(Number(percentage), 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Panel>
      ) : null}

      {usage ? (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
          <Panel eyebrow="30 day view" title="Usage summary">
            <div className="grid gap-4 sm:grid-cols-3">
              <BudgetValue label="Total requests" value={String(usage.total_requests)} />
              <BudgetValue label="Total cost" value={formatCurrency(usage.total_cost_usd, 'USD')} />
              <BudgetValue label="Avg/request" value={formatCurrency(usage.avg_cost_per_request, 'USD')} />
            </div>
          </Panel>

          <Panel eyebrow="Provider mix" title="Usage by platform">
            {Object.keys(usage.by_platform).length ? (
              <div className="space-y-4">
                {Object.entries(usage.by_platform).map(([platform, value]) => (
                  <div
                    key={platform}
                    className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-4"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-semibold capitalize text-[var(--color-text-primary)]">{platform}</div>
                        <div className="mt-1 text-sm text-[var(--color-text-secondary)]">{value.requests} requests</div>
                      </div>
                      <div className="text-sm font-semibold text-[var(--color-accent-cyan)]">
                        {formatCurrency(value.cost_usd, 'USD')}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <EmptyState message="No platform usage records available for this period." />
            )}
          </Panel>
        </div>
      ) : null}
    </div>
  )
}

function BudgetValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-muted p-4">
      <div className="text-xs uppercase tracking-[0.22em] text-[var(--color-text-tertiary)]">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-[var(--color-text-primary)]">{value}</div>
    </div>
  )
}
