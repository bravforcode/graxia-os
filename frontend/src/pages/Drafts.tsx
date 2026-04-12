import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { FileText, Layers3, RefreshCw, ShieldCheck, Sparkles } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { Dialog } from '@/components/ui/Dialog'
import { EmptyState } from '@/components/ui/EmptyState'
import { MetricCard } from '@/components/ui/MetricCard'
import { NoticeBanner } from '@/components/ui/NoticeBanner'
import { PageHeader } from '@/components/ui/PageHeader'
import { Panel } from '@/components/ui/Panel'
import { StatusPill } from '@/components/ui/StatusPill'
import { api, type Draft } from '@/lib/api'
import { formatRelative } from '@/lib/utils'

type Notice = {
  tone: 'success' | 'warning' | 'danger'
  text: string
} | null

export default function Drafts() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('pending')
  const [notice, setNotice] = useState<Notice>(null)
  const [rejectTarget, setRejectTarget] = useState<Draft | null>(null)
  const [rejectReason, setRejectReason] = useState('')

  const { data: drafts, isLoading, refetch } = useQuery({
    queryKey: ['drafts', status],
    queryFn: () => api.getDrafts(status),
  })

  const approveMutation = useMutation({
    mutationFn: (draftId: string) => api.approveDraft(draftId),
    onSuccess: async () => {
      setNotice({ tone: 'success', text: 'Draft approved successfully.' })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['drafts'] }),
        refetch(),
      ])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Failed to approve draft.' })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: ({ draftId, reason }: { draftId: string; reason?: string }) => api.rejectDraft(draftId, reason),
    onSuccess: async () => {
      setNotice({ tone: 'warning', text: 'Draft rejected.' })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['drafts'] }),
        refetch(),
      ])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Failed to reject draft.' })
    },
  })

  const items = drafts?.items ?? []
  const fallbackCount = items.filter((draft) => draft.was_fallback_draft).length
  const modelCount = new Set(items.map((draft) => draft.model_used).filter(Boolean)).size

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Approval lane"
        title="Draft queue"
        description="Review generated drafts before they are sent into the outside world. Only working approval and rejection flows remain here."
        actions={
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => void refetch()}>
            Refresh
          </Button>
        }
      />

      {notice ? <NoticeBanner tone={notice.tone} message={notice.text} onDismiss={() => setNotice(null)} /> : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Visible drafts"
          value={String(drafts?.total ?? 0)}
          helper="Rows returned by the selected filter."
          icon={FileText}
          accent="cyan"
        />
        <MetricCard
          label="Fallback drafts"
          value={String(fallbackCount)}
          helper="Generated through a fallback path."
          icon={ShieldCheck}
          accent="orange"
        />
        <MetricCard
          label="Model variants"
          value={String(modelCount)}
          helper="Distinct models used in current list."
          icon={Sparkles}
          accent="blue"
        />
        <MetricCard
          label="Pending"
          value={String(items.filter((draft) => (draft.status ?? status) === 'pending').length)}
          helper="Drafts still awaiting operator action."
          icon={Layers3}
          accent="green"
        />
      </section>

      <Panel eyebrow="Filters" title="Queue controls">
        <div className="max-w-sm">
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)} className="input-field">
              <option value="pending">Pending</option>
              <option value="approved">Approved</option>
              <option value="rejected">Rejected</option>
            </select>
          </label>
        </div>
      </Panel>

      <Panel eyebrow="Review surface" title="Draft list">
        {isLoading ? (
          <EmptyState message="Loading drafts..." />
        ) : items.length === 0 ? (
          <EmptyState message="No drafts found for the selected filter." />
        ) : (
          <div className="space-y-4">
            {items.map((draft) => (
              <DraftCard
                key={draft.id}
                draft={draft}
                approving={approveMutation.isPending && approveMutation.variables === draft.id}
                rejecting={rejectMutation.isPending && rejectMutation.variables?.draftId === draft.id}
                onApprove={() => approveMutation.mutate(draft.id)}
                onReject={() => {
                  setRejectTarget(draft)
                  setRejectReason('')
                }}
              />
            ))}
          </div>
        )}
      </Panel>

      <Dialog
        open={Boolean(rejectTarget)}
        title="Reject draft"
        description="Capture operator context before removing this draft from the active queue."
        onClose={() => {
          setRejectTarget(null)
          setRejectReason('')
        }}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setRejectTarget(null)
                setRejectReason('')
              }}
            >
              Cancel
            </Button>
            <Button
              variant="secondary"
              loading={rejectMutation.isPending}
              onClick={() => {
                if (!rejectTarget) {
                  return
                }
                rejectMutation.mutate(
                  { draftId: rejectTarget.id, reason: rejectReason.trim() || undefined },
                  {
                    onSuccess: () => {
                      setRejectTarget(null)
                      setRejectReason('')
                    },
                  }
                )
              }}
            >
              Confirm rejection
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <div className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 px-4 py-3 text-sm text-[var(--color-text-secondary)]">
            {rejectTarget?.title || 'Untitled draft'}
          </div>
          <label className="block space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Reason</span>
            <textarea
              value={rejectReason}
              onChange={(event) => setRejectReason(event.target.value)}
              className="input-field min-h-28 resize-y"
              placeholder="Optional context for why this draft was rejected."
            />
          </label>
        </div>
      </Dialog>
    </div>
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
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {draft.type ? <span className="badge-info">{draft.type}</span> : null}
            {draft.model_used ? <span className="badge">{draft.model_used}</span> : null}
            {draft.was_fallback_draft ? <span className="badge-warning">Fallback</span> : null}
            {draft.status ? <StatusPill label={draft.status} tone={draft.status === 'approved' ? 'success' : draft.status === 'rejected' ? 'danger' : 'warning'} /> : null}
            {draft.created_at ? <span className="badge">{formatRelative(draft.created_at)}</span> : null}
          </div>

          <h3 className="mt-4 text-xl font-semibold text-[var(--color-text-primary)]">{draft.title || 'Untitled draft'}</h3>

          {draft.context_notes ? (
            <p className="mt-3 text-sm leading-6 text-[var(--color-text-secondary)]">{draft.context_notes}</p>
          ) : null}

          <div className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-primary)]/70 p-4">
            <pre className="whitespace-pre-wrap break-words font-sans text-sm leading-6 text-[var(--color-text-secondary)]">
              {draft.content}
            </pre>
          </div>
        </div>

        {(draft.status ?? 'pending') === 'pending' ? (
          <div className="flex flex-wrap gap-3 xl:w-auto xl:flex-col">
            <Button size="sm" loading={approving} onClick={onApprove}>
              Approve
            </Button>
            <Button size="sm" variant="secondary" loading={rejecting} onClick={onReject}>
              Reject
            </Button>
          </div>
        ) : null}
      </div>
    </article>
  )
}
