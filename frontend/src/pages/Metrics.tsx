import { useQuery } from '@tanstack/react-query'
import { BarChart3, Gauge, RefreshCw, TrendingDown, TrendingUp, Wallet } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { MetricCard } from '@/components/ui/MetricCard'
import { PageHeader } from '@/components/ui/PageHeader'
import { Panel } from '@/components/ui/Panel'
import { api, type WeeklyMetric } from '@/lib/api'
import { formatCurrency, formatDate } from '@/lib/utils'

export default function Metrics() {
  const { data: metrics, refetch } = useQuery({
    queryKey: ['metrics', 12],
    queryFn: () => api.getMetrics(12),
  })

  const latest = metrics?.[0]
  const previous = metrics?.[1]
  const revenueChange =
    latest?.revenue_thb != null && previous?.revenue_thb != null
      ? Number(latest.revenue_thb) - Number(previous.revenue_thb)
      : null

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Performance"
        title="Weekly metrics"
        description="Track opportunity throughput, revenue movement, reply rate, and operator energy across recent weeks."
        actions={
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => void refetch()}>
            Refresh
          </Button>
        }
      />

      {latest ? (
        <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            label="Revenue"
            value={latest.revenue_thb ? formatCurrency(Number(latest.revenue_thb)) : '฿0'}
            helper={
              revenueChange != null
                ? `${revenueChange >= 0 ? '+' : ''}${formatCurrency(revenueChange)} vs previous week`
                : 'No prior week comparison yet.'
            }
            icon={Wallet}
            accent="green"
          />
          <MetricCard
            label="Found"
            value={String(latest.opps_found ?? 0)}
            helper={`${latest.opps_actioned ?? 0} actioned`}
            icon={BarChart3}
            accent="cyan"
          />
          <MetricCard
            label="Reply rate"
            value={latest.reply_rate != null ? `${Number(latest.reply_rate).toFixed(0)}%` : '—'}
            helper={`${latest.outreach_sent ?? 0} outreach sent`}
            icon={Gauge}
            accent="blue"
          />
          <MetricCard
            label="Avg energy"
            value={latest.avg_energy_this_week != null ? `${Number(latest.avg_energy_this_week).toFixed(1)}/10` : '—'}
            helper={latest.ai_cost_usd != null ? `${formatCurrency(Number(latest.ai_cost_usd), 'USD')} AI cost` : 'No AI cost recorded.'}
            icon={revenueChange != null && revenueChange < 0 ? TrendingDown : TrendingUp}
            accent="orange"
          />
        </section>
      ) : null}

      <Panel eyebrow="History" title="Weekly timeline">
        {!metrics?.length ? (
          <EmptyState message="No weekly metrics have been recorded yet." />
        ) : (
          <div className="space-y-4">
            {metrics.map((week) => (
              <MetricWeekCard key={week.id} week={week} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}

function MetricWeekCard({ week }: { week: WeeklyMetric }) {
  return (
    <article className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
        <div>
          <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">
            Week of {formatDate(week.week_start)}
          </div>
          <div className="mt-3 text-2xl font-semibold text-[var(--color-text-primary)]">
            {week.revenue_thb ? formatCurrency(Number(week.revenue_thb)) : '฿0'}
          </div>
        </div>
        <div className="grid min-w-full gap-4 sm:grid-cols-2 lg:min-w-[32rem] lg:grid-cols-3">
          <WeekValue label="Found" value={String(week.opps_found ?? 0)} />
          <WeekValue label="Actioned" value={String(week.opps_actioned ?? 0)} />
          <WeekValue label="Outreach" value={String(week.outreach_sent ?? 0)} />
          <WeekValue label="Reply rate" value={week.reply_rate != null ? `${Number(week.reply_rate).toFixed(0)}%` : '—'} />
          <WeekValue label="Proposals won" value={String(week.proposals_won ?? 0)} />
          <WeekValue
            label="Avg energy"
            value={week.avg_energy_this_week != null ? `${Number(week.avg_energy_this_week).toFixed(1)}/10` : '—'}
          />
        </div>
      </div>
    </article>
  )
}

function WeekValue({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-muted p-4">
      <div className="text-xs uppercase tracking-[0.22em] text-[var(--color-text-tertiary)]">{label}</div>
      <div className="mt-2 text-xl font-semibold text-[var(--color-text-primary)]">{value}</div>
    </div>
  )
}
