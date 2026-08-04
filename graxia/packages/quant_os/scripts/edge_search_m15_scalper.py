#!/usr/bin/env python3
"""M15 Scalper Edge Search — EA-BENCH trials 1034/1035.

Benchmarks EA-style scalper strategies (HappyGoldScalper on XAUUSD, AsianScalper
on EURUSD/GBPUSD/USDJPY) against the SAME gate stack as trials 1028/1032/1033,
using the engine's MEASURED cost path (SymbolCostProfile from
config/cost_calibration.json — never pip constants) and M15 data.

Pre-registrations:
  research/pre_registration/trial_1034_happy_gold_scalper.md
  research/pre_registration/trial_1035_asian_scalper.md

FROZEN gates (identical to 1028/1032/1033 + SP2):
  primary:  pooled HAC t > 2.0 AND DSR p < 0.05 (N=1050)
  SP2 2-of-3: WFA mean OOS Sharpe > 0, Bootstrap CI lower > 0, MinBTL sufficient
  extra:    trades >= 30/asset, cost-stress 1.5x/2.0x Sharpe > 0,
            label-shuffle p <= 0.05, jackknife delta < 0.5
  NOTE: positive_sharpe_count >= 5 is REPORTED but NOT gated (4-asset benchmark
        universe makes it unreachable — documented deviation in pre-regs).

Engine wiring (all documented precedents):
  * BacktestConfig(spread_pips=None, slippage_pips=None, enable_swap=False,
    strict_mtf=False) — measured-cost lookup per symbol; swap disabled because
    calibration has no swap fields for the 4 core symbols (engine fail-closed
    otherwise, backtest/engine.py:1340-1345).
  * engine._symbol = symbol — thread real symbol (Bug #1 fix, edge_search_all).
  * engine._check_risk_halt = lambda: False — same as edge_search_all.py:469:
    the engine's "daily" halt uses _day_start_balance set ONCE at reset (no daily
    reset), i.e. it is a 0.5% CUMULATIVE-loss halt that would truncate every
    scalper run at the first losing streak. Kept consistent with the existing
    edge-search harness (this is a signal benchmark, not a risk-sim).
  * engine._pnl_tracker = None — classic equity path (edge_search_all.py:471).
  * Session exits via max_bars_open (TIME_STOP): 52 bars (13h London/NY) for
    HappyGoldScalper, 32 bars (8h Asian) for AsianScalper.
  * Stats on DAILY-AGGREGATED returns (ann 252) — M15 bar returns are
    autocorrelated; the pooled HAC/DSR/WFA gates all use daily series,
    matching the 1028/1032/1033 harness convention.
  * monthly_pct from timestamp SPAN (first/last bar), NOT bar count / 96.
  * Grid benchmark (--include-grid) is a SEPARATE section with its own cost
    model (FEE_RATE 0.1%/fill in strategies/grid_backtest.py) — flagged
    NOT cost-comparable with the engine-based scalper runs.

Usage:
  python scripts/edge_search_m15_scalper.py
  python scripts/edge_search_m15_scalper.py --assets XAUUSD,USDJPY,EURUSD,GBPUSD \
      --out reports/edge_search_m15_scalper_core4.json --include-grid
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
for p in (str(GRAXIA_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from graxia.packages.quant_os.backtest.dynamic_spread_model import SymbolCostProfile  # noqa: E402
from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine  # noqa: E402
from graxia.packages.quant_os.strategies.asian_scalper import AsianScalper  # noqa: E402
from graxia.packages.quant_os.strategies.grid_strategy import GridConfig  # noqa: E402
from graxia.packages.quant_os.strategies.grid_backtest import run_grid_backtest  # noqa: E402
from graxia.packages.quant_os.strategies.happy_gold_scalper import HappyGoldScalper  # noqa: E402

# Pre-registered universe (FROZEN — trials 1034/1035)
CORE_ASSETS = ["XAUUSD", "USDJPY", "EURUSD", "GBPUSD"]

# Per-lot commission (USD) — from cost_calibration.json commission_bps
COMMISSION_PER_LOT = {"XAUUSD": 0.0, "USDJPY": 7.0, "EURUSD": 7.0, "GBPUSD": 7.0}

# TIME_STOP session exit (M15 bars): HappyGold 08:00-21:00 = 13h = 52 bars;
# Asian 00:00-08:00 = 8h = 32 bars.
MAX_BARS_OPEN = {"XAUUSD": 52, "USDJPY": 32, "EURUSD": 32, "GBPUSD": 32}

INITIAL_CAPITAL = 10_000.0
RISK_PER_TRADE_BPS = 100  # 1% risk per trade (harness standard)
MIN_TRADES_PER_ASSET = 30
MIN_DAILY_OBS = 30
N_LABEL_SHUFFLES = 200
LABEL_SHUFFLE_SEED = 20260804

# Verified EA reference points (research/pre_registration/*, 2026-08-04)
EA_BENCHMARK_REFERENCES = {
    "happy_gold": {
        "source": "MyFxBook verified family (4 brokers, active)",
        "monthly_pct": "6.9-8.3",
        "max_dd_pct": "8-26",
        "profit_factor": "2.0-3.5",
    },
    "wallstreet_robot": {
        "source": "MyFxBook 10254966 (15+ yrs)",
        "win_pct": 76.0,
        "avg_win_pips": 8.3,
        "profit_factor": 1.37,
    },
}

# Grid baseline parameters (SAME as reports/edge_search_grid_20260721.json
# per-asset params, explicit GridConfig — avoids the edge_search_grid.py:80 bug)
GRID_PARAMS = {"grid_count": 10, "atr_multiplier": 2.0, "order_volume": 0.01, "atr_period": 14}


# ---------------------------------------------------------------------------
# Data loading (M15)
# ---------------------------------------------------------------------------
def load_m15(symbol: str) -> pd.DataFrame:
    path = ROOT / "data" / f"{symbol}_M15.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing {path}")
    df = pd.read_csv(path)
    ts_col = "time" if "time" in df.columns else "date"
    if ts_col not in df.columns:
        raise ValueError(f"{symbol}: no time/date column in {path.name}")
    df[ts_col] = pd.to_datetime(df[ts_col], utc=True)
    df = df.sort_values(ts_col).reset_index(drop=True)
    if len(df) < 500:
        raise ValueError(f"{symbol}: only {len(df)} bars (< 500)")
    return df


def preflight_costs(symbols: list[str]) -> None:
    """Fail fast: every asset MUST have a measured, usable cost profile."""
    for sym in symbols:
        profile = SymbolCostProfile.for_symbol(sym)  # raises UnmeasuredCostError
        print(f"  [preflight] {sym}: status={profile.status} "
              f"spread_bps={profile.spread_bps} p95={profile.spread_bps_p95}")


# ---------------------------------------------------------------------------
# Per-asset backtest
# ---------------------------------------------------------------------------
def strategy_for(symbol: str):
    if symbol == "XAUUSD":
        return HappyGoldScalper()
    return AsianScalper()


def _worker_asset(symbol: str) -> dict:
    """Module-level worker for ProcessPoolExecutor (Windows spawn-safe).

    Builds its own engine inside the worker so no unpicklable state
    (lambdas, engine instances) crosses the process boundary.
    """
    return run_asset_engine(symbol)


def run_all_assets(assets: list[str], parallel: bool = True) -> list[dict]:
    """Run all assets; parallel via ProcessPoolExecutor when possible.

    Each asset is independent (single-TF engine, no shared state), and the
    engine main loop is O(bars^2) in slicing — parallel is the honest way to
    keep the FULL M15 history without touching the engine.
    """
    if not parallel or len(assets) <= 1:
        return [run_asset_engine(s) for s in assets]
    try:
        from concurrent.futures import ProcessPoolExecutor

        with ProcessPoolExecutor(max_workers=min(len(assets), 4)) as pool:
            return list(pool.map(_worker_asset, assets))
    except Exception as e:  # noqa: BLE001 — fall back to serial on spawn issues
        print(f"  [warn] parallel run failed ({e}); falling back to serial")
        return [run_asset_engine(s) for s in assets]


def run_asset_engine(symbol: str) -> dict:
    """Run one asset through the engine with the measured-cost path."""
    df = load_m15(symbol)
    ohlcv = {
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
        "volume": df["volume"].tolist() if "volume" in df.columns else [0.0] * len(df),
    }
    timestamps = df["time"].tolist()

    config = BacktestConfig(
        initial_capital=INITIAL_CAPITAL,
        slippage_pips=None,  # measured path
        spread_pips=None,  # measured path
        commission_per_lot=COMMISSION_PER_LOT.get(symbol, 0.0),
        risk_per_trade_bps=RISK_PER_TRADE_BPS,
        max_positions=1,  # no martingale / no pyramiding
        strict_mtf=False,  # single-TF M15 run
        enable_swap=False,  # no swap fields for core 4 (fail-closed otherwise)
        max_bars_open=MAX_BARS_OPEN[symbol],  # TIME_STOP session exit
    )

    engine = BacktestEngine(config)
    engine._symbol = symbol
    engine.set_strategy(strategy_for(symbol))
    engine.load_data(ohlcv, timestamps)
    # Documented harness precedent (edge_search_all.py:469): engine "daily"
    # halt is cumulative 0.5% (no daily reset of _day_start_balance).
    engine._check_risk_halt = lambda: False  # type: ignore[method-assign]
    engine._pnl_tracker = None  # classic equity path
    # Our strategies compute indicators internally on a trailing window;
    # skipping the engine's per-bar precomputed-indicator slicing keeps the
    # O(bars^2) engine loop tractable on 50-60k M15 bars (identical results —
    # verified trades=895 both ways on USDJPY).
    engine._precomputed_indicators = {}

    result = engine.run()

    trades = result.get("trades", [])
    equity_points = result.get("equity_curve", [])
    return {
        "symbol": symbol,
        "strategy": strategy_for(symbol).id,
        "n_bars": len(ohlcv["close"]),
        "first_bar": timestamps[0].isoformat(),
        "last_bar": timestamps[-1].isoformat(),
        "trades": trades,
        "equity_curve": equity_points,
        "metrics_raw": result.get("metrics", {}),
    }


# ---------------------------------------------------------------------------
# Metrics (daily-aggregated; monthly from timestamp SPAN)
# ---------------------------------------------------------------------------
def daily_returns_from_equity(equity_points: list[dict], first_bar: str) -> pd.Series:
    """Aggregate per-bar equity to daily returns (last equity of each UTC day)."""
    if not equity_points:
        return pd.Series(dtype=float)
    df = pd.DataFrame(
        [
            {"ts": pd.Timestamp(p["timestamp"], tz="UTC"), "eq": float(p["equity"])}
            for p in equity_points
        ]
    )
    df["day"] = df["ts"].dt.date
    daily = df.groupby("day")["eq"].last().sort_index()
    rets = daily.pct_change().dropna()
    return rets


def compute_asset_metrics(asset_result: dict) -> dict:
    """Per-asset metrics. Sharpe/DSR inputs are DAILY returns (ann 252)."""
    trades = asset_result["trades"]
    eq = asset_result["equity_curve"]

    daily_ret = daily_returns_from_equity(eq, asset_result["first_bar"])
    n_days = len(daily_ret)
    mu = float(daily_ret.mean()) if n_days else 0.0
    sd = float(daily_ret.std(ddof=1)) if n_days > 1 else 0.0
    sharpe = mu / (sd + 1e-10) * math.sqrt(252) if n_days else 0.0

    equity_vals = [float(p["equity"]) for p in eq] if eq else [INITIAL_CAPITAL]
    peak = equity_vals[0]
    max_dd = 0.0
    for v in equity_vals:
        if v > peak:
            peak = v
        dd = (peak - v) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    wins = [t for t in trades if float(t["pnl"]) > 0]
    losses = [t for t in trades if float(t["pnl"]) <= 0]
    total_profit = sum(float(t["pnl"]) for t in wins)
    total_loss = abs(sum(float(t["pnl"]) for t in losses))
    pf = total_profit / total_loss if total_loss > 0 else (999.0 if total_profit > 0 else 0.0)

    total_pnl = sum(float(t["pnl"]) for t in trades)
    total_return_pct = (equity_vals[-1] / equity_vals[0] - 1) * 100 if equity_vals else 0.0

    # monthly_pct from timestamp SPAN (first/last bar) — NOT bar count / 96
    t0 = pd.Timestamp(asset_result["first_bar"], tz="UTC")
    t1 = pd.Timestamp(asset_result["last_bar"], tz="UTC")
    span_days = max((t1 - t0).days, 1)
    span_months = span_days / 30.44
    monthly_pct = total_return_pct / span_months

    # Avg hold duration from trades
    avg_hold_hours = 0.0
    if trades:
        holds = []
        for t in trades:
            try:
                holds.append(
                    (pd.Timestamp(t["exit_time"], tz="UTC") - pd.Timestamp(t["entry_time"], tz="UTC")).total_seconds() / 3600.0
                )
            except Exception:
                pass
        avg_hold_hours = float(np.mean(holds)) if holds else 0.0

    return {
        "n_trades": len(trades),
        "n_days": int(n_days),
        "sharpe_daily": round(sharpe, 4),
        "win_pct": round(len(wins) / len(trades) * 100, 2) if trades else 0.0,
        "profit_factor": round(pf, 4) if pf < 100 else 99.99,
        "max_dd_pct": round(max_dd * 100, 2),
        "total_return_pct": round(total_return_pct, 2),
        "total_pnl": round(total_pnl, 2),
        "monthly_pct": round(monthly_pct, 3),
        "avg_hold_hours": round(avg_hold_hours, 2),
        "trades_pass": len(trades) >= MIN_TRADES_PER_ASSET,
    }


# ---------------------------------------------------------------------------
# Pooled + DSR + SP2 gates + jackknife + label shuffle + cost stress
# ---------------------------------------------------------------------------
def build_daily_panel(asset_results: list[dict]) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Daily returns aligned per asset (date index, one column per asset)."""
    series = {}
    for ar in asset_results:
        r = daily_returns_from_equity(ar["equity_curve"], ar["first_bar"])
        r.index = pd.to_datetime(r.index)
        series[ar["symbol"]] = r
    panel = pd.DataFrame(series)
    return panel, series


def jackknife_sharpe(returns_by_symbol: dict[str, pd.Series]) -> dict:
    full = pd.concat(returns_by_symbol.values(), axis=1).mean(axis=1)
    full_sharpe = float(full.mean()) / (float(full.std(ddof=1)) + 1e-10) * math.sqrt(252)
    out = {"full_sharpe": round(full_sharpe, 4)}
    for sym, r in returns_by_symbol.items():
        remaining = {k: v for k, v in returns_by_symbol.items() if k != sym}
        if remaining:
            jack = pd.concat(remaining.values(), axis=1).mean(axis=1)
            js = float(jack.mean()) / (float(jack.std(ddof=1)) + 1e-10) * math.sqrt(252)
            out[f"drop_{sym}"] = round(js, 4)
            out[f"delta_{sym}"] = round(abs(full_sharpe - js), 4)
    return out


def label_shuffle(returns_by_symbol: dict[str, pd.Series]) -> dict:
    cs = pd.concat(returns_by_symbol.values(), axis=1).mean(axis=1).dropna()
    if len(cs) < MIN_DAILY_OBS:
        return {"n_shuffles": 0, "p_value": 1.0, "verdict": "INSUFFICIENT_DATA"}
    obs = float(cs.mean()) / (float(cs.std(ddof=1)) + 1e-10) * math.sqrt(252)
    rng = np.random.default_rng(LABEL_SHUFFLE_SEED)
    count = 0
    for _ in range(N_LABEL_SHUFFLES):
        s = cs * rng.choice([-1.0, 1.0], size=len(cs))
        sh = float(s.mean()) / (float(s.std(ddof=1)) + 1e-10) * math.sqrt(252)
        if sh >= obs:
            count += 1
    p = count / N_LABEL_SHUFFLES
    return {"n_shuffles": N_LABEL_SHUFFLES, "p_value": round(p, 4), "verdict": "PASS" if p <= 0.05 else "FAIL"}


def cost_stress(asset_results: list[dict]) -> dict:
    """Rebuild daily Sharpe under 1.5x / 2.0x TOTAL trade costs.

    Stressed pnl per trade = pnl - (costs * (mult-1)), where costs =
    entry_spread + entry_slippage + exit_slippage + fees (all recorded by the
    engine). Equity reconstructed as capital + cumulative realized pnl
    (max_positions=1 scalper path — no overlap), aggregated to daily returns.
    Documented approximation: unrealized MTM between trades is not modelled.
    """
    out = {}
    for mult in (1.5, 2.0):
        sharpes = []
        for ar in asset_results:
            trades = ar["trades"]
            if not trades:
                continue
            t0 = pd.Timestamp(ar["first_bar"], tz="UTC")
            entries = []
            for t in trades:
                cost = (
                    float(t.get("entry_spread_cost", 0))
                    + float(t.get("entry_slippage_cost", 0))
                    + float(t.get("exit_slippage_cost", 0))
                    + float(t.get("fees", 0))
                )
                pnl_stressed = float(t["pnl"]) - cost * (mult - 1.0)
                entries.append((pd.Timestamp(t["exit_time"], tz="UTC"), pnl_stressed))
            if not entries:
                continue
            srt = sorted(entries, key=lambda x: x[0])
            eq = INITIAL_CAPITAL
            points = []
            for ts, pnl in srt:
                eq += pnl
                points.append((ts, eq))
            df = pd.DataFrame(points, columns=["ts", "eq"])
            df["day"] = df["ts"].dt.date
            daily = df.groupby("day")["eq"].last()
            rets = daily.pct_change().dropna()
            if len(rets) < MIN_DAILY_OBS:
                continue
            sd = float(rets.std(ddof=1))
            mu = float(rets.mean())
            sharpe = mu / (sd + 1e-10) * math.sqrt(252)
            sharpes.append(round(sharpe, 4))
        if sharpes:
            out[f"{mult}x"] = {
                "per_asset": sharpes,
                "mean": round(float(np.mean(sharpes)), 4),
                "pass": float(np.mean(sharpes)) > 0,
            }
        else:
            out[f"{mult}x"] = {"per_asset": [], "mean": 0.0, "pass": False, "reason": "insufficient trades"}
    return out


def run_grid_benchmark(symbols: list[str]) -> dict:
    """Grid run on M15 with FROZEN baseline params — SEPARATE cost model.

    strategies/grid_backtest.py charges FEE_RATE=0.1% per fill, NOT the
    measured engine costs. Results are reported in their own section and are
    NOT cost-comparable with the engine scalper runs.
    """
    out = {}
    for sym in symbols:
        try:
            df = load_m15(sym)
            ohlcv = {
                "open": df["open"].tolist(),
                "high": df["high"].tolist(),
                "low": df["low"].tolist(),
                "close": df["close"].tolist(),
                "volume": df["volume"].tolist() if "volume" in df.columns else [0] * len(df),
            }
            cfg = GridConfig(
                symbol=sym,
                range_method="atr",
                atr_period=GRID_PARAMS["atr_period"],
                atr_multiplier=GRID_PARAMS["atr_multiplier"],
                grid_count=GRID_PARAMS["grid_count"],
                order_volume=GRID_PARAMS["order_volume"],
            )
            res = run_grid_backtest(cfg, ohlcv)
            eq = res.get("equity_curve", [])
            rets = pd.Series(eq).pct_change().dropna()
            sharpe = float(rets.mean()) / (float(rets.std(ddof=1)) + 1e-10) * math.sqrt(252) if len(rets) > 1 else 0.0
            out[sym] = {
                "grid_fills": res.get("grid_fills", 0),
                "total_pnl": res.get("total_pnl", 0),
                "max_dd_pct": round(res.get("max_drawdown", 0) * 100, 2),
                "return_pct": res.get("return_pct", 0),
                "sharpe_bar": round(sharpe, 4),
                "cost_model": "FEE_RATE=0.1%/fill (NOT engine measured-cost — not comparable)",
            }
        except Exception as e:  # noqa: BLE001 — grid is auxiliary; record, don't crash
            out[sym] = {"error": str(e)}
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="M15 scalper benchmark (EA-BENCH 1034/1035)")
    parser.add_argument("--assets", default=",".join(CORE_ASSETS))
    parser.add_argument("--out", default="reports/edge_search_m15_scalper_core4.json")
    parser.add_argument("--include-grid", action="store_true", default=False,
                        help="run grid benchmark section (separate cost model)")
    parser.add_argument("--label-shuffle", type=int, default=N_LABEL_SHUFFLES)
    args = parser.parse_args()

    assets = args.assets.split(",")
    print("=" * 64)
    print("M15 Scalper Edge Search — EA-BENCH trials 1034/1035")
    print("=" * 64)

    # ── Preflight: measured costs fail-fast ──────────────────────────
    print("\n[1/5] Preflight cost calibration (fail-fast):")
    try:
        preflight_costs(assets)
    except Exception as e:
        print(f"  FAIL: {e}")
        return 1

    # ── Per-asset engine runs ────────────────────────────────────────
    print("\n[2/5] Engine backtests (measured costs, swap off, parallel):")
    asset_results = []
    try:
        for ar in run_all_assets(assets, parallel=True):
            asset_results.append(ar)
            sym = ar["symbol"]
            m = compute_asset_metrics(ar)
            print(f"  {sym}: {m['n_trades']} trades, sharpe={m['sharpe_daily']}, "
                  f"win={m['win_pct']}%, PF={m['profit_factor']}, "
                  f"monthly={m['monthly_pct']}%, maxDD={m['max_dd_pct']}%")
    except Exception as e:
        print(f"  FAILED — {e}")
        return 1

    per_asset = {ar["symbol"]: compute_asset_metrics(ar) for ar in asset_results}

    # ── Pooled HAC + DSR + SP2 gates ─────────────────────────────────
    print("\n[3/5] Pooled gates (daily returns, ann 252):")
    panel, series = build_daily_panel(asset_results)

    from graxia.packages.quant_os.scripts.edge_search_all import run_pooled_hac_test
    from graxia.packages.quant_os.validation.deflated_sharpe import dsr_from_annualized
    from graxia.packages.quant_os.validation.n_trials import get_reconciled_n_trials

    n_trials = get_reconciled_n_trials()
    total_trades = sum(len(ar["trades"]) for ar in asset_results)
    pooled = run_pooled_hac_test(panel, total_trades=total_trades, n_trials=n_trials)
    dk_t = float(pooled["dk_t_stat"])
    print(f"  pooled HAC t: {dk_t:.3f} (GO threshold 2.0)")

    portfolio = panel.mean(axis=1).dropna()
    port_mu = float(portfolio.mean())
    port_sd = float(portfolio.std(ddof=1))
    port_sharpe = port_mu / (port_sd + 1e-10) * math.sqrt(252) if len(portfolio) > 1 else 0.0
    dsr = dsr_from_annualized(
        observed_sharpe=port_sharpe,
        n_trials=n_trials,
        n_observations=len(portfolio),
        annualization_factor=252,
        skewness=float(portfolio.skew()),
        kurtosis=float(portfolio.kurtosis()) + 3.0,  # pandas returns EXCESS
    )
    print(f"  DSR: p={dsr.probability_alpha:.4f} observed_SR={port_sharpe:.3f} "
          f"pass={dsr.passes_threshold} (N={n_trials})")

    # SP2 institutional gates
    from graxia.packages.quant_os.scripts._trial_gates import run_institutional_gates

    gates = run_institutional_gates(
        portfolio_returns=portfolio,
        returns_by_symbol=series,
        observed_sharpe=port_sharpe,
        n_trials=n_trials,
        n_bars=len(portfolio),
        annualization_factor=252,
    )
    print(f"  WFA: {gates['wfa']['oos_sharpe_mean']:.3f} pass={gates['wfa']['pass']}")
    print(f"  Bootstrap CI: [{gates['bootstrap_ci']['lower']:.4f}, {gates['bootstrap_ci']['upper']:.4f}] pass={gates['bootstrap_ci']['pass']}")
    print(f"  MinBTL: min={gates['min_btl']['min_observations']} sufficient={gates['min_btl']['sufficient']}")

    # ── Jackknife + label shuffle + cost stress ──────────────────────
    print("\n[4/5] Robustness:")
    jk = jackknife_sharpe(series)
    ls = label_shuffle(series)
    stress = cost_stress(asset_results)
    print(f"  jackknife deltas: { {k: v for k, v in jk.items() if k.startswith('delta_')} }")
    print(f"  label-shuffle p={ls['p_value']} ({ls['verdict']})")
    for k, v in stress.items():
        print(f"  cost-stress {k}: mean={v['mean']} pass={v['pass']}")

    # ── Verdict (frozen gates) ───────────────────────────────────────
    dk_pass = dk_t > 2.0
    dsr_pass = bool(dsr.passes_threshold)
    sp2_passes = sum(
        1 for g in (gates["wfa"]["pass"], gates["bootstrap_ci"]["pass"], gates["min_btl"]["pass"])
    )
    sp2_pass = sp2_passes >= 2
    trades_pass = all(per_asset[s]["trades_pass"] for s in assets)
    stress_pass = all(v.get("pass", False) for v in stress.values())
    ls_pass = ls["verdict"] == "PASS"
    jk_pass = all(v < 0.5 for k, v in jk.items() if k.startswith("delta_"))
    pos_count = int(pooled.get("positive_sharpe_count", 0))

    gates_summary = {
        "pooled_t_gt_2": bool(dk_pass),
        "dsr_p_lt_0.05": dsr_pass,
        "sp2_2_of_3": sp2_pass,
        "trades_ge_30_per_asset": trades_pass,
        "cost_stress_15_2x": stress_pass,
        "label_shuffle_p_le_0.05": ls_pass,
        "jackknife_delta_lt_0.5": jk_pass,
        "positive_sharpe_count": pos_count,
        "positive_sharpe_ge_5": pos_count >= 5,  # REPORTED ONLY — unreachable at 4 assets
    }
    primary = dk_pass and dsr_pass
    combined_verdict = "PASS" if (primary and sp2_pass and trades_pass and stress_pass and ls_pass and jk_pass) else "REJECT"

    print("\n[5/5] GATE SUMMARY (frozen pre-registration):")
    for k, v in gates_summary.items():
        print(f"  {k}: {v}")
    print(f"  -> PRIMARY (t>2.0 AND DSR p<0.05): {'PASS' if primary else 'FAIL'}")
    print(f"  -> COMBINED VERDICT: {combined_verdict}")

    # ── Benchmark table vs verified EAs ──────────────────────────────
    benchmark_table = {
        "scalpers_measured": per_asset,
        "portfolio": {
            "pooled_t": round(dk_t, 4),
            "portfolio_sharpe_daily": round(port_sharpe, 4),
            "total_trades": total_trades,
            "monthly_pct_mean": round(float(np.mean([m["monthly_pct"] for m in per_asset.values()])), 3),
        },
        "verified_ea_references": EA_BENCHMARK_REFERENCES,
        "note": "EA references are MyFxBook-verified track records (not directly "
                "comparable — different period/leverage/execution; shown for context).",
    }

    artifact = {
        "title": "M15 Scalper Benchmark — EA-BENCH trials 1034/1035",
        "registered_at": "2026-08-04",
        "executed_at": datetime.now(UTC).isoformat(),
        "trials": [1034, 1035],
        "universe": assets,
        "config": {
            "engine": "BacktestEngine (measured-cost path, SymbolCostProfile)",
            "spread_pips": None,
            "slippage_pips": None,
            "enable_swap": False,
            "strict_mtf": False,
            "max_positions": 1,
            "max_bars_open": MAX_BARS_OPEN,
            "commission_per_lot": COMMISSION_PER_LOT,
            "risk_per_trade_bps": RISK_PER_TRADE_BPS,
            "initial_capital": INITIAL_CAPITAL,
            "annualization": "daily returns, 252",
            "risk_halt": "disabled (edge_search_all.py:469 precedent — engine halt is cumulative 0.5%, no daily reset)",
        },
        "per_asset": per_asset,
        "pooled": {
            "test_name": pooled.get("test_name", "pooled_hac_t_test"),
            "dk_t_stat": dk_t,
            "pooled_sharpe": pooled.get("pooled_sharpe"),
            "positive_sharpe_count": pos_count,
            "total_days": pooled.get("total_days"),
            "total_trades": total_trades,
            "n_trials_effective": pooled.get("n_trials_effective"),
            "verdict_pooled_func": pooled.get("verdict"),
        },
        "dsr": {
            "observed_sharpe": round(port_sharpe, 4),
            "probability_alpha": round(float(dsr.probability_alpha), 6),
            "passes_threshold": dsr_pass,
            "n_trials": n_trials,
            "n_observations": len(portfolio),
        },
        "institutional_gates": gates,
        "jackknife": jk,
        "label_shuffle": ls,
        "cost_stress": stress,
        "gates": gates_summary,
        "combined_verdict": combined_verdict,
        "benchmark_table": benchmark_table,
        "bollinger_squeeze_note": "Existing BollingerSqueeze is D1-only (strategies/bollinger_squeeze.py:38) — D1 edge-search verdicts REJECTED (edge_search_gold_ict_results.json). Not re-run at M15: not part of trials 1034/1035.",
    }

    if args.include_grid:
        print("\nGrid benchmark (SEPARATE cost model — not cost-comparable):")
        artifact["grid_benchmark"] = run_grid_benchmark(assets)
        for sym, g in artifact["grid_benchmark"].items():
            print(f"  {sym}: fills={g.get('grid_fills')} maxDD={g.get('max_dd_pct')}% return={g.get('return_pct')}%")

    out = ROOT / args.out
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    print(f"\nArtifact written: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
