"""
H1 edge scan — single-asset, cost-aware, honest ranking.
Does NOT burn sacred holdout. GO only if trade-Sharpe > 1.0 AND PF > 1.2 AND n_trades >= 100.
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

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
for p in (str(GRAXIA_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

# H1 spreads (same scale as D1 pooled tests — engine multiplies by tick_size)
SPREADS = {
    "XAUUSD": 100.0,
    "EURUSD": 1.2,
    "GBPUSD": 1.5,
    "USDJPY": 1.2,
    "NAS100": 120.0,
}
COMMISSION = {
    "XAUUSD": 0.0,
    "EURUSD": 7.0,
    "GBPUSD": 7.0,
    "USDJPY": 7.0,
    "NAS100": 5.0,
}


def load_h1(symbol: str, max_bars: int = 25000) -> pd.DataFrame:
    path = ROOT / "data" / f"{symbol}_H1.csv"
    df = pd.read_csv(path)
    ts = "time" if "time" in df.columns else "date"
    df[ts] = pd.to_datetime(df[ts])
    df = df.sort_values(ts).reset_index(drop=True)
    if len(df) > max_bars:
        df = df.iloc[-max_bars:].reset_index(drop=True)
    if "time" not in df.columns:
        df = df.rename(columns={ts: "time"})
    return df


def run_one(symbol: str, strategy, spread: float) -> dict:
    from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine

    df = load_h1(symbol)
    ohlcv = {k: df[k].tolist() for k in ["open", "high", "low", "close"]}
    ohlcv["volume"] = df["volume"].tolist() if "volume" in df.columns else [0.0] * len(df)

    cfg = BacktestConfig(
        initial_capital=Decimal("10000"),
        slippage_pips=0.5,
        spread_pips=spread,
        commission_per_lot=Decimal(str(COMMISSION.get(symbol, 3.5))),
        risk_per_trade_bps=50,
        max_positions=1,
        strict_mtf=False,
    )
    eng = BacktestEngine(cfg)
    eng._symbol = symbol  # Fix Bug #1: thread real symbol through engine
    eng.set_strategy(strategy)
    eng.load_data(ohlcv, df["time"].tolist())
    eng._check_risk_halt = lambda: False
    eng._pnl_tracker = None
    r = eng.run()
    trades = r.get("trades", [])
    pnls = [float(t["pnl"]) for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total = sum(pnls)
    pf = (sum(wins) / abs(sum(losses))) if losses and sum(losses) != 0 else 0.0

    if len(pnls) >= 5:
        eq = 10000.0
        rets = []
        for p in pnls:
            rets.append(p / eq)
            eq += p
        mu = float(np.mean(rets))
        sd = float(np.std(rets, ddof=1)) + 1e-12
        t0 = pd.Timestamp(trades[0]["exit_time"])
        t1 = pd.Timestamp(trades[-1]["exit_time"])
        years = max((t1 - t0).days / 365.25, 0.5)
        tpy = len(pnls) / years
        sharpe = mu / sd * math.sqrt(tpy)
    else:
        sharpe = 0.0

    return {
        "n_bars": len(df),
        "n_trades": len(trades),
        "total_pnl": round(total, 2),
        "win_pct": round(100 * len(wins) / len(pnls), 1) if pnls else 0.0,
        "pf": round(pf, 3),
        "sharpe_trade": round(sharpe, 3),
        "final_eq": round(10000 + total, 2),
        "span": f"{df['time'].iloc[0]} -> {df['time'].iloc[-1]}",
    }


def strategy_variants():
    from graxia.packages.quant_os.strategies.donchian import DonchianBreakout
    from graxia.packages.quant_os.strategies.donchian_adx import DonchianADX
    from graxia.packages.quant_os.strategies.hybrid_mom_mr import HybridMomMR
    from graxia.packages.quant_os.strategies.momentum_12m import Momentum12M
    from graxia.packages.quant_os.strategies.rsi_mean_reversion import RSIMeanReversion

    return [
        (
            "Donchian_10",
            lambda: DonchianBreakout(
                period=10,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
                vol_filter=False,
            ),
        ),
        (
            "Donchian_20",
            lambda: DonchianBreakout(
                period=20,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
                vol_filter=True,
                vol_filter_pctile=0.7,
            ),
        ),
        (
            "DonchianADX_10_25",
            lambda: DonchianADX(
                period=10,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
                adx_period=14,
                adx_threshold=25.0,
            ),
        ),
        (
            "RSI_20_80",
            lambda: RSIMeanReversion(
                rsi_period=14,
                oversold=20,
                overbought=80,
                ema_period=0,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
            ),
        ),
        (
            "HybridMomMR_60",
            lambda: HybridMomMR(
                lookback=60,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
            ),
        ),
        (
            "Momentum12M_126",
            lambda: Momentum12M(
                lookback=126,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
            ),
        ),
    ]


def main() -> int:
    symbols = ["XAUUSD", "EURUSD", "NAS100"]
    variants = strategy_variants()
    out: dict = {}
    ranked = []

    for sym in symbols:
        print(f"\n=== {sym} H1 ===", flush=True)
        out[sym] = {}
        for name, fac in variants:
            print(f"  {name}...", end=" ", flush=True)
            try:
                m = run_one(sym, fac(), SPREADS[sym])
                out[sym][name] = m
                ranked.append({"symbol": sym, "strategy": name, **m})
                print(
                    f"trades={m['n_trades']} pnl={m['total_pnl']} " f"pf={m['pf']} sharpe={m['sharpe_trade']}",
                    flush=True,
                )
            except Exception as e:
                print(f"ERR {e}", flush=True)
                out[sym][name] = {"error": str(e)}

    ranked.sort(key=lambda x: (x.get("sharpe_trade") or -999), reverse=True)
    candidates = [
        r for r in ranked if r.get("n_trades", 0) >= 100 and r.get("pf", 0) > 1.2 and r.get("sharpe_trade", 0) > 1.0
    ]

    print("\n" + "=" * 72)
    print("  H1 RANKING (by trade-Sharpe)")
    print("=" * 72)
    print(f"  {'Symbol':<8} {'Strategy':<22} {'Trades':>6} {'PnL':>10} {'PF':>6} {'Sharpe':>8}")
    print("  " + "-" * 68)
    for r in ranked[:15]:
        print(
            f"  {r['symbol']:<8} {r['strategy']:<22} {r.get('n_trades', 0):>6} "
            f"{r.get('total_pnl', 0):>10.1f} {r.get('pf', 0):>6.2f} {r.get('sharpe_trade', 0):>8.3f}"
        )
    print(f"\n  Candidates (trades>=100, PF>1.2, Sharpe>1.0): {len(candidates)}")
    for c in candidates:
        print(f"    {c['symbol']} {c['strategy']} sharpe={c['sharpe_trade']} pf={c['pf']}")

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "timeframe": "H1",
        "candidate_rule": "n_trades>=100 AND pf>1.2 AND sharpe_trade>1.0",
        "candidates": candidates,
        "ranked": ranked,
        "results": out,
        "honest_note": "H1 single-asset scan is exploratory. Not GO for live without pooled DK + label-shuffle.",
    }
    out_path = ROOT / "reports" / "edge_search_h1_results.json"
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\n  Saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
