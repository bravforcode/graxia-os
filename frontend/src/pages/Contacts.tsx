import { useQuery } from '@tanstack/react-query'
import { Building2, Linkedin, Mail, MessageSquare, RefreshCw, UserRound, Users } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { MetricCard } from '@/components/ui/MetricCard'
import { PageHeader } from '@/components/ui/PageHeader'
import { Panel } from '@/components/ui/Panel'
import { StatusPill } from '@/components/ui/StatusPill'
import { api, type Contact } from '@/lib/api'
import { formatRelative } from '@/lib/utils'

export default function Contacts() {
  const { data: contacts, isLoading, refetch } = useQuery({
    queryKey: ['contacts'],
    queryFn: api.getContacts,
  })

  const items = contacts?.items ?? []
  const highStrengthCount = items.filter((contact) => (contact.relationship_strength ?? 0) >= 7).length
  const companyCount = new Set(items.map((contact) => contact.company).filter(Boolean)).size

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Relationship graph"
        title="Contacts"
        description="The active network surface for collaborators, prospects, and warm relationships tracked by the system."
        actions={
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => void refetch()}>
            Refresh
          </Button>
        }
      />

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Total contacts"
          value={String(items.length)}
          helper="Contacts visible in the current workspace."
          icon={Users}
          accent="cyan"
        />
        <MetricCard
          label="High strength"
          value={String(highStrengthCount)}
          helper="Relationships scoring 7 or above."
          icon={UserRound}
          accent="green"
        />
        <MetricCard
          label="Companies"
          value={String(companyCount)}
          helper="Distinct organizations represented."
          icon={Building2}
          accent="blue"
        />
        <MetricCard
          label="With email"
          value={String(items.filter((contact) => Boolean(contact.email)).length)}
          helper="Contacts ready for direct outreach."
          icon={Mail}
          accent="orange"
        />
      </section>

      <Panel eyebrow="Directory" title="Contact list">
        {isLoading ? (
          <EmptyState message="Loading contacts..." />
        ) : items.length === 0 ? (
          <EmptyState message="No contacts have been captured yet." />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {items.map((contact) => (
              <ContactCard key={contact.id} contact={contact} />
            ))}
          </div>
        )}
      </Panel>
    </div>
  )
}

function ContactCard({ contact }: { contact: Contact }) {
  return (
    <article className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">{contact.name}</h3>
          {contact.role ? <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{contact.role}</p> : null}
          {contact.company ? <p className="mt-1 text-sm text-[var(--color-text-tertiary)]">{contact.company}</p> : null}
        </div>
        {contact.contact_type ? <StatusPill label={contact.contact_type} tone="info" /> : null}
      </div>

      <div className="mt-4 space-y-3 text-sm text-[var(--color-text-secondary)]">
        {contact.email ? (
          <div className="flex items-center gap-2">
            <Mail size={14} className="text-[var(--color-accent-cyan)]" />
            <span className="truncate">{contact.email}</span>
          </div>
        ) : null}
        {contact.telegram_handle ? (
          <div className="flex items-center gap-2">
            <MessageSquare size={14} className="text-[var(--color-accent-cyan)]" />
            <span>{contact.telegram_handle}</span>
          </div>
        ) : null}
        {contact.last_contacted_at ? (
          <div className="text-[var(--color-text-tertiary)]">Last contacted {formatRelative(contact.last_contacted_at)}</div>
        ) : null}
      </div>

      {typeof contact.relationship_strength === 'number' ? (
        <div className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 px-4 py-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-[var(--color-text-secondary)]">Relationship strength</span>
            <span className="font-semibold text-[var(--color-text-primary)]">{contact.relationship_strength}/10</span>
          </div>
        </div>
      ) : null}

      {contact.notes ? (
        <div className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 p-4 text-sm leading-6 text-[var(--color-text-secondary)]">
          {contact.notes}
        </div>
      ) : null}

      {contact.linkedin_url ? (
        <div className="mt-4">
          <a
            href={contact.linkedin_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 text-sm font-medium text-[var(--color-accent-cyan)] transition hover:text-[var(--color-accent-lime)]"
          >
            <Linkedin size={16} />
            Open LinkedIn
          </a>
        </div>
      ) : null}
    </article>
  )
}
