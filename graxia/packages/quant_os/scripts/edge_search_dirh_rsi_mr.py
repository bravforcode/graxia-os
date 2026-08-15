"""Direction H Trial 9002 — RSI Mean-Reversion on forex 4 pairs (H1, measured costs).

Frozen per research/pre_registration/trial_9002_forex4_rsi_mr.md (2026-08-06):
RSIMeanReversion(RSI 14, oversold 30, overbought 70, EMA off, ATR SL 2.0 / TP 3.0),
risk_per_trade_bps=50, max_positions=1, USDCAD/USDCHF/AUDUSD/NZDUSD H1 full history,
measured FROM_TICKS costs via SymbolCostProfile (fail-closed, no default fallback).

Gates (frozen): GO if DK t>2.0 AND Sharpe>0 in >=3/4; MARGINAL if DK t>1.5 OR
Sharpe>0 in >=2/4; else REJECT. Min trades >= 100 per pair.

Usage:
    python scripts/edge_search_dirh_rsi_mr.py
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

SYMBOLS = ["USDCAD", "USDCHF", "AUDUSD", "NZDUSD"]
TIMEFRAME = "H1"
OUT_PATH = ROOT / "reports" / "edge_search_dirh_rsi_mr_9002.json"

# Frozen params (pre-registration doc)
FROZEN = {
    "rsi_period": 14,
    "oversold": 30.0,
    "overbought": 70.0,
    "ema_period": 0,
    "atr_period": 14,
    "atr_sl_mult": 2.0,
    "atr_tp_mult": 3.0,
    "risk_per_trade_bps": 50,
    "max_positions": 1,
    "initial_capital": 10000.0,
}


def load_h1(symbol: str) -> pd.DataFrame:
    path = ROOT / "data" / f"{symbol}_H1.csv"
    df = pd.read_csv(path)
    ts = "time" if "time" in df.columns else "date"
    df[ts] = pd.to_datetime(df[ts], utc=True)
    df = df.sort_values(ts).reset_index(drop=True)
    return df


def run_engine(symbol: str) -> dict:
    """BacktestEngine measured-cost path (slippage_pips=None -> SymbolCostProfile)."""
    from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine
    from graxia.packages.quant_os.strategies.rsi_mean_reversion import RSIMeanReversion

    class _TrailingRSI(RSIMeanReversion):
        """RSI/ATR are backward-looking — a fixed trailing window is EXACTLY
        equivalent to full history (no lookahead, no result change) and avoids
        the O(bars^2) full-loop re-computation per bar (50k bars x 50k closes
        = 2.5e9 ops/symbol). Window 100 >> needed 16 (RSI) + 15 (ATR)."""

        _WINDOW = 100

        def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):  # noqa: ARG002
            sliced = {
                k: v[-self._WINDOW:] if isinstance(v, list) else v
                for k, v in ohlcv_data.items()
            }
            return super().generate_signal(symbol, sliced, indicators, regime, **kwargs)

    df = load_h1(symbol)
    ohlcv = {k: df[k].tolist() for k in ["open", "high", "low", "close"]}
    ohlcv["volume"] = df["volume"].tolist() if "volume" in df.columns else [0.0] * len(df)

    config = BacktestConfig(
        initial_capital=Decimal(str(FROZEN["initial_capital"])),
        slippage_pips=None,  # measured path — fail-closed via SymbolCostProfile
        spread_pips=None,
        commission_per_lot=Decimal("7.0"),
        risk_per_trade_bps=FROZEN["risk_per_trade_bps"],
        max_positions=FROZEN["max_positions"],
        strict_mtf=False,
        enable_swap=False,
    )
    strategy = _TrailingRSI(
        rsi_period=FROZEN["rsi_period"],
        oversold=FROZEN["oversold"],
        overbought=FROZEN["overbought"],
        ema_period=FROZEN["ema_period"],
        atr_period=FROZEN["atr_period"],
        atr_sl_mult=FROZEN["atr_sl_mult"],
        atr_tp_mult=FROZEN["atr_tp_mult"],
    )
    engine = BacktestEngine(config)
    engine._symbol = symbol
    engine.set_strategy(strategy)
    engine.load_data(ohlcv, df["time"].tolist())
    engine._check_risk_halt = lambda: False  # type: ignore[method-assign]
    engine._pnl_tracker = None
    engine._precomputed_indicators = {}
    result = engine.run()
    result["_symbol"] = symbol
    result["_timestamps"] = df["time"].tolist()
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
    all_results = {}
    per_asset_returns = {}

    for symbol in SYMBOLS:
        print(f"Running {symbol}...", end=" ", flush=True)
        try:
            res = run_engine(symbol)
            all_results[symbol] = res
            trades = res.get("trades", [])
            # daily returns from equity curve
            eq = res.get("equity_curve", [])
            rows = []
            prev = None
            for p in eq:
                try:
                    eqv = float(getattr(p, "equity", p.get("equity", 0)) if not isinstance(p, dict) else p.get("equity", 0))
                except Exception:  # noqa: BLE001
                    continue
                if prev is not None and prev > 0:
                    rows.append(eqv / prev - 1.0)
                prev = eqv
            daily = pd.Series(rows)
            if len(daily) >= 20:
                per_asset_returns[symbol] = daily
            print(f"{len(trades)} trades, {len(daily)} daily points")
        except Exception as e:  # noqa: BLE001
            print(f"ERROR: {e}")

    if len(per_asset_returns) < 3:
        print("FAIL: <3 assets with returns — INSUFFICIENT_SAMPLE")
        return 1

    panel = pd.DataFrame(per_asset_returns)
    panel = panel.fillna(0.0)
    daily_means = panel.mean(axis=1).values
    dk_t, dk_mean, dk_se = driscoll_kraay_t(daily_means)
    dk_sharpe = dk_mean / (daily_means.std(ddof=1) + 1e-10) * math.sqrt(252)

    total_trades = 0
    positive_sharpe = 0
    per_asset = {}
    for symbol in SYMBOLS:
        if symbol not in all_results:
            per_asset[symbol] = {"error": "no_result"}
            continue
        trades = all_results[symbol].get("trades", [])
        pnls = [float(t["pnl"]) for t in trades]
        total_trades += len(pnls)
        wins = sum(p for p in pnls if p > 0)
        losses = abs(sum(p for p in pnls if p < 0))
        pf = wins / losses if losses > 0 else (float("inf") if wins > 0 else 0.0)
        nw = 0.0
        if len(pnls) >= 20:
            arr = np.array(pnls)
            mu = arr.mean()
            b = max(int(4 * (len(arr) / 100) ** (2 / 9)), 1)
            g0 = float(np.mean((arr - mu) ** 2))
            v = g0
            for k in range(1, b + 1):
                w = 1 - k / (b + 1)
                v += 2 * w * float(np.mean((arr[k:] - mu) * (arr[:-k] - mu)))
            nw = mu / (math.sqrt(v / len(arr)) + 1e-10)
        sharpe = float("nan")
        if symbol in per_asset_returns:
            r = per_asset_returns[symbol].values
            sharpe = float(r.mean()) / (float(r.std(ddof=1)) + 1e-10) * math.sqrt(252)
            if sharpe > 0:
                positive_sharpe += 1
        per_asset[symbol] = {
            "n_trades": len(pnls),
            "net_pnl": round(sum(pnls), 2),
            "profit_factor": round(float(pf), 4) if pf != float("inf") else 99.99,
            "trade_nw_t": round(nw, 4),
            "sharpe_daily": round(sharpe, 4) if sharpe == sharpe else None,
        }
        print(
            f"  {symbol}: {len(pnls)} trades, PF={per_asset[symbol]['profit_factor']}, "
            f"t={nw:.3f}, Sharpe={sharpe:.3f}"
        )

    # Gates (frozen)
    min_trades_ok = all(per_asset[s]["n_trades"] >= 100 for s in SYMBOLS if "error" not in per_asset[s])
    if dk_t > 2.0 and positive_sharpe >= 3:
        verdict = "GO"
        reason = f"DK t={dk_t:.3f} > 2.0 AND Sharpe>0 in {positive_sharpe}/4"
    elif dk_t > 1.5 or positive_sharpe >= 2:
        verdict = "MARGINAL"
        reason = f"DK t={dk_t:.3f} (>1.5) OR Sharpe>0 in {positive_sharpe}/4 (>=2)"
    else:
        verdict = "REJECT"
        reason = f"DK t={dk_t:.3f} (<1.5) AND Sharpe>0 in {positive_sharpe}/4 (<2)"
    if not min_trades_ok:
        verdict = "INSUFFICIENT_TRADES"
        reason += " | min-trades gate (>=100/pair) NOT met"

    artifact = {
        "title": "Direction H Trial 9002 — RSI Mean-Reversion forex4 H1",
        "frozen": FROZEN,
        "executed_at": datetime.now(UTC).isoformat(),
        "universe": SYMBOLS,
        "per_asset": per_asset,
        "pooled": {
            "dk_t_stat": round(dk_t, 4),
            "dk_mean_return": round(dk_mean, 8),
            "dk_se": round(dk_se, 8),
            "dk_sharpe": round(dk_sharpe, 4),
            "total_trades": total_trades,
            "positive_sharpe_count": positive_sharpe,
            "n_assets": len(per_asset_returns),
        },
        "gates": {
            "dk_t_gt_2": dk_t > 2.0,
            "positive_sharpe_ge_3": positive_sharpe >= 3,
            "min_trades_100_per_pair": min_trades_ok,
        },
        "verdict": verdict,
        "reason": reason,
    }
    OUT_PATH.write_text(json.dumps(artifact, indent=2, default=str), encoding="utf-8")
    print(f"\nVERDICT: {verdict} — {reason}")
    print(f"Artifact: {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
