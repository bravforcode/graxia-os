"""
Label-shuffle test for Gold ICT strategies on XAUUSD D1.

Shuffles daily returns → rebuilds OHLC → re-runs batch signal generators.
p-value = fraction of shuffled Sharpes >= real Sharpe.
If p > 0.05 → cannot reject null (no edge / chance).

Does NOT use sacred holdout.

Usage:
  python scripts/label_shuffle_gold_ict.py
  python scripts/label_shuffle_gold_ict.py --only gi_bos_choch,gi_ema_cross
"""
from __future__ import annotations

import argparse
import json
import math
import sys
import time
from datetime import UTC, datetime
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

from graxia.packages.quant_os.paper_engine.strategies.gold_ict_batch import BATCH_REGISTRY

N_SHUFFLES = 200
COST_RT_BPS = 0.30  # XAUUSD measured spread+slip
OOS_RATIO = 0.2     # last 20% for OOS


def load_xauusd_d1() -> pd.DataFrame:
    path = ROOT / "data" / "XAUUSD_D1.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing {path}")
    df = pd.read_csv(path)
    ts = "time" if "time" in df.columns else "date"
    df[ts] = pd.to_datetime(df[ts])
    df = df[df[ts] >= "2005-01-01"].sort_values(ts).reset_index(drop=True)
    if ts != "time":
        df = df.rename(columns={ts: "time"})
    return df


def simulate_bar_returns(close: np.ndarray, directions: np.ndarray, cost_bps: float) -> np.ndarray:
    """Position-held bar returns with round-trip cost on flips."""
    n = len(close)
    rets = np.zeros(n)
    pos = 0
    for i in range(1, n):
        bar_ret = close[i] / close[i - 1] - 1.0
        rets[i] = pos * bar_ret
        new_pos = int(directions[i])
        if new_pos != pos and new_pos != 0:
            rets[i] -= cost_bps / 10000.0
            pos = new_pos
        elif new_pos == 0 and pos != 0:
            rets[i] -= cost_bps / 10000.0
            pos = 0
        else:
            pos = new_pos
    return rets


def sharpe_ann(rets: np.ndarray) -> float:
    r = rets[np.isfinite(rets)]
    if len(r) < 30:
        return 0.0
    mu = float(np.mean(r))
    sd = float(np.std(r, ddof=1))
    if sd <= 0:
        return 0.0
    return mu / sd * math.sqrt(252)


def rebuild_prices(opens, highs, lows, closes, seed: int):
    """Shuffle log-returns, rebuild OHLC preserving relative bar shape."""
    rng = np.random.default_rng(seed)
    log_rets = np.diff(np.log(np.maximum(closes, 1e-10)))
    shuffled = rng.permutation(log_rets)
    new_closes = np.zeros_like(closes)
    new_closes[0] = closes[0]
    for i in range(1, len(closes)):
        new_closes[i] = new_closes[i - 1] * math.exp(shuffled[i - 1])

    with np.errstate(divide="ignore", invalid="ignore"):
        open_ratio = np.where(closes > 0, opens / closes, 1.0)
        high_ratio = np.where(closes > 0, highs / closes, 1.0)
        low_ratio = np.where(closes > 0, lows / closes, 1.0)
    new_opens = new_closes * open_ratio
    new_highs = new_closes * high_ratio
    new_lows = new_closes * low_ratio
    new_highs = np.maximum(new_highs, np.maximum(new_opens, new_closes))
    new_lows = np.minimum(new_lows, np.minimum(new_opens, new_closes))
    return new_opens, new_highs, new_lows, new_closes


def run_label_shuffle(
    strategy_id: str,
    close: np.ndarray,
    high: np.ndarray,
    low: np.ndarray,
    volume: np.ndarray | None,
    cost_bps: float,
) -> dict:
    """Run label shuffle test for a single strategy."""
    import inspect

    fn = BATCH_REGISTRY[strategy_id]
    sig = inspect.signature(fn)
    kwargs = {"close": close, "high": high, "low": low}
    if "volume" in sig.parameters and volume is not None:
        kwargs["volume"] = volume

    # Real signals
    result = fn(**kwargs)
    real_dirs = result.directions
    real_rets = simulate_bar_returns(close, real_dirs, cost_bps)

    # OOS split
    split = int(len(close) * (1 - OOS_RATIO))
    real_oos_sharpe = sharpe_ann(real_rets[split:])
    real_full_sharpe = sharpe_ann(real_rets)
    real_mean = float(np.mean(real_rets[split:]))

    # Shuffle null distribution
    null_sharpes = []
    for k in range(N_SHUFFLES):
        no, nh, nl, nc = rebuild_prices(
            close, high, low, close, seed=1000 + k
        )
        # Rebuild kwargs with shuffled OHLC
        nkwargs = {"close": nc, "high": nh, "low": nl}
        if "volume" in sig.parameters and volume is not None:
            nkwargs["volume"] = volume
        try:
            nresult = fn(**nkwargs)
            nrets = simulate_bar_returns(nc, nresult.directions, cost_bps)
            null_sharpes.append(sharpe_ann(nrets[split:]))
        except Exception:
            null_sharpes.append(0.0)

    null_arr = np.array(null_sharpes)
    p_value = float(np.mean(null_arr >= real_oos_sharpe))
    verdict = "EDGE_SURVIVES" if p_value < 0.05 and real_oos_sharpe > 0 else "NO_EDGE"

    return {
        "strategy": strategy_id,
        "n_bars": len(close),
        "cost_rt_bps": cost_bps,
        "full_sharpe": round(real_full_sharpe, 4),
        "oos_sharpe": round(real_oos_sharpe, 4),
        "oos_mean_ret": round(real_mean, 8),
        "null_mean_sharpe": round(float(np.mean(null_arr)), 4),
        "null_p95_sharpe": round(float(np.percentile(null_arr, 95)), 4),
        "p_value": round(p_value, 4),
        "n_shuffles": N_SHUFFLES,
        "verdict": verdict,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Label shuffle for Gold ICT strategies")
    parser.add_argument("--only", type=str, default="", help="Comma-separated strategy IDs")
    parser.add_argument("--out", type=str, default=str(ROOT / "reports" / "label_shuffle_gold_ict_results.json"))
    args = parser.parse_args()

    print("=" * 70)
    print("  LABEL SHUFFLE — Gold ICT on XAUUSD D1")
    print("  %d iterations per strategy" % N_SHUFFLES)
    print("=" * 70)

    df = load_xauusd_d1()
    print("  Data: %d D1 bars" % len(df))

    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    vol = df["volume"].values.astype(float) if "volume" in df.columns else None

    strategies = list(BATCH_REGISTRY.keys())
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        strategies = [s for s in strategies if s in wanted]

    results = []
    for strat_id in strategies:
        print("  Running %s..." % strat_id, end=" ", flush=True)
        t0 = time.time()
        r = run_label_shuffle(strat_id, close, high, low, vol, COST_RT_BPS)
        t1 = time.time()
        results.append(r)
        print(
            "OOS_sharpe=%.3f  p=%.4f  null_p95=%.3f  -> %s [%.1fs]" % (
                r["oos_sharpe"], r["p_value"], r["null_p95_sharpe"],
                r["verdict"], t1 - t0,
            ),
            flush=True,
        )

    survives = [r["strategy"] for r in results if r["verdict"] == "EDGE_SURVIVES"]
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "symbol": "XAUUSD",
        "timeframe": "D1",
        "n_shuffles": N_SHUFFLES,
        "cost_rt_bps": COST_RT_BPS,
        "method": "shuffle log-returns, rebuild OHLC, re-run batch signals, OOS last 20%",
        "survives": survives,
        "results": results,
        "honest_note": (
            "EDGE_SURVIVES means p<0.05 on label-shuffle OOS only. "
            "Still not live-ready without pooled multi-asset DK + cost stress + paper."
        ),
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print("\n  Survives: %s" % (survives or "NONE"))
    print("  Saved: %s" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
