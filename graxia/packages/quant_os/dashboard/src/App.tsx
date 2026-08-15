/* ═══════════════════════════════════════════════════════
   Quant OS Dashboard — Main App
   ═══════════════════════════════════════════════════════ */

import { useState, useEffect, useCallback } from 'react';
import './index.css';
import type { DashboardState, LiveStatus, Position, NewsItem } from './types';
import {
  fetchDashboardState,
  fetchLiveStatus,
  fetchPositions,
  fetchTrades,
  fetchNews,
} from './api';
import { Header } from './components/Header';
import { MetricCards } from './components/MetricCards';
import { RegimePanel } from './components/RegimePanel';
import { RiskPanel } from './components/RiskPanel';
import { PositionsTable } from './components/PositionsTable';
import { TradesTable } from './components/TradesTable';
import { SystemHealth } from './components/SystemHealth';
import { NewsFeed } from './components/NewsFeed';

const REFRESH_INTERVAL = 10_000; // 10s

export default function App() {
  const [state, setState] = useState<DashboardState | null>(null);
  const [live, setLive] = useState<LiveStatus | null>(null);
  const [positions, setPositions] = useState<Position[]>([]);
  const [trades, setTrades] = useState<Array<{ timestamp: number; symbol: string; side: string; pnl: number }>>([]);
  const [news, setNews] = useState<NewsItem[]>([]);
  const [lastUpdate, setLastUpdate] = useState<Date>(new Date());
  const [isOnline, setIsOnline] = useState(true);

  const refresh = useCallback(async () => {
    const [stateData, liveData, posData, tradeData, newsData] = await Promise.all([
      fetchDashboardState(),
      fetchLiveStatus(),
      fetchPositions(),
      fetchTrades(),
      fetchNews(),
    ]);

    if (stateData) setState(stateData);
    if (liveData) setLive(liveData);
    if (posData) setPositions(posData);
    setTrades(tradeData);
    if (newsData) setNews(newsData);

    setIsOnline(stateData !== null || liveData !== null);
    setLastUpdate(new Date());
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, REFRESH_INTERVAL);
    return () => clearInterval(interval);
  }, [refresh]);

  // Derive unified metrics
  const balance = live?.balance ?? 0;
  const dailyPnl = live?.daily_pnl ?? state?.macro_regime ? 0 : 0;
  const openPositions = live?.position ? 1 : positions.length;
  const maxPositions = 5;
  const regime = state?.macro_regime;
  const system = state?.system;

  // Compute win rate from trades
  const computedWinRate = trades.length > 0
    ? trades.filter(t => (t.pnl ?? 0) > 0).length / trades.length
    : 0;

  return (
    <div className="app">
      <Header
        isOnline={isOnline}
        lastUpdate={lastUpdate}
        systemStatus={system?.status}
        onRefresh={refresh}
      />

      <MetricCards
        balance={balance}
        dailyPnl={dailyPnl}
        openPositions={openPositions}
        maxPositions={maxPositions}
        winRate={computedWinRate}
        totalTrades={trades.length}
      />

      <div className="two-col">
        <RegimePanel regime={regime} />
        <RiskPanel
          dailyPnl={dailyPnl}
          weeklyPnl={0}
          openPositions={openPositions}
          maxPositions={maxPositions}
          canTrade={system?.status === 'OPERATIONAL'}
          canTradeReason={system?.status === 'LOCKDOWN' ? 'System in lockdown' : ''}
        />
      </div>

      <div className="bottom-row">
        <PositionsTable positions={positions} livePosition={live?.position ?? null} />
        <TradesTable trades={trades} />
      </div>

      <div className="two-col">
        <SystemHealth
          feedStatus={isOnline ? 'connected' : 'disconnected'}
          latencyMs={live?.confidence ? 12.5 : 0}
          dataAgeS={live?.timestamp ? (Date.now() / 1000 - new Date(live.timestamp).getTime() / 1000) : 0}
          model={live?.model}
          hotPathBudget={system?.hot_path_budget_ms}
        />
        <NewsFeed news={news} />
      </div>
    </div>
  );
}
