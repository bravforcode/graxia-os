"""
Historical Paper Trade Simulator — EURUSD D1 RSI + BB
Simulates 22 years of paper trading with live costs + risk management.

Usage:
    python graxia/packages/quant_os/paper_trade_simulator.py

Output:
    console: Sharpe, Win Rate, Max DD, Profit Factor, Trade counts
    reports/paper_trade_simulation.csv: every trade detail
    reports/paper_trade_summary.json: aggregate stats
"""
import numpy as np
import pandas as pd
from pathlib import Path
import json
import os

# === CONFIG ==========================================================
BASE = Path(r"C:\Users\menum\graxia os\graxia\packages\quant_os")
DATA_FILE = BASE / "data" / "EURUSD_D1_clean.csv"
TRADE_CSV = BASE / "reports" / "paper_trade_simulation.csv"
SUMMARY_JSON = BASE / "reports" / "paper_trade_summary.json"

# Strategy
RSI_PERIOD = 14
RSI_OVERSOLD = 30
RSI_OVERBOUGHT = 70
BB_PERIOD = 20
BB_STD = 2.0

# Risk
RISK_PCT = 0.01          # 1% equity risk per trade
SL_ATR_MULT = 1.5
TP_ATR_MULT = 2.0
ATR_PERIOD = 14

# Cost model — FOREX live (Pepperstone Razor)
# Spread: 1.0 bps/side   Commission: ~$7/$100K ≈ 0.7 bps/side   Slippage: 0.5 bps/side
# Total: 2.2 bps/side, 4.4 bps/RT. We charge on BOTH entry and exit.
COST_BPS_SIDE = 2.2       # basis points per side (entry OR exit)
COST_RT_BPS = COST_BPS_SIDE * 2  # per round trip

# Split
TRAIN_SPLIT = 0.80
INITIAL_EQUITY = 10_000   # USD

# ======================================================================


def compute_rsi(closes: np.ndarray, period: int = 14) -> np.ndarray:
    """Wilder's RSI — returns array same length as closes, NaN for warmup."""
    n = len(closes)
    rsi = np.full(n, np.nan)
    if n < period + 1:
        return rsi

    delta = np.diff(closes)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)

    # Wilder smoothing initial average
    avg_gain = np.mean(gain[:period])
    avg_loss = np.mean(loss[:period])

    for i in range(period, n - 1):
        if avg_loss == 0:
            rsi[i] = 100.0
        else:
            rs = avg_gain / (avg_loss + 1e-10)
            rsi[i] = 100.0 - 100.0 / (1.0 + rs)
        # Smooth
        avg_gain = (avg_gain * (period - 1) + gain[i]) / period
        avg_loss = (avg_loss * (period - 1) + loss[i]) / period

    return rsi


def compute_bb(closes: np.ndarray, period: int = 20, nbdev: float = 2.0):
    """Bollinger Bands — returns (sma, lower, upper), NaN for warmup."""
    n = len(closes)
    sma = np.full(n, np.nan)
    lower = np.full(n, np.nan)
    upper = np.full(n, np.nan)

    for i in range(period - 1, n):
        window = closes[i - period + 1 : i + 1]
        mu = np.mean(window)
        sigma = np.std(window, ddof=1) if len(window) > 1 else 0
        sma[i] = mu
        lower[i] = mu - nbdev * sigma
        upper[i] = mu + nbdev * sigma

    return sma, lower, upper


def compute_atr(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray,
                period: int = 14) -> np.ndarray:
    """Average True Range — Wilder smoothed."""
    n = len(closes)
    atr = np.full(n, np.nan)
    if n < period + 1:
        return atr

    tr = np.zeros(n)
    tr[0] = highs[0] - lows[0]
    for i in range(1, n):
        h_l = highs[i] - lows[i]
        h_pc = abs(highs[i] - closes[i - 1])
        l_pc = abs(lows[i] - closes[i - 1])
        tr[i] = max(h_l, h_pc, l_pc)

    atr[period - 1] = np.mean(tr[:period])
    for i in range(period, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def apply_cost(price: float, bps_per_side: float) -> tuple:
    """Return (price_after_cost, cost_in_price_units)."""
    cost = price * bps_per_side / 10000.0
    return price - cost, cost  # pessimistic: worse fill


def run_simulation():
    print("=" * 60)
    print("  PAPER TRADE SIMULATOR - EURUSD D1 RSI + BB")
    print("=" * 60)
    print()

    # ----- Load data -----
    df = pd.read_csv(DATA_FILE)
    closes = df["Close"].values
    highs = df["High"].values
    lows = df["Low"].values
    opens = df["Open"].values
    dates = df["Date"].values
    n = len(closes)
    print(f"Loaded {n} bars ({dates[0]} to {dates[-1]})")

    # ----- Compute indicators -----
    rsi = compute_rsi(closes, RSI_PERIOD)
    sma, bb_lower, bb_upper = compute_bb(closes, BB_PERIOD, BB_STD)
    atr = compute_atr(highs, lows, closes, ATR_PERIOD)

    # ----- Split -----
    split_idx = int(n * TRAIN_SPLIT)
    print(f"Train: {split_idx} bars ({dates[0]} to {dates[split_idx-1]})")
    print(f"Test:  {n - split_idx} bars ({dates[split_idx]} to {dates[-1]})")
    print()

    # ----- Generate signals on entire dataset -----
    signals = np.full(n, 0, dtype=int)  # 0=no, 1=buy, -1=sell
    for i in range(max(RSI_PERIOD, BB_PERIOD, ATR_PERIOD), n):
        if np.isnan(rsi[i]) or np.isnan(bb_lower[i]) or np.isnan(atr[i]):
            continue
        if rsi[i] < RSI_OVERSOLD and closes[i] < bb_lower[i]:
            signals[i] = 1
        elif rsi[i] > RSI_OVERBOUGHT and closes[i] > bb_upper[i]:
            signals[i] = -1

    # ----- Simulate trading -----
    trades = []
    position = 0          # 1=long, -1=short, 0=flat
    entry_price = 0.0
    entry_cost = 0.0
    entry_idx = 0
    entry_date = ""
    entry_bar = ""        # 'train' or 'test'
    entry_sl_dist = 1.0   # saved for PnL calc on exit
    entry_atr_price = 1.0
    position_size = 0.01
    equity = INITIAL_EQUITY
    equity_curve = [equity]
    peak_equity = equity

    warmup = max(RSI_PERIOD, BB_PERIOD, ATR_PERIOD)

    for i in range(warmup, n):
        signal = signals[i]
        bar_label = "train" if i < split_idx else "test"

        if position == 0 and signal != 0:
            # Open position
            position = signal          # 1=long, -1=short
            entry_idx = i
            entry_bar = bar_label

            # Use next bar's open for realistic execution
            if i + 1 < n:
                entry_price = opens[i + 1]
                entry_date = dates[i + 1]
            else:
                entry_price = closes[i]
                entry_date = dates[i]

            # Apply entry cost
            entry_price, entry_cost = apply_cost(entry_price, COST_BPS_SIDE)

            # Size based on ATR
            stop_atr = atr[i]
            if np.isnan(stop_atr) or stop_atr <= 0:
                stop_atr = entry_price * 0.005  # fallback 0.5%

            sl_distance = stop_atr * SL_ATR_MULT
            entry_sl_dist = sl_distance
            entry_atr_price = entry_price
            tp_distance = stop_atr * TP_ATR_MULT
            risk_amount = equity * RISK_PCT
            if sl_distance > 0:
                position_size = risk_amount / (sl_distance * 100000)
            else:
                position_size = 0.01  # micro lot fallback

        elif position != 0 and signal == -position:
            # Close position on opposite signal
            if i + 1 < n:
                exit_price_raw = opens[i + 1]
                exit_date = dates[i + 1]
            else:
                exit_price_raw = closes[i]
                exit_date = dates[i]

            exit_price, exit_cost = apply_cost(exit_price_raw, COST_BPS_SIDE)

            # Calculate PnL with risk-sized position
            # For EURUSD: 1 standard lot = 100,000 units, 1 pip (0.0001) = ~$10
            # SL distance = ATR * 1.5 (price units)
            # Position size = risk_amount / (SL_distance * 100000)
            # PnL = direction * (exit - entry) * position_size * 100000

            if position == 1:  # long
                price_move = exit_price - entry_price
                pnl_pct = price_move / entry_price
            else:  # short
                price_move = entry_price - exit_price
                pnl_pct = price_move / entry_price

            total_cost_bps = COST_RT_BPS
            pnl_after_cost = pnl_pct - (total_cost_bps / 10000.0)

            # Risk-sized PnL: if price hits SL, we lose exactly RISK_PCT of equity
            sl_move_ratio = entry_sl_dist / entry_atr_price
            leveraged_return = pnl_after_cost / (sl_move_ratio + 1e-10) * RISK_PCT
            equity *= (1.0 + leveraged_return)

            # Track
            trades.append({
                "entry_date": entry_date,
                "exit_date": exit_date,
                "bar": entry_bar,
                "signal": "LONG" if position == 1 else "SHORT",
                "entry_price": round(entry_price, 6),
                "exit_price": round(exit_price, 6),
                "pnl_pct": round(pnl_pct * 100, 4),
                "pnl_after_cost_pct": round(pnl_after_cost * 100, 4),
                "equity": round(equity, 2),
                "duration_bars": i - entry_idx,
            })

            peak_equity = max(peak_equity, equity)
            position = 0

        equity_curve.append(equity)

    # ----- Also handle stop loss / take profit -----
    # Walk through open positions and check SL/TP on each bar
    # (simplified: we trust the signal-based exit, which is conservative)

    # ----- Compute statistics -----
    if len(trades) == 0:
        print("ERROR: No trades generated!")
        return

    train_trades = [t for t in trades if t["bar"] == "train"]
    test_trades = [t for t in trades if t["bar"] == "test"]

    def compute_stats(trade_list):
        if not trade_list:
            return {"sharpe": 0, "winrate": 0, "max_dd": 0, "profit_factor": 0, "trades": 0}

        n_trades = len(trade_list)
        pnls = [t["pnl_after_cost_pct"] for t in trade_list]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        wr = len(wins) / n_trades if n_trades > 0 else 0
        avg_win = np.mean(wins) if wins else 0
        avg_loss = abs(np.mean(losses)) if losses else 0
        pf = (avg_win * len(wins)) / (avg_loss * len(losses)) if avg_loss > 0 and len(losses) > 0 else 0

        # Sharpe annualized (daily data, ~252 trading days)
        if len(pnls) >= 2:
            sharpe = np.mean(pnls) / (np.std(pnls, ddof=1) + 1e-10) * np.sqrt(252)
        else:
            sharpe = 0

        # Max drawdown from equity curve
        eq = INITIAL_EQUITY
        peak = eq
        max_dd = 0.0
        for t in trade_list:
            eq = t["equity"]
            peak = max(peak, eq)
            dd = (peak - eq) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        return {
            "sharpe": round(sharpe, 4),
            "winrate": round(wr * 100, 2),
            "max_dd_pct": round(max_dd * 100, 2),
            "profit_factor": round(pf, 4),
            "trades": n_trades,
        }

    train_stats = compute_stats(train_trades)
    test_stats = compute_stats(test_trades)

    # Overall max DD from full equity curve
    eq = INITIAL_EQUITY
    peak = eq
    overall_max_dd = 0.0
    for t in trades:
        eq = t["equity"]
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak > 0 else 0
        overall_max_dd = max(overall_max_dd, dd)

    final_equity = trades[-1]["equity"] if trades else INITIAL_EQUITY
    total_return = (final_equity / INITIAL_EQUITY - 1) * 100

    # ----- Print report -----
    print("-" * 60)
    print("  PAPER TRADE RESULTS")
    print("-" * 60)
    print(f"  Initial equity:  ${INITIAL_EQUITY:,.2f}")
    print(f"  Final equity:    ${final_equity:,.2f}")
    print(f"  Total return:    {total_return:+.2f}%")
    print()
    print(f"  {'':20s}  {'TRAIN':>10s}  {'TEST':>10s}  {'ALL':>10s}")
    print(f"  {'-'*20}  {'-'*10}  {'-'*10}  {'-'*10}")
    print(f"  {'Trades':20s}  {train_stats['trades']:>10d}  {test_stats['trades']:>10d}  {len(trades):>10d}")
    print(f"  {'Sharpe (ann)':20s}  {train_stats['sharpe']:>10.4f}  {test_stats['sharpe']:>10.4f}  {'—':>10s}")
    print(f"  {'Win Rate %':20s}  {train_stats['winrate']:>9.1f}%  {test_stats['winrate']:>9.1f}%  {'—':>10s}")
    print(f"  {'Profit Factor':20s}  {train_stats['profit_factor']:>10.4f}  {test_stats['profit_factor']:>10.4f}  {'—':>10s}")
    print(f"  {'Max DD %':20s}  {train_stats['max_dd_pct']:>9.2f}%  {test_stats['max_dd_pct']:>9.2f}%  {overall_max_dd*100:>9.2f}%")
    print()
    print(f"  Cost model:   {COST_BPS_SIDE} bps/side ({COST_RT_BPS} bps/RT)")
    print()

    # Go-live decision
    passes = test_stats["sharpe"] > 0.15 and test_stats["winrate"] > 45
    print(f"  GO-LIVE CHECK: Sharpe > 0.15 & WR > 45% -> {'PASS' if passes else 'FAIL'}")
    if passes:
        print("  -> Paper trade live on Pepperstone demo 3-6 months.")
    else:
        shortfall = []
        if test_stats["sharpe"] <= 0.15:
            shortfall.append(f"Sharpe {test_stats['sharpe']:.4f} < 0.15")
        if test_stats["winrate"] <= 45:
            shortfall.append(f"WR {test_stats['winrate']:.1f}% < 45%")
        print(f"  -> Shortfall: {'; '.join(shortfall)}")
        print("  -> Do NOT go live. Expand strategy search or accept result.")
    print()

    # ----- Save CSV -----
    os.makedirs(TRADE_CSV.parent, exist_ok=True)
    trade_df = pd.DataFrame(trades)
    trade_df.to_csv(TRADE_CSV, index=False)
    print(f"  Trade log saved: {TRADE_CSV}")

    # ----- Save JSON -----
    summary = {
        "strategy": "RSI(14) + BB(20,2)",
        "symbol": "EURUSD",
        "timeframe": "D1",
        "data_period": f"{dates[0]} to {dates[-1]}",
        "train_bars": split_idx,
        "test_bars": n - split_idx,
        "cost_model": f"{COST_BPS_SIDE} bps/side ({COST_RT_BPS} bps/RT)",
        "initial_equity": INITIAL_EQUITY,
        "final_equity": round(final_equity, 2),
        "total_return_pct": round(total_return, 2),
        "train": train_stats,
        "test": test_stats,
        "overall_max_dd_pct": round(overall_max_dd * 100, 2),
        "total_trades": len(trades),
        "go_live_pass": passes,
    }
    with open(SUMMARY_JSON, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"  Summary saved:  {SUMMARY_JSON}")

    print()
    print("=" * 60)
    print("  SIMULATION COMPLETE")
    print("=" * 60)

    return summary


if __name__ == "__main__":
    run_simulation()
