#!/usr/bin/env python3
"""
Phase 6 - Cost-Aware Backtest Framework (Multi-Asset)

Runs a rule-based SMC signal strategy across XAUUSD, EURUSD, BTCUSD, ETHUSD
with realistic transaction cost models:
  - Spread cost (configurable per symbol)
  - Slippage model (proportional to volatility)
  - Commission (per lot)
  - Swap/rollover cost for overnight positions

Outputs:
  - reports/backtest_cost_{symbol}.json  (per-symbol metrics)
  - reports/cost_analysis.md             (cross-asset summary)

Usage:
    python scripts/backtest_cost_aware.py                   # all symbols
    python scripts/backtest_cost_aware.py --symbol XAUUSD   # single symbol
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE = Path(__file__).resolve().parent.parent
FEAT_DIR = BASE / "artifacts" / "features_v3"
REPORT_DIR = BASE / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Symbol-specific cost defaults
# ---------------------------------------------------------------------------
@dataclass
class SymbolCosts:
    """Transaction cost profile for one symbol."""
    symbol: str
    spread_pips: float        # one-way spread in pips
    commission_per_lot: float  # USD per round-trip lot
    slippage_pips: float      # base one-way slippage in pips
    swap_long_daily: float    # daily swap cost for long positions
    swap_short_daily: float   # daily swap cost for short positions
    pip_value: float          # USD value of 1 pip for 1 standard lot
    point: float              # minimum price increment


SYMBOL_COSTS: dict[str, SymbolCosts] = {
    "XAUUSD": SymbolCosts(
        symbol="XAUUSD", spread_pips=0.3, commission_per_lot=0.0,
        slippage_pips=0.1, swap_long_daily=-2.50, swap_short_daily=0.80,
        pip_value=1.0, point=0.01,
    ),
    "EURUSD": SymbolCosts(
        symbol="EURUSD", spread_pips=0.1, commission_per_lot=0.0,
        slippage_pips=0.05, swap_long_daily=-0.60, swap_short_daily=0.35,
        pip_value=10.0, point=0.0001,
    ),
    "BTCUSD": SymbolCosts(
        symbol="BTCUSD", spread_pips=50.0, commission_per_lot=0.0,
        slippage_pips=10.0, swap_long_daily=-5.00, swap_short_daily=1.20,
        pip_value=0.01, point=0.01,
    ),
    "ETHUSD": SymbolCosts(
        symbol="ETHUSD", spread_pips=5.0, commission_per_lot=0.0,
        slippage_pips=1.0, swap_long_daily=-1.50, swap_short_daily=0.40,
        pip_value=0.01, point=0.01,
    ),
}


# ---------------------------------------------------------------------------
# ATR helper
# ---------------------------------------------------------------------------
def compute_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Compute ATR from OHLC columns."""
    high, low, close = df["high"], df["low"], df["close"]
    tr = pd.concat([
        high - low,
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(window=period, min_periods=1).mean()


# ---------------------------------------------------------------------------
# Signal generation - rule-based SMC strategy
# ---------------------------------------------------------------------------
def generate_smc_signals(df: pd.DataFrame) -> pd.Series:
    """Rule-based SMC signal using features with actual signal in V3 parquet.

    Strategy:
      BUY when:
        - sweep_bullish_flag, OR
        - structure_event_flag AND structure_state indicates uptrend (value 1)
        AND (is_overlap OR is_london_open)
        AND bars_since_bos_choch < 10 (recent structure event)
      SELL when:
        - sweep_bearish_flag, OR
        - structure_event_flag AND structure_state indicates downtrend (value 2)
        AND (is_overlap OR is_london_open)
        AND bars_since_bos_choch < 10
    """
    has_bull = df.get("sweep_bullish_flag", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    has_bear = df.get("sweep_bearish_flag", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    struct_flag = df.get("structure_event_flag", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    struct_state = df.get("structure_state", pd.Series(0, index=df.index)).fillna(0)
    bars_since = df.get("bars_since_bos_choch", pd.Series(999.0, index=df.index)).fillna(999.0)
    is_active = (
        df.get("is_overlap", pd.Series(False, index=df.index)).fillna(False).astype(bool)
        | df.get("is_london_open", pd.Series(False, index=df.index)).fillna(False).astype(bool)
    )

    # Recent structure event (within last 10 bars)
    recent_struct = bars_since < 10

    # Bullish: sweep or (recent structure event in uptrend)
    # Note: after cat.encoding, state 2 = 'up' (forward-filled), 0 = 'down'
    bull = has_bull | (struct_flag & (struct_state == 2) & recent_struct)
    # Bearish: sweep or (recent structure event in downtrend)
    bear = has_bear | (struct_flag & (struct_state == 0) & recent_struct)

    # Apply session filter
    bull = bull & is_active
    bear = bear & is_active

    signal = np.zeros(len(df), dtype=int)
    signal[bull] = 1
    signal[bear] = -1
    signal[bull & bear] = 0
    return pd.Series(signal, index=df.index, name="signal")


# ---------------------------------------------------------------------------
# Trade record
# ---------------------------------------------------------------------------
@dataclass
class TradeRecord:
    """Single trade record with full cost breakdown."""
    entry_bar: int
    exit_bar: int
    side: int
    entry_price: float
    exit_price: float
    bars_held: int
    gross_pnl: float
    spread_cost: float
    slippage_cost: float
    commission_cost: float
    swap_cost: float
    net_pnl: float
    cost_pct_of_gross: float


# ---------------------------------------------------------------------------
# Cost-aware backtest engine
# ---------------------------------------------------------------------------
def run_cost_aware_backtest(
    df: pd.DataFrame,
    costs: SymbolCosts,
    initial_capital: float = 10000.0,
    max_bars_in_trade: int = 20,
    vol_slippage_mult: float = 1.5,
    lot_size: float = 0.01,
) -> dict:
    """Run bar-by-bar backtest with full cost model.

    Args:
        lot_size: Position size in standard lots (0.01 = micro lot).
                  PnL = price_change_in_pips * pip_value * lot_size.
    """
    signals = generate_smc_signals(df)
    close = df["close"].values
    atr = compute_atr(df, period=14).values

    n = len(df)
    equity = initial_capital
    peak_equity = initial_capital
    equity_curve = [initial_capital]
    trades: list[TradeRecord] = []
    in_trade = False
    trade_side = 0
    trade_entry_bar = 0
    trade_entry_price = 0.0
    total_spread = total_slippage = total_commission = total_swap = 0.0
    total_gross = total_net = 0.0

    def _close_trade(i: int):
        nonlocal in_trade, trade_side, equity
        nonlocal total_spread, total_slippage, total_commission, total_swap
        nonlocal total_gross, total_net
        bars_held = i - trade_entry_bar
        exit_price = close[i]
        spread_cost = costs.spread_pips * costs.pip_value * lot_size
        bar_atr = atr[i] if not np.isnan(atr[i]) and atr[i] > 0 else 1.0
        entry_atr = atr[max(0, trade_entry_bar)]
        entry_atr = entry_atr if not np.isnan(entry_atr) and entry_atr > 0 else 1.0
        vol_ratio = bar_atr / entry_atr
        slippage_cost = costs.slippage_pips * costs.pip_value * lot_size * min(vol_ratio, vol_slippage_mult)
        commission_cost = costs.commission_per_lot * lot_size
        days_held = bars_held / 96.0
        swap_cost = (costs.swap_long_daily if trade_side > 0 else abs(costs.swap_short_daily)) * lot_size * days_held
        gross_pnl = ((exit_price - trade_entry_price) if trade_side > 0 else (trade_entry_price - exit_price)) / costs.point * costs.pip_value * lot_size
        total_cost = spread_cost + slippage_cost + commission_cost + swap_cost
        net_pnl = gross_pnl - total_cost
        cost_pct = (total_cost / abs(gross_pnl) * 100) if abs(gross_pnl) > 0 else 0.0
        trades.append(TradeRecord(
            entry_bar=trade_entry_bar, exit_bar=i, side=trade_side,
            entry_price=trade_entry_price, exit_price=exit_price, bars_held=bars_held,
            gross_pnl=gross_pnl, spread_cost=spread_cost, slippage_cost=slippage_cost,
            commission_cost=commission_cost, swap_cost=swap_cost, net_pnl=net_pnl,
            cost_pct_of_gross=cost_pct,
        ))
        total_spread += spread_cost
        total_slippage += slippage_cost
        total_commission += commission_cost
        total_swap += swap_cost
        total_gross += gross_pnl
        total_net += net_pnl
        equity += net_pnl
        in_trade = False
        trade_side = 0

    for i in range(1, n):
        sig = int(signals.iloc[i])
        if in_trade:
            if (i - trade_entry_bar) >= max_bars_in_trade:
                _close_trade(i)
        if not in_trade and sig != 0:
            in_trade = True
            trade_side = sig
            trade_entry_bar = i
            trade_entry_price = close[i]
            entry_spread = costs.spread_pips * costs.pip_value * lot_size
            total_spread += entry_spread
            equity -= entry_spread
        if equity > peak_equity:
            peak_equity = equity
        equity_curve.append(equity)

    if in_trade:
        _close_trade(n - 1)
        equity_curve.append(equity)

    # --- Metrics ---
    equity_arr = np.array(equity_curve)
    returns = np.diff(equity_arr) / equity_arr[:-1]
    returns = returns[np.isfinite(returns)]
    bars_per_year = 96 * 252
    sharpe = sortino = 0.0
    if len(returns) > 1 and np.std(returns) > 0:
        mean_ret, std_ret = np.mean(returns), np.std(returns, ddof=1)
        sharpe = (mean_ret / std_ret) * math.sqrt(bars_per_year)
        ds = returns[returns < 0]
        if len(ds) > 0:
            ds_std = math.sqrt(np.mean(ds ** 2))
            if ds_std > 0:
                sortino = (mean_ret / ds_std) * math.sqrt(bars_per_year)
    peak = np.maximum.accumulate(equity_arr)
    dd = (peak - equity_arr) / peak
    max_dd_pct = float(np.max(dd) * 100) if len(dd) > 0 else 0.0

    win_rate = avg_win = avg_loss = profit_factor = 0.0
    if trades:
        wins = [t for t in trades if t.net_pnl > 0]
        losses = [t for t in trades if t.net_pnl <= 0]
        win_rate = len(wins) / len(trades) * 100
        avg_win = float(np.mean([t.net_pnl for t in wins])) if wins else 0.0
        avg_loss = float(np.mean([t.net_pnl for t in losses])) if losses else 0.0
        sum_win = sum(t.net_pnl for t in wins)
        sum_loss = abs(sum(t.net_pnl for t in losses))
        profit_factor = sum_win / sum_loss if sum_loss > 0 else (float("inf") if sum_win > 0 else 0.0)

    total_cost = total_spread + total_slippage + total_commission + total_swap
    return {
        "symbol": costs.symbol,
        "lot_size": lot_size,
        "initial_capital": initial_capital,
        "final_equity": round(float(equity), 2),
        "total_return_pct": round(float((equity - initial_capital) / initial_capital * 100), 2),
        "total_trades": len(trades),
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": round(profit_factor, 3),
        "avg_win": round(avg_win, 2),
        "avg_loss": round(avg_loss, 2),
        "sharpe_ratio": round(sharpe, 3),
        "sortino_ratio": round(sortino, 3),
        "max_drawdown_pct": round(max_dd_pct, 2),
        "gross_pnl": round(total_gross, 2),
        "net_pnl": round(total_net, 2),
        "costs": {
            "total_spread": round(total_spread, 2),
            "total_slippage": round(total_slippage, 2),
            "total_commission": round(total_commission, 2),
            "total_swap": round(total_swap, 2),
            "total_cost": round(total_cost, 2),
            "cost_as_pct_of_gross": round(
                (total_cost / abs(total_gross) * 100) if abs(total_gross) > 0 else 0.0, 2
            ),
        },
        "cost_profile": {
            "spread_pips": costs.spread_pips,
            "slippage_pips": costs.slippage_pips,
            "commission_per_lot": costs.commission_per_lot,
            "swap_long_daily": costs.swap_long_daily,
            "swap_short_daily": costs.swap_short_daily,
        },
        "trades": [
            {
                "entry_bar": t.entry_bar, "exit_bar": t.exit_bar,
                "side": "LONG" if t.side > 0 else "SHORT",
                "entry_price": round(t.entry_price, 5),
                "exit_price": round(t.exit_price, 5),
                "bars_held": t.bars_held,
                "gross_pnl": round(t.gross_pnl, 2),
                "spread_cost": round(t.spread_cost, 2),
                "slippage_cost": round(t.slippage_cost, 2),
                "commission_cost": round(t.commission_cost, 2),
                "swap_cost": round(t.swap_cost, 2),
                "net_pnl": round(t.net_pnl, 2),
                "cost_pct_of_gross": round(t.cost_pct_of_gross, 2),
            }
            for t in trades
        ],
    }


# ---------------------------------------------------------------------------
# Feature loader
# ---------------------------------------------------------------------------
def load_features(symbol: str) -> pd.DataFrame:
    """Load V3 feature parquet for a symbol."""
    path = FEAT_DIR / f"features_v3_{symbol}_M15.parquet"
    if not path.exists():
        print(f"  [ERROR] Features not found: {path}")
        sys.exit(1)
    df = pd.read_parquet(path)
    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], utc=True)
    # Keep numeric + boolean columns (bools are needed for signal flags)
    keep_cols = df.select_dtypes(include=[np.number, "bool", "object"]).columns.tolist()
    # Ensure OHLCV are always included
    for c in ["time", "open", "high", "low", "close", "volume"]:
        if c in df.columns and c not in keep_cols:
            keep_cols.append(c)
    df = df[keep_cols].copy()
    print(f"  [OK] {path.name}: {len(df)} rows x {len(df.columns)} cols")
    return df


# ---------------------------------------------------------------------------
# Cost analysis report generation
# ---------------------------------------------------------------------------
def generate_cost_analysis(results: dict[str, dict]) -> str:
    """Generate the cost_analysis.md report from per-symbol results."""
    lines = [
        "# Cost Analysis -- Multi-Asset Backtest (Phase 6)",
        "",
        f"**Generated:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "## Strategy",
        "",
        "Rule-based SMC signal strategy using:",
        "- Liquidity sweep flags (bullish/bearish)",
        "- Structure event flags (BOS/CHoCH) with trend state filter",
        "- Session filter (London open / overlap only)",
        "- Max holding period: 20 bars (5 hours at M15)",
        "",
        "## Cost Model",
        "",
        "| Symbol | Spread (pips) | Slippage (pips) | Commission | Swap Long | Swap Short |",
        "|--------|:------------:|:---------------:|:----------:|:---------:|:----------:|",
    ]
    for sym, res in results.items():
        cp = res["cost_profile"]
        lines.append(
            f"| {sym} | {cp['spread_pips']:.1f} | {cp['slippage_pips']:.2f} | "
            f"${cp['commission_per_lot']:.0f} | ${cp['swap_long_daily']:.2f}/d | "
            f"${cp['swap_short_daily']:.2f}/d |"
        )

    lines += [
        "",
        "## Performance Summary",
        "",
        "| Symbol | Trades | Win Rate | Sharpe | Sortino | Max DD% | Gross PnL | Net PnL | Cost erosion |",
        "|--------|:------:|:--------:|:------:|:-------:|:-------:|:---------:|:-------:|:------------:|",
    ]
    for sym, res in results.items():
        cost_pct = res["costs"]["cost_as_pct_of_gross"]
        lines.append(
            f"| {sym} | {res['total_trades']} | {res['win_rate_pct']:.1f}% | "
            f"{res['sharpe_ratio']:.2f} | {res['sortino_ratio']:.2f} | "
            f"{res['max_drawdown_pct']:.1f}% | ${res['gross_pnl']:.0f} | "
            f"${res['net_pnl']:.0f} | {cost_pct:.1f}% |"
        )

    lines += [
        "",
        "## Cost Breakdown",
        "",
        "| Symbol | Spread | Slippage | Commission | Swap | Total Cost | % of Gross |",
        "|--------|:------:|:--------:|:----------:|:----:|:----------:|:----------:|",
    ]
    for sym, res in results.items():
        c = res["costs"]
        lines.append(
            f"| {sym} | ${c['total_spread']:.0f} | ${c['total_slippage']:.0f} | "
            f"${c['total_commission']:.0f} | ${c['total_swap']:.0f} | "
            f"${c['total_cost']:.0f} | {c['cost_as_pct_of_gross']:.1f}% |"
        )

    # Cost sensitivity ranking
    lines += ["", "## Cost Sensitivity Ranking", ""]
    if results:
        ranked = sorted(results.items(), key=lambda x: x[1]["costs"]["cost_as_pct_of_gross"])
        lines.append("| Rank | Symbol | Cost Erosion | Net PnL | Verdict |")
        lines.append("|:----:|--------|:------------:|:-------:|---------|")
        for rank, (sym, res) in enumerate(ranked, 1):
            erosion = res["costs"]["cost_as_pct_of_gross"]
            if erosion < 1:
                verdict = "MINIMAL cost impact"
            elif erosion < 3:
                verdict = "LOW cost impact"
            elif erosion < 8:
                verdict = "MODERATE cost impact"
            elif erosion < 20:
                verdict = "HIGH cost impact"
            else:
                verdict = "VERY HIGH cost impact"
            lines.append(f"| {rank} | {sym} | {erosion:.1f}% | ${res['net_pnl']:.0f} | {verdict} |")

    lines += [
        "",
        "## Recommendations for Cost Optimization",
        "",
        "1. **ECN/Razor account** for all symbols to minimize spread",
        "2. **Limit orders** where possible to avoid slippage entirely",
        "3. **Avoid trading during low-liquidity sessions** (Asian for FX, weekends for crypto)",
        "4. **Longer holding periods** dilute fixed entry/exit costs across larger moves",
        "5. **BTCUSD** has highest absolute spread -- consider ETH for crypto exposure",
        "6. **EURUSD** is the cheapest to trade -- ideal for high-frequency strategies",
        "7. **XAUUSD** offers good cost/resilience ratio with Pepperstone zero-commission",
        "8. **Swap costs** favor short positions in most symbols -- factor into carry analysis",
        "",
        "---",
        "*Generated by backtest_cost_aware.py (Phase 6)*",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Numpy JSON helper
# ---------------------------------------------------------------------------
def convert_numpy(obj):
    """Recursively convert numpy types to native Python."""
    if isinstance(obj, dict):
        return {k: convert_numpy(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy(v) for v in obj]
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Phase 6: Cost-aware backtest (multi-asset)")
    parser.add_argument("--symbol", type=str, default=None,
                        help="Single symbol to test (default: all four)")
    parser.add_argument("--capital", type=float, default=10000.0)
    parser.add_argument("--max-bars", type=int, default=20,
                        help="Max holding period in M15 bars")
    args = parser.parse_args()

    symbols = [args.symbol] if args.symbol else ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD"]
    all_results = {}

    for sym in symbols:
        if sym not in SYMBOL_COSTS:
            print(f"  [SKIP] Unknown symbol: {sym}")
            continue

        print(f"\n{'='*60}")
        print(f"  COST-AWARE BACKTEST: {sym}")
        print(f"  Spread: {SYMBOL_COSTS[sym].spread_pips} pips | Slippage: {SYMBOL_COSTS[sym].slippage_pips} pips")
        print(f"{'='*60}")

        df = load_features(sym)
        costs = SYMBOL_COSTS[sym]

        result = run_cost_aware_backtest(df, costs, initial_capital=args.capital, max_bars_in_trade=args.max_bars, lot_size=0.01)
        all_results[sym] = result

        print(f"\n  --- {sym} Results ---")
        print(f"  Trades: {result['total_trades']}")
        print(f"  Win rate: {result['win_rate_pct']:.1f}%")
        print(f"  Gross PnL: ${result['gross_pnl']:.2f}")
        print(f"  Total cost: ${result['costs']['total_cost']:.2f}")
        print(f"  Net PnL: ${result['net_pnl']:.2f}")
        print(f"  Cost erosion: {result['costs']['cost_as_pct_of_gross']:.1f}%")
        print(f"  Sharpe: {result['sharpe_ratio']:.3f}")
        print(f"  Sortino: {result['sortino_ratio']:.3f}")
        print(f"  Max DD: {result['max_drawdown_pct']:.1f}%")
        print(f"  Profit factor: {result['profit_factor']:.3f}")

        save_result = {k: v for k, v in result.items() if k != "trades"}
        save_result["trade_count"] = len(result["trades"])
        save_result["sample_trades"] = result["trades"][:10]
        out_path = REPORT_DIR / f"backtest_cost_{sym}.json"
        with open(out_path, "w") as f:
            json.dump(convert_numpy(save_result), f, indent=2)
        print(f"\n  Saved: {out_path}")

    if all_results:
        analysis = generate_cost_analysis(all_results)
        analysis_path = REPORT_DIR / "cost_analysis.md"
        with open(analysis_path, "w") as f:
            f.write(analysis)
        print(f"\n{'='*60}")
        print(f"  COST ANALYSIS: {analysis_path}")
        print(f"{'='*60}")


if __name__ == "__main__":
    main()
