import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, CheckCircle2, RefreshCw, RotateCcw, Trash2 } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { EmptyState } from '@/components/ui/empty-state'
import { MetricCard } from '@/components/ui/metric-card'
import { NoticeBanner } from '@/components/ui/notice-banner'
import { PageHeader } from '@/components/ui/page-header'
import { Panel } from '@/components/ui/panel'
import { StatusPill } from '@/components/ui/status-pill'
import { api } from '@/lib/api'
import { formatNumber } from '@/lib/utils'

type Notice = {
  tone: 'success' | 'warning' | 'danger'
  text: string
} | null

function statusTone(status: string) {
  if (status === 'healthy') {
    return 'success' as const
  }
  if (status === 'degraded') {
    return 'warning' as const
  }
  return 'danger' as const
}

export default function EventBus() {
  const queryClient = useQueryClient()
  const [notice, setNotice] = useState<Notice>(null)
  const [pendingAction, setPendingAction] = useState<
    | { kind: 'clear-all' }
    | { kind: 'replay'; index: number }
    | { kind: 'remove'; index: number }
    | null
  >(null)

  const { data: stats, isLoading: statsLoading, refetch: refetchStats } = useQuery({
    queryKey: ['events', 'stats'],
    queryFn: api.getEventStats,
    refetchInterval: 10000,
  })

  const { data: failedEvents, isLoading: failedLoading, refetch: refetchFailed } = useQuery({
    queryKey: ['events', 'failed'],
    queryFn: api.getFailedEvents,
    refetchInterval: 10000,
  })

  const { data: health, isLoading: healthLoading, refetch: refetchHealth } = useQuery({
    queryKey: ['events', 'health'],
    queryFn: api.getEventHealth,
    refetchInterval: 10000,
  })

  const replayMutation = useMutation({
    mutationFn: (index: number) => api.replayFailedEvent(index),
    onSuccess: async () => {
      setNotice({ tone: 'success', text: 'Failed event replayed successfully.' })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['events'] }),
        refetchStats(),
        refetchFailed(),
        refetchHealth(),
      ])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Replay failed.' })
    },
  })

  const removeMutation = useMutation({
    mutationFn: (index: number) => api.removeFailedEvent(index),
    onSuccess: async () => {
      setNotice({ tone: 'warning', text: 'Failed event removed.' })
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['events'] }), refetchFailed(), refetchHealth()])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Failed to remove failed event.' })
    },
  })

  const clearAllMutation = useMutation({
    mutationFn: api.clearFailedEvents,
    onSuccess: async () => {
      setNotice({ tone: 'warning', text: 'All failed events cleared.' })
      await Promise.all([queryClient.invalidateQueries({ queryKey: ['events'] }), refetchFailed(), refetchHealth()])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Failed to clear failed events.' })
    },
  })

  async function refreshAll() {
    await Promise.all([refetchStats(), refetchFailed(), refetchHealth()])
  }

  const loading = statsLoading || failedLoading || healthLoading

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Operations"
        title="Event bus control plane"
        description="Monitor queue depth, failed events, and runtime processing health from a single operations surface."
        actions={
          <>
            <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => void refreshAll()}>
              Refresh
            </Button>
            <Button
              variant="destructive"
              icon={<Trash2 size={16} />}
              loading={clearAllMutation.isPending}
              onClick={() => {
                if (failedEvents?.events?.length) {
                  setPendingAction({ kind: 'clear-all' })
                }
              }}
            >
              Clear failed
            </Button>
          </>
        }
      />

      {notice ? <NoticeBanner tone={notice.tone} message={notice.text} onDismiss={() => setNotice(null)} /> : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Queue size"
          value={formatNumber(health?.queue_size ?? 0)}
          helper="Active events waiting for processing."
          icon={RefreshCw}
          accent="cyan"
        />
        <MetricCard
          label="Processed"
          value={formatNumber(health?.total_events_processed ?? 0)}
          helper="Total events processed across runtime uptime."
          icon={CheckCircle2}
          accent="green"
        />
        <MetricCard
          label="Failed events"
          value={formatNumber(health?.failed_events ?? 0)}
          helper="Events currently parked for manual intervention."
          icon={AlertTriangle}
          accent="orange"
        />
        <MetricCard
          label="Event types"
          value={formatNumber(health?.event_types ?? 0)}
          helper="Distinct event classes seen by the bus."
          icon={RotateCcw}
          accent="blue"
        />
      </section>

      <Panel
        eyebrow="Health"
        title="Processing posture"
        actions={
          <StatusPill label={health?.status ?? (loading ? 'loading' : 'unknown')} tone={statusTone(health?.status ?? 'down')} />
        }
      >
        <div className="grid gap-4 md:grid-cols-4">
          <DataPoint label="Running" value={health?.running ? 'Yes' : 'No'} />
          <DataPoint label="Total events" value={formatNumber(stats?.total_events ?? 0)} />
          <DataPoint label="Failed queue" value={formatNumber(failedEvents?.total ?? 0)} />
          <DataPoint label="Refresh cadence" value="10s" />
        </div>
      </Panel>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <Panel eyebrow="Distribution" title="Events by type">
          <div className="grid gap-3">
            {Object.entries(stats?.by_type ?? {}).length ? (
              Object.entries(stats?.by_type ?? {}).map(([type, count]) => (
                <div
                  key={type}
                  className="flex items-center justify-between rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 px-4 py-3"
                >
                  <span className="text-sm text-[var(--color-text-secondary)]">{type}</span>
                  <span className="font-mono text-sm text-[var(--color-text-primary)]">{formatNumber(count)}</span>
                </div>
              ))
            ) : (
              <EmptyState message="No event stats available yet." />
            )}
          </div>
        </Panel>

        <Panel eyebrow="Intervention queue" title={`Failed events (${failedEvents?.total ?? 0})`}>
          <div className="space-y-4">
            {failedEvents?.events?.length ? (
              failedEvents.events.map((event) => (
                <article
                  key={event.index}
                  className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5"
                >
                  <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <StatusPill label={`#${event.index}`} tone="warning" />
                        <span className="badge-danger">{event.event}</span>
                      </div>
                      <div className="mt-4 text-sm leading-6 text-[var(--color-accent-red)]">{event.error}</div>
                    </div>
                    <div className="flex flex-wrap gap-3">
                      <Button
                        size="sm"
                        variant="secondary"
                        icon={<RotateCcw size={16} />}
                        loading={replayMutation.isPending && replayMutation.variables === event.index}
                        onClick={() => setPendingAction({ kind: 'replay', index: event.index })}
                      >
                        Replay
                      </Button>
                      <Button
                        size="sm"
                        variant="destructive"
                        icon={<Trash2 size={16} />}
                        loading={removeMutation.isPending && removeMutation.variables === event.index}
                        onClick={() => setPendingAction({ kind: 'remove', index: event.index })}
                      >
                        Remove
                      </Button>
                    </div>
                  </div>

                  <details className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-primary)]/65 px-4 py-3">
                    <summary className="cursor-pointer text-sm font-medium text-[var(--color-text-secondary)]">
                      View payload
                    </summary>
                    <pre className="mt-3 overflow-auto whitespace-pre-wrap break-all rounded-2xl bg-slate-950/70 p-4 text-xs text-slate-200">
                      {JSON.stringify(event.payload, null, 2)}
                    </pre>
                  </details>
                </article>
              ))
            ) : (
              <EmptyState message="No failed events are waiting for intervention." />
            )}
          </div>
        </Panel>
      </div>

      <Dialog
        open={Boolean(pendingAction)}
        title={
          pendingAction?.kind === 'clear-all'
            ? 'Clear failed events'
            : pendingAction?.kind === 'replay'
              ? 'Replay failed event'
              : 'Remove failed event'
        }
        description={
          pendingAction?.kind === 'clear-all'
            ? 'This will remove every parked failed event from the queue.'
            : pendingAction?.kind === 'replay'
              ? 'Replay the selected failed event back into the event bus.'
              : 'Remove the selected failed event without replaying it.'
        }
        onClose={() => setPendingAction(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPendingAction(null)}>
              Cancel
            </Button>
            <Button
              variant={pendingAction?.kind === 'remove' || pendingAction?.kind === 'clear-all' ? 'destructive' : 'secondary'}
              loading={
                (pendingAction?.kind === 'clear-all' && clearAllMutation.isPending) ||
                (pendingAction?.kind === 'replay' &&
                  replayMutation.isPending &&
                  replayMutation.variables === pendingAction.index) ||
                (pendingAction?.kind === 'remove' &&
                  removeMutation.isPending &&
                  removeMutation.variables === pendingAction.index)
              }
              onClick={() => {
                if (!pendingAction) {
                  return
                }
                if (pendingAction.kind === 'clear-all') {
                  clearAllMutation.mutate(undefined, {
                    onSuccess: () => setPendingAction(null),
                  })
                  return
                }
                if (pendingAction.kind === 'replay') {
                  replayMutation.mutate(pendingAction.index, {
                    onSuccess: () => setPendingAction(null),
                  })
                  return
                }
                removeMutation.mutate(pendingAction.index, {
                  onSuccess: () => setPendingAction(null),
                })
              }}
            >
              Confirm
            </Button>
          </>
        }
      >
        <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 px-4 py-3 text-sm text-[var(--color-text-secondary)]">
          {pendingAction?.kind === 'clear-all'
            ? `There are currently ${failedEvents?.total ?? 0} failed events in the queue.`
            : `Event #${pendingAction?.index ?? 0}`}
        </div>
      </Dialog>
    </div>
  )
}

function DataPoint({ label, value }: { label: string; value: string }) {
  return (
    <div className="panel-muted p-4">
      <div className="text-xs uppercase tracking-[0.22em] text-[var(--color-text-tertiary)]">{label}</div>
      <div className="mt-2 text-2xl font-semibold text-[var(--color-text-primary)]">{value}</div>
    </div>
  )
}
