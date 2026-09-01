import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCircle2, Mail, Paperclip, RefreshCw, Workflow } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/ui/empty-state'
import { MetricCard } from '@/components/ui/metric-card'
import { PageHeader } from '@/components/ui/page-header'
import { Panel } from '@/components/ui/panel'
import { StatusPill } from '@/components/ui/status-pill'
import { api, type EmailThread } from '@/lib/api'
import { formatDateTime } from '@/lib/utils'

function categoryTone(category: string | undefined) {
  switch (category) {
    case 'urgent':
      return 'danger' as const
    case 'important':
      return 'warning' as const
    case 'normal':
      return 'info' as const
    default:
      return 'neutral' as const
  }
}

export default function EmailThreads() {
  const queryClient = useQueryClient()
  const [category, setCategory] = useState('all')
  const [unreadOnly, setUnreadOnly] = useState(true)

  const { data: threads, isLoading, refetch } = useQuery({
    queryKey: ['email-threads', category, unreadOnly],
    queryFn: () =>
      api.getEmailThreads({
        category: category === 'all' ? undefined : category,
        unread_only: unreadOnly,
      }),
  })

  const { data: stats } = useQuery({
    queryKey: ['email-stats'],
    queryFn: api.getEmailStats,
  })

  const markReadMutation = useMutation({
    mutationFn: (threadId: string) => api.markThreadRead(threadId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['email-threads'] }),
        queryClient.invalidateQueries({ queryKey: ['email-stats'] }),
        refetch(),
      ])
    },
  })

  const items = threads?.items ?? []

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Specialized agent"
        title="Email inbox"
        description="Triage the inbox by urgency, unread state, and extracted action items without placeholder thread actions."
        actions={
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => void refetch()}>
            Refresh
          </Button>
        }
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard
          label="Total"
          value={String(stats?.total_threads ?? 0)}
          helper="Threads known to the system."
          icon={Mail}
          accent="cyan"
        />
        <MetricCard
          label="Unread"
          value={String(stats?.unread_count ?? 0)}
          helper="Threads with unread messages."
          icon={AlertCircle}
          accent="blue"
        />
        <MetricCard
          label="Urgent"
          value={String(stats?.by_category?.urgent ?? 0)}
          helper="Threads labeled urgent."
          icon={Workflow}
          accent="orange"
        />
        <MetricCard
          label="Important"
          value={String(stats?.by_category?.important ?? 0)}
          helper="Threads labeled important."
          icon={CheckCircle2}
          accent="green"
        />
        <MetricCard
          label="Action items"
          value={String(stats?.action_items_count ?? 0)}
          helper="Extracted follow-ups across threads."
          icon={Paperclip}
          accent="orange"
        />
      </section>

      <Panel eyebrow="Filters" title="Inbox controls">
        <div className="grid gap-4 md:grid-cols-[minmax(0,18rem)_auto] md:items-end">
          <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
            <span>Category</span>
            <select value={category} onChange={(event) => setCategory(event.target.value)} className="input-field">
              <option value="all">All categories</option>
              <option value="urgent">Urgent</option>
              <option value="important">Important</option>
              <option value="normal">Normal</option>
              <option value="newsletter">Newsletter</option>
              <option value="spam">Spam</option>
            </select>
          </label>

          <label className="inline-flex items-center gap-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 px-4 py-3 text-sm text-[var(--color-text-secondary)]">
            <input
              type="checkbox"
              checked={unreadOnly}
              onChange={(event) => setUnreadOnly(event.target.checked)}
              className="h-4 w-4 rounded border-[var(--color-border)] bg-transparent"
            />
            Unread only
          </label>
        </div>
      </Panel>

      <Panel eyebrow="Inbox surface" title="Thread list">
        {isLoading ? (
          <EmptyState message="Loading inbox threads..." />
        ) : items.length === 0 ? (
          <EmptyState message="No email threads match the current filters." />
        ) : (
          <div className="space-y-4">
            {items.map((thread) => (
              <EmailThreadCard
                key={thread.id}
                thread={thread}
                markingRead={markReadMutation.isPending && markReadMutation.variables === thread.id}
                onMarkRead={() => markReadMutation.mutate(thread.id)}
              />
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}

function EmailThreadCard({
  thread,
  markingRead,
  onMarkRead,
}: {
  thread: EmailThread
  markingRead: boolean
  onMarkRead: () => void
}) {
  const displayTimestamp = thread.last_message_at ?? thread.created_at
  const category = thread.category ?? 'uncategorized'
  const participants = thread.participants?.map((participant) => participant.name || participant.email || 'Unknown').join(', ')

  return (
    <article className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5">
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusPill label={category} tone={categoryTone(thread.category)} />
            <span className="badge">Priority {thread.priority}/10</span>
            {thread.unread_count > 0 ? <span className="badge-info">{thread.unread_count} unread</span> : null}
            {thread.has_attachments ? <span className="badge">Attachment</span> : null}
          </div>

          <h3 className="mt-4 text-xl font-semibold text-[var(--color-text-primary)]">{thread.subject || '(No subject)'}</h3>
          <p className="mt-2 text-sm text-[var(--color-text-secondary)]">{participants}</p>

          {thread.action_items?.length ? (
            <div className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 p-4">
              <div className="text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">
                Action items
              </div>
              <div className="mt-3 space-y-2">
                {thread.action_items.map((item, index) => (
                  <div key={`${thread.id}-${index}`} className="text-sm leading-6 text-[var(--color-text-secondary)]">
                    {item.task}
                  </div>
                ))}
              </div>
            </div>
          ) : null}

          <div className="mt-4 text-sm text-[var(--color-text-tertiary)]">Last activity {formatDateTime(displayTimestamp)}</div>
        </div>

        {thread.status === 'unread' ? (
          <Button size="sm" variant="secondary" loading={markingRead} onClick={onMarkRead}>
            Mark read
          </Button>
        ) : null}
      </div>
    </article>
  )
}
