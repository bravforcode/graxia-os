import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Calendar, ExternalLink, RefreshCw, ShieldCheck, Target, TimerReset, Zap } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { MetricCard } from '@/components/ui/MetricCard'
import { NoticeBanner } from '@/components/ui/NoticeBanner'
import { PageHeader } from '@/components/ui/PageHeader'
import { Panel } from '@/components/ui/Panel'
import { api, type Opportunity } from '@/lib/api'
import { formatRelative, getScoreBadgeClass, getStatusBadgeClass } from '@/lib/utils'

type Notice = {
  tone: 'success' | 'warning' | 'danger'
  text: string
} | null

export default function Opportunities() {
  const queryClient = useQueryClient()
  const [decision, setDecision] = useState('')
  const [actionPriority, setActionPriority] = useState('')
  const [status, setStatus] = useState('')
  const [notice, setNotice] = useState<Notice>(null)

  const { data: opportunities, isLoading, refetch } = useQuery({
    queryKey: ['opportunities', decision, actionPriority, status],
    queryFn: () =>
      api.getOpportunities({
        decision: decision || undefined,
        action_priority: actionPriority || undefined,
        status: status || undefined,
        limit: 50,
      }),
  })

  const approveMutation = useMutation({
    mutationFn: (opportunityId: string) => api.approveOpportunity(opportunityId),
    onSuccess: async () => {
      setNotice({ tone: 'success', text: 'Opportunity approved successfully.' })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['opportunities'] }),
        refetch(),
      ])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Failed to approve opportunity.' })
    },
  })

  const skipMutation = useMutation({
    mutationFn: (opportunityId: string) => api.skipOpportunity(opportunityId),
    onSuccess: async () => {
      setNotice({ tone: 'warning', text: 'Opportunity moved out of the active queue.' })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['opportunities'] }),
        refetch(),
      ])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Failed to update opportunity.' })
    },
  })

  const items = opportunities?.items ?? []
  const scoredItems = items.filter((item) => typeof item.total_score === 'number')
  const doNowCount = items.filter((item) => item.decision === 'do_now' || item.action_priority === 'do_now').length
  const approvedCount = items.filter((item) => item.status === 'approved').length
  const averageScore =
    scoredItems.length > 0
      ? scoredItems.reduce((total, item) => total + (item.total_score ?? 0), 0) / scoredItems.length
      : 0

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Pipeline"
        title="Opportunities"
        description="Review the active opportunity funnel with score, decision rationale, and operator approval paths."
        actions={
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => void refetch()}>
            Refresh
          </Button>
        }
      />

      {notice ? <NoticeBanner tone={notice.tone} message={notice.text} onDismiss={() => setNotice(null)} /> : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Visible opportunities"
          value={String(opportunities?.total ?? 0)}
          helper="Current rows after active filters."
          icon={Target}
          accent="cyan"
        />
        <MetricCard
          label="Do now"
          value={String(doNowCount)}
          helper="Decision or priority marked for immediate execution."
          icon={Zap}
          accent="green"
        />
        <MetricCard
          label="Approved"
          value={String(approvedCount)}
          helper="Opportunities already promoted into execution."
          icon={ShieldCheck}
          accent="blue"
        />
        <MetricCard
          label="Average score"
          value={scoredItems.length ? `${averageScore.toFixed(1)}/10` : '—'}
          helper="Mean score across scored rows."
          icon={TimerReset}
          accent="orange"
        />
      </section>

      <Panel eyebrow="Filters" title="Queue controls">
        <div className="grid gap-4 md:grid-cols-3">
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Decision</span>
            <select value={decision} onChange={(event) => setDecision(event.target.value)} className="input-field">
              <option value="">All decisions</option>
              <option value="do_now">Do now</option>
              <option value="delay">Delay</option>
              <option value="skip">Skip</option>
            </select>
          </label>
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Action priority</span>
            <select
              value={actionPriority}
              onChange={(event) => setActionPriority(event.target.value)}
              className="input-field"
            >
              <option value="">All priorities</option>
              <option value="do_now">Do now</option>
              <option value="this_week">This week</option>
              <option value="later">Later</option>
            </select>
          </label>
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)} className="input-field">
              <option value="">All statuses</option>
              <option value="found">Found</option>
              <option value="scored">Scored</option>
              <option value="decided">Decided</option>
              <option value="approved">Approved</option>
              <option value="ignored">Ignored</option>
            </select>
          </label>
        </div>
      </Panel>

      <Panel eyebrow="Active queue" title="Opportunity list">
        {isLoading ? (
          <EmptyState message="Loading opportunities..." />
        ) : items.length === 0 ? (
          <EmptyState message="No opportunities match the current filters." />
        ) : (
          <div className="space-y-4">
            {items.map((opportunity) => (
              <OpportunityCard
                key={opportunity.id}
                opportunity={opportunity}
                approving={approveMutation.isPending && approveMutation.variables === opportunity.id}
                skipping={skipMutation.isPending && skipMutation.variables === opportunity.id}
                onApprove={() => approveMutation.mutate(opportunity.id)}
                onSkip={() => skipMutation.mutate(opportunity.id)}
              />
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}

function OpportunityCard({
  opportunity,
  approving,
  skipping,
  onApprove,
  onSkip,
}: {
  opportunity: Opportunity
  approving: boolean
  skipping: boolean
  onApprove: () => void
  onSkip: () => void
}) {
  const status = opportunity.status ?? 'unknown'
  const canApprove = opportunity.status === 'decided' && opportunity.decision === 'do_now'
  const canSkip = opportunity.status !== 'ignored'

  return (
    <article className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className={getScoreBadgeClass(opportunity.total_score ?? 0)}>
              {typeof opportunity.total_score === 'number' ? `${opportunity.total_score.toFixed(1)}/10` : '—'}
            </span>
            <span className="badge">{opportunity.type}</span>
            <span className={getStatusBadgeClass(status)}>{status}</span>
            {opportunity.action_priority ? <span className="badge-info">{opportunity.action_priority}</span> : null}
            {opportunity.deadline ? (
              <span className="badge">
                <Calendar size={12} />
                <span className="ml-1">{opportunity.deadline}</span>
              </span>
            ) : null}
          </div>

          <h3 className="mt-4 text-xl font-semibold text-[var(--color-text-primary)]">{opportunity.title}</h3>

          <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">
            {opportunity.fit_summary || opportunity.description || 'No summary available.'}
          </p>

          {opportunity.tags?.length ? (
            <div className="mt-4 flex flex-wrap gap-2">
              {opportunity.tags.map((tag) => (
                <span key={tag} className="badge">
                  {tag}
                </span>
              ))}
            </div>
          ) : null}

          {opportunity.decision_reasoning ? (
            <div className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">
                Decision reasoning
              </div>
              <p className="mt-2 text-sm leading-6 text-[var(--color-text-secondary)]">{opportunity.decision_reasoning}</p>
            </div>
          ) : null}

          <div className="mt-4 flex flex-wrap items-center gap-4 text-sm text-[var(--color-text-tertiary)]">
            {opportunity.found_at ? <span>Found {formatRelative(opportunity.found_at)}</span> : null}
            {opportunity.prize_amount ? <span className="text-[var(--color-accent-green)]">{opportunity.prize_amount}</span> : null}
            {opportunity.source_platform ? <span>{opportunity.source_platform}</span> : null}
          </div>
        </div>

        <div className="flex flex-wrap gap-3 xl:w-auto xl:flex-col">
          {opportunity.source_url ? (
            <a
              href={opportunity.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center justify-center gap-2 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg-tertiary)] px-4 py-2.5 text-sm font-medium text-[var(--color-text-primary)] transition hover:border-[var(--color-accent-cyan)]"
            >
              <ExternalLink size={16} />
              Source
            </a>
          ) : null}
          {canApprove ? (
            <Button size="sm" loading={approving} onClick={onApprove}>
              Approve
            </Button>
          ) : null}
          {canSkip ? (
            <Button size="sm" variant="secondary" loading={skipping} onClick={onSkip}>
              Skip
            </Button>
          ) : null}
        </div>
      </div>
    </article>
  )
}
