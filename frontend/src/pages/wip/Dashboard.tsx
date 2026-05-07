import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useOutletContext } from 'react-router-dom'
import {
  Activity,
  Bot,
  CalendarClock,
  FileText,
  RefreshCw,
  Shield,
  Sparkles,
  Target,
  Users,
  Wallet,
  Zap,
} from 'lucide-react'

import { ActivityFeed } from '@/components/ui/ActivityFeed'
import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { MetricCard } from '@/components/ui/MetricCard'
import { NoticeBanner } from '@/components/ui/NoticeBanner'
import { PageHeader } from '@/components/ui/PageHeader'
import { Panel } from '@/components/ui/Panel'
import { StatusPill } from '@/components/ui/StatusPill'
import type { AppShellContext } from '@/components/Layout'
import { api, type Draft, type Opportunity, type SystemStatsHistoryItem } from '@/lib/api'
import { formatCurrency, formatRelative, getScoreBadgeClass } from '@/lib/utils'

type NoticeTone = 'success' | 'warning' | 'danger' | 'info'

type NoticeState = {
  tone: NoticeTone
  text: string
} | null

export default function Dashboard() {
  const queryClient = useQueryClient()
  const { health, stats, feed, refreshRuntime } = useOutletContext<AppShellContext>()
  const [notice, setNotice] = useState<NoticeState>(null)
  const [checkinModal, setCheckinModal] = useState(false)
  const [checkinData, setCheckinData] = useState({ energy: 7, stress: 3, available_hours_this_week: 20 })

  const { data: opportunities } = useQuery({
    queryKey: ['opportunities', 'do_now'],
    queryFn: () => api.getOpportunities({ decision: 'do_now', limit: 4 }),
  })

  const { data: drafts } = useQuery({
    queryKey: ['drafts', 'pending'],
    queryFn: () => api.getDrafts('pending'),
  })

  const { data: cognitive } = useQuery({
    queryKey: ['cognitive'],
    queryFn: api.getCognitiveToday,
  })

  const { data: metrics } = useQuery({
    queryKey: ['metrics'],
    queryFn: () => api.getMetrics(1),
  })

  const { data: costs } = useQuery({
    queryKey: ['costs', 'summary'],
    queryFn: api.getCostsSummary,
  })

  const { data: systemStats } = useQuery({
    queryKey: ['system', 'stats'],
    queryFn: api.getSystemStats,
    refetchInterval: 30_000,
  })

  const scanMutation = useMutation({
    mutationFn: api.triggerScan,
    onSuccess: async () => {
      setNotice({ tone: 'success', text: 'Opportunity scan triggered successfully.' })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['opportunities'] }),
        refreshRuntime(),
      ])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Failed to trigger opportunity scan.' })
    },
  })

  const briefMutation = useMutation({
    mutationFn: api.triggerBrief,
    onSuccess: async () => {
      setNotice({ tone: 'success', text: 'Daily brief triggered successfully.' })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['drafts'] }),
        refreshRuntime(),
      ])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Failed to trigger daily brief.' })
    },
  })

  const checkinMutation = useMutation({
    mutationFn: () => api.checkin(checkinData),
    onSuccess: async () => {
      setNotice({ tone: 'success', text: 'Cognitive check-in updated.' })
      setCheckinModal(false)
      await queryClient.invalidateQueries({ queryKey: ['cognitive'] })
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Failed to save check-in.' })
    },
  })

  const approveDraftMutation = useMutation({
    mutationFn: (draftId: string) => api.approveDraft(draftId),
    onSuccess: async () => {
      setNotice({ tone: 'success', text: 'Draft approved.' })
      await queryClient.invalidateQueries({ queryKey: ['drafts'] })
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Failed to approve draft.' })
    },
  })

  const rejectDraftMutation = useMutation({
    mutationFn: (draftId: string) => api.rejectDraft(draftId),
    onSuccess: async () => {
      setNotice({ tone: 'warning', text: 'Draft rejected.' })
      await queryClient.invalidateQueries({ queryKey: ['drafts'] })
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Failed to reject draft.' })
    },
  })

  const weeklyMetrics = metrics?.[0]
  const todayCost = costs?.today
  const feedSlice = feed.slice(0, 6)
  const runtimeHealthy = health && !health.llm_degraded && !health.llm_cost_paused

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Phase 2 surface"
        title="Executive dashboard"
        description="A high-signal control surface for opportunity flow, draft approvals, runtime health, and budget discipline."
        actions={
          <>
            <Button
              variant="secondary"
              icon={<RefreshCw size={16} />}
              loading={scanMutation.isPending}
              onClick={() => scanMutation.mutate()}
            >
              Run scan
            </Button>
            <Button
              variant="secondary"
              icon={<Sparkles size={16} />}
              loading={briefMutation.isPending}
              onClick={() => briefMutation.mutate()}
            >
              Draft brief
            </Button>
            <Button icon={<CalendarClock size={16} />} onClick={() => setCheckinModal(true)}>
              Update check-in
            </Button>
          </>
        }
      />

      {notice ? <NoticeBanner tone={notice.tone} message={notice.text} onDismiss={() => setNotice(null)} /> : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Do now"
          value={String(opportunities?.total ?? 0)}
          helper="High-priority opportunities ready for action."
          accent="cyan"
          icon={Target}
        />
        <MetricCard
          label="Pending drafts"
          value={String(drafts?.total ?? 0)}
          helper="Approval queue waiting on operator review."
          accent="blue"
          icon={FileText}
        />
        <MetricCard
          label="Week revenue"
          value={weeklyMetrics?.revenue_thb ? formatCurrency(Number(weeklyMetrics.revenue_thb)) : '฿0'}
          helper={`${weeklyMetrics?.opps_actioned ?? 0} opportunities actioned this week.`}
          accent="green"
          icon={Wallet}
        />
        <MetricCard
          label="AI spend today"
          value={todayCost ? formatCurrency(todayCost.cost_usd, 'USD') : '$0'}
          helper={
            todayCost
              ? `${todayCost.percentage.toFixed(0)}% of ${formatCurrency(todayCost.budget_usd, 'USD')} budget`
              : 'No usage recorded yet.'
          }
          accent="orange"
          icon={Activity}
        />
      </section>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Leads scanned"
          value={String(systemStats?.leads_scanned ?? 0)}
          helper={`${systemStats?.active_leads ?? 0} active leads and ${systemStats?.opportunities_found ?? 0} opportunities.`}
          accent="cyan"
          icon={Users}
        />
        <MetricCard
          label="AI actions"
          value={String(systemStats?.ai_actions ?? 0)}
          helper={`${systemStats?.completed_24h ?? 0} completed and ${systemStats?.failed_24h ?? 0} failed in 24h.`}
          accent="blue"
          icon={Bot}
        />
        <MetricCard
          label="Success rate"
          value={`${systemStats?.success_rate ?? 0}%`}
          helper={`${systemStats?.outreach_sent_24h ?? 0} outreach touches in the last 24h.`}
          accent="green"
          icon={Shield}
        />
        <MetricCard
          label="AI engine"
          value={systemStats?.active_ai_provider ?? 'Unknown'}
          helper={systemStats?.active_ai_model ?? 'No active model reported.'}
          accent="orange"
          icon={Zap}
        />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div className="space-y-6">
          <Panel
            eyebrow="Opportunity queue"
            title="Top opportunities"
            actions={<StatusPill label={`${opportunities?.total ?? 0} open`} tone="info" />}
          >
            <div className="space-y-4">
              {opportunities?.items?.length ? (
                opportunities.items.map((opp) => <OpportunityCard key={opp.id} opportunity={opp} />)
              ) : (
                <EmptyState message="No high-priority opportunities are currently queued." />
              )}
            </div>
          </Panel>

          <Panel eyebrow="Draft approvals" title="Pending drafts">
            <div className="space-y-4">
              {drafts?.items?.length ? (
                drafts.items.map((draft) => (
                  <DraftCard
                    key={draft.id}
                    draft={draft}
                    approving={approveDraftMutation.isPending && approveDraftMutation.variables === draft.id}
                    rejecting={rejectDraftMutation.isPending && rejectDraftMutation.variables === draft.id}
                    onApprove={() => approveDraftMutation.mutate(draft.id)}
                    onReject={() => rejectDraftMutation.mutate(draft.id)}
                  />
                ))
              ) : (
                <EmptyState message="No drafts are waiting for review." />
              )}
            </div>
          </Panel>
        </div>

        <div className="space-y-6">
          <Panel eyebrow="Runtime posture" title="Operational state">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="panel-muted p-4">
                <div className="text-xs uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">Readiness</div>
                <div className="mt-2 flex items-center gap-3">
                  <StatusPill
                    label={health?.readiness.mode ?? 'unknown'}
                    tone={runtimeHealthy ? 'success' : 'warning'}
                  />
                </div>
                <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">
                  {health?.readiness.issues?.length
                    ? health.readiness.issues[0]
                    : 'Runtime is operating without readiness blockers.'}
                </p>
              </div>
              <div className="panel-muted p-4">
                <div className="text-xs uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">Event flow</div>
                <div className="mt-2 text-3xl font-semibold text-[var(--color-text-primary)]">
                  {stats?.total_events ?? 0}
                </div>
                <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">
                  {Object.keys(stats?.by_type ?? {}).length} event types observed across the active pipeline.
                </p>
              </div>
            </div>

            <div className="mt-4 grid gap-4 sm:grid-cols-4">
              <StatDetail label="Energy" value={`${cognitive?.energy ?? 7}/10`} icon={Zap} />
              <StatDetail label="Stress" value={`${cognitive?.stress ?? 3}/10`} icon={Shield} />
              <StatDetail
                label="Available hours"
                value={`${cognitive?.available_hours_this_week ?? 20}h`}
                icon={CalendarClock}
              />
              <StatDetail label="Engine" value={systemStats?.active_ai_provider ?? 'Unknown'} icon={Bot} />
            </div>
          </Panel>

          <Panel
            eyebrow="Real-time metrics"
            title="7-day execution history"
            actions={<StatusPill label={systemStats?.environment ?? 'unknown'} tone="info" />}
          >
            <ExecutionHistoryChart items={systemStats?.history ?? []} />
          </Panel>

          <ActivityFeed items={feedSlice} />
        </div>
      </div>

      <Dialog
        open={checkinModal}
        title="Update cognitive state"
        description="Keep the system aligned with your actual energy, stress, and weekly capacity before the next automation pass."
        onClose={() => setCheckinModal(false)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCheckinModal(false)}>
              Cancel
            </Button>
            <Button loading={checkinMutation.isPending} onClick={() => checkinMutation.mutate()}>
              Save check-in
            </Button>
          </>
        }
      >
        <div className="grid gap-4 sm:grid-cols-3">
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Energy (0-10)</span>
            <input
              type="number"
              min="0"
              max="10"
              className="input-field"
              value={checkinData.energy}
              onChange={(event) =>
                setCheckinData((current) => ({ ...current, energy: Number(event.target.value) }))
              }
            />
          </label>
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Stress (0-10)</span>
            <input
              type="number"
              min="0"
              max="10"
              className="input-field"
              value={checkinData.stress}
              onChange={(event) =>
                setCheckinData((current) => ({ ...current, stress: Number(event.target.value) }))
              }
            />
          </label>
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Hours this week</span>
            <input
              type="number"
              min="0"
              max="168"
              className="input-field"
              value={checkinData.available_hours_this_week}
              onChange={(event) =>
                setCheckinData((current) => ({
                  ...current,
                  available_hours_this_week: Number(event.target.value),
                }))
              }
            />
          </label>
        </div>
      </Dialog>
    </div>
  )
}

function ExecutionHistoryChart({ items }: { items: SystemStatsHistoryItem[] }) {
  const maxValue = Math.max(
    1,
    ...items.map((item) => item.success + item.failed + item.leads + item.outreach)
  )

  if (!items.length) {
    return <EmptyState message="No execution history is available yet." />
  }

  return (
    <div aria-label="7-day execution history" className="space-y-4">
      <div className="grid h-56 grid-cols-7 items-end gap-3 rounded-[20px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/50 p-4">
        {items.map((item) => {
          const successHeight = Math.max(4, (item.success / maxValue) * 100)
          const failedHeight = Math.max(4, (item.failed / maxValue) * 100)
          const leadHeight = Math.max(4, (item.leads / maxValue) * 100)
          const outreachHeight = Math.max(4, (item.outreach / maxValue) * 100)

          return (
            <div key={item.date} className="flex h-full min-w-0 flex-col justify-end gap-1">
              <div className="flex h-full items-end gap-1" title={`${item.date}: ${item.success} success, ${item.failed} failed, ${item.leads} leads, ${item.outreach} outreach`}>
                <div
                  className="min-h-[6px] flex-1 rounded-t bg-[var(--color-accent-green)]"
                  style={{ height: `${successHeight}%` }}
                />
                <div
                  className="min-h-[6px] flex-1 rounded-t bg-[var(--color-accent-red)]"
                  style={{ height: `${failedHeight}%` }}
                />
                <div
                  className="min-h-[6px] flex-1 rounded-t bg-[var(--color-accent-cyan)]"
                  style={{ height: `${leadHeight}%` }}
                />
                <div
                  className="min-h-[6px] flex-1 rounded-t bg-[var(--color-accent-orange)]"
                  style={{ height: `${outreachHeight}%` }}
                />
              </div>
              <div className="truncate text-center text-[11px] text-[var(--color-text-tertiary)]">{item.name}</div>
            </div>
          )
        })}
      </div>
      <div className="flex flex-wrap gap-3 text-xs text-[var(--color-text-secondary)]">
        <LegendDot className="bg-[var(--color-accent-green)]" label="Success" />
        <LegendDot className="bg-[var(--color-accent-red)]" label="Failed" />
        <LegendDot className="bg-[var(--color-accent-cyan)]" label="Leads" />
        <LegendDot className="bg-[var(--color-accent-orange)]" label="Outreach" />
      </div>
    </div>
  )
}

function LegendDot({ className, label }: { className: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className={`h-2.5 w-2.5 rounded-full ${className}`} />
      {label}
    </span>
  )
}

function StatDetail({
  label,
  value,
  icon: Icon,
}: {
  label: string
  value: string
  icon: typeof Zap
}) {
  return (
    <div className="panel-muted p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm text-[var(--color-text-secondary)]">{label}</span>
        <Icon size={16} className="text-[var(--color-accent-cyan)]" />
      </div>
      <div className="mt-2 text-xl font-semibold text-[var(--color-text-primary)]">{value}</div>
    </div>
  )
}

function OpportunityCard({ opportunity }: { opportunity: Opportunity }) {
  return (
    <article className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={getScoreBadgeClass(opportunity.total_score ?? 0)}>
          {(opportunity.total_score ?? 0).toFixed(1)}/10
        </span>
        <span className="badge">{opportunity.type}</span>
        {opportunity.action_priority ? <span className="badge-info">{opportunity.action_priority}</span> : null}
      </div>

      <h3 className="mt-4 text-xl font-semibold text-[var(--color-text-primary)]">{opportunity.title}</h3>
      <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">
        {opportunity.fit_summary || opportunity.description || 'No summary is available for this opportunity yet.'}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-[var(--color-text-tertiary)]">
        {opportunity.deadline ? <span>Deadline {opportunity.deadline}</span> : null}
        {opportunity.found_at ? <span>Found {formatRelative(opportunity.found_at)}</span> : null}
        {opportunity.prize_amount ? <span className="text-[var(--color-accent-green)]">{opportunity.prize_amount}</span> : null}
      </div>
    </article>
  )
}

function DraftCard({
  draft,
  approving,
  rejecting,
  onApprove,
  onReject,
}: {
  draft: Draft
  approving: boolean
  rejecting: boolean
  onApprove: () => void
  onReject: () => void
}) {
  return (
    <article className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="badge-info">{draft.type ?? 'draft'}</span>
        {draft.created_at ? <span className="badge">{formatRelative(draft.created_at)}</span> : null}
      </div>
      <h3 className="mt-4 text-lg font-semibold text-[var(--color-text-primary)]">{draft.title || 'Untitled draft'}</h3>
      <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">
        {draft.content ? `${draft.content.slice(0, 180)}${draft.content.length > 180 ? '...' : ''}` : 'No preview available.'}
      </p>
      <div className="mt-5 flex flex-wrap gap-3">
        <Button size="sm" loading={approving} onClick={onApprove}>
          Approve
        </Button>
        <Button size="sm" variant="secondary" loading={rejecting} onClick={onReject}>
          Reject
        </Button>
      </div>
    </article>
  )
}
