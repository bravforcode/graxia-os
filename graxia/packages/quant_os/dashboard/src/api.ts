/* ═══════════════════════════════════════════════════════
   Quant OS Dashboard — API Client
   ═══════════════════════════════════════════════════════ */

import type { DashboardState, LiveStatus } from './types';

const BASE = '';

async function fetchJSON<T>(url: string): Promise<T | null> {
  try {
    const res = await fetch(`${BASE}${url}`, {
      cache: 'no-store',
      headers: { 'Accept': 'application/json' },
    });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

export async function fetchDashboardState(): Promise<DashboardState | null> {
  return fetchJSON<DashboardState>('/api/state');
}

export async function fetchLiveStatus(): Promise<LiveStatus | null> {
  return fetchJSON<LiveStatus>('/api/status');
}

export async function fetchRiskBudget(): Promise<{
  current_daily_pnl: number;
  current_weekly_pnl: number;
  open_positions: number;
  max_open_positions: number;
  can_trade: boolean;
  can_trade_reason: string;
} | null> {
  return fetchJSON('/api/risk');
}

export async function fetchNews(): Promise<Array<{
  timestamp: string;
  regime: string;
  confidence: number;
  headlines: Array<{ title: string }>;
}> | null> {
  return fetchJSON('/api/news');
}

export async function fetchPositions(): Promise<Array<{
  symbol: string;
  side: string;
  entry_price: number;
  pnl: number;
}> | null> {
  return fetchJSON('/api/positions');
}

export async function fetchTrades(): Promise<Array<{
  timestamp: number;
  symbol: string;
  side: string;
  pnl: number;
}>> {
  const result = await fetchJSON<Array<{
    timestamp: number;
    symbol: string;
    side: string;
    pnl: number;
  }>>('/api/trades');
  return result ?? [];
}
