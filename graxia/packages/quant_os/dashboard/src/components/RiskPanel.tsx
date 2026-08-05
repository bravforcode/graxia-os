/* ═══════════════════════════════════════════════════════
   Risk Panel — Risk budget + trading status
   ═══════════════════════════════════════════════════════ */

interface RiskPanelProps {
  dailyPnl: number;
  weeklyPnl: number;
  openPositions: number;
  maxPositions: number;
  canTrade: boolean;
  canTradeReason: string;
}

function formatPnl(val: number): string {
  const sign = val >= 0 ? '+' : '';
  return `${sign}${val.toFixed(2)}%`;
}

export function RiskPanel({
  dailyPnl,
  weeklyPnl,
  openPositions,
  maxPositions,
  canTrade,
  canTradeReason,
}: RiskPanelProps) {
  // Risk level: 0-100 based on position utilization + drawdown
  const positionUtil = maxPositions > 0 ? (openPositions / maxPositions) * 100 : 0;
  const riskLevel = Math.min(100, positionUtil);
  const riskClass = riskLevel < 40 ? 'low' : riskLevel < 70 ? 'medium' : 'high';

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Risk Budget</span>
      </div>

      <div className="risk-items">
        <div className="risk-item">
          <span className="risk-item-label">Daily PnL</span>
          <span
            className="risk-item-value"
            style={{ color: dailyPnl >= 0 ? 'var(--positive)' : 'var(--negative)' }}
          >
            {formatPnl(dailyPnl)}
          </span>
        </div>

        <div className="risk-item">
          <span className="risk-item-label">Weekly PnL</span>
          <span
            className="risk-item-value"
            style={{ color: weeklyPnl >= 0 ? 'var(--positive)' : 'var(--negative)' }}
          >
            {formatPnl(weeklyPnl)}
          </span>
        </div>

        <div className="risk-item">
          <span className="risk-item-label">Positions</span>
          <span className="risk-item-value">
            {openPositions} / {maxPositions}
          </span>
        </div>

        <div>
          <div className="risk-item">
            <span className="risk-item-label">Risk Level</span>
            <span className="risk-item-value">{riskLevel.toFixed(0)}%</span>
          </div>
          <div className="risk-bar-container">
            <div
              className={`risk-bar-fill ${riskClass}`}
              style={{ width: `${riskLevel}%` }}
            />
          </div>
        </div>
      </div>

      <div className={`trade-status ${canTrade ? 'enabled' : 'disabled'}`}>
        <span className="trade-status-dot" />
        {canTrade ? 'Trading enabled' : canTradeReason || 'Trading disabled'}
      </div>
    </div>
  );
}
