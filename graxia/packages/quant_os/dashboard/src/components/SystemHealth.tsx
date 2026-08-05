/* ═══════════════════════════════════════════════════════
   System Health — Feed, latency, model info
   ═══════════════════════════════════════════════════════ */

interface SystemHealthProps {
  feedStatus: string;
  latencyMs: number;
  dataAgeS: number;
  model?: string;
  hotPathBudget?: number;
}

export function SystemHealth({
  feedStatus,
  latencyMs,
  dataAgeS,
  model,
  hotPathBudget,
}: SystemHealthProps) {
  const isGood = feedStatus === 'connected';

  return (
    <div className="panel">
      <div className="panel-header">
        <span className="panel-title">System Health</span>
        <span
          style={{
            fontSize: 'var(--text-xs)',
            fontWeight: 500,
            color: isGood ? 'var(--positive)' : 'var(--negative)',
          }}
        >
          {isGood ? '● Operational' : '● Degraded'}
        </span>
      </div>

      <div className="health-grid">
        <div className="health-item">
          <span className="health-label">Feed</span>
          <span className={`health-value ${isGood ? 'good' : 'bad'}`}>
            {feedStatus}
          </span>
        </div>

        <div className="health-item">
          <span className="health-label">Latency</span>
          <span className="health-value">
            {latencyMs > 0 ? `${latencyMs.toFixed(1)}ms` : '—'}
          </span>
        </div>

        <div className="health-item">
          <span className="health-label">Data Age</span>
          <span className="health-value">
            {dataAgeS > 0 ? `${dataAgeS.toFixed(0)}s` : '—'}
          </span>
        </div>

        {hotPathBudget && (
          <div className="health-item">
            <span className="health-label">Hot Path Budget</span>
            <span className="health-value">{hotPathBudget}ms</span>
          </div>
        )}

        {model && (
          <div className="health-item">
            <span className="health-label">Model</span>
            <span className="health-value">{model}</span>
          </div>
        )}
      </div>
    </div>
  );
}
