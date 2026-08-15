"""Direction H Trial 9003 — mechanism sweep on USDCAD/USDCHF (H1, measured costs).

Frozen per research/pre_registration/trial_9003_mech_sweep.md (2026-08-06):
arms = HybridMomMR, VolumeBreakout, MultiTimeframeMomentum, MeanReversionBollinger,
LiquiditySweepV2, SessionPattern(SPConfig). Engine measured-cost path
(commission_per_lot=$7/lot, slippage via SymbolCostProfile), trailing-window
subclass for O(n) indicators.

Usage:
    python scripts/edge_search_dirh_mech_sweep.py
"""
from __future__ import annotations

import json
import math
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
for p in (str(GRAXIA_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

SYMBOLS = ["USDCAD", "USDCHF"]
OUT_PATH = ROOT / "reports" / "edge_search_dirh_mech_sweep_9003.json"


def load_h1(symbol: str) -> pd.DataFrame:
    path = ROOT / "data" / f"{symbol}_H1.csv"
    df = pd.read_csv(path)
    ts = "time" if "time" in df.columns else "date"
    df[ts] = pd.to_datetime(df[ts], utc=True)
    return df.sort_values(ts).reset_index(drop=True)


def build_arm(name: str):
    from graxia.packages.quant_os.strategies.hybrid_mom_mr import HybridMomMR
    from graxia.packages.quant_os.strategies.volume_breakout import VolumeBreakout
    from graxia.packages.quant_os.strategies.mtm import MultiTimeframeMomentum
    from graxia.packages.quant_os.strategies.mrb import MeanReversionBollinger
    from graxia.packages.quant_os.strategies.liquidity_sweep_v2 import LiquiditySweepV2

    arms = {
        "hybrid_mom_mr": HybridMomMR,
        "volume_breakout": VolumeBreakout,
        "mtm": MultiTimeframeMomentum,
        "mrb": MeanReversionBollinger,
        "liquidity_sweep_v2": LiquiditySweepV2,
    }
    cls = arms.get(name)
    if cls is None:
        raise ValueError(f"unknown arm {name}")
    try:
        return cls()
    except TypeError:
        return cls(**{})


def trailing_wrap(strategy):
    """Wrap generate_signal with a trailing window (O(n) indicators, no lookahead)."""
    from graxia.packages.quant_os.strategies.base import Strategy

    class _Wrapped(strategy.__class__):
        _WINDOW = 100

        def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
            sliced = {k: (v[-self._WINDOW:] if isinstance(v, list) else v) for k, v in ohlcv_data.items()}
            return super().generate_signal(symbol, sliced, indicators, regime, **kwargs)

    wrapped = _Wrapped.__new__(_Wrapped)
    wrapped.__dict__.update(strategy.__dict__)
    wrapped.__class__ = _Wrapped
    return wrapped


def run_engine(symbol: str, strategy) -> dict:
    from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine

    df = load_h1(symbol)
    ohlcv = {k: df[k].tolist() for k in ["open", "high", "low", "close"]}
    ohlcv["volume"] = df["volume"].tolist() if "volume" in df.columns else [0.0] * len(df)

    config = BacktestConfig(
        initial_capital=Decimal("10000"),
        slippage_pips=None,
        spread_pips=None,
        commission_per_lot=Decimal("7.0"),
        risk_per_trade_bps=50,
        max_positions=1,
        strict_mtf=False,
        enable_swap=False,
    )
    engine = BacktestEngine(config)
    engine._symbol = symbol
    engine.set_strategy(trailing_wrap(strategy))
    engine.load_data(ohlcv, df["time"].tolist())
    engine._check_risk_halt = lambda: False
    engine._pnl_tracker = None
    engine._precomputed_indicators = {}
    result = engine.run()
    result["_symbol"] = symbol
    # engine.equity_curve is authoritative; result dict may omit it at scale
    if not result.get("equity_curve"):
        result["equity_curve"] = [
            {"equity": float(p.equity), "timestamp": str(p.timestamp)}
            for p in getattr(engine, "equity_curve", [])
        ]
    return result


def driscoll_kraay_t(daily_means: np.ndarray) -> tuple[float, float, float]:
    n = len(daily_means)
    if n < 20:
        return 0.0, 0.0, 0.0
    mu = daily_means.mean()
    bandwidth = max(int(4 * (n / 100) ** (2 / 9)), 1)
    gamma_0 = float(np.mean((daily_means - mu) ** 2))
    nw_var = gamma_0
    for k in range(1, bandwidth + 1):
        weight = 1 - k / (bandwidth + 1)
        gamma_k = float(np.mean((daily_means[k:] - mu) * (daily_means[:-k] - mu)))
        nw_var += 2 * weight * gamma_k
    nw_se = math.sqrt(nw_var / n)
    return mu / (nw_se + 1e-10), mu, nw_se


def daily_returns_from_equity(res: dict) -> np.ndarray:
    """Compute per-trade PnL series (engine stores no equity curve in this path)."""
    trades = res.get("trades", [])
    pnls = []
    for t in trades:
        try:
            pnl = float(getattr(t, "pnl", t.get("pnl", 0)) if not isinstance(t, dict) else t.get("pnl", 0))
            pnls.append(pnl)
        except Exception:  # noqa: BLE001
            continue
    arr = np.array(pnls) if len(pnls) >= 20 else np.array([])
    if len(arr) < 20:
        return arr
    # normalize to per-trade returns on $10k capital
    return arr / 10000.0


def run_session_pattern(symbol: str) -> dict:
    """Session Pattern via compute_sp_signals (function-based, not a Strategy)."""
    from graxia.packages.quant_os.strategies.session_pattern import SPConfig, compute_sp_signals

    df = load_h1(symbol)
    ts = "time" if "time" in df.columns else "date"
    df = df.set_index(pd.DatetimeIndex(pd.to_datetime(df[ts], utc=True)))
    res = compute_sp_signals(
        close=df["close"],
        highs=df["high"],
        lows=df["low"],
        timestamps=df.index,
        config=SPConfig(),
    )
    signals = res.signal  # -1/0/+1 per bar
    prices = df["close"].to_numpy()
    n = len(prices)
    pos = 0.0
    cash = 10000.0
    eqs = []
    for i in range(1, n):
        sig = 0.0
        try:
            sig = float(signals.iloc[i])
        except (ValueError, TypeError, IndexError):
            sig = 0.0
        if sig != 0 and pos == 0:
            pos = 1.0 if sig > 0 else -1.0
        elif sig == 0 and pos != 0:
            pos = 0.0
        eqs.append(cash + pos * (prices[i] - prices[i - 1]) * 100000.0 * 0.0001)
    arr = np.array(eqs) if len(eqs) >= 20 else np.array([])
    if len(arr) < 20:
        return {"n_trades": 0, "daily_returns": arr, "error": "insufficient equity"}
    rets = np.diff(arr) / np.abs(arr[:-1] + 1e-9)
    n_signals = int((signals != 0).sum()) if hasattr(signals, "sum") else 0
    return {"n_trades": n_signals, "daily_returns": rets}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True, help="arm name")
    parser.add_argument("--symbol", required=True, help="symbol")
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    arm, symbol = args.arm, args.symbol
    print(f"[{arm} {symbol}]", end=" ", flush=True)
    result = {}
    try:
        if arm == "session_pattern":
            r = run_session_pattern(symbol)
        else:
            strat = build_arm(arm)
            res = run_engine(symbol, strat)
            r = {"n_trades": len(res.get("trades", [])), "daily_returns": daily_returns_from_equity(res)}
        n = len(r["daily_returns"])
        if n < 20:
            result = {"n_trades": r.get("n_trades", 0), "verdict": "INSUFFICIENT", "n_days": n}
            print("INSUFFICIENT")
        else:
            dk_t, dk_mean, _ = driscoll_kraay_t(r["daily_returns"])
            sharpe = float(r["daily_returns"].mean()) / (float(r["daily_returns"].std(ddof=1)) + 1e-10) * math.sqrt(252)
            # MARGINAL requires REAL signal (dk_t > 1.5); sharpe>0 alone is noise
            # (dk_t≈0.004 with sharpe 0.0001 is flat — not an edge)
            verdict = "GO" if (dk_t > 2.0 and sharpe > 0) else ("MARGINAL" if dk_t > 1.5 else "REJECT")
            result = {
                "n_trades": r.get("n_trades", 0),
                "dk_t": round(dk_t, 4),
                "sharpe": round(sharpe, 4),
                "verdict": verdict,
            }
            print(f"trades={r.get('n_trades')} dk_t={dk_t:.3f} sharpe={sharpe:.3f} -> {verdict}")
    except Exception as e:  # noqa: BLE001
        result = {"error": str(e)[:200]}
        print(f"ERROR {e}")

    # Incremental merge into OUT_PATH
    out_path = Path(args.out)
    data = None
    if out_path.exists():
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = None  # corrupt/partial file — rebuild from scratch
    if data is None:
        data = {"title": "Direction H Trial 9003 — mechanism sweep USDCAD/USDCHF",
                "executed_at": datetime.now(UTC).isoformat(), "symbols": SYMBOLS, "arms": {}}
    data["arms"].setdefault(arm, {})[symbol] = result
    data["executed_at"] = datetime.now(UTC).isoformat()

    # Trial verdict: any GO -> PROMOTE; any MARGINAL -> CONDITIONAL; else REJECT
    best = "REJECT"
    for a, syms in data["arms"].items():
        for s, r in syms.items():
            v = r.get("verdict", "")
            if v == "GO":
                best = "PROMOTE"
            elif v == "MARGINAL" and best != "PROMOTE":
                best = "CONDITIONAL"
    data["verdict"] = best
    out_path.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    print(f"merged -> {out_path} (trial verdict: {best})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
