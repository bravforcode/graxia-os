import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Building2,
  CalendarClock,
  Mail,
  RefreshCw,
  Search,
  UserRound,
  Cpu,
} from "lucide-react";
import { useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";

import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/ui/empty-state";
import { MetricCard } from "@/components/ui/metric-card";
import { NoticeBanner } from "@/components/ui/notice-banner";
import { PageHeader } from "@/components/ui/page-header";
import { GlassCard } from "@/components/ui/glass-card";
import { LeadForm, type LeadDraft } from "@/components/leads/LeadForm";
import { LeadCard } from "@/components/leads/LeadCard";
import { api, type Contact } from "@/lib/api";

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
  const [selectedLeadForStatus, setSelectedLeadForStatus] = useState<Contact | null>(null);

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
        status: "New",
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

  const updateStatusMutation = useMutation({
    mutationFn: ({ id, status }: { id: string; status: string }) =>
      api.updateContact(id, { status }),
    onSuccess: async () => {
      setNotice({ tone: "success", text: "Status updated successfully." });
      await queryClient.invalidateQueries({ queryKey: ["leads"] });
      setSelectedLeadForStatus(null);
    },
    onError: () => {
      setNotice({ tone: "danger", text: "Failed to update status." });
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
          <div className="flex gap-2">
            <motion.div whileHover={{ scale: 1.02 }} whileTap={{ scale: 0.98 }}>
              <Button
                variant="secondary"
                icon={<RefreshCw size={16} className={leadQuery.isFetching ? "animate-spin" : ""} />}
                onClick={() => void leadQuery.refetch()}
              >
                Refresh
              </Button>
            </motion.div>
          </div>
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
                      onUpdateStatus={(lead) => setSelectedLeadForStatus(lead)}
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

      {/* Status Selection Popup (Brav OS Modal) */}
      <AnimatePresence>
        {selectedLeadForStatus && (
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm flex items-center justify-center z-[100] p-4">
            <motion.div 
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.95 }}
              className="bg-zinc-900 border border-white/10 rounded-2xl p-6 max-w-sm w-full shadow-2xl"
            >
              <div className="flex items-center gap-3 mb-6">
                <div className="p-2 bg-blue-600/20 rounded-lg">
                  <Cpu className="w-5 h-5 text-blue-500" />
                </div>
                <div>
                  <h3 className="text-lg font-bold text-white">Update Status</h3>
                  <p className="text-[10px] text-zinc-500 uppercase tracking-widest font-mono">Core Lifecycle Management</p>
                </div>
              </div>
              
              <div className="grid grid-cols-1 gap-2 mb-8">
                {['New', 'Discovery', 'High Intent', 'Nurturing', 'Closed', 'Lost'].map((s) => (
                  <button
                    key={s}
                    disabled={updateStatusMutation.isPending}
                    onClick={() => updateStatusMutation.mutate({ id: selectedLeadForStatus.id, status: s })}
                    className={`w-full text-left px-4 py-3 rounded-xl text-sm font-semibold transition-all flex items-center justify-between group
                      ${selectedLeadForStatus.status === s 
                        ? 'bg-blue-600 text-white shadow-lg shadow-blue-500/20' 
                        : 'bg-white/5 text-zinc-400 hover:bg-white/10 hover:text-white border border-transparent hover:border-white/10'}`}
                  >
                    {s}
                    {selectedLeadForStatus.status === s && <div className="w-1.5 h-1.5 bg-white rounded-full animate-pulse" />}
                  </button>
                ))}
              </div>
              
              <div className="flex gap-3">
                <button 
                  onClick={() => setSelectedLeadForStatus(null)}
                  className="flex-1 py-3 text-xs font-bold uppercase tracking-widest text-zinc-500 hover:text-white transition-colors bg-white/5 rounded-xl"
                >
                  Cancel
                </button>
              </div>
            </motion.div>
          </div>
        )}
      </AnimatePresence>

      <section id="lead-form" className="mt-12 pt-12 border-t border-white/5">
        <PageHeader
          eyebrow="Onboarding"
          title="Add New Asset"
          description="Manually ingest a high-value lead into the autonomous pipeline."
        />
        <GlassCard intensity="low" className="mt-8 p-8 max-w-4xl">
          <LeadForm
            draft={draft}
            setDraft={setDraft}
            saving={createMutation.isPending}
            onSubmit={handleCreate}
          />
        </GlassCard>
      </section>
    </div>
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
