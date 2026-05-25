import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CalendarClock,
  Mail,
  Plus,
  RefreshCw,
  Search,
  Trash2,
  UserRound,
} from "lucide-react";
import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { MetricCard } from "@/components/ui/metric-card";
import { NoticeBanner } from "@/components/ui/notice-banner";
import { PageHeader } from "@/components/ui/page-header";
import { GlassCard } from "@/components/ui/glass-card";
import { AnimatedTooltip } from "@/components/ui/animated-tooltip";
import { StatusPill } from "@/components/ui/status-pill";
import { api, type Contact } from "@/lib/api";
import { formatRelative } from "@/lib/utils";

type LeadDraft = {
  name: string;
  company: string;
  role: string;
  email: string;
  linkedin_url: string;
  value_score: string;
  next_followup_date: string;
  followup_reason: string;
  notes: string;
};

type NoticeTone = "success" | "warning" | "danger" | "info";

const emptyDraft: LeadDraft = {
  name: "",
  company: "",
  role: "",
  email: "",
  linkedin_url: "",
  value_score: "7",
  next_followup_date: "",
  followup_reason: "",
  notes: "",
};

export default function Leads() {
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [minScore, setMinScore] = useState("0");
  const [followupDueOnly, setFollowupDueOnly] = useState(false);
  const [draft, setDraft] = useState<LeadDraft>(emptyDraft);
  const [notice, setNotice] = useState<{
    tone: NoticeTone;
    text: string;
  } | null>(null);

  const leadQuery = useQuery({
    queryKey: ["leads", search, minScore, followupDueOnly],
    queryFn: () =>
      api.getContacts({
        contact_type: "lead",
        q: search.trim() || undefined,
        min_value_score: Number(minScore) > 0 ? Number(minScore) : undefined,
        followup_due_only: followupDueOnly || undefined,
        limit: 100,
      }),
  });

  const statsQuery = useQuery({
    queryKey: ["contacts", "stats"],
    queryFn: api.getContactStats,
    refetchInterval: 30_000,
  });

  const withEmail = useMemo(() => {
    const items = leadQuery.data?.items ?? [];
    return items.filter((lead) => Boolean(lead.email)).length;
  }, [leadQuery.data?.items]);
  const followupDue = useMemo(() => {
    const items = leadQuery.data?.items ?? [];
    const today = new Date().toISOString().slice(0, 10);
    return items.filter(
      (lead) => lead.next_followup_date && lead.next_followup_date <= today,
    ).length;
  }, [leadQuery.data?.items]);

  const createMutation = useMutation({
    mutationFn: () =>
      api.createContact({
        name: draft.name.trim(),
        company: draft.company.trim() || undefined,
        role: draft.role.trim() || undefined,
        email: draft.email.trim() || undefined,
        linkedin_url: draft.linkedin_url.trim() || undefined,
        contact_type: "lead",
        value_score: Number(draft.value_score || 0) || undefined,
        next_followup_date: draft.next_followup_date || undefined,
        followup_reason: draft.followup_reason.trim() || undefined,
        notes: draft.notes.trim() || undefined,
      }),
    onSuccess: async () => {
      setDraft(emptyDraft);
      setNotice({
        tone: "success",
        text: "Lead added to the active pipeline.",
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["leads"] }),
        queryClient.invalidateQueries({ queryKey: ["contacts", "stats"] }),
      ]);
    },
    onError: () => {
      setNotice({ tone: "danger", text: "Lead could not be saved." });
    },
  });

  const markContactedMutation = useMutation({
    mutationFn: (lead: Contact) =>
      api.updateContact(lead.id, {
        last_contacted_at: todayIsoDate(),
        next_followup_date: addDaysIsoDate(3),
        followup_reason: lead.followup_reason || "Recent outreach touch",
      }),
    onSuccess: async () => {
      setNotice({ tone: "success", text: "Lead marked as contacted." });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["leads"] }),
        queryClient.invalidateQueries({ queryKey: ["contacts", "stats"] }),
      ]);
    },
    onError: () => {
      setNotice({
        tone: "danger",
        text: "Contact status could not be updated.",
      });
    },
  });

  const scheduleFollowupMutation = useMutation({
    mutationFn: (lead: Contact) =>
      api.updateContact(lead.id, {
        next_followup_date: addDaysIsoDate(3),
        followup_reason:
          lead.followup_reason || "Scheduled next outreach sequence",
      }),
    onSuccess: async () => {
      setNotice({ tone: "info", text: "Follow-up scheduled for the lead." });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["leads"] }),
        queryClient.invalidateQueries({ queryKey: ["contacts", "stats"] }),
      ]);
    },
    onError: () => {
      setNotice({ tone: "danger", text: "Follow-up could not be scheduled." });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (leadId: string) => api.deleteContact(leadId),
    onSuccess: async () => {
      setNotice({
        tone: "warning",
        text: "Lead removed from the active pipeline.",
      });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["leads"] }),
        queryClient.invalidateQueries({ queryKey: ["contacts", "stats"] }),
      ]);
    },
    onError: () => {
      setNotice({ tone: "danger", text: "Lead could not be removed." });
    },
  });

  function handleCreate() {
    if (!draft.name.trim()) {
      setNotice({ tone: "warning", text: "Lead name is required." });
      return;
    }
    createMutation.mutate();
  }

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        eyebrow="Revenue pipeline"
        title="Leads"
        description="Qualified prospects, next follow-ups, and direct outreach readiness."
        actions={
          <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
            <Button
              variant="secondary"
              icon={<RefreshCw size={16} />}
              onClick={() => void leadQuery.refetch()}
            >
              Refresh
            </Button>
          </motion.div>
        }
      />

      <AnimatePresence>
        {notice && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
          >
            <NoticeBanner
              tone={notice.tone}
              message={notice.text}
              onDismiss={() => setNotice(null)}
            />
          </motion.div>
        )}
      </AnimatePresence>

      <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard
          label="Active leads"
          value={String(
            statsQuery.data?.leads ?? (leadQuery.data?.items ?? []).length,
          )}
          helper="Prospects tagged as leads."
          icon={UserRound}
          accent="cyan"
        />
        <MetricCard
          label="With email"
          value={String(statsQuery.data?.with_email ?? withEmail)}
          helper="Ready for direct outreach."
          icon={Mail}
          accent="green"
        />
        <MetricCard
          label="Follow-up due"
          value={String(statsQuery.data?.followup_due ?? followupDue)}
          helper="Needs action today or earlier."
          icon={CalendarClock}
          accent="orange"
        />
        <MetricCard
          label="Total network"
          value={String(statsQuery.data?.total ?? 0)}
          helper="All active contact records."
          icon={Building2}
          accent="blue"
        />
      </section>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] items-start">
        <GlassCard intensity="low" className="p-5">
          <div className="mb-4">
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">
              Capture
            </div>
            <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Add lead</h2>
          </div>
          <LeadForm
            draft={draft}
            setDraft={setDraft}
            saving={createMutation.isPending}
            onSubmit={handleCreate}
          />
        </GlassCard>

        <GlassCard intensity="low" className="p-5 overflow-hidden flex flex-col">
          <div className="mb-6 flex flex-col sm:flex-row sm:items-start justify-between gap-4 border-b border-white/5 pb-4">
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-[0.24em] text-[var(--color-text-tertiary)]">
                Pipeline
              </div>
              <h2 className="text-lg font-semibold text-[var(--color-text-primary)]">Active lead list</h2>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <label className="relative block">
                <span className="sr-only">Search leads</span>
                <Search
                  size={15}
                  className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--color-text-tertiary)]"
                />
                <input
                  className="input-field max-w-[16rem] py-2 pl-9 bg-black/20"
                  placeholder="Search leads"
                  value={search}
                  onChange={(event) => setSearch(event.target.value)}
                />
              </label>
              <label className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)]">
                <span className="hidden sm:inline">Min score</span>
                <select
                  className="input-field min-w-[5rem] py-2 bg-black/20"
                  value={minScore}
                  onChange={(event) => setMinScore(event.target.value)}
                >
                  <option value="0">All</option>
                  <option value="5">5+</option>
                  <option value="7">7+</option>
                  <option value="9">9+</option>
                </select>
              </label>
              <label className="flex items-center gap-2 text-sm text-[var(--color-text-secondary)] cursor-pointer hover:text-white transition-colors">
                <input
                  type="checkbox"
                  className="rounded border-white/10 bg-black/20 text-primary focus:ring-primary focus:ring-offset-black"
                  checked={followupDueOnly}
                  onChange={(event) => setFollowupDueOnly(event.target.checked)}
                />
                <span>Due only</span>
              </label>
            </div>
          </div>

          <div className="flex-1">
            {leadQuery.isLoading ? (
              <EmptyState message="Loading leads..." />
            ) : (leadQuery.data?.items ?? []).length ? (
              <motion.div layout className="grid gap-4 lg:grid-cols-2">
                <AnimatePresence mode="popLayout">
                  {(leadQuery.data?.items ?? []).map((lead) => (
                    <LeadCard
                      key={lead.id}
                      lead={lead}
                      contacting={
                        markContactedMutation.isPending &&
                        markContactedMutation.variables?.id === lead.id
                      }
                      scheduling={
                        scheduleFollowupMutation.isPending &&
                        scheduleFollowupMutation.variables?.id === lead.id
                      }
                      deleting={
                        deleteMutation.isPending &&
                        deleteMutation.variables === lead.id
                      }
                      onMarkContacted={() => markContactedMutation.mutate(lead)}
                      onScheduleFollowup={() =>
                        scheduleFollowupMutation.mutate(lead)
                      }
                      onDelete={() => deleteMutation.mutate(lead.id)}
                    />
                  ))}
                </AnimatePresence>
              </motion.div>
            ) : (
              <EmptyState message="No active leads match the current filters." />
            )}
          </div>
        </GlassCard>
      </div>
    </div>
  );
}

function LeadForm({
  draft,
  setDraft,
  saving,
  onSubmit,
}: {
  draft: LeadDraft;
  setDraft: (draft: LeadDraft) => void;
  saving: boolean;
  onSubmit: () => void;
}) {
  function update(field: keyof LeadDraft, value: string) {
    setDraft({ ...draft, [field]: value });
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Name"
          value={draft.name}
          onChange={(value) => update("name", value)}
          required
        />
        <Field
          label="Company"
          value={draft.company}
          onChange={(value) => update("company", value)}
        />
        <Field
          label="Role"
          value={draft.role}
          onChange={(value) => update("role", value)}
        />
        <Field
          label="Email"
          type="email"
          value={draft.email}
          onChange={(value) => update("email", value)}
        />
        <Field
          label="LinkedIn URL"
          value={draft.linkedin_url}
          onChange={(value) => update("linkedin_url", value)}
        />
        <Field
          label="Value score"
          type="number"
          min="1"
          max="10"
          value={draft.value_score}
          onChange={(value) => update("value_score", value)}
        />
        <Field
          label="Next follow-up"
          type="date"
          value={draft.next_followup_date}
          onChange={(value) => update("next_followup_date", value)}
        />
        <Field
          label="Follow-up reason"
          value={draft.followup_reason}
          onChange={(value) => update("followup_reason", value)}
        />
      </div>
      <label className="space-y-2 text-sm text-[var(--color-text-secondary)]">
        <span>Notes</span>
        <textarea
          className="input-field min-h-[8rem] resize-y"
          value={draft.notes}
          onChange={(event) => update("notes", event.target.value)}
        />
      </label>
      <motion.div whileHover={{ scale: 1.01 }} whileTap={{ scale: 0.99 }}>
        <Button className="w-full justify-center" icon={<Plus size={16} />} loading={saving} onClick={onSubmit}>
          Add lead
        </Button>
      </motion.div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = "text",
  required = false,
  min,
  max,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  required?: boolean;
  min?: string;
  max?: string;
}) {
  return (
    <label className="space-y-1.5 text-sm text-[var(--color-text-secondary)] block">
      <span>{label}</span>
      <input
        className="input-field py-2"
        type={type}
        value={value}
        required={required}
        min={min}
        max={max}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
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
  lead: Contact;
  contacting: boolean;
  scheduling: boolean;
  deleting: boolean;
  onMarkContacted: () => void;
  onScheduleFollowup: () => void;
  onDelete: () => void;
}) {
  const isHighValue = (lead.value_score ?? 0) >= 7;
  
  return (
    <motion.article 
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      className="rounded-2xl border border-white/5 bg-zinc-900/40 p-5 shadow-lg backdrop-blur-md transition-all hover:bg-zinc-900/60 hover:border-white/10"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)]">
            {lead.name}
          </h3>
          {lead.role ? (
            <p className="mt-0.5 text-sm text-[var(--color-text-secondary)]">
              {lead.role}
            </p>
          ) : null}
          {lead.company ? (
            <p className="mt-0.5 text-xs text-primary/80 font-medium">
              {lead.company}
            </p>
          ) : null}
        </div>
        <AnimatedTooltip content={isHighValue ? "High priority prospect based on recent activity." : "Standard priority prospect."}>
          <div>
            <StatusPill
              label={`Score ${lead.value_score ?? 0}/10`}
              tone={isHighValue ? "success" : "info"}
            />
          </div>
        </AnimatedTooltip>
      </div>

      <div className="mt-4 space-y-1.5 text-sm text-[var(--color-text-secondary)]">
        {lead.email ? (
          <div className="truncate flex items-center gap-2">
            <Mail size={14} className="opacity-50" />
            {lead.email}
          </div>
        ) : null}
        {lead.next_followup_date ? (
          <div className="flex items-center gap-2">
            <CalendarClock size={14} className="opacity-50 text-orange-400" />
            <span className="text-orange-400/90 font-medium">Due: {lead.next_followup_date}</span>
          </div>
        ) : null}
        {lead.last_contacted_at ? (
          <div className="text-xs mt-2 opacity-70">
            Last touch: {formatRelative(lead.last_contacted_at)}
          </div>
        ) : null}
      </div>

      {lead.followup_reason ? (
        <div className="mt-4 rounded-xl border border-white/5 bg-black/20 p-3 text-sm leading-relaxed text-zinc-300 relative overflow-hidden">
          <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-blue-500/50 to-purple-500/50" />
          <span className="opacity-70 mr-2 uppercase text-[10px] font-bold tracking-wider">Note</span>
          {lead.followup_reason}
        </div>
      ) : null}

      {lead.notes ? (
        <p className="mt-3 text-sm leading-6 text-[var(--color-text-tertiary)] italic pl-3 border-l-2 border-white/5">
          {lead.notes}
        </p>
      ) : null}

      <div className="mt-5 flex flex-wrap gap-2 pt-2 border-t border-white/5">
        <motion.div whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} className="flex-1 min-w-[120px]">
          <Button
            size="sm"
            variant="secondary"
            className="w-full text-xs"
            loading={contacting}
            onClick={onMarkContacted}
          >
            Mark contacted
          </Button>
        </motion.div>
        <motion.div whileHover={{ scale: 1.03 }} whileTap={{ scale: 0.97 }} className="flex-1 min-w-[120px]">
          <Button
            size="sm"
            variant="outline"
            className="w-full text-xs"
            loading={scheduling}
            onClick={onScheduleFollowup}
          >
            Schedule +3d
          </Button>
        </motion.div>
        <motion.div whileHover={{ scale: 1.05 }} whileTap={{ scale: 0.95 }}>
          <Button
            size="sm"
            variant="ghost"
            className="px-2 hover:text-red-400 hover:bg-red-400/10"
            loading={deleting}
            icon={<Trash2 size={15} />}
            onClick={onDelete}
            aria-label="Delete lead"
          />
        </motion.div>
      </div>
    </motion.article>
  );
}

function todayIsoDate() {
  return new Date().toISOString().slice(0, 10);
}

function addDaysIsoDate(days: number) {
  const nextDate = new Date();
  nextDate.setUTCDate(nextDate.getUTCDate() + days);
  return nextDate.toISOString().slice(0, 10);
}