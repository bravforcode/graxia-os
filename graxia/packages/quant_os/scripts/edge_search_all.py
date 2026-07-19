"""
Unified Edge Search — Pooled DK-test across all single-asset OHLCV strategies
==============================================================================
Honest search: same universe, same costs, same DK threshold as prior pooled tests.
Does NOT burn sacred holdout. Does NOT claim live edge without GO + label-shuffle.

GO criteria (pre-registered, same as pooled_trend_test.py):
  dk_t > 2.0 AND positive_sharpe_count >= 5  → GO
  dk_t > 1.5 OR (dk_t > 1.0 AND pos >= 4)    → MARGINAL
  else                                        → REJECT

Usage:
  python scripts/edge_search_all.py
  python scripts/edge_search_all.py --only HybridMomMR,VolumeBreakout
  python scripts/edge_search_all.py --no-btc
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import traceback
from datetime import UTC, datetime
from decimal import Decimal
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

# Pre-registered universe (same as prior pooled tests + liquid extras with D1 data)
CORE_UNIVERSE = [
    "XAUUSD",
    "XAGUSD",
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "NAS100",
    "US30",
    "BTCUSD",
]
EXTRA_UNIVERSE = ["AUDUSD", "USDCHF", "USDCAD", "ETHUSD"]

SYMBOL_SPREAD_PIPS: dict[str, float] = {
    "XAUUSD": 100.0,
    "XAGUSD": 150.0,
    "EURUSD": 1.2,
    "GBPUSD": 1.5,
    "USDJPY": 1.2,
    "NAS100": 120.0,
    "US30": 120.0,
    "BTCUSD": 5000.0,
    "AUDUSD": 1.5,
    "USDCHF": 1.5,
    "USDCAD": 1.8,
    "ETHUSD": 3000.0,
}

SYMBOL_COMMISSION: dict[str, float] = {
    "XAUUSD": 0.0,
    "XAGUSD": 0.0,
    "EURUSD": 7.0,
    "GBPUSD": 7.0,
    "USDJPY": 7.0,
    "NAS100": 5.0,
    "US30": 5.0,
    "BTCUSD": 0.0,
    "AUDUSD": 7.0,
    "USDCHF": 7.0,
    "USDCAD": 7.0,
    "ETHUSD": 0.0,
}

# Minimum bars after 2005 filter — skip symbol if data too short
MIN_BARS = 500


def load_asset_data(symbol: str) -> pd.DataFrame:
    path = ROOT / "data" / f"{symbol}_D1.csv"
    if not path.exists():
        raise FileNotFoundError(f"missing {path}")
    df = pd.read_csv(path)
    ts_col = "time" if "time" in df.columns else "date"
    df[ts_col] = pd.to_datetime(df[ts_col])
    df = df[df[ts_col] >= "2005-01-01"].sort_values(ts_col).reset_index(drop=True)
    if "time" not in df.columns and ts_col != "time":
        df = df.rename(columns={ts_col: "time"})
    if len(df) < MIN_BARS:
        raise ValueError(f"{symbol}: only {len(df)} bars (< {MIN_BARS})")
    return df


def _trade_pnl(t) -> float:
    if isinstance(t, dict):
        return float(t.get("pnl", t.get("net_pnl", 0)))
    return float(getattr(t, "pnl", 0))


def _trade_exit_time(t):
    if isinstance(t, dict):
        ts = t.get("exit_time")
    else:
        ts = getattr(t, "exit_time", None)
    if ts is None:
        return None
    return pd.Timestamp(ts)


def reconstruct_equity_from_trades(
    trades: list,
    initial_capital: float = 10000.0,
) -> list[dict]:
    """Build equity points from trade exits.

    Engine Phase-4 path may leave equity_curve empty (uses RealTimePnLTracker
    without appending EquityPoint). Trade ledger is authoritative.
    """
    if not trades:
        return [{"timestamp": pd.Timestamp("2005-01-01"), "equity": initial_capital, "balance": initial_capital}]

    sorted_trades = sorted(
        [t for t in trades if _trade_exit_time(t) is not None],
        key=_trade_exit_time,
    )
    equity = float(initial_capital)
    points = [
        {"timestamp": _trade_exit_time(sorted_trades[0]) - pd.Timedelta(days=1), "equity": equity, "balance": equity}
    ]
    for t in sorted_trades:
        equity += _trade_pnl(t)
        points.append(
            {
                "timestamp": _trade_exit_time(t),
                "equity": equity,
                "balance": equity,
            }
        )
    return points


# ---------------------------------------------------------------------------
# External data loaders for Path B strategies
# ---------------------------------------------------------------------------

def _load_fred_series(series_id: str) -> pd.Series:
    """Load a FRED daily CSV. Returns Series with DatetimeIndex."""
    path = ROOT / "data" / "fred" / "daily" / f"{series_id}.csv"
    if not path.exists():
        return pd.Series(dtype=float, name=series_id)
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.columns = [series_id]
    return df[series_id].dropna()


def _load_gvz() -> pd.Series:
    """Load GVZ (Gold VIX) from FRED GVZCLS.csv. Returns Series with DatetimeIndex."""
    return _load_fred_series("GVZCLS")


def _load_dxy() -> pd.DataFrame:
    """Load DXY daily OHLCV. Returns DataFrame with DatetimeIndex."""
    path = ROOT / "data" / "DXY_D1.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path)
    ts_col = "time" if "time" in df.columns else "date"
    df[ts_col] = pd.to_datetime(df[ts_col])
    df = df.set_index(ts_col).sort_index()
    return df


def _load_interest_rates() -> tuple[pd.Series, pd.Series]:
    """Load US 10Y (DGS10) and 2Y (DGS2) Treasury yields from FRED.

    Returns (base_rate, quote_rate) as aligned Series.
    For carry trade: base = USD (high yield proxy), quote = USD (reference).
    We use DGS10 as the "risk-free" base and DGS2 as short-term reference.
    """
    dgs10 = _load_fred_series("DGS10")
    dgs2 = _load_fred_series("DGS2")
    if dgs10.empty or dgs2.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    # Align on common dates
    aligned = pd.concat([dgs10, dgs2], axis=1).dropna()
    aligned.columns = ["base_rate", "quote_rate"]
    return aligned["base_rate"], aligned["quote_rate"]


def _load_cot_data() -> tuple[pd.Series, pd.Series]:
    """Load CFTC COT parquet files. Returns (cot_dates, net_positioning) as Series.

    Uses Managed Money positions (M_Money_Positions_Long/Short_All) for
    the contrarian signal. net_positioning = MM_Long - MM_Short.
    """
    cot_dir = ROOT / "data" / "cot"
    if not cot_dir.exists():
        return pd.Series(dtype=float), pd.Series(dtype=float)
    frames = []
    for f in sorted(cot_dir.glob("cot_xauusd_*.parquet")):
        try:
            df = pd.read_parquet(f)
            frames.append(df)
        except Exception:
            continue
    if not frames:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    combined = pd.concat(frames)
    # Find date column — prefer Report_Date_as_YYYY-MM-DD
    date_col = "Report_Date_as_YYYY-MM-DD" if "Report_Date_as_YYYY-MM-DD" in combined.columns else None
    if date_col is None:
        for col in combined.columns:
            if "date" in col.lower() and "yy" not in col.lower():
                date_col = col
                break
    if date_col is None:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    combined[date_col] = pd.to_datetime(combined[date_col], errors="coerce")
    combined = combined.dropna(subset=[date_col])
    combined = combined.sort_values(date_col)
    # Find Managed Money positioning
    if "M_Money_Positions_Long_All" in combined.columns and "M_Money_Positions_Short_All" in combined.columns:
        net = combined["M_Money_Positions_Long_All"].astype(float) - combined["M_Money_Positions_Short_All"].astype(float)
    elif "net_positioning" in combined.columns:
        net = combined["net_positioning"].astype(float)
    elif "long" in combined.columns and "short" in combined.columns:
        net = combined["long"].astype(float) - combined["short"].astype(float)
    else:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    dates = combined[date_col]
    return dates, net


def _load_external_indicators(symbol: str, trading_dates: list) -> dict[str, Any]:
    """Load all external data needed by Path B strategies.

    Returns dict that can be merged into engine._precomputed_indicators.
    Data is aligned to trading_dates (forward-filled for non-trading days).
    """
    indicators: dict[str, Any] = {}

    # Always inject timestamps for FOMC strategy
    indicators["_timestamps"] = trading_dates

    # DXY close for CAM strategy
    dxy_df = _load_dxy()
    if not dxy_df.empty:
        dxy_close = dxy_df["close"].reindex(trading_dates, method="ffill")
        indicators["dxy_close"] = dxy_close

    # GVZ for VRP strategy
    gvz = _load_gvz()
    if not gvz.empty:
        gvz_aligned = gvz.reindex(trading_dates, method="ffill")
        indicators["gvz_close"] = gvz_aligned

    # Interest rates for Carry strategy
    base_rate, quote_rate = _load_interest_rates()
    if not base_rate.empty and not quote_rate.empty:
        indicators["base_rate"] = base_rate.reindex(trading_dates, method="ffill")
        indicators["quote_rate"] = quote_rate.reindex(trading_dates, method="ffill")

    # COT data for COT Positioning strategy
    cot_dates, cot_net = _load_cot_data()
    if not cot_dates.empty and not cot_net.empty:
        indicators["cot_dates"] = cot_dates
        indicators["cot_net_positioning"] = cot_net

    return indicators


def _precompute_strategy_signal(strategy, ohlcv: dict, ext: dict, n_bars: int) -> list | None:
    """Pre-compute the full signal series for a Path B strategy ONCE.

    This avoids O(n²) recomputation where the engine calls generate_signal
    with progressively longer ohlcv_data per bar.
    """
    try:
        # Import the strategy's signal computation function directly
        name = type(strategy).__name__
        if name == "CarryStrategy":
            from graxia.packages.quant_os.strategies.carry import compute_carry_signal
            base_rate = ext.get("base_rate")
            quote_rate = ext.get("quote_rate")
            if base_rate is None or quote_rate is None:
                return None
            result = compute_carry_signal(base_rate, quote_rate, strategy.vol_target)
            return result.signal.tolist()

        elif name == "TSMOMStrategy":
            from graxia.packages.quant_os.strategies.tsmom import compute_tsmom_signal
            close = pd.Series(ohlcv.get("close", []), dtype=float)
            result = compute_tsmom_signal(close, strategy.lookbacks, strategy.vol_target)
            return result.signal.tolist()

        elif name == "CrossAssetMomentumStrategy":
            from graxia.packages.quant_os.strategies.cross_asset_momentum import CAMConfig, compute_cam_signals
            xau_close = pd.Series(ohlcv.get("close", []), dtype=float)
            dxy_close = ext.get("dxy_close")
            if dxy_close is None:
                return None
            if isinstance(dxy_close, pd.Series) and len(dxy_close) > len(xau_close):
                dxy_close = dxy_close.iloc[:len(xau_close)].reset_index(drop=True)
            if len(dxy_close) == len(xau_close):
                dxy_close.index = xau_close.index
            config = CAMConfig(window=strategy.window, z_threshold=strategy.z_threshold, hold_days=strategy.hold_days)
            result = compute_cam_signals(xau_close, dxy_close, config)
            return result.signal.tolist()

        elif name == "FOMCDriftStrategy":
            from graxia.packages.quant_os.strategies.fomc_drift import FOMCDriftConfig, compute_fomc_drift_signals
            close = pd.Series(ohlcv.get("close", []), dtype=float)
            high = pd.Series(ohlcv.get("high", []), dtype=float)
            low = pd.Series(ohlcv.get("low", []), dtype=float)
            ts = ext.get("_timestamps")
            if ts is not None and len(ts) == len(close):
                dt_idx = pd.DatetimeIndex(ts)
                close.index = dt_idx
                high.index = dt_idx
                low.index = dt_idx
            config = FOMCDriftConfig(
                drift_window_days=strategy.drift_window_days,
                min_fomc_return=strategy.min_fomc_return,
                max_fomc_return=strategy.max_fomc_return,
                atr_period=strategy.atr_period,
                stop_atr=strategy.stop_atr,
            )
            result = compute_fomc_drift_signals(close, high, low, config)
            return result.signal.tolist()

        elif name == "COTPositioningStrategy":
            from graxia.packages.quant_os.strategies.cot_positioning import COTPositioningConfig, compute_cot_positioning_signals
            cot_dates = ext.get("cot_dates")
            cot_net = ext.get("cot_net_positioning")
            if cot_dates is None or cot_net is None:
                return None
            if isinstance(cot_dates, list):
                cot_dates = pd.Series(cot_dates)
            if isinstance(cot_net, list):
                cot_net = pd.Series(cot_net, dtype=float)
            config = COTPositioningConfig(
                lookback_weeks=strategy.lookback_weeks,
                entry_z=strategy.entry_z,
                exit_z=strategy.exit_z,
                min_hold_weeks=strategy.min_hold_weeks,
                max_hold_weeks=strategy.max_hold_weeks,
            )
            result = compute_cot_positioning_signals(cot_dates, cot_net, config)
            return result.signal.tolist()

        elif name == "VolRiskPremiumStrategy":
            # VRP has inline computation — compute full signal once
            close = pd.Series(ohlcv.get("close", []), dtype=float)
            gvz = ext.get("gvz_close")
            if gvz is None:
                return None
            if isinstance(gvz, list):
                gvz = pd.Series(gvz, dtype=float)
            if isinstance(gvz, pd.Series) and isinstance(close.index, pd.RangeIndex) and not isinstance(gvz.index, pd.RangeIndex):
                gvz = gvz.iloc[:len(close)].reset_index(drop=True)
            elif len(gvz) == len(close) and not gvz.index.equals(close.index):
                gvz.index = close.index
            log_ret = np.log(close / close.shift(1))
            realized_vol = log_ret.rolling(strategy.realized_vol_window).std() * np.sqrt(252)
            gvz_smooth = gvz.rolling(strategy.gvz_smoothing).mean()
            vrp = gvz_smooth - realized_vol
            vrp_mean = vrp.rolling(strategy.vrp_lookback).mean()
            vrp_std = vrp.rolling(strategy.vrp_lookback).std()
            vrp_z = (vrp - vrp_mean) / vrp_std.replace(0, np.nan)
            signal = pd.Series(0, index=close.index, dtype=float)
            mr_entry = vrp_z > strategy.entry_z
            mr_exit = vrp_z < strategy.exit_z
            tf_entry = vrp_z < -strategy.entry_z
            tf_exit = vrp_z > -strategy.exit_z
            in_position = False
            position_dir = 0
            for i in range(len(signal)):
                if pd.isna(vrp_z.iloc[i]):
                    continue
                if not in_position:
                    if mr_entry.iloc[i]:
                        in_position = True
                        position_dir = 1
                    elif tf_entry.iloc[i]:
                        ret_20d = (close.iloc[i] / close.iloc[max(0, i - 20)] - 1) if i >= 20 else 0
                        in_position = True
                        position_dir = 1 if ret_20d > 0 else -1
                else:
                    if position_dir == 1 and mr_exit.iloc[i]:
                        in_position = False
                        position_dir = 0
                    elif position_dir == -1 and tf_exit.iloc[i]:
                        in_position = False
                        position_dir = 0
                signal.iloc[i] = float(position_dir)
            return signal.tolist()

    except Exception as e:
        print(f"  [WARN] _precompute failed for {type(strategy).__name__}: {e}", file=sys.stderr)
    return None


def run_engine_for_asset(symbol: str, strategy) -> dict:
    from graxia.packages.quant_os.backtest.engine import BacktestConfig, BacktestEngine

    df = load_asset_data(symbol)
    ohlcv = {
        "open": df["open"].tolist(),
        "high": df["high"].tolist(),
        "low": df["low"].tolist(),
        "close": df["close"].tolist(),
        "volume": df["volume"].tolist() if "volume" in df.columns else [0.0] * len(df),
    }
    timestamps = df["time"].tolist()

    config = BacktestConfig(
        initial_capital=Decimal("100000"),
        slippage_pips=0.5,
        spread_pips=SYMBOL_SPREAD_PIPS.get(symbol, 2.0),
        commission_per_lot=Decimal(str(SYMBOL_COMMISSION.get(symbol, 3.5))),
        risk_per_trade_bps=100,
        max_positions=1,
        strict_mtf=False,
    )

    engine = BacktestEngine(config)
    engine._symbol = symbol  # Fix Bug #1: thread real symbol through engine
    engine.set_strategy(strategy)
    engine.load_data(ohlcv, timestamps)
    engine._check_risk_halt = lambda: False
    # Prefer classic equity path if Phase-4 tracker leaves curve empty
    engine._pnl_tracker = None

    # Inject external data for Path B strategies that need it
    # Monkey-patch _calculate_indicators to merge external data into precomputed indicators
    if hasattr(strategy, "set_external_data"):
        ext = _load_external_indicators(symbol, timestamps)
        strategy.set_external_data(**ext)

        # Pre-compute the full signal series ONCE (avoids O(n²) recomputation per bar)
        _precomputed_signal = _precompute_strategy_signal(strategy, ohlcv, ext, len(timestamps))

        # Also inject into engine's precomputed indicators so they get auto-sliced per bar
        _orig_calc = engine._calculate_indicators
        _external = {k: v for k, v in ext.items() if k.startswith("_") or k in ("dxy_close", "gvz_close", "base_rate", "quote_rate", "cot_dates", "cot_net_positioning")}

        def _patched_calc(up_to_index):
            result = _orig_calc(up_to_index)
            if result is None:
                result = {}
            # Inject external indicators (lists for proper slicing)
            for k, v in _external.items():
                if isinstance(v, pd.Series):
                    # Convert Series to list for engine slicing
                    result[k] = v.tolist()[:up_to_index + 1]
                elif isinstance(v, list):
                    result[k] = v[:up_to_index + 1]
            # Inject pre-computed signal if available
            if _precomputed_signal is not None:
                result["_precomputed_signal"] = _precomputed_signal[:up_to_index + 1]
            return result

        engine._calculate_indicators = _patched_calc

    results = engine.run()
    trades = results.get("trades", []) or []

    # Prefer live equity_curve; fall back to trade reconstruction
    full_equity = [{"timestamp": p.timestamp, "equity": p.equity, "balance": p.balance} for p in engine.equity_curve]
    if len(full_equity) < 2:
        full_equity = reconstruct_equity_from_trades(trades, initial_capital=100000.0)

    results["_full_equity_curve"] = full_equity
    results["_symbol"] = symbol
    results["_n_bars"] = len(df)
    results["_n_trades"] = len(trades)
    return results


def extract_daily_returns(results: dict) -> pd.DataFrame:
    """Daily returns from equity curve (or trade-reconstructed equity)."""
    equity_curve = results.get("_full_equity_curve", [])
    symbol = results.get("_symbol", "UNKNOWN")
    if len(equity_curve) < 2:
        return pd.DataFrame()

    rows = []
    for i in range(1, len(equity_curve)):
        prev_eq = float(equity_curve[i - 1]["equity"])
        curr_eq = float(equity_curve[i]["equity"])
        ts = equity_curve[i]["timestamp"]
        if isinstance(ts, str):
            ts = pd.Timestamp(ts)
        ret = (curr_eq - prev_eq) / prev_eq if prev_eq > 0 else 0.0
        rows.append({"date": ts.date() if hasattr(ts, "date") else ts, "return": ret})

    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    daily = df.groupby("date")["return"].sum().reset_index()
    daily = daily.set_index("date")
    daily.columns = [symbol]
    return daily


def compute_per_asset_metrics(results: dict) -> dict:
    equity_curve = results.get("_full_equity_curve", [])
    trades = results.get("trades", [])
    if not equity_curve and not trades:
        return {
            "n_trades": 0,
            "n_bars": results.get("_n_bars", 0),
            "sharpe": 0.0,
            "win_pct": 0.0,
            "profit_factor": 0.0,
            "max_dd_pct": 0.0,
            "total_return_pct": 0.0,
        }

    bar_returns = []
    for i in range(1, len(equity_curve)):
        prev_eq = float(equity_curve[i - 1]["equity"])
        curr_eq = float(equity_curve[i]["equity"])
        if prev_eq > 0:
            bar_returns.append((curr_eq - prev_eq) / prev_eq)

    arr = np.array(bar_returns) if bar_returns else np.array([0.0])
    n_obs = len(arr)
    mu = float(arr.mean()) if n_obs else 0.0
    std = float(arr.std(ddof=1)) if n_obs > 1 else 0.0
    # Annualize: if trade-based sparse series, use sqrt(n_trades/years) approx via 252
    sharpe = mu / (std + 1e-10) * math.sqrt(252)

    equity_vals = [float(e["equity"]) for e in equity_curve] if equity_curve else [10000.0]
    peak = equity_vals[0]
    max_dd = 0.0
    for eq in equity_vals:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd

    wins = [t for t in trades if _trade_pnl(t) > 0]
    losses = [t for t in trades if _trade_pnl(t) <= 0]
    total_profit = sum(_trade_pnl(t) for t in wins)
    total_loss = abs(sum(_trade_pnl(t) for t in losses))
    pf = total_profit / total_loss if total_loss > 0 else (999.0 if total_profit > 0 else 0.0)
    win_pct = len(wins) / len(trades) * 100 if trades else 0.0

    return {
        "n_trades": len(trades),
        "n_bars": results.get("_n_bars", n_obs),
        "sharpe": round(sharpe, 4),
        "win_pct": round(win_pct, 2),
        "profit_factor": round(pf, 4) if pf < 100 else 99.99,
        "max_dd_pct": round(max_dd * 100, 2),
        "total_return_pct": round((equity_vals[-1] / equity_vals[0] - 1) * 100, 2) if equity_vals else 0.0,
    }


def run_dk_test(all_returns: pd.DataFrame, total_trades: int) -> dict:
    if all_returns.empty or len(all_returns.columns) < 2:
        return {
            "dk_t_stat": 0.0,
            "pooled_sharpe": 0.0,
            "positive_sharpe_count": 0,
            "total_assets": len(all_returns.columns) if not all_returns.empty else 0,
            "total_days": 0,
            "total_trades": total_trades,
            "verdict": "INSUFFICIENT_DATA",
        }

    cs_mean = all_returns.mean(axis=1).dropna()
    if len(cs_mean) < 30:
        return {
            "dk_t_stat": 0.0,
            "pooled_sharpe": 0.0,
            "positive_sharpe_count": 0,
            "total_assets": len(all_returns.columns),
            "total_days": len(cs_mean),
            "total_trades": total_trades,
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
        "total_assets": len(all_returns.columns),
        "total_days": T,
        "total_trades": total_trades,
        "verdict": verdict,
    }


def strategy_registry() -> list[tuple[str, callable]]:
    """Pre-registered strategy factories. Params frozen before seeing results.

    ponytail: each import wrapped in try/except so missing strategy files
    don't crash the entire search. Skipped strategies logged to stderr.
    """
    import importlib

    def _try_import(module_name: str, cls_name: str):
        try:
            mod = importlib.import_module(module_name)
            return getattr(mod, cls_name)
        except (ImportError, AttributeError) as e:
            print(f"  [SKIP] {module_name}.{cls_name}: {e}", file=sys.stderr)
            return None

    BollingerSqueeze = _try_import("graxia.packages.quant_os.strategies.bollinger_squeeze", "BollingerSqueeze")
    DonchianBreakout = _try_import("graxia.packages.quant_os.strategies.donchian", "DonchianBreakout")
    DonchianADX = _try_import("graxia.packages.quant_os.strategies.donchian_adx", "DonchianADX")
    HybridMomMR = _try_import("graxia.packages.quant_os.strategies.hybrid_mom_mr", "HybridMomMR")
    LiquiditySweepStrategy = _try_import("graxia.packages.quant_os.strategies.liquidity_sweep", "LiquiditySweepStrategy")
    Momentum12M = _try_import("graxia.packages.quant_os.strategies.momentum_12m", "Momentum12M")
    MeanReversionBollinger = _try_import("graxia.packages.quant_os.strategies.mrb", "MeanReversionBollinger")
    MultiTimeframeMomentum = _try_import("graxia.packages.quant_os.strategies.mtm", "MultiTimeframeMomentum")
    RSIMeanReversion = _try_import("graxia.packages.quant_os.strategies.rsi_mean_reversion", "RSIMeanReversion")
    VolumeBreakout = _try_import("graxia.packages.quant_os.strategies.volume_breakout", "VolumeBreakout")

    # Path B wrappers (carry/vol/cross-asset)
    TSMOMStrategy = _try_import("graxia.packages.quant_os.strategies.path_b_wrappers", "TSMOMStrategy")
    CrossAssetMomentumStrategy = _try_import("graxia.packages.quant_os.strategies.path_b_wrappers", "CrossAssetMomentumStrategy")
    FOMCDriftStrategy = _try_import("graxia.packages.quant_os.strategies.path_b_wrappers", "FOMCDriftStrategy")
    VolRiskPremiumStrategy = _try_import("graxia.packages.quant_os.strategies.path_b_wrappers", "VolRiskPremiumStrategy")
    CarryStrategy = _try_import("graxia.packages.quant_os.strategies.path_b_wrappers", "CarryStrategy")
    COTPositioningStrategy = _try_import("graxia.packages.quant_os.strategies.path_b_wrappers", "COTPositioningStrategy")
    DXYDivergence = _try_import("graxia.packages.quant_os.strategies.dxy_divergence", "DXYDivergence")

    _raw = [
        # --- previously tested (re-run for ranking consistency) ---
        (
            "RSI_25_75",
            lambda: RSIMeanReversion(
                rsi_period=14,
                oversold=25,
                overbought=75,
                ema_period=0,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
            ),
        ),
        (
            "RSI_30_70",
            lambda: RSIMeanReversion(
                rsi_period=14,
                oversold=30,
                overbought=70,
                ema_period=0,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
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
            "Donchian_55",
            lambda: DonchianBreakout(
                period=55,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
                vol_filter=True,
                vol_filter_pctile=0.7,
            ),
        ),
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
            "BollingerSqueeze_p20",
            lambda: BollingerSqueeze(
                bb_period=20,
                bb_std=2.0,
                squeeze_lookback=120,
                squeeze_pctile=0.2,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
            ),
        ),
        # --- untested single-asset OHLCV ---
        (
            "Momentum12M_252",
            lambda: Momentum12M(
                lookback=252,
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
            "HybridMomMR_20",
            lambda: HybridMomMR(
                lookback=20,
                atr_period=14,
                atr_sl_mult=2.0,
                atr_tp_mult=3.0,
            ),
        ),
        (
            "VolumeBreakout_2.0",
            lambda: VolumeBreakout(
                lookback=20,
                volume_threshold=2.0,
            ),
        ),
        (
            "VolumeBreakout_1.5",
            lambda: VolumeBreakout(
                lookback=20,
                volume_threshold=1.5,
            ),
        ),
        ("LiquiditySweep", lambda: LiquiditySweepStrategy()),
        ("MRB_default", lambda: MeanReversionBollinger()),
        ("MTM_default", lambda: MultiTimeframeMomentum()),
        # --- Path B: carry / vol / cross-asset ---
        ("TSMOM_default", lambda: TSMOMStrategy()),
        ("CAM_default", lambda: CrossAssetMomentumStrategy()),
        ("FOMC_default", lambda: FOMCDriftStrategy()),
        ("VRP_default", lambda: VolRiskPremiumStrategy()),
        ("Carry_default", lambda: CarryStrategy()),
        ("COT_default", lambda: COTPositioningStrategy()),
        ("DXYDiv_default", lambda: DXYDivergence()),
    ]

    # ponytail: skip strategies whose import failed (None classes)
    _null_classes = {name for name, cls in {
        "RSIMeanReversion": RSIMeanReversion,
        "DonchianBreakout": DonchianBreakout,
        "DonchianADX": DonchianADX,
        "BollingerSqueeze": BollingerSqueeze,
        "Momentum12M": Momentum12M,
        "HybridMomMR": HybridMomMR,
        "VolumeBreakout": VolumeBreakout,
        "LiquiditySweepStrategy": LiquiditySweepStrategy,
        "MeanReversionBollinger": MeanReversionBollinger,
        "MultiTimeframeMomentum": MultiTimeframeMomentum,
        "TSMOMStrategy": TSMOMStrategy,
        "CrossAssetMomentumStrategy": CrossAssetMomentumStrategy,
        "FOMCDriftStrategy": FOMCDriftStrategy,
        "VolRiskPremiumStrategy": VolRiskPremiumStrategy,
        "CarryStrategy": CarryStrategy,
        "COTPositioningStrategy": COTPositioningStrategy,
        "DXYDivergence": DXYDivergence,
    }.items() if cls is None}

    def _safe_factory(cls, *args, **kwargs):
        if cls is None:
            return None
        return cls(*args, **kwargs)

    result = []
    for name, factory in _raw:
        # Check if any null class would be called — skip by wrapping
        try:
            # Quick test: call factory in a try to see if it raises ImportError
            test = factory()
            if test is not None:
                result.append((name, factory))
            else:
                print(f"  [SKIP] {name}: class is None", file=sys.stderr)
        except (ImportError, NameError, TypeError) as e:
            print(f"  [SKIP] {name}: {e}", file=sys.stderr)
    return result


def run_variant(name: str, factory, universe: list[str]) -> dict:
    print(f"\n{'=' * 64}")
    print(f"  Strategy: {name}")
    print(f"{'=' * 64}")

    all_returns = pd.DataFrame()
    total_trades = 0
    per_asset: dict = {}

    for sym in universe:
        print(f"  {sym}...", end=" ", flush=True)
        try:
            strategy = factory()
            results = run_engine_for_asset(sym, strategy)
            metrics = compute_per_asset_metrics(results)
            per_asset[sym] = metrics
            total_trades += metrics.get("n_trades", 0)
            daily_ret = extract_daily_returns(results)
            if not daily_ret.empty:
                all_returns = pd.concat([all_returns, daily_ret], axis=1)
            print(
                f"bars={metrics.get('n_bars', 0)} trades={metrics.get('n_trades', 0)} "
                f"sharpe={metrics.get('sharpe', 0):.3f} maxdd={metrics.get('max_dd_pct', 0):.1f}%"
            )
        except Exception as e:
            print(f"ERROR: {e}")
            per_asset[sym] = {"error": str(e)}

    dk = run_dk_test(all_returns, total_trades)
    dk["per_asset"] = per_asset
    dk["strategy"] = name

    print(f"\n  Total trades: {total_trades}")
    print(f"  DK t-stat:    {dk.get('dk_t_stat', 0)}")
    print(f"  Pooled Sharpe:{dk.get('pooled_sharpe', 0)}")
    print(f"  Pos Sharpe:   {dk.get('positive_sharpe_count', 0)}/{dk.get('total_assets', 0)}")
    print(f"  VERDICT:      {dk.get('verdict', '?')}")
    return dk


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified edge search (DK pooled)")
    parser.add_argument("--only", type=str, default="", help="Comma-separated strategy names")
    parser.add_argument("--no-btc", action="store_true", help="Exclude BTCUSD/ETHUSD")
    parser.add_argument("--extras", action="store_true", help="Include AUD/CHF/CAD/ETH")
    parser.add_argument(
        "--out",
        type=str,
        default=str(ROOT / "reports" / "edge_search_all_results.json"),
    )
    args = parser.parse_args()

    universe = list(CORE_UNIVERSE)
    if args.extras:
        universe.extend(EXTRA_UNIVERSE)
    if args.no_btc:
        universe = [s for s in universe if s not in ("BTCUSD", "ETHUSD")]

    # Validate data availability up front
    usable = []
    for s in universe:
        try:
            df = load_asset_data(s)
            usable.append(s)
            print(f"  data OK {s}: {len(df)} bars")
        except Exception as e:
            print(f"  data SKIP {s}: {e}")
    universe = usable
    if len(universe) < 3:
        print("FATAL: need >= 3 assets with data")
        return 1

    variants = strategy_registry()
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        variants = [(n, f) for n, f in variants if n in wanted]
        if not variants:
            print(f"FATAL: no strategies match --only {wanted}")
            return 1

    print(f"\nEdge search start: {datetime.now(UTC).isoformat()}")
    print(f"Universe ({len(universe)}): {universe}")
    print(f"Strategies: {len(variants)}")
    print("GO rule: dk_t>2.0 AND pos_sharpe>=5")

    all_results: dict = {}
    for name, factory in variants:
        try:
            all_results[name] = run_variant(name, factory, universe)
        except Exception as e:
            print(f"\n  FATAL on {name}: {e}")
            traceback.print_exc()
            all_results[name] = {
                "strategy": name,
                "verdict": "ERROR",
                "error": str(e),
                "dk_t_stat": 0.0,
            }

    # Rank by dk_t
    ranked = sorted(
        all_results.items(),
        key=lambda kv: float(kv[1].get("dk_t_stat") or 0),
        reverse=True,
    )

    print(f"\n{'=' * 72}")
    print("  EDGE SEARCH SUMMARY — ranked by DK t-stat")
    print(f"{'=' * 72}")
    print(f"  {'Strategy':<28} {'Trades':>7} {'DK-t':>8} {'Sharpe':>8} {'Pos':>6} {'Verdict':<12}")
    print(f"  {'-' * 70}")
    for name, r in ranked:
        print(
            f"  {name:<28} {r.get('total_trades', 0):>7} "
            f"{float(r.get('dk_t_stat') or 0):>8.3f} "
            f"{float(r.get('pooled_sharpe') or 0):>8.3f} "
            f"{r.get('positive_sharpe_count', 0):>3}/{r.get('total_assets', 0):<2} "
            f"{r.get('verdict', '?'):<12}"
        )

    go = [n for n, r in ranked if r.get("verdict") == "GO"]
    marginal = [n for n, r in ranked if r.get("verdict") == "MARGINAL"]
    print(f"\n  GO:       {go or 'NONE'}")
    print(f"  MARGINAL: {marginal or 'NONE'}")
    print(
        f"  Best:     {ranked[0][0] if ranked else 'NONE'} "
        f"(dk_t={ranked[0][1].get('dk_t_stat') if ranked else 'n/a'})"
    )

    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "universe": universe,
        "go_rule": "dk_t>2.0 AND positive_sharpe_count>=5",
        "marginal_rule": "dk_t>1.5 OR (dk_t>1.0 AND pos>=4)",
        "n_strategies_tested": len(all_results),
        "go": go,
        "marginal": marginal,
        "ranked": [
            {
                "strategy": n,
                "dk_t_stat": r.get("dk_t_stat"),
                "pooled_sharpe": r.get("pooled_sharpe"),
                "total_trades": r.get("total_trades"),
                "positive_sharpe_count": r.get("positive_sharpe_count"),
                "total_assets": r.get("total_assets"),
                "verdict": r.get("verdict"),
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
    print(f"\n  Saved: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
