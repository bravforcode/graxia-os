import { motion } from "framer-motion";
import { AnimatedTooltip } from "@/components/ui/animated-tooltip";
import { StatusPill } from "@/components/ui/status-pill";
import { Button } from "@/components/ui/button";
import { Mail, CalendarClock, Trash2 } from "lucide-react";
import type { Contact } from "@/lib/api";
import { formatRelative } from "@/lib/utils";

export function LeadCard({
  lead,
  contacting,
  scheduling,
  deleting,
  onMarkContacted,
  onScheduleFollowup,
  onDelete,
  onUpdateStatus,
}: {
  lead: Contact;
  contacting: boolean;
  scheduling: boolean;
  deleting: boolean;
  onMarkContacted: () => void;
  onScheduleFollowup: () => void;
  onDelete: () => void;
  onUpdateStatus: (lead: Contact) => void;
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
        <div className="min-w-0">
          <h3 className="text-lg font-semibold text-[var(--color-text-primary)] truncate">
            {lead.name}
          </h3>
          {lead.role ? (
            <p className="mt-0.5 text-sm text-[var(--color-text-secondary)] truncate">
              {lead.role}
            </p>
          ) : null}
          {lead.company ? (
            <p className="mt-0.5 text-xs text-primary/80 font-medium truncate">
              {lead.company}
            </p>
          ) : null}
        </div>
        <div className="flex flex-col items-end gap-2 shrink-0">
          <AnimatedTooltip content={isHighValue ? "High priority prospect based on recent activity." : "Standard priority prospect."}>
            <div>
              <StatusPill
                label={`Score ${lead.value_score ?? 0}/10`}
                tone={isHighValue ? "success" : "info"}
              />
            </div>
          </AnimatedTooltip>
          <button
            onClick={() => onUpdateStatus(lead)}
            className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-wider border transition-all active:scale-95
              ${lead.status === 'High Intent' ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400 hover:bg-emerald-500/20' :
                lead.status === 'Lost' ? 'bg-rose-500/10 border-rose-500/20 text-rose-400 hover:bg-rose-500/20' :
                lead.status === 'New' ? 'bg-blue-500/10 border-blue-500/20 text-blue-400 hover:bg-blue-500/20' :
                'bg-white/5 border-white/10 text-zinc-400 hover:bg-white/10'}`}
          >
            {lead.status || 'New'}
          </button>
        </div>
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
            className="px-2 hover:text-rose-400 hover:bg-rose-400/10"
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
