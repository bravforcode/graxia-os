"""Direction H Trial 9004 — final mechanism arms on USDCAD/USDCHF.

Frozen per research/pre_registration/trial_9004_final_arms.md (2026-08-06):
arms = Momentum12M, TSMDXYDivergence (DXY injected). Engine measured-cost path,
trailing-window subclass, true costs. Incremental per-(arm,symbol) merge.

Usage:
    python scripts/edge_search_dirh_9004.py --arm <name> --symbol <SYM>
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
OUT_PATH = ROOT / "reports" / "edge_search_dirh_9004.json"


def load_h1(symbol: str) -> pd.DataFrame:
    path = ROOT / "data" / f"{symbol}_H1.csv"
    df = pd.read_csv(path)
    ts = "time" if "time" in df.columns else "date"
    df[ts] = pd.to_datetime(df[ts], utc=True)
    return df.sort_values(ts).reset_index(drop=True)


def trailing_wrap(strategy):
    class _Wrapped(strategy.__class__):
        _WINDOW = 300

        def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
            sliced = {k: (v[-self._WINDOW:] if isinstance(v, list) else v) for k, v in ohlcv_data.items()}
            return super().generate_signal(symbol, sliced, indicators, regime, **kwargs)

    wrapped = _Wrapped.__new__(_Wrapped)
    wrapped.__dict__.update(strategy.__dict__)
    return wrapped


def build_arm(name: str, symbol: str):
    if name == "momentum_12m":
        from graxia.packages.quant_os.strategies.momentum_12m import Momentum12M

        return Momentum12M()
    if name == "tsm_dxy":
        from graxia.packages.quant_os.strategies.tsm_dxy_divergence import TSMDXYDivergence

        return TSMDXYDivergence(dxy_csv_path=str(ROOT / "data" / "DXY_D1.csv"))
    raise ValueError(f"unknown arm {name}")


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


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", required=True)
    parser.add_argument("--symbol", required=True)
    parser.add_argument("--out", default=str(OUT_PATH))
    args = parser.parse_args()

    print(f"[{args.arm} {args.symbol}]", end=" ", flush=True)
    result = {}
    try:
        strat = build_arm(args.arm, args.symbol)
        res = run_engine(args.symbol, strat)
        trades = res.get("trades", [])
        pnls = []
        for t in trades:
            try:
                pnl = float(getattr(t, "pnl", t.get("pnl", 0)) if not isinstance(t, dict) else t.get("pnl", 0))
                pnls.append(pnl)
            except Exception:  # noqa: BLE001
                continue
        arr = np.array(pnls) / 10000.0 if len(pnls) >= 20 else np.array([])
        if len(arr) < 20:
            result = {"n_trades": len(pnls), "verdict": "INSUFFICIENT"}
            print(f"INSUFFICIENT (trades={len(pnls)})")
        else:
            dk_t, dk_mean, _ = driscoll_kraay_t(arr)
            sharpe = float(arr.mean()) / (float(arr.std(ddof=1)) + 1e-10) * math.sqrt(252)
            verdict = "GO" if (dk_t > 2.0 and sharpe > 0) else ("MARGINAL" if dk_t > 1.5 else "REJECT")
            result = {"n_trades": len(pnls), "dk_t": round(dk_t, 4), "sharpe": round(sharpe, 4), "verdict": verdict}
            print(f"trades={len(pnls)} dk_t={dk_t:.3f} sharpe={sharpe:.3f} -> {verdict}")
    except Exception as e:  # noqa: BLE001
        result = {"error": str(e)[:200]}
        print(f"ERROR {e}")

    out_path = Path(args.out)
    data = None
    if out_path.exists():
        try:
            data = json.loads(out_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            data = None
    if data is None:
        data = {"title": "Direction H Trial 9004 — final arms", "executed_at": datetime.now(UTC).isoformat(),
                "symbols": SYMBOLS, "arms": {}}
    data["arms"].setdefault(args.arm, {})[args.symbol] = result
    data["executed_at"] = datetime.now(UTC).isoformat()
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
