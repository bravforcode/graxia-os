type Tone = 'success' | 'danger' | 'warning' | 'info';

const toneStyles: Record<Tone, string> = {
  success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  danger: 'bg-red-500/10 text-red-400 border-red-500/20',
  warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  info: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
};

interface StatusPillProps {
  label: string;
  tone?: Tone;
}

export function StatusPill({ label, tone = 'info' }: StatusPillProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2 py-0.5 text-[11px] font-medium ${toneStyles[tone]}`}
    >
      {label}
    </span>
  );
}
