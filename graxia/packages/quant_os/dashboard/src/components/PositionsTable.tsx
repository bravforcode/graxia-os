/* ═══════════════════════════════════════════════════════
   Positions Table — Open positions display
   ═══════════════════════════════════════════════════════ */

import type { Position } from '../types';

interface PositionsTableProps {
  positions: Position[];
  livePosition: Position | null;
}

export function PositionsTable({ positions, livePosition }: PositionsTableProps) {
  // Merge live position with positions array
  const allPositions = livePosition
    ? [livePosition, ...positions.filter(p => p.symbol !== livePosition.symbol)]
    : positions;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Open Positions</span>
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--muted)' }}>
          {allPositions.length} active
        </span>
      </div>

      {allPositions.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon">—</div>
          <span>No open positions</span>
        </div>
      ) : (
        <div className="table-wrapper">
          <table className="data-table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Side</th>
                <th>Entry</th>
                <th>PnL</th>
              </tr>
            </thead>
            <tbody>
              {allPositions.map((pos, i) => (
                <tr key={`${pos.symbol}-${i}`}>
                  <td style={{ fontWeight: 500 }}>{pos.symbol}</td>
                  <td>
                    <span className={`cell-side ${pos.side.toLowerCase()}`}>
                      {pos.side.toUpperCase()}
                    </span>
                  </td>
                  <td style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)' }}>
                    {pos.entry_price.toFixed(2)}
                  </td>
                  <td className={pos.pnl >= 0 ? 'cell-positive' : 'cell-negative'}>
                    {pos.pnl >= 0 ? '+' : ''}{pos.pnl.toFixed(2)}
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
