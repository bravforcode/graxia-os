"""
Gold Bot Backtest Runner
Reads 1 month of M15 XAUUSD data from MT5, runs all 13 strategies,
simulates trades with risk rules, and outputs performance metrics.
"""
from __future__ import annotations
import sys
import os
from pathlib import Path

# Ensure project root on path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import MetaTrader5 as mt5

from graxia.packages.quant_os.gold_bot.core.engine import (
    GoldBotEngine, SignalDirection, StrategySignal, AggregatedSignal, TradeRecord,
)
from graxia.packages.quant_os.gold_bot.core.config import BotConfig


def _log(msg: str):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# 1. MT5 Connection
# ---------------------------------------------------------------------------

def connect_mt5() -> bool:
    path = os.getenv("MT5_PATH", r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe")
    login = int(os.getenv("MT5_LOGIN", "0"))
    password = os.getenv("MT5_PASSWORD", "")
    server = os.getenv("MT5_SERVER", "Pepperstone-Demo")
    timeout = int(os.getenv("MT5_TIMEOUT_MS", "60000"))

    if login > 0 and password:
        ok = mt5.initialize(path=path, login=login, password=password,
                            server=server, timeout=timeout)
    else:
        ok = mt5.initialize(path=path, timeout=timeout)

    if not ok:
        _log(f"MT5 init failed: {mt5.last_error()}")
        return False

    info = mt5.account_info()
    if info:
        _log(f"MT5 connected: {info.server} | Balance: ${info.balance:,.2f}")
    return True


# ---------------------------------------------------------------------------
# 2. Download M15 History (1 month)
# ---------------------------------------------------------------------------

def download_m15_data(symbol: str, days: int = 30) -> Dict:
    """Download `days` of M15 bars from MT5 and return OHLCV dict."""
    # M15 bars per day = 96 (24h * 4)
    num_bars = days * 96

    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, num_bars)
    if rates is None or len(rates) == 0:
        _log(f"MT5 copy_rates failed: {mt5.last_error()}")
        return {}

    _log(f"Downloaded {len(rates)} M15 bars ({days} days)")
    _log(f"  First: {datetime.fromtimestamp(rates[0]['time'])}")
    _log(f"  Last:  {datetime.fromtimestamp(rates[-1]['time'])}")

    return {
        "open":   [float(r["open"]) for r in rates],
        "high":   [float(r["high"]) for r in rates],
        "low":    [float(r["low"]) for r in rates],
        "close":  [float(r["close"]) for r in rates],
        "volume": [float(r["tick_volume"]) for r in rates],
        "timestamps": [r["time"] for r in rates],
    }


# ---------------------------------------------------------------------------
# 3. Backtest Configuration
# ---------------------------------------------------------------------------

@dataclass
class BacktestConfig:
    initial_capital: float = 10000.0
    risk_per_trade_pct: float = 0.25
    sl_distance_points: float = 37.0
    risk_reward_ratio: float = 2.0
    min_score_to_trade: int = 350
    min_active_strategies: int = 3
    max_positions: int = 1
    max_position_size_lots: float = 0.05
    units_per_lot: float = 100.0
    # Bar lookback: how many historical bars to pass to strategies
    lookback_bars: int = 200


# ---------------------------------------------------------------------------
# 4. Position Tracker
# ---------------------------------------------------------------------------

@dataclass
class OpenPosition:
    direction: SignalDirection
    entry_price: float
    entry_bar: int
    quantity: float
    stop_loss: float
    take_profit: float
    strategy_scores: Dict[str, int] = field(default_factory=dict)


@dataclass
class ClosedTrade:
    direction: SignalDirection
    entry_price: float
    exit_price: float
    quantity: float
    entry_bar: int
    exit_bar: int
    stop_loss: float
    take_profit: float
    pnl: float = 0.0
    pnl_pips: float = 0.0
    strategy_scores: Dict[str, int] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# 5. Backtest Engine
# ---------------------------------------------------------------------------

class BacktestEngine:
    def __init__(self, config: BacktestConfig):
        self.config = config
        self.bot_config = BotConfig(
            min_score_to_trade=config.min_score_to_trade,
            min_active_strategies=config.min_active_strategies,
            max_risk_per_trade_pct=config.risk_per_trade_pct,
            max_positions=config.max_positions,
            max_position_size_lots=config.max_position_size_lots,
            sl_distance_points=config.sl_distance_points,
            risk_reward_ratio=config.risk_reward_ratio,
            ai_validation_enabled=False,  # Skip AI in backtest
            initial_capital=config.initial_capital,
        )
        self.engine = GoldBotEngine(self.bot_config)
        self.engine._register_strategies()

        self.balance = config.initial_capital
        self.open_positions: List[OpenPosition] = []
        self.closed_trades: List[ClosedTrade] = []

    def _calc_sl_tp(self, entry: float, direction: SignalDirection) -> Tuple[float, float]:
        sl_dist = self.config.sl_distance_points
        tp_dist = sl_dist * self.config.risk_reward_ratio
        if direction == SignalDirection.BUY:
            return entry - sl_dist, entry + tp_dist
        return entry + sl_dist, entry - tp_dist

    def _calc_position_size(self, entry: float, sl: float) -> float:
        risk_pct = self.config.risk_per_trade_pct / 100.0
        risk_amount = self.balance * risk_pct
        risk_per_unit = abs(entry - sl)
        if risk_per_unit <= 0:
            return 0.0
        qty = risk_amount / (risk_per_unit * 100)
        qty = round(qty, 2)
        qty = min(qty, self.config.max_position_size_lots)
        qty = max(qty, 0.01)
        return qty

    def _calc_pnl(self, direction: SignalDirection, entry: float, exit: float, qty: float) -> Tuple[float, float]:
        if direction == SignalDirection.BUY:
            pips = (exit - entry) / 0.01
        else:
            pips = (entry - exit) / 0.01
        dollars = pips * qty * (self.config.units_per_lot / 100)
        return dollars, pips

    def run(self, data: Dict) -> Dict:
        """Walk through bars, run strategies, simulate trades."""
        closes = data["close"]
        highs = data["high"]
        lows = data["low"]
        n_bars = len(closes)
        lookback = self.config.lookback_bars

        _log(f"\nRunning backtest: {n_bars} bars, lookback={lookback}")

        trades_taken = 0
        cooldown_until = -1  # bar index cooldown

        for i in range(lookback, n_bars):
            current_price = closes[i]

            # --- Check open positions against current bar's high/low ---
            still_open = []
            for pos in self.open_positions:
                hit_sl = False
                hit_tp = False
                exit_price = 0.0

                if pos.direction == SignalDirection.BUY:
                    if lows[i] <= pos.stop_loss:
                        hit_sl = True
                        exit_price = pos.stop_loss
                    elif highs[i] >= pos.take_profit:
                        hit_tp = True
                        exit_price = pos.take_profit
                else:  # SELL
                    if highs[i] >= pos.stop_loss:
                        hit_sl = True
                        exit_price = pos.stop_loss
                    elif lows[i] <= pos.take_profit:
                        hit_tp = True
                        exit_price = pos.take_profit

                if hit_sl or hit_tp:
                    reason = "SL" if hit_sl else "TP"
                    pnl, pips = self._calc_pnl(pos.direction, pos.entry_price, exit_price, pos.quantity)
                    self.balance += pnl
                    trade = ClosedTrade(
                        direction=pos.direction,
                        entry_price=pos.entry_price,
                        exit_price=exit_price,
                        quantity=pos.quantity,
                        entry_bar=pos.entry_bar,
                        exit_bar=i,
                        stop_loss=pos.stop_loss,
                        take_profit=pos.take_profit,
                        pnl=pnl,
                        pnl_pips=pips,
                        strategy_scores=pos.strategy_scores,
                    )
                    self.closed_trades.append(trade)
                    # Feed win/loss back to engine strategy stats
                    is_win = pnl > 0
                    for sname, sc in pos.strategy_scores.items():
                        if sname in self.engine.strategy_stats:
                            st = self.engine.strategy_stats[sname]
                            if is_win:
                                st["wins"] += 1
                                st["total_win_pnl"] = st.get("total_win_pnl", 0.0) + pnl
                            else:
                                st["losses"] += 1
                                st["total_loss_pnl"] = st.get("total_loss_pnl", 0.0) + pnl
                            st["pnl"] += pnl
                else:
                    still_open.append(pos)

            self.open_positions = still_open

            # --- Skip if cooldown or max positions ---
            if i < cooldown_until:
                continue
            if len(self.open_positions) >= self.config.max_positions:
                continue

            # --- Build windowed data for strategies ---
            start = max(0, i - lookback + 1)
            window = {
                "M15": {
                    "close": closes[start:i+1],
                    "high":  highs[start:i+1],
                    "low":   lows[start:i+1],
                    "volume": data["volume"][start:i+1],
                }
            }

            # --- Run strategies ---
            self.engine.price_cache = {"mid": current_price}
            signals: List[StrategySignal] = []
            for name, strategy in self.engine.strategies.items():
                if not self.engine.strategy_stats[name]["active"]:
                    continue
                try:
                    sig = strategy.analyze(
                        data=window,
                        current_price=current_price,
                        symbol="XAUUSD",
                    )
                    if sig:
                        signals.append(sig)
                        self.engine.strategy_stats[name]["signals"] += 1
                except Exception:
                    pass

            if not signals:
                continue

            # --- Aggregate ---
            agg = self.engine._aggregate_signals(signals)

            if agg.total_score < self.config.min_score_to_trade:
                continue
            if agg.active_strategies < self.config.min_active_strategies:
                continue

            # --- Execute trade ---
            entry = current_price
            sl, tp = self._calc_sl_tp(entry, agg.direction)
            qty = self._calc_position_size(entry, sl)
            if qty <= 0:
                continue

            pos = OpenPosition(
                direction=agg.direction,
                entry_price=entry,
                entry_bar=i,
                quantity=qty,
                stop_loss=sl,
                take_profit=tp,
                strategy_scores={s.strategy_name: s.score for s in signals},
            )
            self.open_positions.append(pos)
            trades_taken += 1

            # Update strategy trade counts
            for s in signals:
                if s.strategy_name in self.engine.strategy_stats:
                    self.engine.strategy_stats[s.strategy_name]["trades"] += 1

            # Cooldown: 10 bars (2.5 hours at M15)
            cooldown_until = i + 10

            if trades_taken % 10 == 0:
                _log(f"  Bar {i}/{n_bars} | Trades: {trades_taken} | "
                     f"Open: {len(self.open_positions)} | Balance: ${self.balance:,.2f}")

        # --- Close remaining open positions at last close ---
        for pos in self.open_positions:
            exit_price = closes[-1]
            pnl, pips = self._calc_pnl(pos.direction, pos.entry_price, exit_price, pos.quantity)
            self.balance += pnl
            trade = ClosedTrade(
                direction=pos.direction,
                entry_price=pos.entry_price,
                exit_price=exit_price,
                quantity=pos.quantity,
                entry_bar=pos.entry_bar,
                exit_bar=n_bars - 1,
                stop_loss=pos.stop_loss,
                take_profit=pos.take_profit,
                pnl=pnl,
                pnl_pips=pips,
                strategy_scores=pos.strategy_scores,
            )
            self.closed_trades.append(trade)
            # Feed win/loss back to engine strategy stats
            is_win = pnl > 0
            for sname, sc in pos.strategy_scores.items():
                if sname in self.engine.strategy_stats:
                    st = self.engine.strategy_stats[sname]
                    if is_win:
                        st["wins"] += 1
                        st["total_win_pnl"] = st.get("total_win_pnl", 0.0) + pnl
                    else:
                        st["losses"] += 1
                        st["total_loss_pnl"] = st.get("total_loss_pnl", 0.0) + pnl
                    st["pnl"] += pnl

        return self._compute_metrics()

    def _compute_metrics(self) -> Dict:
        trades = self.closed_trades
        if not trades:
            return {
                "total_trades": 0, "wins": 0, "losses": 0,
                "win_rate": 0.0, "total_pnl": 0.0,
                "avg_pnl": 0.0, "sharpe": 0.0,
                "max_drawdown": 0.0, "max_drawdown_pct": 0.0,
                "profit_factor": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
                "strategy_stats": {},
            }

        wins = [t for t in trades if t.pnl > 0]
        losses = [t for t in trades if t.pnl <= 0]
        total_pnl = sum(t.pnl for t in trades)
        win_rate = len(wins) / len(trades) * 100 if trades else 0

        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0

        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in losses))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (999.0 if gross_profit > 0 else 0)

        # Sharpe ratio (annualized from M15 returns)
        pnls = [t.pnl for t in trades]
        mean_ret = sum(pnls) / len(pnls)
        var_ret = sum((p - mean_ret) ** 2 for p in pnls) / len(pnls) if len(pnls) > 1 else 0
        std_ret = math.sqrt(var_ret)
        # Annualize: ~35,040 M15 bars per year, avg ~N trades
        trades_per_year = len(trades) * (35040 / len(trades)) if trades else 1
        sharpe = (mean_ret / std_ret * math.sqrt(trades_per_year)) if std_ret > 0 else 0

        # Max drawdown
        equity = self.config.initial_capital
        peak = equity
        max_dd = 0.0
        max_dd_pct = 0.0
        for t in trades:
            equity += t.pnl
            if equity > peak:
                peak = equity
            dd = peak - equity
            dd_pct = (dd / peak * 100) if peak > 0 else 0
            if dd > max_dd:
                max_dd = dd
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct

        # Per-strategy stats
        strat_stats = {}
        for name, stats in self.engine.strategy_stats.items():
            if stats["trades"] > 0:
                strat_stats[name] = {
                    "signals": stats["signals"],
                    "trades": stats["trades"],
                    "wins": stats["wins"],
                    "losses": stats["losses"],
                    "win_rate": stats["wins"] / stats["trades"] * 100,
                    "pnl": stats["pnl"],
                }

        return {
            "total_trades": len(trades),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": win_rate,
            "total_pnl": total_pnl,
            "final_balance": self.balance,
            "avg_pnl": total_pnl / len(trades),
            "sharpe": sharpe,
            "max_drawdown": max_dd,
            "max_drawdown_pct": max_dd_pct,
            "profit_factor": profit_factor,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "strategy_stats": strat_stats,
        }


# ---------------------------------------------------------------------------
# 6. Pretty Print Results
# ---------------------------------------------------------------------------

def print_results(m: Dict):
    _log("\n" + "=" * 70)
    _log("  GOLD BOT BACKTEST RESULTS")
    _log("=" * 70)
    _log(f"  Total Trades:    {m['total_trades']}")
    _log(f"  Wins / Losses:   {m['wins']}W / {m['losses']}L")
    _log(f"  Win Rate:        {m['win_rate']:.1f}%")
    _log(f"  Final Balance:   ${m['final_balance']:,.2f}")
    _log(f"  Total P&L:       ${m['total_pnl']:+,.2f}")
    _log(f"  Avg P&L/Trade:   ${m['avg_pnl']:+,.2f}")
    _log(f"  Avg Win:         ${m['avg_win']:+,.2f}")
    _log(f"  Avg Loss:        ${m['avg_loss']:+,.2f}")
    _log(f"  Profit Factor:   {m['profit_factor']:.2f}")
    _log(f"  Sharpe Ratio:    {m['sharpe']:.2f}")
    _log(f"  Max Drawdown:    ${m['max_drawdown']:,.2f} ({m['max_drawdown_pct']:.1f}%)")

    if m["strategy_stats"]:
        _log(f"\n  {'Strategy':<20} {'Signals':<10} {'Trades':<10} {'Win%':<10} {'P&L':<12}")
        _log(f"  {'-'*62}")
        for name, s in sorted(m["strategy_stats"].items(),
                               key=lambda x: x[1]["pnl"], reverse=True):
            _log(f"  {name:<20} {s['signals']:<10} {s['trades']:<10} "
                 f"{s['win_rate']:<10.1f} ${s['pnl']:+,.2f}")

    _log("\n" + "=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    _log("=" * 70)
    _log("  GOLD BOT - Backtest Runner")
    _log("  13 Strategies | MT5 Historical Data | M15")
    _log("=" * 70)

    if not connect_mt5():
        _log("Failed to connect to MT5. Exiting.")
        sys.exit(1)

    # Download 1 month of M15 data
    data = download_m15_data("XAUUSD", days=30)
    if not data:
        _log("No data downloaded. Exiting.")
        mt5.shutdown()
        sys.exit(1)

    # Run backtest
    config = BacktestConfig()
    bt = BacktestEngine(config)
    results = bt.run(data)

    # Print results
    print_results(results)

    mt5.shutdown()
    _log("MT5 shutdown.")


if __name__ == "__main__":
    main()
