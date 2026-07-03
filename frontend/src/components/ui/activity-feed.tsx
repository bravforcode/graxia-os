import { AlertTriangle, CheckCircle2, Dot, Radio, ShieldAlert } from 'lucide-react'

import { Panel } from '@/components/ui/panel'
import { formatRelative } from '@/lib/utils'
import type { AgentFeedItem } from '@/hooks/useAgentStream'

function toneIcon(tone: AgentFeedItem['tone']) {
  switch (tone) {
    case 'success':
      return <CheckCircle2 size={16} className="text-[var(--color-accent-green)]" />
    case 'warning':
      return <AlertTriangle size={16} className="text-[var(--color-accent-orange)]" />
    case 'danger':
      return <ShieldAlert size={16} className="text-[var(--color-accent-red)]" />
    default:
      return <Radio size={16} className="text-[var(--color-accent-cyan)]" />
  }
}

type ActivityFeedProps = {
  items: AgentFeedItem[]
  title?: string
  eyebrow?: string
}

export function ActivityFeed({
  items,
  title = 'Agent activity',
  eyebrow = 'Realtime pulse',
}: ActivityFeedProps) {
  return (
    <Panel title={title} eyebrow={eyebrow}>
      <div className="space-y-3">
        {items.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-[var(--color-border)] px-4 py-6 text-sm text-[var(--color-text-tertiary)]">
            No agent events yet. The feed will populate as runtime snapshots arrive.
          </div>
        ) : null}
        {items.map((item) => (
          <div
            key={item.id}
            className="flex gap-3 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/75 p-4"
          >
            <div className="mt-0.5">{toneIcon(item.tone)}</div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium text-[var(--color-text-primary)]">{item.title}</div>
                <div className="text-xs text-[var(--color-text-tertiary)]">{formatRelative(item.timestamp)}</div>
              </div>
              <div className="mt-1 text-sm leading-6 text-[var(--color-text-secondary)]">{item.detail}</div>
              <div className="mt-2 inline-flex items-center gap-1 text-[11px] uppercase tracking-[0.2em] text-[var(--color-text-tertiary)]">
                <Dot size={14} />
                {item.source}
              </div>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  )
}
