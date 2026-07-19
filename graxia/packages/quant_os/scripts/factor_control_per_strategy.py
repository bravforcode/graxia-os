"""
Factor-Control Per-Strategy: R² of each strategy's XAUUSD returns vs DXY/VIX/SPX
================================================================================
Runs each strategy on XAUUSD D1, extracts daily returns, computes R² against factors.
"""
import json
import sys
import importlib
from pathlib import Path
from decimal import Decimal

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
GRAXIA_ROOT = ROOT.parent.parent.parent
for p in (str(GRAXIA_ROOT), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


def load_returns(csv_path, date_col="time", close_col="close"):
    df = pd.read_csv(csv_path)
    date_col_found = None
    for c in [date_col, "date", "Date"]:
        if c in df.columns:
            date_col_found = c
            break
    if date_col_found is None:
        date_col_found = df.columns[0]
    df[date_col_found] = pd.to_datetime(df[date_col_found])
    df = df.sort_values(date_col_found)
    df["_date"] = df[date_col_found].dt.date
    df = df.drop_duplicates("_date", keep="last").set_index("_date")
    # Auto-detect close column
    close_col = None
    for c in ["close", "Close", "CLOSE", "price", "Price"]:
        if c in df.columns:
            close_col = c
            break
    if close_col is None:
        close_col = df.columns[1]
    vals = pd.to_numeric(df[close_col], errors="coerce").dropna()
    return vals.pct_change().dropna()


def run_strategy_on_xauusd(strategy_factory, strategy_name):
    """Run a strategy on XAUUSD D1 and return daily returns series."""
    from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine

    data_path = ROOT / "data" / "XAUUSD_D1.csv"
    df = pd.read_csv(data_path)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    df = df[df["time"] >= "2005-01-01"].reset_index(drop=True)

    ohlcv = {
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
        "volume": df["volume"].tolist(),
    }
    timestamps = df["time"].tolist()

    config = BacktestConfig(
        initial_capital=Decimal("10000"),
        slippage_pips=0.5,
        spread_pips=100.0,  # XAUUSD spread
        commission_per_lot=Decimal("0.0"),
        risk_per_trade_bps=100,
        max_positions=1,
        strict_mtf=False,
    )

    strategy = strategy_factory()
    engine = BacktestEngine(config)
    engine._symbol = "XAUUSD"
    engine.set_strategy(strategy)
    engine.load_data(ohlcv, timestamps)
    engine._check_risk_halt = lambda: False

    results = engine.run()

    # Extract equity curve as daily returns
    equity_curve = engine.equity_curve
    if not equity_curve or len(equity_curve) < 30:
        return None

    eq = pd.Series(
        [float(p.equity) for p in equity_curve],
        index=[p.timestamp.date() if hasattr(p.timestamp, 'date') else p.timestamp for p in equity_curve],
    )
    # Handle duplicate dates by keeping last
    eq = eq[~eq.index.duplicated(keep='last')]
    returns = eq.pct_change().dropna()
    returns.name = strategy_name
    return returns


def compute_r2(y, x):
    aligned = pd.concat([y, x], axis=1).dropna()
    if len(aligned) < 30:
        return None, 0
    corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1])
    r2 = float(corr ** 2) if not np.isnan(corr) else None
    return r2, len(aligned)


def main():
    data_dir = ROOT / "data"

    # Load factors
    factors = {}
    for name, path in {
        "DXY": data_dir / "DXY_D1.csv",
        "VIX": data_dir / "market_data" / "yfinance" / "_VIX.csv",
        "SPX": data_dir / "market_data" / "yfinance" / "_GSPC.csv",
    }.items():
        if path.exists():
            factors[name] = load_returns(path)

    if not factors:
        print("FATAL: no factor data")
        return 1

    # Strategy factories (same as edge_search_all.py)
    def _try_import(module_name, cls_name):
        try:
            mod = importlib.import_module(module_name)
            return getattr(mod, cls_name)
        except Exception:
            return None

    strategies = {}
    for name, mod, cls in [
        ("RSI_25_75", "strategies.rsi_mean_reversion", "RSIMeanReversion"),
        ("RSI_30_70", "strategies.rsi_mean_reversion", "RSIMeanReversion"),
        ("RSI_20_80", "strategies.rsi_mean_reversion", "RSIMeanReversion"),
        ("Donchian_20", "strategies.donchian", "DonchianBreakout"),
        ("Donchian_55", "strategies.donchian", "DonchianBreakout"),
        ("Donchian_10", "strategies.donchian", "DonchianBreakout"),
        ("DonchianADX_10_25", "strategies.donchian_adx", "DonchianADX"),
        ("BollingerSqueeze_p20", "strategies.bollinger_squeeze", "BollingerSqueeze"),
        ("Momentum12M_252", "strategies.momentum_12m", "Momentum12M"),
        ("Momentum12M_126", "strategies.momentum_12m", "Momentum12M"),
        ("HybridMomMR_60", "strategies.hybrid_mom_mr", "HybridMomMR"),
        ("HybridMomMR_20", "strategies.hybrid_mom_mr", "HybridMomMR"),
        ("VolumeBreakout_2.0", "strategies.volume_breakout", "VolumeBreakout"),
        ("VolumeBreakout_1.5", "strategies.volume_breakout", "VolumeBreakout"),
        ("LiquiditySweep", "strategies.liquidity_sweep", "LiquiditySweepStrategy"),
        ("MRB_default", "strategies.mrb", "MeanReversionBollinger"),
    ]:
        cls_obj = _try_import(f"graxia.packages.quant_os.{mod}", cls)
        if cls_obj is None:
            continue
        strategies[name] = (cls_obj, name)

    # Parameter overrides for specific variants
    param_overrides = {
        "RSI_25_75": {"rsi_period": 14, "oversold": 25, "overbought": 75, "ema_period": 0, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
        "RSI_30_70": {"rsi_period": 14, "oversold": 30, "overbought": 70, "ema_period": 0, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
        "RSI_20_80": {"rsi_period": 14, "oversold": 20, "overbought": 80, "ema_period": 0, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
        "Donchian_20": {"period": 20, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "vol_filter": True, "vol_filter_pctile": 0.7},
        "Donchian_55": {"period": 55, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "vol_filter": True, "vol_filter_pctile": 0.7},
        "Donchian_10": {"period": 10, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "vol_filter": False},
        "DonchianADX_10_25": {"period": 10, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0, "adx_period": 14, "adx_threshold": 25.0},
        "BollingerSqueeze_p20": {"bb_period": 20, "bb_std": 2.0, "squeeze_lookback": 120, "squeeze_pctile": 0.2, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
        "Momentum12M_252": {"lookback": 252, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
        "Momentum12M_126": {"lookback": 126, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
        "HybridMomMR_60": {"lookback": 60, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
        "HybridMomMR_20": {"lookback": 20, "atr_period": 14, "atr_sl_mult": 2.0, "atr_tp_mult": 3.0},
        "VolumeBreakout_2.0": {"lookback": 20, "volume_threshold": 2.0},
        "VolumeBreakout_1.5": {"lookback": 20, "volume_threshold": 1.5},
        "LiquiditySweep": {},
        "MRB_default": {},
    }

    print("=" * 80)
    print("  Factor-Control Per-Strategy: R² vs DXY/VIX/SPX")
    print("=" * 80)
    print()

    results = {}
    for name, (cls_obj, sname) in strategies.items():
        params = param_overrides.get(name, {})
        try:
            factory = lambda c=cls_obj, p=params: c(**p)
            returns = run_strategy_on_xauusd(factory, name)
            if returns is None or len(returns) < 30:
                print(f"  {name:25s}: SKIP (insufficient data)")
                continue

            r2s = {}
            for fname, fdata in factors.items():
                r2, n = compute_r2(returns, fdata)
                r2s[fname] = {"r2": round(r2, 4) if r2 is not None else None, "n": n}

            high = [f for f, v in r2s.items() if v["r2"] is not None and v["r2"] > 0.30]
            flag = f" ** HIGH: {', '.join(high)} **" if high else ""
            dxy_r2 = r2s.get("DXY", {}).get("r2", "N/A")
            vix_r2 = r2s.get("VIX", {}).get("r2", "N/A")
            spx_r2 = r2s.get("SPX", {}).get("r2", "N/A")
            print(f"  {name:25s}: DXY={dxy_r2}  VIX={vix_r2}  SPX={spx_r2}{flag}")
            results[name] = r2s

        except Exception as e:
            print(f"  {name:25s}: ERROR {e}")

    # Save
    out_path = ROOT / "reports" / "factor_control_per_strategy.json"
    with open(out_path, "w") as f:
        json.dump({
            "analysis": "Factor-Control Per-Strategy",
            "description": "R² of each strategy's XAUUSD daily returns vs DXY/VIX/SPX",
            "threshold": 0.30,
            "results": results,
        }, f, indent=2)
    print(f"\n  Saved: {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
