/* ═══════════════════════════════════════════════════════
   Regime Panel — Market regime display
   ═══════════════════════════════════════════════════════ */

import type { MacroRegime } from '../types';

interface RegimePanelProps {
  regime?: MacroRegime;
}

const REGIME_BADGE: Record<string, { label: string; className: string }> = {
  NORMAL: { label: 'Normal', className: 'normal' },
  HIGH_UNCERTAINTY: { label: 'High Uncertainty', className: 'warning' },
  CRISIS: { label: 'Crisis', className: 'crisis' },
};

const BIAS_DISPLAY: Record<string, string> = {
  BULLISH: 'Bullish',
  BEARISH: 'Bearish',
  NEUTRAL: 'Neutral',
  PANIC: 'Panic',
};

export function RegimePanel({ regime }: RegimePanelProps) {
  if (!regime) {
    return (
      <div className="panel">
        <div className="panel-header">
          <span className="panel-title">Macro Regime</span>
        </div>
        <div className="empty-state">
          <div className="empty-state-icon">—</div>
          <span>No regime data available</span>
        </div>
      </div>
    );
  }

  const badge = REGIME_BADGE[regime.regime_label] ?? { label: regime.regime_label, className: '' };
  const bias = BIAS_DISPLAY[regime.bias] ?? regime.bias;

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">Macro Regime</span>
        <span className={`panel-badge ${badge.className}`}>
          {badge.label}
        </span>
      </div>

      <div className="regime-grid">
        <div className="regime-stat">
          <span className="regime-stat-label">Bias</span>
          <span className="regime-stat-value">{bias}</span>
        </div>
        <div className="regime-stat">
          <span className="regime-stat-label">Confidence</span>
          <span className="regime-stat-value">
            {(regime.confidence * 100).toFixed(0)}%
          </span>
        </div>
        <div className="regime-stat">
          <span className="regime-stat-label">Position Size</span>
          <span className="regime-stat-value">
            {regime.position_multiplier.toFixed(2)}×
          </span>
        </div>
      </div>

      {regime.headline && (
        <div className="regime-headline">
          {regime.headline}
        </div>
      )}

      <div className="regime-meta">
        {regime.source} · {new Date(regime.updated_at).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false })}
      </div>
    </div>
  );
}
