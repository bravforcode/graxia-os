type NoticeTone = 'info' | 'success' | 'warning' | 'danger';

const noticeStyles: Record<NoticeTone, string> = {
  info: 'border-sky-500/20 bg-sky-500/5 text-sky-300',
  success: 'border-emerald-500/20 bg-emerald-500/5 text-emerald-300',
  warning: 'border-amber-500/20 bg-amber-500/5 text-amber-300',
  danger: 'border-red-500/20 bg-red-500/5 text-red-300',
};

interface NoticeBannerProps {
  tone?: NoticeTone;
  msg?: string;
  message?: string;
}

export function NoticeBanner({ tone = 'info', msg, message }: NoticeBannerProps) {
  const text = message ?? msg ?? '';
  return (
    <div
      role={tone === 'danger' ? 'alert' : 'status'}
      aria-live={tone === 'danger' ? 'assertive' : 'polite'}
      className={`rounded-[12px] border px-4 py-3 text-sm ${noticeStyles[tone]}`}
    >
      {text}
    </div>
  );
}
