import { useEffect, useState, useCallback } from 'react'

// ── Types ────────────────────────────────────────────────────────
interface Health {
  status: string
  uptime_s: number
  signal_queue_depth: number
  write_queue_depth: number
  event_bus_pending: number
}

interface SystemStats {
  ai_actions: number
  completed_24h: number
  success_rate: number
  active_leads: number
  total_contacts: number
  opportunities_found: number
  outreach_sent_24h: number
  active_ai_provider: string
  active_ai_model: string
  open_positions: number
  daily_order_count: number
  kill_switch_active: boolean
}

interface Regime {
  bias: string
  confidence: number
  position_multiplier: number
  regime_label: string
  updated_at: string
  source: string
  headline: string
}

interface RiskBudget {
  current_daily_pnl: number
  current_weekly_pnl: number
  open_positions: number
  max_open_positions: number
  can_trade: boolean
  trade_reason: string
}

interface Regime {
  regime_label: string
  bias: string
  confidence: number
  position_multiplier: number
  source: string
  headline: string
  updated_at: string
}

// ── API ──────────────────────────────────────────────────────────
const API = '/api/v1'

async function fetchJSON<T>(path: string): Promise<T> {
  const res = await fetch(`${API}${path}`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

// ── Components ───────────────────────────────────────────────────
function MetricCard({ label, value, sub, color }: {
  label: string
  value: string | number
  sub?: string
  color?: string
}) {
  return (
    <div className="card">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={{ color: color || 'inherit' }}>{value}</div>
      {sub && <div style={{ color: 'var(--text-muted)', fontSize: '0.75rem', marginTop: '0.25rem' }}>{sub}</div>}
    </div>
  )
}

function StatusDot({ status }: { status: string }) {
  const colors: Record<string, string> = {
    healthy: 'var(--green)',
    NORMAL: 'var(--green)',
    HIGH_UNCERTAINTY: 'var(--amber)',
    CRISIS: 'var(--red)',
  }
  return (
    <span style={{
      display: 'inline-block',
      width: 8,
      height: 8,
      borderRadius: '50%',
      background: colors[status] || 'var(--text-muted)',
      marginRight: 8,
    }} />
  )
}

function LogLines({ lines }: { lines: string[] }) {
  return (
    <div style={{ maxHeight: 200, overflow: 'auto' }}>
      {lines.map((l, i) => (
        <div key={i} className="log-entry">{l.slice(0, 120)}</div>
      ))}
    </div>
  )
}

// ── App ──────────────────────────────────────────────────────────
export default function App() {
  const [health, setHealth] = useState<Health | null>(null)
  const [stats, setStats] = useState<SystemStats | null>(null)
  const [regime, setRegime] = useState<Regime | null>(null)
  const [risk, setRisk] = useState<RiskBudget | null>(null)
  const [logs, setLogs] = useState<string[]>([])
  const [error, setError] = useState<string | null>(null)
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date())

  const refresh = useCallback(async () => {
    try {
      const [h, s, r, rb] = await Promise.all([
        fetchJSON<Health>('/health'),
        fetchJSON<SystemStats>('/system/stats'),
        fetchJSON<Regime>('/regime'),
        fetchJSON<RiskBudget>('/risk-budget'),
      ])
      setHealth(h)
      setStats(s)
      setRegime(r)
      setRisk(rb)
      setError(null)
      setLastUpdate(new Date())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Connection failed')
    }

    // Fetch logs from news_pipeline.log (via a simple proxy endpoint or direct)
    try {
      const logRes = await fetch('/api/v1/health/detailed')
      if (logRes.ok) {
        const detail = await logRes.json()
        const logLines = [
          `Status: ${detail.environment || 'unknown'}`,
          `Uptime: ${detail.uptime_s || 0}s`,
          `Signal queue: ${detail.signal_queue_depth || 0}`,
          `Event bus: ${detail.event_bus_pending || 0}`,
        ]
        setLogs(logLines)
      }
    } catch { /* ignore */ }
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 15000)
    return () => clearInterval(interval)
  }, [refresh])

  const regimeColor = (label: string) => {
    if (label === 'NORMAL') return 'var(--green)'
    if (label === 'HIGH_UNCERTAINTY') return 'var(--amber)'
    if (label === 'CRISIS') return 'var(--red)'
    return 'var(--text-muted)'
  }

  return (
    <div style={{ maxWidth: 1200, margin: '0 auto', padding: '2rem 1.5rem' }}>
      {/* Header */}
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 600, margin: 0 }}>Quant OS</h1>
        <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem', marginTop: 4 }}>
          Trading dashboard · {lastUpdate.toLocaleTimeString()} UTC
          {error && <span style={{ color: 'var(--red)', marginLeft: 12 }}>● {error}</span>}
          {!error && health && <span style={{ color: 'var(--green)', marginLeft: 12 }}>● Connected</span>}
        </div>
      </div>

      {/* Main Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '1rem', marginBottom: '2rem' }}>
        {/* Regime */}
        <div className="card">
          <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '1rem' }}>Regime</div>
          {regime ? (
            <>
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: '0.5rem' }}>
                <StatusDot status={regime.regime_label} />
                <span className="metric-value" style={{ color: regimeColor(regime.regime_label) }}>
                  {regime.regime_label}
                </span>
              </div>
              <div className="metric-label">Position Mult</div>
              <div className="metric-value">{regime.position_multiplier.toFixed(2)}×</div>
              <div style={{ marginTop: '0.75rem' }}>
                <div className="metric-label">Confidence</div>
                <div className="metric-value">{(regime.confidence * 100).toFixed(0)}%</div>
              </div>
              <div style={{ marginTop: '0.75rem' }}>
                <div className="metric-label">Bias</div>
                <div style={{ fontSize: '0.9rem' }}>{regime.bias}</div>
              </div>
              {regime.headline && (
                <div style={{ marginTop: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                  {regime.headline.slice(0, 80)}
                </div>
              )}
            </>
          ) : (
            <div style={{ color: 'var(--text-muted)' }}>Loading...</div>
          )}
        </div>

        {/* Risk Budget */}
        <div className="card">
          <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '1rem' }}>Risk Budget</div>
          {risk ? (
            <>
              <div className="metric-label">Daily PnL</div>
              <div className="metric-value" style={{ color: risk.current_daily_pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                {risk.current_daily_pnl >= 0 ? '+' : ''}{risk.current_daily_pnl.toFixed(2)}%
              </div>
              <div style={{ marginTop: '0.75rem' }}>
                <div className="metric-label">Weekly PnL</div>
                <div className="metric-value" style={{ color: risk.current_weekly_pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
                  {risk.current_weekly_pnl >= 0 ? '+' : ''}{risk.current_weekly_pnl.toFixed(2)}%
                </div>
              </div>
              <div style={{ marginTop: '0.75rem' }}>
                <div className="metric-label">Positions</div>
                <div className="metric-value">{risk.open_positions}/{risk.max_open_positions}</div>
              </div>
              <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: risk.can_trade ? 'var(--green)' : 'var(--red)' }}>
                {risk.can_trade ? '✓ Trading enabled' : `✗ ${risk.trade_reason}`}
              </div>
            </>
          ) : (
            <div style={{ color: 'var(--text-muted)' }}>Loading...</div>
          )}
        </div>

        {/* System Health */}
        <div className="card">
          <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '1rem' }}>System</div>
          {health ? (
            <>
              <div style={{ display: 'flex', alignItems: 'center', marginBottom: '0.5rem' }}>
                <StatusDot status={health.status} />
                <span style={{ fontWeight: 500 }}>{health.status}</span>
              </div>
              <div className="metric-label">Uptime</div>
              <div className="metric-value">{Math.max(0, health.uptime_s).toFixed(0)}s</div>
              <div style={{ marginTop: '0.75rem' }}>
                <div className="metric-label">Queue Depth</div>
                <div style={{ fontSize: '0.9rem' }}>{health.signal_queue_depth}</div>
              </div>
            </>
          ) : (
            <div style={{ color: 'var(--text-muted)' }}>Loading...</div>
          )}
        </div>
      </div>

      {/* Second Row: Trading + Performance */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '2rem' }}>
        {/* Trading Status */}
        <div className="card">
          <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '1rem' }}>Trading</div>
          {stats ? (
            <>
              <div className="metric-label">Mode</div>
              <div className="metric-value">{stats.active_ai_model}</div>
              <div style={{ marginTop: '0.75rem' }}>
                <div className="metric-label">Open Positions</div>
                <div className="metric-value">{stats.open_positions}</div>
              </div>
              <div style={{ marginTop: '0.75rem' }}>
                <div className="metric-label">Orders Today</div>
                <div style={{ fontSize: '0.9rem' }}>{stats.daily_order_count}</div>
              </div>
              {stats.kill_switch_active && (
                <div style={{ color: 'var(--red)', fontSize: '0.8rem', marginTop: '0.5rem', fontWeight: 500 }}>
                  ● KILL SWITCH ACTIVE
                </div>
              )}
            </>
          ) : (
            <div style={{ color: 'var(--text-muted)' }}>Loading...</div>
          )}
        </div>

        {/* Performance */}
        <div className="card">
          <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '1rem' }}>Performance</div>
          {stats ? (
            <>
              <div className="metric-label">AI Actions</div>
              <div className="metric-value">{stats.ai_actions}</div>
              <div style={{ marginTop: '0.75rem' }}>
                <div className="metric-label">Success Rate</div>
                <div className="metric-value" style={{ color: stats.success_rate >= 90 ? 'var(--green)' : 'var(--amber)' }}>
                  {stats.success_rate}%
                </div>
              </div>
              <div style={{ marginTop: '0.75rem' }}>
                <div className="metric-label">Completed (24h)</div>
                <div style={{ fontSize: '0.9rem' }}>{stats.completed_24h}</div>
              </div>
            </>
          ) : (
            <div style={{ color: 'var(--text-muted)' }}>Loading...</div>
          )}
        </div>
      </div>

      {/* Pipeline Status */}
      <div className="card" style={{ marginBottom: '1rem' }}>
        <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '0.75rem' }}>Pipeline Status</div>
        {logs.length > 0 ? (
          <LogLines lines={logs} />
        ) : (
          <div style={{ color: 'var(--text-muted)', fontSize: '0.8rem' }}>No log data</div>
        )}
      </div>

      {/* Footer */}
      <div style={{ color: 'var(--text-muted)', fontSize: '0.7rem', textAlign: 'center', marginTop: '2rem' }}>
        Quant OS · Trading System · {health?.status === 'healthy' ? 'Operational' : 'Checking...'}
      </div>
    </div>
  )
}
