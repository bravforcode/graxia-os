import { motion } from "framer-motion";
import { Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

export type LeadDraft = {
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

export function LeadForm({
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
