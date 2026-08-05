/* ═══════════════════════════════════════════════════════
   Header — Brand + Status + Refresh
   ═══════════════════════════════════════════════════════ */

interface HeaderProps {
  isOnline: boolean;
  lastUpdate: Date;
  systemStatus?: string;
  onRefresh: () => void;
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

export function Header({ isOnline, lastUpdate, systemStatus, onRefresh }: HeaderProps) {
  return (
    <header className="header">
      <div className="header-left">
        <h1 className="header-title">Quant OS</h1>
        <div className="header-status">
          <span className={`header-dot ${isOnline ? '' : 'offline'}`} />
          <span>{isOnline ? 'Live' : 'Offline'}</span>
          {systemStatus && systemStatus !== 'OPERATIONAL' && (
            <span style={{ color: 'var(--negative)', fontWeight: 500 }}>
              {systemStatus}
            </span>
          )}
        </div>
      </div>
      <div className="header-right">
        <span className="header-time">{formatTime(lastUpdate)}</span>
        <button className="btn-refresh" onClick={onRefresh} aria-label="Refresh data">
          <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M14 8A6 6 0 1 1 8 2" />
            <path d="M8 2L12 2L12 6" />
          </svg>
          Refresh
        </button>
      </div>
    </header>
  );
}
