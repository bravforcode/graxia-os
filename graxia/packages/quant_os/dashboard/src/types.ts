/* ═══════════════════════════════════════════════════════
   Quant OS Dashboard — Type Definitions
   ═══════════════════════════════════════════════════════ */

export interface MacroRegime {
  bias: 'BULLISH' | 'BEARISH' | 'NEUTRAL' | 'PANIC';
  confidence: number;
  position_multiplier: number;
  regime_label: 'NORMAL' | 'HIGH_UNCERTAINTY' | 'CRISIS';
  source: string;
  headline: string;
  updated_at: string;
}

export interface SystemStatus {
  hot_path_budget_ms: number;
  status: 'OPERATIONAL' | 'LOCKDOWN';
}

export interface DashboardState {
  timestamp: string;
  macro_regime: MacroRegime;
  system: SystemStatus;
}

export interface TradeEntry {
  timestamp: number;
  symbol: string;
  side: 'buy' | 'sell';
  entry_price?: number;
  pnl?: number;
  event?: string;
}

export interface Position {
  symbol: string;
  side: string;
  entry_price: number;
  pnl: number;
}

export interface RiskBudget {
  current_daily_pnl: number;
  current_weekly_pnl: number;
  open_positions: number;
  max_open_positions: number;
  can_trade_flag: boolean;
  can_trade_reason: string;
}

export interface NewsItem {
  timestamp: string;
  regime: string;
  confidence: number;
  headlines: Array<{ title: string }>;
}

export interface LiveStatus {
  bid: number;
  ask: number;
  spread: number;
  confidence: number;
  prediction: string;
  position: Position | null;
  daily_pnl: number;
  daily_trades: number;
  balance: number;
  uptime_seconds: number;
  session: string;
  signal_strength: string;
  timestamp: string;
  model: string;
  config: string;
  last_trade: TradeEntry | null;
}
