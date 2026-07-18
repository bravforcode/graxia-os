"""
Gold ICT Edge Search — WFA + DK-test for gold_bot strategies on XAUUSD.

Runs walk-forward validation for all gi_* strategies, then applies pooled DK-test
across strategy-param variants. Does NOT burn sacred holdout.

GO criteria (pre-registered):
  dk_t > 2.0 AND positive_sharpe_count >= 5  → GO
  dk_t > 1.5 OR (dk_t > 1.0 AND pos >= 4)    → MARGINAL
  else                                        → REJECT

Usage:
  python scripts/edge_search_gold_ict.py
  python scripts/edge_search_gold_ict.py --only gi_bos_choch,gi_ema_cross
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
for p in (str(GRAXIA_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Measured costs from config/cost_calibration.json (Pepperstone Razor)
XAUUSD_SPREAD_BPS = 0.30  # $0 commission, measured spread+slip

# Strategies with batch generators (O(n) — fast enough for full history)
BATCH_STRATEGIES = [
    "gi_ema_cross",
    "gi_bos_choch",
    "gi_fair_value_gap",
    "gi_rsi_divergence",
    "gi_supply_demand",
    "gi_london_breakout",
    "gi_vwap_rejection",
    "gi_liquidity_sweep",
]

# Bar-by-bar only (O(n²) — slow, limited to D1)
BAR_STRATEGIES = [
    "gi_order_block",
    "gi_multi_tf_align",
    "gi_news_fade",
    "gi_fibonacci",
    "gi_opening_range",
]

# Param grid per strategy (from campaign.py)
PARAM_GRIDS = {
    "gi_ema_cross": [{"min_bars": 60}, {"min_bars": 80}, {"min_bars": 100}],
    "gi_bos_choch": [{"min_bars": 35}, {"min_bars": 50}, {"min_bars": 65}],
    "gi_fair_value_gap": [{"min_bars": 30}, {"min_bars": 40}, {"min_bars": 50}],
    "gi_rsi_divergence": [{"min_bars": 35}, {"min_bars": 50}, {"min_bars": 65}],
    "gi_supply_demand": [{"min_bars": 60}, {"min_bars": 80}, {"min_bars": 100}],
    "gi_london_breakout": [{"min_bars": 30}, {"min_bars": 40}, {"min_bars": 50}],
    "gi_vwap_rejection": [{"min_bars": 30}, {"min_bars": 40}, {"min_bars": 50}],
    "gi_liquidity_sweep": [{"min_bars": 35}, {"min_bars": 50}, {"min_bars": 65}],
    "gi_order_block": [{"min_bars": 60}],
    "gi_multi_tf_align": [{"min_bars": 60}],
    "gi_news_fade": [{"min_bars": 35}],
    "gi_fibonacci": [{"min_bars": 60}],
    "gi_opening_range": [{"min_bars": 20}],
}


def load_xauusd_d1() -> pd.DataFrame:
    """Load XAUUSD D1 data from 2005 onward."""
    path = ROOT / "data" / "XAUUSD_D1.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing {path}")
    df = pd.read_csv(path)
    ts = "time" if "time" in df.columns else "date"
    df[ts] = pd.to_datetime(df[ts])
    df = df[df[ts] >= "2005-01-01"].sort_values(ts).reset_index(drop=True)
    if ts != "time":
        df = df.rename(columns={ts: "time"})
    if len(df) < 500:
        raise ValueError(f"XAUUSD D1: only {len(df)} bars (< 500)")
    return df


def simulate_signals_to_trades(
    directions: np.ndarray,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    min_bars: int,
    cost_bps: float = XAUUSD_SPREAD_BPS,
) -> list[dict]:
    """Convert batch signals to simulated trades (next-bar execution)."""
    n = len(close)
    trades = []
    open_trade = None

    for i in range(min_bars, n - 1):
        d = directions[i]
        next_close = close[i + 1]
        next_high = high[i + 1]
        next_low = low[i + 1]

        if open_trade is None:
            if d != 0:
                open_trade = {
                    "entry_bar": i + 1,
                    "entry_price": next_close,
                    "direction": d,
                }
        else:
            # Check SL/TP first (using high/low of next bar)
            hit_sl = False
            hit_tp = False
            if open_trade["direction"] == 1:
                # LONG: check SL (next_low) and TP (next_high)
                pass  # We don't have SL/TP in batch output for trade sim
            elif open_trade["direction"] == -1:
                pass

            # Close on signal change or flat
            if d != open_trade["direction"]:
                exit_price = next_close
                pnl_raw = (exit_price - open_trade["entry_price"]) * open_trade["direction"]
                cost = exit_price * cost_bps / 10000.0 + open_trade["entry_price"] * cost_bps / 10000.0
                trades.append({
                    "entry_bar": open_trade["entry_bar"],
                    "exit_bar": i + 1,
                    "direction": open_trade["direction"],
                    "entry_price": open_trade["entry_price"],
                    "exit_price": exit_price,
                    "pnl_raw": pnl_raw,
                    "cost": cost,
                    "net_pnl": pnl_raw - cost,
                })
                if d != 0:
                    open_trade = {
                        "entry_bar": i + 1,
                        "entry_price": next_close,
                        "direction": d,
                    }
                else:
                    open_trade = None

    # Close remaining open trade
    if open_trade is not None:
        exit_price = close[-1]
        pnl_raw = (exit_price - open_trade["entry_price"]) * open_trade["direction"]
        cost = exit_price * cost_bps / 10000.0 + open_trade["entry_price"] * cost_bps / 10000.0
        trades.append({
            "entry_bar": open_trade["entry_bar"],
            "exit_bar": n - 1,
            "direction": open_trade["direction"],
            "entry_price": open_trade["entry_price"],
            "exit_price": exit_price,
            "pnl_raw": pnl_raw,
            "cost": cost,
            "net_pnl": pnl_raw - cost,
        })

    return trades


def sharpe_from_trades(trades: list[dict]) -> float:
    """Annualized Sharpe from trades list."""
    if len(trades) < 5:
        return 0.0
    pnls = np.array([t["net_pnl"] for t in trades])
    std = float(np.std(pnls, ddof=1))
    if std <= 1e-10:
        return 0.0
    mu = float(np.mean(pnls))
    # Estimate trades per year from bar indices
    bars = [t["exit_bar"] for t in trades]
    if len(bars) >= 2:
        bar_span = bars[-1] - bars[0]
        years = bar_span / 252.0  # D1
        tpy = len(trades) / years if years > 0 else 252.0
    else:
        tpy = 252.0
    return mu / std * math.sqrt(tpy)


def dk_test_pooled(all_returns: pd.DataFrame, total_trades: int) -> dict:
    """Pooled DK-test across strategy variants (each variant = column)."""
    if all_returns.empty or len(all_returns.columns) < 2:
        return {
            "dk_t_stat": 0.0, "pooled_sharpe": 0.0,
            "positive_sharpe_count": 0, "total_variants": 0,
            "total_days": 0, "total_trades": total_trades,
            "verdict": "INSUFFICIENT_DATA",
        }

    cs_mean = all_returns.mean(axis=1).dropna()
    if len(cs_mean) < 30:
        return {
            "dk_t_stat": 0.0, "pooled_sharpe": 0.0,
            "positive_sharpe_count": 0, "total_variants": len(all_returns.columns),
            "total_days": len(cs_mean), "total_trades": total_trades,
            "verdict": "INSUFFICIENT_DATA",
        }

    mu = float(cs_mean.mean())
    T = len(cs_mean)
    max_lag = max(1, int(T ** (1 / 3)))
    gamma_0 = float(cs_mean.var(ddof=1))
    nw_var = gamma_0
    for lag in range(1, max_lag + 1):
        cov = float(cs_mean.iloc[lag:].cov(cs_mean.iloc[:-lag]))
        weight = 1.0 - lag / (max_lag + 1)
        nw_var += 2 * weight * cov

    nw_se = math.sqrt(nw_var / T) if nw_var > 0 else 1e-10
    dk_t = mu / nw_se if nw_se > 0 else 0.0
    pooled_sharpe = mu / (math.sqrt(gamma_0) + 1e-10) * math.sqrt(252)

    pos_sharpe = 0
    for col in all_returns.columns:
        r = all_returns[col].dropna()
        if len(r) > 30:
            s = float(r.mean()) / (float(r.std(ddof=1)) + 1e-10) * math.sqrt(252)
            if s > 0:
                pos_sharpe += 1

    if dk_t > 2.0 and pos_sharpe >= 5:
        verdict = "GO"
    elif dk_t > 1.5 or (dk_t > 1.0 and pos_sharpe >= 4):
        verdict = "MARGINAL"
    else:
        verdict = "REJECT"

    return {
        "dk_t_stat": round(dk_t, 4),
        "pooled_sharpe": round(pooled_sharpe, 4),
        "positive_sharpe_count": pos_sharpe,
        "total_variants": len(all_returns.columns),
        "total_days": T,
        "total_trades": total_trades,
        "verdict": verdict,
    }


def run_strategy_wfa(
    strategy_id: str,
    df: pd.DataFrame,
    params_grid: list[dict],
    cost_bps: float = XAUUSD_SPREAD_BPS,
) -> dict:
    """Run WFA for a single strategy, return per-fold + OOS results."""
    from graxia.packages.quant_os.paper_engine.strategies.gold_ict import GOLD_ICT_REGISTRY
    from graxia.packages.quant_os.paper_engine.strategies.gold_ict_batch import BATCH_REGISTRY

    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    vol = df["volume"].values.astype(float) if "volume" in df.columns else None
    n = len(close)

    # WFA splits
    n_splits = 5
    embargo = max(5, int(n * 0.01))  # 1% embargo
    train_ratio = 0.7
    fold_size = n // n_splits
    splits = []
    for fold in range(n_splits):
        fold_start = fold * fold_size
        fold_end = min(fold_start + fold_size, n)
        train_end = fold_start + int((fold_end - fold_start) * train_ratio)
        test_start = train_end + embargo
        test_end = fold_end
        if test_start >= test_end:
            continue
        splits.append(((fold_start, train_end), (test_start, test_end)))

    if not splits:
        return {"strategy_id": strategy_id, "error": "Not enough bars for WFA splits"}

    # Run each param combo via batch or bar-by-bar
    batch_fn = BATCH_REGISTRY.get(strategy_id)
    combo_trades = []

    for params in params_grid:
        if batch_fn is not None:
            sig = __import__("inspect").signature(batch_fn)
            kwargs = {"close": close, "high": high, "low": low}
            if "volume" in sig.parameters and vol is not None:
                kwargs["volume"] = vol
            result = batch_fn(**kwargs)
            directions = result.directions
        else:
            # Fall back to bar-by-bar wrapper
            wrapper_cls = GOLD_ICT_REGISTRY.get(strategy_id)
            if wrapper_cls is None:
                combo_trades.append([])
                continue
            wrapper = wrapper_df_result = wrapper_cls()
            sr = wrapper.generate_signals(df, params)
            directions = np.zeros(n, dtype=int)
            for s in sr.signals:
                if s.bar_index is not None and 0 <= s.bar_index < n:
                    directions[s.bar_index] = s.direction

        min_bars = params.get("min_bars", 50)
        trades = simulate_signals_to_trades(directions, close, high, low, min_bars, cost_bps)
        combo_trades.append(trades)

    # WFA: pick best combo per fold on train, evaluate on test
    fold_reports = []
    oos_trades = []

    for (train_start, train_end), (test_start, test_end) in splits:
        best_idx, best_sharpe = None, -float("inf")
        for combo_idx, trades in enumerate(combo_trades):
            train_t = [t for t in trades if train_start <= t["entry_bar"] < train_end]
            if len(train_t) < 3:
                continue
            s = sharpe_from_trades(train_t)
            if s > best_sharpe:
                best_sharpe, best_idx = s, combo_idx

        if best_idx is None:
            fold_reports.append({
                "train_range": [train_start, train_end],
                "test_range": [test_start, test_end],
                "skipped": "no combo reached min trades",
            })
            continue

        test_t = [t for t in combo_trades[best_idx] if test_start <= t["entry_bar"] < test_end]
        fold_reports.append({
            "train_range": [train_start, train_end],
            "test_range": [test_start, test_end],
            "chosen_params": params_grid[best_idx],
            "train_sharpe": round(best_sharpe, 3),
            "test_trades": len(test_t),
        })
        oos_trades.extend(test_t)

    oos_sharpe = sharpe_from_trades(oos_trades) if oos_trades else 0.0
    oos_trades_total = len(oos_trades)
    oos_wins = sum(1 for t in oos_trades if t["net_pnl"] > 0)
    oos_wr = oos_wins / oos_trades_total * 100 if oos_trades_total > 0 else 0.0
    oos_pnl = sum(t["net_pnl"] for t in oos_trades)

    return {
        "strategy_id": strategy_id,
        "data_bars": n,
        "wfa_splits": len(splits),
        "folds_used": sum(1 for f in fold_reports if "skipped" not in f),
        "param_grid_size": len(params_grid),
        "folds": fold_reports,
        "oos_trades": oos_trades_total,
        "oos_sharpe": round(oos_sharpe, 4),
        "oos_win_rate": round(oos_wr, 1),
        "oos_total_pnl": round(oos_pnl, 2),
        "oos_trades_list": oos_trades,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Gold ICT edge search (WFA + DK-test)")
    parser.add_argument("--only", type=str, default="", help="Comma-separated strategy IDs")
    parser.add_argument("--out", type=str, default=str(ROOT / "reports" / "edge_search_gold_ict_results.json"))
    args = parser.parse_args()

    print("=" * 70)
    print("  GOLD ICT EDGE SEARCH — WFA + DK-test on XAUUSD D1")
    print("=" * 70)
    print(f"  GO rule: dk_t>2.0 AND pos_sharpe>=5")
    print(f"  Time: {datetime.now(timezone.utc).isoformat()}")

    df = load_xauusd_d1()
    print(f"  Data: {len(df)} D1 bars (from {df.iloc[0].get('time', '?')})")

    # Filter strategies
    all_strategies = BATCH_STRATEGIES + BAR_STRATEGIES
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        all_strategies = [s for s in all_strategies if s in wanted]

    print(f"  Strategies: {len(all_strategies)}")
    print(f"  Cost: {XAUUSD_SPREAD_BPS} bps round-trip")

    all_results = {}
    total_trades = 0

    for strat_id in all_strategies:
        params_grid = PARAM_GRIDS.get(strat_id, [{"min_bars": 50}])
        print(f"\n  Running {strat_id} ({len(params_grid)} param combos)...", end=" ", flush=True)
        t0 = time.time()

        try:
            result = run_strategy_wfa(strat_id, df, params_grid, XAUUSD_SPREAD_BPS)
            t1 = time.time()
            total_trades += result.get("oos_trades", 0)

            print(
                "OOS trades=%d sharpe=%.3f wr=%.1f%% pnl=$%.2f [%.1fs]" % (
                    result.get("oos_trades", 0),
                    result.get("oos_sharpe", 0),
                    result.get("oos_win_rate", 0),
                    result.get("oos_total_pnl", 0),
                    t1 - t0,
                )
            )

            # Store OOS trades for DK-test
            all_results[strat_id] = result

        except Exception as e:
            t1 = time.time()
            print("ERROR: %.1fs %s" % (t1 - t0, e))
            traceback.print_exc()
            all_results[strat_id] = {"strategy_id": strat_id, "error": str(e), "oos_sharpe": 0}

    # Build daily returns DataFrame across strategy variants
    # Each strategy's OOS trades → daily returns as a column
    # For DK-test: treat each strategy as a separate "asset"
    all_returns = pd.DataFrame()
    for strat_id, result in all_results.items():
        oos_trades = result.get("oos_trades_list", [])
        if not oos_trades:
            continue
        # Convert trades to daily returns
        daily_pnl = {}
        time_col = df["time"].values if "time" in df.columns else None
        for t in oos_trades:
            bar = t.get("exit_bar", 0)
            if 0 <= bar < len(df) and time_col is not None:
                day = pd.Timestamp(time_col[bar]).date()
            else:
                continue
            daily_pnl[day] = daily_pnl.get(day, 0.0) + t.get("net_pnl", 0.0)

        if daily_pnl:
            series = pd.Series(daily_pnl, name=strat_id)
            all_returns = pd.concat([all_returns, series], axis=1)

    # DK-test
    dk = dk_test_pooled(all_returns, total_trades)

    # Summary
    print("\n" + "=" * 70)
    print("  RESULTS — ranked by OOS Sharpe")
    print("=" * 70)
    print("  %-28s %7s %8s %8s %6s" % ("Strategy", "Trades", "DK-t", "Sharpe", "Verdict"))
    print("  " + "-" * 60)

    ranked = sorted(
        [(k, v) for k, v in all_results.items() if "error" not in v],
        key=lambda x: x[1].get("oos_sharpe", 0),
        reverse=True,
    )

    for name, r in ranked:
        print(
            "  %-28s %7d %8.3f %8.3f %6s" % (
                name,
                r.get("oos_trades", 0),
                dk.get("dk_t_stat", 0) if name == ranked[0][0] else 0,
                r.get("oos_sharpe", 0),
                "",
            )
        )

    print("\n  DK-test: dk_t=%.4f  pooled_sharpe=%.4f  pos=%d/%d" % (
        dk.get("dk_t_stat", 0),
        dk.get("pooled_sharpe", 0),
        dk.get("positive_sharpe_count", 0),
        dk.get("total_variants", 0),
    ))
    print("  VERDICT: %s" % dk.get("verdict", "?"))

    # Save
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "symbol": "XAUUSD",
        "timeframe": "D1",
        "cost_bps": XAUUSD_SPREAD_BPS,
        "go_rule": "dk_t>2.0 AND positive_sharpe_count>=5",
        "dk_test": dk,
        "ranked": [
            {
                "strategy": n,
                "oos_sharpe": r.get("oos_sharpe"),
                "oos_trades": r.get("oos_trades"),
                "oos_win_rate": r.get("oos_win_rate"),
                "oos_total_pnl": r.get("oos_total_pnl"),
            }
            for n, r in ranked
        ],
        "results": all_results,
        "honest_note": (
            "GO does not equal live-ready. Must still pass label-shuffle, "
            "cost-stress, and not burn sacred holdout until single pre-committed hypothesis."
        ),
    }

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)
    print("\n  Saved: %s" % out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
