type Tone = 'neutral' | 'success' | 'danger' | 'warning' | 'info';

const toneStyles: Record<Tone, string> = {
  neutral: 'bg-zinc-500/10 text-zinc-400 border-zinc-500/20',
  success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20',
  danger: 'bg-red-500/10 text-red-400 border-red-500/20',
  warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20',
  info: 'bg-sky-500/10 text-sky-400 border-sky-500/20',
};

interface StatusPillProps {
  label: string;
  tone?: Tone;
  pulse?: boolean;
}

export function StatusPill({ label, tone = 'info', pulse = false }: StatusPillProps) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-[11px] font-medium ${toneStyles[tone]}`}
    >
      {pulse ? <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" /> : null}
      {label}
    </span>
  );
}
