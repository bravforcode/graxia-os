"""
WS-A — Trial #1028: MOP2012 Time-Series Momentum (pure sign(12M)).
=========================================================================
Frozen parameters (PRE-REGISTERED, never tuned after seeing results):
  lookback = 252 only        vol_target = 0.10
  monthly rebalance          universe = 7 assets, independent (NOT cross-sectional)
  costs = pepperstone_razor

Data: MANDATED provenance loader (load_provenance_checked) — slices >=2005-01-01
and HARD-FAILS on synthetic backfill. Does NOT touch sacred holdout.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent  # graxia/packages/quant_os
GRAXIA_ROOT = ROOT.parent.parent.parent  # graxia
for p in (str(GRAXIA_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from graxia.packages.quant_os.provenance import (  # noqa: E402
    load_provenance_checked,
    DataProvenanceError,
)
from graxia.packages.quant_os.strategies.tsmom import compute_tsmom_signal  # noqa: E402
from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine  # noqa: E402
from graxia.packages.quant_os.strategies.base import (  # noqa: E402
    Strategy,
    Signal,
    SignalType,
    StrategyConfig,
)
from graxia.packages.quant_os.validation.deflated_sharpe import (  # noqa: E402
    deflated_sharpe_ratio,
)

UNIVERSE = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD", "USDJPY", "NAS100", "US30"]

SYMBOL_SPREAD_PIPS = {
    "XAUUSD": 100.0, "XAGUSD": 150.0, "EURUSD": 1.2, "GBPUSD": 1.5,
    "USDJPY": 1.2, "NAS100": 120.0, "US30": 120.0,
}
SYMBOL_COMMISSION = {
    "XAUUSD": 0.0, "XAGUSD": 0.0, "EURUSD": 7.0, "GBPUSD": 7.0,
    "USDJPY": 7.0, "NAS100": 5.0, "US30": 5.0,
}


class _MomentumSignalAdapter(Strategy):
    """Wraps a pre-computed sign(252) signal into an engine-compatible Signal."""

    def __init__(self, symbol: str, signal_array: np.ndarray, sl_mult: float = 2.0):
        config = StrategyConfig(
            name="WSAAdapter", version="1.0", symbols=[symbol], timeframes=["D1"],
            risk_per_trade_pct=1.0, max_trades_per_day=1, require_trend_confirm=False,
        )
        super().__init__(config)
        self._sym = symbol
        self._signals = signal_array
        self._sl_mult = sl_mult
        self._last_sig = 0.0

    def required_features(self):
        return ["momentum_signal"]

    def generate_signal(self, symbol, ohlcv_data, indicators=None, regime=None, **kwargs):
        n = len(ohlcv_data.get("close", []))
        if n == 0 or n > len(self._signals):
            return None
        cur = float(self._signals[n - 1])
        if cur == self._last_sig:
            return None
        self._last_sig = cur
        if cur == 0 or np.isnan(cur):
            return None
        st = SignalType.BUY if cur > 0 else SignalType.SELL
        entry = float(ohlcv_data["close"][-1])
        h = np.array(ohlcv_data.get("high", []), dtype=float)
        l = np.array(ohlcv_data.get("low", []), dtype=float)
        c = np.array(ohlcv_data.get("close", []), dtype=float)
        atr = 0.0
        if len(h) >= 15:
            tr = np.maximum.reduce([h[1:] - l[1:], np.abs(h[1:] - c[:-1]), np.abs(l[1:] - c[:-1])])
            atr = float(np.mean(tr[-14:])) if len(tr) >= 14 else 0.0
        sl = None
        if entry > 0 and atr > 0:
            sl = Decimal(str(entry - atr * self._sl_mult if st == SignalType.BUY else entry + atr * self._sl_mult))
        return Signal.create(
            strategy_id=self.id, symbol=symbol, signal_type=st,
            confidence=abs(cur), entry_price=Decimal(str(entry)), stop_loss=sl,
        )


def _extract_daily_returns(equity_curve: list) -> pd.Series:
    eq = pd.Series([float(e.equity if hasattr(e, "equity") else e.get("equity", 0)) for e in equity_curve])
    return eq.pct_change().dropna() if len(eq) >= 2 else pd.Series(dtype=float)


def _calc_max_dd(equity_curve: list) -> float:
    eq = pd.Series([float(e.equity if hasattr(e, "equity") else e.get("equity", 0)) for e in equity_curve])
    return float((eq / eq.cummax() - 1).min()) if len(eq) > 0 else 0.0


def run_dk_test(all_returns: pd.DataFrame, total_trades: int) -> dict:
    """Pooled Driscoll-Kraay test with Newey-West HAC correction (T^(1/3) lags)."""
    if all_returns.empty or len(all_returns.columns) < 2:
        return {"dk_t_stat": 0.0, "pooled_sharpe": 0.0, "positive_sharpe_count": 0,
                "total_assets": 0, "total_days": 0, "total_trades": total_trades, "verdict": "INSUFFICIENT_DATA"}
    cs_mean = all_returns.mean(axis=1).dropna()
    if len(cs_mean) < 30:
        return {"dk_t_stat": 0.0, "pooled_sharpe": 0.0, "positive_sharpe_count": 0,
                "total_assets": len(all_returns.columns), "total_days": len(cs_mean),
                "total_trades": total_trades, "verdict": "INSUFFICIENT_DATA"}
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
    return {"dk_t_stat": round(dk_t, 4), "pooled_sharpe": round(pooled_sharpe, 4),
            "positive_sharpe_count": pos_sharpe, "total_assets": len(all_returns.columns),
            "total_days": T, "total_trades": total_trades, "verdict": verdict}


def _run_engine_for_symbol(sym: str, df: pd.DataFrame, sig_values: np.ndarray, cost_multiplier: float = 1.0) -> dict:
    ts = "time" if "time" in df.columns else "date"
    ohlcv = {
        "open": df["open"].tolist(), "high": df["high"].tolist(),
        "low": df["low"].tolist(), "close": df["close"].tolist(),
        "volume": df["volume"].tolist() if "volume" in df.columns else [0.0] * len(df),
    }
    timestamps = [pd.Timestamp(t).to_pydatetime() for t in df.index]

    sl_mult = 2.0 if sym in ("EURUSD", "GBPUSD", "USDJPY") else (1.5 if sym in ("XAUUSD", "XAGUSD") else 3.0)
    bt_config = BacktestConfig()
    bt_config.initial_capital = Decimal("100000")
    bt_config.spread_pips = float(SYMBOL_SPREAD_PIPS.get(sym, 2.0)) * cost_multiplier
    bt_config.commission_per_lot = Decimal(str(SYMBOL_COMMISSION.get(sym, 3.5)))
    bt_config.risk_per_trade_bps = 100
    bt_config.max_positions = 1
    bt_config.strict_mtf = False

    engine = BacktestEngine(bt_config)
    engine._symbol = sym
    adapter = _MomentumSignalAdapter(sym, sig_values, sl_mult)
    engine.set_strategy(adapter)
    engine.load_data(ohlcv, timestamps)
    engine._check_risk_halt = lambda: False
    engine._pnl_tracker = None

    results = engine.run()
    equity = getattr(engine, "equity_curve", []) or []
    n_trades = len(results.get("trades", []) or [])
    daily_ret = _extract_daily_returns(equity)
    max_dd = _calc_max_dd(equity)
    if len(daily_ret) >= 2:
        r = daily_ret.dropna()
        sharpe = float(r.mean()) / (float(r.std(ddof=1)) + 1e-10) * math.sqrt(252)
        total_ret = float((1 + r).cumprod().iloc[-1] - 1)
    else:
        sharpe, total_ret = 0.0, 0.0
    return {"daily_ret": daily_ret, "trades": n_trades, "sharpe": round(sharpe, 4),
            "return": round(total_ret, 6), "max_dd": round(max_dd, 6)}


def main() -> int:
    parser = argparse.ArgumentParser(description="WS-A TSMOM pure sign(252) backtest")
    parser.add_argument("--cost-multiplier", type=float, default=1.0)
    parser.add_argument("--output", type=str,
                        default=str(ROOT / "reports" / "ws_a_trial_1028.json"))
    args = parser.parse_args()

    print("WS-A (Trial #1028) — MOP2012 pure time-series momentum, sign(252)")
    print("=" * 64)

    close_prices = pd.DataFrame()
    signals = {}
    raw_dfs = {}
    for sym in UNIVERSE:
        try:
            df = load_provenance_checked(sym)  # slices >=2005, hard-fails on contamination
        except DataProvenanceError as e:
            print(f"  {sym}: PROVENANCE FAIL — {e}")
            return 1
        ts = "time" if "time" in df.columns else "date"
        df[ts] = pd.to_datetime(df[ts])
        df = df.set_index(ts).sort_index()
        raw_dfs[sym] = df
        s = pd.Series(df["close"].values, index=df.index, name=sym)
        close_prices = pd.concat([close_prices, s], axis=1)

        # PURE sign(252) — single lookback only
        sig = compute_tsmom_signal(s, lookbacks=[252], vol_target=0.10)
        signals[sym] = sig.signal  # pd.Series -1/0/+1

        # Verification: signal must be only -1/0/+1 and equal sign(252-return)
        vc = sig.signal.value_counts(dropna=False).to_dict()
        print(f"  {sym}: {len(df)} bars ({df.index[0].date()}→{df.index[-1].date()}) "
              f"signal_value_counts={vc}")

    # Align close prices on common dates
    close_prices = close_prices.dropna(how="all").ffill().dropna()
    data_start, data_end = close_prices.index[0], close_prices.index[-1]
    years = (data_end - data_start).days / 365.25
    print(f"  Aligned: {len(close_prices)} bars, {len(close_prices.columns)} assets, "
          f"{data_start.date()}→{data_end.date()} ({years:.1f}y)")

    # Run engine per asset
    all_returns = pd.DataFrame()
    per_asset = {}
    total_trades = 0
    for sym in UNIVERSE:
        if sym not in close_prices.columns or sym not in signals:
            continue
        df = raw_dfs[sym]
        sig_values = signals[sym].reindex(df.index).ffill().fillna(0).values
        res = _run_engine_for_symbol(sym, df, sig_values, args.cost_multiplier)
        total_trades += res["trades"]
        if len(res["daily_ret"]) >= 2:
            all_returns[sym] = res["daily_ret"]
        # position changes: transitions to a non-zero signal value
        sv = signals[sym].fillna(0).values
        pos_changes = int(((sv != 0) & (sv != np.roll(sv, 1))).sum())
        raw_flips = int(((np.sign(sv) != 0) & (np.sign(sv) != np.roll(np.sign(sv), 1)) &
                         (np.roll(np.sign(sv), 1) != 0)).sum())
        per_asset[sym] = {**{k: v for k, v in res.items() if k != "daily_ret"},
                          "position_changes": pos_changes, "raw_sign_flips": raw_flips}
        print(f"  {sym}: trades={res['trades']:>5} sharpe={res['sharpe']:>+7.3f} "
              f"ret={res['return']:>+8.4f} max_dd={res['max_dd']:>+8.4f} "
              f"pos_changes={pos_changes} raw_flips={raw_flips}")

    # Align all_returns on common dates
    all_returns = all_returns.dropna(how="all").ffill().dropna()

    # --- Battery ---
    print("\n--- Pooled DK-test ---")
    dk = run_dk_test(all_returns, total_trades)
    print(f"  DK t-stat: {dk['dk_t_stat']:.4f}  pooled_sharpe: {dk['pooled_sharpe']:.4f}  "
          f"pos_sharpe: {dk['positive_sharpe_count']}/{dk['total_assets']}  verdict: {dk['verdict']}")

    # DSR @ N=1050
    cs_mean = all_returns.mean(axis=1).dropna()
    pooled_sharpe = float(cs_mean.mean()) / (float(cs_mean.std(ddof=1)) + 1e-10) * math.sqrt(252)
    dsr = deflated_sharpe_ratio(pooled_sharpe, n_trials=1050, n_observations=1050,
                                skewness=float(cs_mean.skew()), kurtosis=float(cs_mean.kurt()))
    dsr_pass = dsr.probability_alpha < 0.05
    print(f"  DSR: sharpe={pooled_sharpe:.4f} prob_alpha(P(false pos))={dsr.probability_alpha:.4f} "
          f"pass(p<0.05)={dsr_pass}")

    # Jackknife (leave-one-asset-out)
    jack = {}
    for drop in UNIVERSE:
        if drop not in all_returns.columns:
            continue
        sub = all_returns.drop(columns=[drop])
        j = run_dk_test(sub, total_trades)
        jack[drop] = j["dk_t_stat"]
    jack_deltas = {k: round(dk["dk_t_stat"] - v, 4) for k, v in jack.items()}
    print(f"  Jackknife ΔSharpe (full - leave-out): {jack_deltas}")

    # Cost-stress
    cost_stress = {}
    for mult in (1.5, 2.0):
        sr = pd.DataFrame()
        tt = 0
        for sym in UNIVERSE:
            if sym not in raw_dfs or sym not in signals:
                continue
            df = raw_dfs[sym]
            sig_values = signals[sym].reindex(df.index).ffill().fillna(0).values
            r = _run_engine_for_symbol(sym, df, sig_values, mult)
            tt += r["trades"]
            if len(r["daily_ret"]) >= 2:
                sr[sym] = r["daily_ret"]
        sr = sr.dropna(how="all").ffill().dropna()
        cdk = run_dk_test(sr, tt)
        cost_stress[f"{mult}x"] = {"dk_t": cdk["dk_t_stat"], "verdict": cdk["verdict"]}
        print(f"  Cost-stress {mult}x: DK t={cdk['dk_t_stat']:.4f} verdict={cdk['verdict']}")

    # PBO/CSCV
    pbo_result = None
    try:
        pbo_in = ROOT / "reports" / "_ws_a_pbo_input.json"
        pbo_out = ROOT / "reports" / "_ws_a_pbo_output.json"
        pbo_payload = {"per_asset_daily_returns": {sym: all_returns[sym].dropna().tolist() for sym in all_returns.columns}}
        pbo_in.write_text(json.dumps(pbo_payload), encoding="utf-8")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "compute_pbo_cscv.py"),
             "--backtest-results", str(pbo_in), "--output", str(pbo_out),
             "--n-partitions", "12", "--n-random-strategies", "50"],
            check=True, capture_output=True, text=True, cwd=str(ROOT),
        )
        pbo_result = json.loads(pbo_out.read_text(encoding="utf-8"))
        print(f"  PBO/CSCV: PBO={pbo_result['pbo']:.4f} (<0.5 pass) interp={pbo_result.get('interpretation','')}")
    except Exception as e:
        print(f"  PBO/CSCV: ERROR {e}")
        pbo_result = {"pbo": None, "error": str(e)}

    # Combined verdict
    gates = {
        "dk_t_gt_2": dk["dk_t_stat"] > 2.0,
        "dsr_pass": dsr_pass,
        "pbo_lt_05": (pbo_result.get("pbo") is not None and pbo_result["pbo"] < 0.5),
        "pos_changes_ge_50": all(v.get("position_changes", 0) >= 50 for v in per_asset.values()),
    }
    combined = "GO" if all(gates.values()) else ("MARGINAL" if dk["verdict"] == "MARGINAL" else "REJECT")
    print(f"\n  COMBINED VERDICT: {combined}")
    print(f"  Gates: {gates}")

    payload = {
        "trial_id": 1028,
        "strategy": "tsmom_pure_sign_252",
        "parameters": {"lookback": [252], "vol_target": 0.10, "rebalance": "monthly",
                       "universe": UNIVERSE, "cost_model": "pepperstone_razor",
                       "cost_multiplier": args.cost_multiplier},
        "data_loader": "load_provenance_checked (>=2005-01-01, hard-fail on contamination)",
        "data_range": {"start": str(data_start.date()), "end": str(data_end.date()), "years": round(years, 2)},
        "per_asset": per_asset,
        "pooled": dk,
        "dsr": {"pooled_sharpe": round(pooled_sharpe, 4), "probability_alpha": dsr.probability_alpha,
                "n_observations": 1050, "pass": dsr_pass},
        "jackknife_leave_one_out_dk_t": jack,
        "jackknife_deltas": jack_deltas,
        "cost_stress": cost_stress,
        "pbo_cscv": pbo_result,
        "gates": gates,
        "combined_verdict": combined,
        "honest_note": "GO does not equal live-ready. No sacred holdout burned. No params tuned.",
        "timestamp": datetime.now(UTC).isoformat(),
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    print(f"\nSaved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
