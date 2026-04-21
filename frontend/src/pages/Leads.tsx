import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Building2, CalendarClock, Mail, Plus, RefreshCw, Search, Trash2, UserRound } from 'lucide-react'

import { Button } from '@/components/ui/Button'
import { EmptyState } from '@/components/ui/EmptyState'
import { MetricCard } from '@/components/ui/MetricCard'
import { NoticeBanner } from '@/components/ui/NoticeBanner'
import { PageHeader } from '@/components/ui/PageHeader'
import { Panel } from '@/components/ui/Panel'
import { StatusPill } from '@/components/ui/StatusPill'
import { api, type Contact } from '@/lib/api'
import { formatRelative } from '@/lib/utils'

type LeadDraft = {
  name: string
  company: string
  role: string
  email: string
  linkedin_url: string
  value_score: string
  next_followup_date: string
  followup_reason: string
  notes: string
}

type NoticeTone = 'success' | 'warning' | 'danger' | 'info'

const emptyDraft: LeadDraft = {
  name: '',
  company: '',
  role: '',
  email: '',
  linkedin_url: '',
  value_score: '7',
  next_followup_date: '',
  followup_reason: '',
  notes: '',
}

export default function Leads() {
  const queryClient = useQueryClient()
  const [search, setSearch] = useState('')
  const [minScore, setMinScore] = useState('0')
  const [followupDueOnly, setFollowupDueOnly] = useState(false)
  const [draft, setDraft] = useState<LeadDraft>(emptyDraft)
  const [notice, setNotice] = useState<{ tone: NoticeTone; text: string } | null>(null)

  const leadQuery = useQuery({
    queryKey: ['leads', search, minScore, followupDueOnly],
    queryFn: () =>
      api.getContacts({
        contact_type: 'lead',
        q: search.trim() || undefined,
        min_value_score: Number(minScore) > 0 ? Number(minScore) : undefined,
        followup_due_only: followupDueOnly || undefined,
        limit: 100,
      }),
  })

  const statsQuery = useQuery({
    queryKey: ['contacts', 'stats'],
    queryFn: api.getContactStats,
    refetchInterval: 30_000,
  })

  const leads = leadQuery.data?.items ?? []
  const withEmail = useMemo(() => leads.filter((lead) => Boolean(lead.email)).length, [leads])
  const followupDue = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10)
    return leads.filter((lead) => lead.next_followup_date && lead.next_followup_date <= today).length
  }, [leads])

  const createMutation = useMutation({
    mutationFn: () =>
      api.createContact({
        name: draft.name.trim(),
        company: draft.company.trim() || undefined,
        role: draft.role.trim() || undefined,
        email: draft.email.trim() || undefined,
        linkedin_url: draft.linkedin_url.trim() || undefined,
        contact_type: 'lead',
        value_score: Number(draft.value_score || 0) || undefined,
        next_followup_date: draft.next_followup_date || undefined,
        followup_reason: draft.followup_reason.trim() || undefined,
        notes: draft.notes.trim() || undefined,
      }),
    onSuccess: async () => {
      setDraft(emptyDraft)
      setNotice({ tone: 'success', text: 'Lead added to the active pipeline.' })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['leads'] }),
        queryClient.invalidateQueries({ queryKey: ['contacts', 'stats'] }),
      ])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Lead could not be saved.' })
    },
  })

  const markContactedMutation = useMutation({
    mutationFn: (lead: Contact) =>
      api.updateContact(lead.id, {
        last_contacted_at: todayIsoDate(),
        next_followup_date: addDaysIsoDate(3),
        followup_reason: lead.followup_reason || 'Recent outreach touch',
      }),
    onSuccess: async () => {
      setNotice({ tone: 'success', text: 'Lead marked as contacted.' })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['leads'] }),
        queryClient.invalidateQueries({ queryKey: ['contacts', 'stats'] }),
      ])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Contact status could not be updated.' })
    },
  })

  const scheduleFollowupMutation = useMutation({
    mutationFn: (lead: Contact) =>
      api.updateContact(lead.id, {
        next_followup_date: addDaysIsoDate(3),
        followup_reason: lead.followup_reason || 'Scheduled next outreach sequence',
      }),
    onSuccess: async () => {
      setNotice({ tone: 'info', text: 'Follow-up scheduled for the lead.' })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['leads'] }),
        queryClient.invalidateQueries({ queryKey: ['contacts', 'stats'] }),
      ])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Follow-up could not be scheduled.' })
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (leadId: string) => api.deleteContact(leadId),
    onSuccess: async () => {
      setNotice({ tone: 'warning', text: 'Lead removed from the active pipeline.' })
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ['leads'] }),
        queryClient.invalidateQueries({ queryKey: ['contacts', 'stats'] }),
      ])
    },
    onError: () => {
      setNotice({ tone: 'danger', text: 'Lead could not be removed.' })
    },
  })

  function handleCreate() {
    if (!draft.name.trim()) {
      setNotice({ tone: 'warning', text: 'Lead name is required.' })
      return
    }
    createMutation.mutate()
  }

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Revenue pipeline"
        title="Leads"
        description="Qualified prospects, next follow-ups, and direct outreach readiness."
        actions={
          <Button variant="secondary" icon={<RefreshCw size={16} />} onClick={() => void leadQuery.refetch()}>
            Refresh
          </Button>
        }
      />

      {notice ? <NoticeBanner tone={notice.tone} message={notice.text} onDismiss={() => setNotice(null)} /> : null}

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Active leads" value={String(statsQuery.data?.leads ?? leads.length)} helper="Prospects tagged as leads." icon={UserRound} accent="cyan" />
        <MetricCard label="With email" value={String(statsQuery.data?.with_email ?? withEmail)} helper="Ready for direct outreach." icon={Mail} accent="green" />
        <MetricCard label="Follow-up due" value={String(statsQuery.data?.followup_due ?? followupDue)} helper="Needs action today or earlier." icon={CalendarClock} accent="orange" />
        <MetricCard label="Total network" value={String(statsQuery.data?.total ?? 0)} helper="All active contact records." icon={Building2} accent="blue" />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
        <Panel eyebrow="Capture" title="Add lead">
          <LeadForm draft={draft} setDraft={setDraft} saving={createMutation.isPending} onSubmit={handleCreate} />
        </Panel>

        <Panel
          eyebrow="Pipeline"
          title="Active lead list"
          actions={
            <div className="flex flex-wrap items-center gap-3">
              <label className="relative block">
                <span className="sr-only">Search leads</span>
                <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)]" />
                <input
                  className="input-field max-w-[16rem] py-2 pl-9"
                  placeholder="Search leads"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
              <label className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                <span>Min score</span>
                <select
                  className="input-field min-w-[6rem] py-2"
                  value={minScore}
                  onChange={(event) => setMinScore(event.target.value)}
                >
                  <option value="0">All</option>
                  <option value="5">5+</option>
                  <option value="7">7+</option>
                  <option value="9">9+</option>
                </select>
              </label>
              <label className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                <input
                  type="checkbox"
                  checked={followupDueOnly}
                  onChange={(event) => setFollowupDueOnly(event.target.checked)}
                />
                <span>Due only</span>
              </label>
            </div>
          }
        >
          {leadQuery.isLoading ? (
            <EmptyState message="Loading leads..." />
          ) : leads.length ? (
            <div className="grid gap-4 lg:grid-cols-2">
              {leads.map((lead) => (
                <LeadCard
                  key={lead.id}
                  lead={lead}
                  contacting={markContactedMutation.isPending && markContactedMutation.variables?.id === lead.id}
                  scheduling={scheduleFollowupMutation.isPending && scheduleFollowupMutation.variables?.id === lead.id}
                  deleting={deleteMutation.isPending && deleteMutation.variables === lead.id}
                  onMarkContacted={() => markContactedMutation.mutate(lead)}
                  onScheduleFollowup={() => scheduleFollowupMutation.mutate(lead)}
                  onDelete={() => deleteMutation.mutate(lead.id)}
                />
              ))}
            </div>
          ) : (
            <EmptyState message="No active leads match the current filters." />
          )}
        </Panel>
      </div>
    </div>
  )
}

function LeadForm({
  draft,
  setDraft,
  saving,
  onSubmit,
}: {
  draft: LeadDraft
  setDraft: (draft: LeadDraft) => void
  saving: boolean
  onSubmit: () => void
}) {
  function update(field: keyof LeadDraft, value: string) {
    setDraft({ ...draft, [field]: value })
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name" value={draft.name} onChange={(value) => update('name', value)} required />
        <Field label="Company" value={draft.company} onChange={(value) => update('company', value)} />
        <Field label="Role" value={draft.role} onChange={(value) => update('role', value)} />
        <Field label="Email" type="email" value={draft.email} onChange={(value) => update('email', value)} />
        <Field label="LinkedIn URL" value={draft.linkedin_url} onChange={(value) => update('linkedin_url', value)} />
        <Field label="Value score" type="number" min="1" max="10" value={draft.value_score} onChange={(value) => update('value_score', value)} />
        <Field label="Next follow-up" type="date" value={draft.next_followup_date} onChange={(value) => update('next_followup_date', value)} />
        <Field label="Follow-up reason" value={draft.followup_reason} onChange={(value) => update('followup_reason', value)} />
      </div>
      <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
        <span>Notes</span>
        <textarea
          className="input-field min-h-[8rem] resize-y"
          value={draft.notes}
          onChange={(event) => update('notes', event.target.value)}
        />
      </label>
      <Button icon={<Plus size={16} />} loading={saving} onClick={onSubmit}>
        Add lead
      </Button>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
  required = false,
  min,
  max,
}: {
  label: string
  value: string
  onChange: (value: string) => void
  type?: string
  required?: boolean
  min?: string
  max?: string
}) {
  return (
    <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
      <span>{label}</span>
      <input
        className="input-field"
        type={type}
        value={value}
        required={required}
        min={min}
        max={max}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  )
}

function LeadCard({
  lead,
  contacting,
  scheduling,
  deleting,
  onMarkContacted,
  onScheduleFollowup,
  onDelete,
}: {
  lead: Contact
  contacting: boolean
  scheduling: boolean
  deleting: boolean
  onMarkContacted: () => void
  onScheduleFollowup: () => void
  onDelete: () => void
}) {
  return (
    <article className="rounded-[24px] border border-[var(--color-border)] bg-[var(--color-bg-secondary)]/70 p-5">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">{lead.name}</h3>
          {lead.role ? <p className="mt-1 text-sm text-[var(--color-text-secondary)]">{lead.role}</p> : null}
          {lead.company ? <p className="mt-1 text-sm text-[var(--color-text-tertiary)]">{lead.company}</p> : null}
        </div>
        <StatusPill label={`Score ${lead.value_score ?? 0}/10`} tone={(lead.value_score ?? 0) >= 7 ? 'success' : 'info'} />
      </div>

      <div className="mt-4 space-y-2 text-sm text-[var(--color-text-secondary)]">
        {lead.email ? <div className="truncate">Email: {lead.email}</div> : null}
        {lead.next_followup_date ? <div>Next follow-up: {lead.next_followup_date}</div> : null}
        {lead.last_contacted_at ? <div>Last contacted {formatRelative(lead.last_contacted_at)}</div> : null}
      </div>

      {lead.followup_reason ? (
        <p className="mt-4 rounded-2xl border border-[var(--color-border)] bg-[var(--color-bg-primary)]/60 p-4 text-sm leading-6 text-[var(--color-text-secondary)]">
          {lead.followup_reason}
        </p>
      ) : null}

      {lead.notes ? (
        <p className="mt-4 text-sm leading-6 text-[var(--color-text-tertiary)]">{lead.notes}</p>
      ) : null}

      <div className="mt-5 flex flex-wrap gap-3">
        <Button size="sm" variant="secondary" loading={contacting} onClick={onMarkContacted}>
          Mark contacted
        </Button>
        <Button size="sm" variant="outline" loading={scheduling} onClick={onScheduleFollowup}>
          Schedule +3d
        </Button>
        <Button size="sm" variant="ghost" loading={deleting} icon={<Trash2 size={15} />} onClick={onDelete}>
          Remove
        </Button>
      </div>
    </article>
  )
}

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10)
}

function addDaysIsoDate(days: number) {
  const nextDate = new Date()
  nextDate.setUTCDate(nextDate.getUTCDate() + days)
  return nextDate.toISOString().slice(0, 10)
}
