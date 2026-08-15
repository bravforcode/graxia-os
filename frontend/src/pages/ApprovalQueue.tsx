import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Clock3, Layers3, RefreshCw, ShieldCheck, XCircle } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Dialog } from '@/components/ui/dialog'
import { EmptyState } from '@/components/ui/empty-state'
import { MetricCard } from '@/components/ui/metric-card'
import { NoticeBanner } from '@/components/ui/notice-banner'
import { PageHeader } from '@/components/ui/page-header'
import { Panel } from '@/components/ui/panel'
import { StatusPill } from '@/components/ui/status-pill'
import { api, type ApprovalRequest } from '@/lib/api'
import { formatRelative } from '@/lib/utils'

type Notice = {
  tone: 'success' | 'warning' | 'danger'
  text: string
} | null

const statusOptions = ['pending', 'approved', 'rejected', 'expired', 'cancelled']

export default function ApprovalQueue() {
  const queryClient = useQueryClient()
  const [status, setStatus] = useState('pending')
  const [notice, setNotice] = useState<Notice>(null)
  const [rejectTarget, setRejectTarget] = useState<ApprovalRequest | null>(null)
  const [rejectNote, setRejectNote] = useState('')

  const {
    data: approvals,
    isError,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['approvals', status],
    queryFn: () => api.getApprovals({ status, limit: 50 }),
  })

  const approveMutation = useMutation({
    mutationFn: (approvalId: string) => api.approveApproval(approvalId),
    onSuccess: async () => {
      setNotice({ tone: 'success', text: 'Approval accepted.' })
      await queryClient.invalidateQueries({ queryKey: ['approvals'] })
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Approval failed.' })
    },
  })

  const rejectMutation = useMutation({
    mutationFn: ({ approvalId, note }: { approvalId: string; note?: string }) =>
      api.rejectApproval(approvalId, note),
    onSuccess: async () => {
      setNotice({ tone: 'warning', text: 'Approval rejected.' })
      await queryClient.invalidateQueries({ queryKey: ['approvals'] })
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Rejection failed.' })
    },
  })

  const items = approvals?.items ?? []
  const pendingCount = items.filter((approval) => approval.status === 'pending').length
  const batchCount = new Set(items.map((approval) => approval.batch_key).filter(Boolean)).size

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Control plane"
        title="Approval queue"
        description="Approve high-impact actions only after the execution context is clear."
        actions={
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => void refetch()}>
            Refresh
          </Button>
        }
      />

      {notice ? <NoticeBanner tone={notice.tone} message={notice.text} onDismiss={() => setNotice(null)} /> : null}
      {isError ? <NoticeBanner tone="danger" message="Approval data is unavailable." /> : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Returned"
          value={String(approvals?.total ?? 0)}
          helper="Actions matching the selected status."
          icon={ShieldCheck}
          accent="cyan"
        />
        <MetricCard
          label="Pending"
          value={String(pendingCount)}
          helper="Actions still waiting for operator decision."
          icon={Clock3}
          accent="orange"
        />
        <MetricCard
          label="Batches"
          value={String(batchCount)}
          helper="Grouped requests in the active filter."
          icon={Layers3}
          accent="blue"
        />
        <MetricCard
          label="Policy classes"
          value={String(new Set(items.map((approval) => approval.policy_class)).size)}
          helper="Distinct control policies in view."
          icon={CheckCircle2}
          accent="green"
        />
      </section>

      <Panel eyebrow="Filters" title="Queue controls">
        <div className="max-w-sm">
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Status</span>
            <select value={status} onChange={(event) => setStatus(event.target.value)} className="input-field">
              {statusOptions.map((option) => (
                <option key={option} value={option}>
                  {option}
                </option>
              ))}
            </select>
          </label>
        </div>
      </Panel>

      <Panel eyebrow="Review" title="Approval requests">
        {isLoading ? (
          <EmptyState message="Loading approvals..." />
        ) : items.length === 0 ? (
          <EmptyState message="No approvals match the selected filter." />
        ) : (
          <div className="space-y-4">
            {items.map((approval) => (
              <ApprovalCard
                key={approval.id}
                approval={approval}
                approving={approveMutation.isPending && approveMutation.variables === approval.id}
                rejecting={rejectMutation.isPending && rejectMutation.variables?.approvalId === approval.id}
                onApprove={() => approveMutation.mutate(approval.id)}
                onReject={() => {
                  setRejectTarget(approval)
                  setRejectNote('')
                }}
              />
            ))}
          </div>
        )}
      </Panel>

      <Dialog
        open={Boolean(rejectTarget)}
        title="Reject approval"
        description="Record the operator reason before closing this request."
        onClose={() => {
          setRejectTarget(null)
          setRejectNote('')
        }}
        footer={
          <>
            <Button
              variant="ghost"
              onClick={() => {
                setRejectTarget(null)
                setRejectNote('')
              }}
            >
              Cancel
            </Button>
            <Button
              variant="secondary"
              icon={<XCircle size={16} />}
              loading={rejectMutation.isPending}
              onClick={() => {
                if (!rejectTarget) {
                  return
                }
                rejectMutation.mutate(
                  { approvalId: rejectTarget.id, note: rejectNote.trim() || undefined },
                  {
                    onSuccess: () => {
                      setRejectTarget(null)
                      setRejectNote('')
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
        <label className="block space-y-2 text-sm text-[var(--color-text-secondary)]">
          <span>Reason</span>
          <textarea
            value={rejectNote}
            onChange={(event) => setRejectNote(event.target.value)}
            className="input-field min-h-28 resize-y"
            placeholder="Why should this action be blocked?"
          />
        </label>
      </Dialog>
    </div>
  )
}

function ApprovalCard({
  approval,
  approving,
  rejecting,
  onApprove,
  onReject,
}: {
  approval: ApprovalRequest
  approving: boolean
  rejecting: boolean
  onApprove: () => void
  onReject: () => void
}) {
  const canDecide = approval.status === 'pending'

  return (
    <article className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill
              label={approval.status}
              tone={
                approval.status === 'approved'
                  ? 'success'
                  : approval.status === 'rejected'
                    ? 'danger'
                    : approval.status === 'pending'
                      ? 'warning'
                      : 'neutral'
              }
            />
            <span className="badge-info">{approval.action_type}</span>
            <span className="badge">{approval.policy_class}</span>
            {approval.batch_key ? <span className="badge">{approval.batch_key}</span> : null}
            {approval.created_at ? <span className="badge">{formatRelative(approval.created_at)}</span> : null}
          </div>

          <h3 className="mt-4 text-xl font-semibold text-[var(--color-text-primary)]">{approval.title}</h3>

          {approval.requested_by ? (
            <p className="mt-2 text-sm text-[var(--color-text-tertiary)]">Requested by {approval.requested_by}</p>
          ) : null}

          <div className="mt-4 grid gap-4 xl:grid-cols-2">
            <ApprovalPayload title="Preview" value={approval.preview} emptyText="No preview payload." />
            <ApprovalPayload title="Details" value={approval.details} emptyText="No detail payload." />
          </div>
        </div>

        {canDecide ? (
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

function ApprovalPayload({
  title,
  value,
  emptyText,
}: {
  title: string
  value?: Record<string, unknown> | null
  emptyText: string
}) {
  const content = value && Object.keys(value).length > 0 ? JSON.stringify(value, null, 2) : emptyText

  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-bg-primary)]/70 p-4">
      <div className="text-xs uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">{title}</div>
      <pre className="mt-3 whitespace-pre-wrap break-words font-mono text-xs leading-5 text-[var(--color-text-secondary)]">
        {content}
      </pre>
    </div>
  )
}
