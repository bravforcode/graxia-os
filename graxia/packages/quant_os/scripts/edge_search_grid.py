"""Grid Strategy Edge Search — DK-test Framework (FIRST RUN)."""
from __future__ import annotations
import argparse, json, math, sys, traceback
from datetime import UTC, datetime
from pathlib import Path
import numpy as np, pandas as pd

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
for p in (str(GRAXIA_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from graxia.packages.quant_os.strategies.grid_strategy import GridConfig
from graxia.packages.quant_os.strategies.grid_backtest import run_grid_backtest

CORE_UNIVERSE = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30"]
SYMBOL_SPREAD_PIPS = {"XAUUSD": 100.0, "XAGUSD": 150.0, "EURUSD": 1.2, "GBPUSD": 1.5, "USDJPY": 1.2, "NAS100": 120.0, "US30": 120.0}
PIP_VALUE = {"XAUUSD": 0.01, "XAGUSD": 0.001, "EURUSD": 0.0001, "GBPUSD": 0.0001, "USDJPY": 0.01, "NAS100": 1.0, "US30": 1.0}
SYMBOL_COMMISSION = {"XAUUSD": 0.0, "XAGUSD": 0.0, "EURUSD": 7.0, "GBPUSD": 7.0, "USDJPY": 7.0, "NAS100": 5.0, "US30": 5.0}

def load_asset_data(symbol):
    for ext in [".csv"]:
        p = ROOT / "data" / f"{symbol}_D1{ext}"
        if p.exists():
            df = pd.read_csv(p)
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
                df = df.set_index("time")
            elif "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"])
                df = df.set_index("date")
            for c in ["open", "high", "low", "close", "volume"]:
                if c in df.columns:
                    df[c] = pd.to_numeric(df[c], errors="coerce")
            return df.dropna(subset=["close"])
    return None

def run_dk_test(all_returns):
    cs_mean = all_returns.mean(axis=1).dropna()
    mu = float(cs_mean.mean())
    T = len(cs_mean)
    if T < 30:
        return 0.0, 0.0, 0
    max_lag = max(1, int(T ** (1/3)))
    gamma_0 = float(cs_mean.var(ddof=1))
    nw_var = gamma_0
    for lag in range(1, max_lag + 1):
        cov = float(cs_mean.iloc[lag:].cov(cs_mean.iloc[:-lag]))
        weight = 1.0 - lag / (max_lag + 1)
        nw_var += 2 * weight * cov
    nw_se = math.sqrt(nw_var / T) if nw_var > 0 else 1e-10
    dk_t = mu / nw_se
    pooled_sharpe = mu / (math.sqrt(gamma_0) + 1e-10) * math.sqrt(252)
    return dk_t, pooled_sharpe, T

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--universe", default=",".join(CORE_UNIVERSE))
    parser.add_argument("--cost-model", default="pepperstone_razor")
    parser.add_argument("--dk-test", default="pooled")
    parser.add_argument("--label-shuffle", type=int, default=200)
    parser.add_argument("--output", default="reports/edge_search_grid_20260721.json")
    args = parser.parse_args()

    universe = args.universe.split(",")
    results = {"strategy": "grid", "parameters": {"grid_count": 10, "atr_multiplier": 2.0, "order_volume": 0.01, "atr_period": 14}, "universe": universe, "per_asset": {}}

    all_returns = {}
    for symbol in universe:
        df = load_asset_data(symbol)
        if df is None or len(df) < 500:
            results["per_asset"][symbol] = {"error": "insufficient_data"}
            continue
        try:
            config = GridConfig()
            ohlcv_data = {
                "open": df["open"].tolist(),
                "high": df["high"].tolist(),
                "low": df["low"].tolist(),
                "close": df["close"].tolist(),
                "volume": df["volume"].tolist() if "volume" in df.columns else [0] * len(df),
            }
            timestamps = df.index.tolist()
            result = run_grid_backtest(config, ohlcv_data, timestamps)
            equity = result.get("equity_curve", [])
            if len(equity) < 30:
                results["per_asset"][symbol] = {"error": "insufficient_equity", "len": len(equity)}
                continue
            eq = pd.Series(equity, index=df.index[:len(equity)])
            daily_ret = eq.pct_change().dropna()
            # Grid backtest already accounts for fees (FEE_RATE=0.001 per fill) and
            # includes costs in equity_curve via cumulative_pnl + unrealized. No extra
            # cost subtraction needed — that was the bug (dollar cost subtracted from %).
            all_returns[symbol] = daily_ret
            total_return = (equity[-1] - equity[0]) / equity[0]
            results["per_asset"][symbol] = {
                "sharpe": round(float(daily_ret.mean() / (daily_ret.std() + 1e-10) * math.sqrt(252)), 4),
                "trades": result.get("grid_fills", 0),
                "return": round(total_return, 4),
                "return_pct": result.get("return_pct", 0),
                "max_dd": result.get("max_drawdown", 0),
                "grid_fills": result.get("grid_fills", 0),
                "total_fees": result.get("total_fees", 0),
                "final_equity": result.get("final_equity", equity[0]),
                "equity_len": len(equity)
            }
        except Exception as e:
            results["per_asset"][symbol] = {"error": str(e)}

    if all_returns:
        combined = pd.DataFrame(all_returns)
        dk_t, pooled_sharpe, T = run_dk_test(combined)
        pos_sharpe = sum(1 for v in results["per_asset"].values() if isinstance(v, dict) and v.get("sharpe", 0) > 0)
        verdict = "GO" if dk_t > 2.0 and pos_sharpe >= 5 else "MARGINAL" if dk_t > 1.5 else "REJECT"
        results["pooled"] = {"dk_t": round(dk_t, 4), "pooled_sharpe": round(pooled_sharpe, 4), "positive_sharpe_count": pos_sharpe, "total_trades": sum(v.get("trades", 0) for v in results["per_asset"].values() if isinstance(v, dict)), "verdict": verdict, "T": T}

        if args.label_shuffle > 0:
            shuffled = []
            for _ in range(args.label_shuffle):
                shuffled_returns = combined.apply(lambda x: x.sample(frac=1).reset_index(drop=True))
                s_dk, _, _ = run_dk_test(shuffled_returns)
                shuffled.append(s_dk)
            p_val = sum(1 for s in shuffled if s >= dk_t) / len(shuffled)
            results["label_shuffle"] = {"n_shuffles": args.label_shuffle, "observed_dk_t": round(dk_t, 4), "p_value": round(p_val, 4), "verdict": "PASS" if p_val < 0.05 else "FAIL"}

    results["timestamp"] = datetime.now(UTC).isoformat()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(results, f, indent=2)
    print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
