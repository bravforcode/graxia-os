/* ═══════════════════════════════════════════════════════
   Metric Cards — Top-level KPIs
   ═══════════════════════════════════════════════════════ */

interface MetricCardsProps {
  balance: number;
  dailyPnl: number;
  openPositions: number;
  maxPositions: number;
  winRate: number;
  totalTrades: number;
}

function formatCurrency(val: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(val);
}

function formatPnl(val: number): string {
  const sign = val >= 0 ? '+' : '';
  return `${sign}${val.toFixed(2)}%`;
}

export function MetricCards({
  balance,
  dailyPnl,
  openPositions,
  maxPositions,
  winRate,
  totalTrades,
}: MetricCardsProps) {
  const pnlClass = dailyPnl >= 0 ? 'positive' : 'negative';

  return (
    <div className="metrics-row">
      <div className="metric-card">
        <div className="metric-label">Balance</div>
        <div className="metric-value">{formatCurrency(balance)}</div>
        <div className="metric-sub">Equity</div>
      </div>

      <div className="metric-card">
        <div className="metric-label">Daily PnL</div>
        <div className={`metric-value ${pnlClass}`}>
          {formatPnl(dailyPnl)}
        </div>
        <div className="metric-sub">
          {dailyPnl >= 0 ? '↑' : '↓'} Today
        </div>
      </div>

      <div className="metric-card">
        <div className="metric-label">Positions</div>
        <div className="metric-value">
          {openPositions}
          <span style={{ color: 'var(--muted)', fontWeight: 400, fontSize: 'var(--text-lg)' }}>
            /{maxPositions}
          </span>
        </div>
        <div className="metric-sub">Open slots</div>
      </div>

      <div className="metric-card">
        <div className="metric-label">Win Rate</div>
        <div className="metric-value gold">
          {totalTrades > 0 ? `${(winRate * 100).toFixed(1)}%` : '—'}
        </div>
        <div className="metric-sub">{totalTrades} trades</div>
      </div>
    </div>
  );
}
