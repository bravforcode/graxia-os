/* ═══════════════════════════════════════════════════════
   Trades Table — Recent trade history
   ═══════════════════════════════════════════════════════ */

interface Trade {
  timestamp: number;
  symbol: string;
  side: string;
  pnl: number;
}

interface TradesTableProps {
  trades: Trade[];
}

function formatTime(ts: number): string {
  const date = new Date(ts * 1000);
  return date.toLocaleTimeString('en-US', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
  });
}

export function TradesTable({ trades }: TradesTableProps) {
  const recent = trades.slice(-10).reverse();

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Recent Trades</span>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)' }}>
          {trades.length} total
        </span>
      </div>

      {recent.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">—</div>
          <span>No trades yet</span>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Symbol</th>
                <th>Side</th>
                <th>PnL</th>
              </tr>
            </thead>
            <tbody>
              {recent.map((trade, i) => (
                <tr key={`${trade.timestamp}-${i}`}>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)' }}>
                    {formatTime(trade.timestamp)}
                  </td>
                  <td style={{ fontWeight: 500 }}>{trade.symbol}</td>
                  <td>
                    <span className={`cell-side ${trade.side.toLowerCase()}`}>
                      {trade.side.toUpperCase()}
                    </span>
                  </td>
                  <td className={trade.pnl >= 0 ? 'cell-positive' : 'cell-negative'}>
                    {trade.pnl >= 0 ? '+' : ''}{trade.pnl.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
