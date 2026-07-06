type NoticeTone = 'info' | 'success' | 'warning' | 'danger';

const noticeStyles: Record<NoticeTone, string> = {
  info: 'border-sky-500/20 bg-sky-500/5 text-sky-300',
  success: 'border-emerald-500/20 bg-emerald-500/5 text-emerald-300',
  warning: 'border-amber-500/20 bg-amber-500/5 text-amber-300',
  danger: 'border-red-500/20 bg-red-500/5 text-red-300',
};

interface NoticeBannerProps {
  tone?: NoticeTone;
  message: string;
  onDismiss?: () => void;
}

export function NoticeBanner({ tone = 'info', message, onDismiss }: NoticeBannerProps) {
  const isDanger = tone === 'danger';

  return (
    <div
      role={isDanger ? 'alert' : 'status'}
      aria-live={isDanger ? 'assertive' : 'polite'}
      className={`rounded-[12px] border px-4 py-3 text-sm ${noticeStyles[tone]}`}
    >
      <span>{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className="ml-2 float-right text-current opacity-60 hover:opacity-100"
          aria-label="Dismiss"
        >
          ×
        </button>
      )}
    </div>
  );
}
