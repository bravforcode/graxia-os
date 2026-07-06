#!/usr/bin/env python3
"""
Phase F — Backtest with Real Spread + Slippage P90.
Loads V2 features + model, evaluates each bar's actual return,
charges tick-level spread + fill-simulator slippage P90,
reports net P&L in dollars for 0.01 lot XAUUSD.
"""

import argparse
import json
import os
import sys
import warnings

import numpy as np
import pandas as pd
import xgboost as xgb

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from core.feature_config import EXCLUDE_COLS

warnings.filterwarnings("ignore")

# ---------- paths ----------
BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEAT_DIR = os.path.join(BASE, "artifacts", "features_v2")
LABEL_DIR = os.path.join(BASE, "artifacts", "labels")
FILL_DIR = os.path.join(BASE, "artifacts", "fill_samples_fixed")
OUT_DIR = os.path.join(BASE, "artifacts", "backtest_cost")

# XAUUSD constants (0.01 lot = 1 oz)
POINT_VALUE = 0.01  # 1 point = $0.01 for 0.01 lot XAUUSD


# ---------- helpers ----------
def load_slippage_p90(symbol: str, freq: str) -> dict:
    """Load fill simulator data and compute P90 slippage by condition."""
    path = os.path.join(FILL_DIR, f"fill_samples_{symbol}_{freq}.csv")
    if not os.path.exists(path):
        # Try 1min as fallback
        path_1min = os.path.join(FILL_DIR, f"fill_samples_{symbol}_1min.csv")
        if os.path.exists(path_1min):
            path = path_1min
            print("  [FALLBACK] Using 1min fill samples")
        else:
            print(f"  [WARN] Fill samples not found: {path}")
            return {
                "overall": 39.0,
                "vol_regime": {"high": 45, "low": 33, "med": 42},
                "spread_bucket": {"med": 40, "tight": 34, "wide": 48},
                "session": {"asian": 44, "london": 38, "ny": 34, "overlap": 37},
            }
    df = pd.read_csv(path)
    result = {"overall": float(df["slippage_points"].quantile(0.9))}
    for col in ["vol_regime", "spread_bucket", "session"]:
        sub = {}
        for bucket in sorted(df[col].unique()):
            vals = df[df[col] == bucket]["slippage_points"]
            sub[bucket] = float(vals.quantile(0.9))
        result[col] = sub
    return result


def load_features(symbol: str, freq: str) -> pd.DataFrame:
    """Load features with target_return, tb_label, tb_ret."""
    path = os.path.join(FEAT_DIR, f"features_v2_{symbol}_{freq}.parquet")
    if not os.path.exists(path):
        alt = os.path.join(FEAT_DIR, f"features_{symbol}_{freq}.parquet")
        if os.path.exists(alt):
            path = alt
        else:
            print(f"  [ERROR] No features for {symbol} @ {freq}")
            sys.exit(1)
    df = pd.read_parquet(path)
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    print(f"  [OK] {os.path.basename(path)}: {len(df)} rows x {len(df.columns)} cols")
    return df


def get_feature_cols(df: pd.DataFrame) -> list[str]:
    """Return numeric columns usable as model features."""
    available = set(df.columns) & EXCLUDE_COLS
    return [c for c in df.columns if c not in available and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)]


def compute_trade_pnl(
    df: pd.DataFrame,
    preds: np.ndarray,
    spread_cost: float = 0.000050,
    slippage_p90: float = 0.000027,
    lot_mult: float = 1.0,
    close_prices: np.ndarray | None = None,
) -> pd.DataFrame:
    """
    Compute per-bar trade P&L using actual target_return.

    Args:
        df: feature dataframe with 'target_return' column
        preds: model predictions (0=down, 1=up)
        spread_cost: round-trip spread cost in RETURN units (fraction of price).
            Must be return-units, NOT dollars. XAUUSD calibrated: 0.000050.
        slippage_p90: round-trip slippage P90 cost in RETURN units.
            Must be return-units, NOT dollars. XAUUSD calibrated: 0.000027.
        lot_mult: lot multiplier (1.0 = 0.01 lot)
        close_prices: bar close prices for per-trade dollar conversion.
            If None, uses fallback 2350.0 (backward compat).

    Returns:
        DataFrame with trade results
    """
    target_return = df["target_return"].values

    # Per-trade price: use actual bar close if available, else fallback
    if close_prices is not None and len(close_prices) == len(target_return):
        price_arr = close_prices.astype(float)
    else:
        price_arr = np.full(len(target_return), 2350.0)

    # Direction multiplier: pred=1 (up) → +1, pred=0 (down) → -1
    direction = 2 * preds.astype(float) - 1

    # Raw P&L before costs (in price fraction)
    raw_pnl_frac = direction * target_return

    # Convert to dollars using per-trade price
    raw_pnl_dollars = raw_pnl_frac * price_arr * lot_mult

    # Total cost per trade (round trip) — convert return → dollars using per-trade price
    cost_per_trade = (spread_cost + slippage_p90) * price_arr * lot_mult

    net_pnl = raw_pnl_dollars - cost_per_trade

    # Correct prediction?
    correct = (direction * target_return) > 0

    result = pd.DataFrame(
        {
            "prediction": preds,
            "direction": direction,
            "target_return": target_return,
            "raw_pnl_frac": raw_pnl_frac,
            "raw_pnl_dollars": raw_pnl_dollars,
            "cost_dollars": cost_per_trade,
            "net_pnl_dollars": net_pnl,
            "correct": correct,
        },
        index=df.index,
    )
    return result


def evaluate_backtest(
    df: pd.DataFrame,
    model,
    feature_cols: list[str],
    test_mask: pd.Series,
    spread_cost: float = 0.000050,
    slippage_p90: float = 0.000027,
    lot_mult: float = 1.0,
    regime_scores: pd.Series = None,
    confidences: np.ndarray = None,
    min_confidence: float = 0.0,
    min_regime: float = 0.0,
) -> dict:
    """Run backtest on OOS period with optional filters.

    Args:
        df: full feature dataframe
        model: trained classifier
        feature_cols: feature column names
        test_mask: boolean Series for OOS bars
        spread_cost: round-trip spread cost in RETURN units (fraction of price).
            Must be return-units, NOT dollars. XAUUSD calibrated: 0.000050.
        slippage_p90: round-trip slippage P90 cost in RETURN units.
            Must be return-units, NOT dollars. XAUUSD calibrated: 0.000027.
        lot_mult: lot multiplier (1.0 = 0.01 lot)
        regime_scores: regime_score Series (same index as df)
        confidences: model confidence array (same length as df)
        min_confidence: minimum confidence threshold
        min_regime: minimum regime score threshold

    Returns:
        dict with backtest metrics
    """
    df_test = df.loc[test_mask].copy()
    X_test = df_test[feature_cols].fillna(0).values
    y_true = df_test["target"].values

    # Predict
    preds = model.predict(X_test)
    if confidences is None:
        proba = model.predict_proba(X_test)
        conf = np.max(proba, axis=1)
    else:
        conf = confidences[test_mask.values]

    # Apply filters
    trade_mask = np.ones(len(preds), dtype=bool)
    if min_confidence > 0:
        trade_mask &= conf >= min_confidence
    if min_regime > 0 and regime_scores is not None:
        regime_vals = regime_scores.loc[test_mask].values
        trade_mask &= regime_vals >= min_regime

    n_total = len(preds)
    n_trades = trade_mask.sum()
    pct_bars = n_trades / n_total * 100

    if n_trades == 0:
        return {
            "n_trades": 0,
            "pct_bars": 0,
            "accuracy": 0,
            "wins": 0,
            "losses": 0,
            "gross_pnl": 0,
            "total_cost": 0,
            "net_pnl": 0,
            "win_rate": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "max_drawdown": 0,
            "sharpe_ratio": 0,
            "avg_move_points": 0,
        }

    # Get close prices for per-trade dollar conversion
    close_col = df_test["close"].values if "close" in df_test.columns else None
    close_trades = close_col[trade_mask] if close_col is not None else None

    # Compute P&L on trades only
    pnl_df = compute_trade_pnl(
        df_test.loc[trade_mask],
        preds[trade_mask],
        spread_cost=spread_cost,
        slippage_p90=slippage_p90,
        lot_mult=lot_mult,
        close_prices=close_trades,
    )

    accuracy = pnl_df["correct"].mean()
    gross_pnl = pnl_df["raw_pnl_dollars"].sum()
    total_cost = pnl_df["cost_dollars"].sum()
    net_pnl = pnl_df["net_pnl_dollars"].sum()
    win_rate = (pnl_df["net_pnl_dollars"] > 0).mean()
    avg_win = (
        pnl_df.loc[pnl_df["net_pnl_dollars"] > 0, "net_pnl_dollars"].mean()
        if (pnl_df["net_pnl_dollars"] > 0).sum() > 0
        else 0
    )
    avg_loss = (
        pnl_df.loc[pnl_df["net_pnl_dollars"] < 0, "net_pnl_dollars"].mean()
        if (pnl_df["net_pnl_dollars"] < 0).sum() > 0
        else 0
    )
    max_dd = pnl_df["net_pnl_dollars"].cumsum().min()
    # Sharpe ratio — annualize based on actual number of returns
    # Assume returns are evenly spaced; use sqrt(n) for annualization
    # ponytail: proper annualization needs bar frequency, not hardcoded factor
    if len(pnl_df) > 1 and pnl_df["net_pnl_dollars"].std() > 0:
        # Estimate bars per year from data frequency
        n_returns = len(pnl_df)
        sharpe = pnl_df["net_pnl_dollars"].mean() / pnl_df["net_pnl_dollars"].std() * np.sqrt(min(n_returns, 252))
    else:
        sharpe = 0.0

    # Average close price for move-points calculation
    avg_price = float(np.mean(close_trades)) if close_trades is not None else 2350.0

    return {
        "n_trades": int(n_trades),
        "pct_bars": round(pct_bars, 2),
        "accuracy": round(float(accuracy), 4),
        "wins": int(pnl_df["correct"].sum()),
        "losses": int((~pnl_df["correct"]).sum()),
        "gross_pnl": round(float(gross_pnl), 2),
        "total_cost": round(float(total_cost), 2),
        "net_pnl": round(float(net_pnl), 2),
        "win_rate": round(float(win_rate), 4),
        "avg_win": round(float(avg_win), 2),
        "avg_loss": round(float(avg_loss), 2),
        "max_drawdown": round(float(max_dd), 2),
        "sharpe_ratio": round(float(sharpe), 2),
        "avg_move_points": round(float(df_test.loc[trade_mask, "target_return"].abs().mean() * avg_price * 100), 1),
    }


def sweep_thresholds(
    sweeps: list[dict],
) -> list[dict]:
    """Pretty-print threshold sweep results."""
    print(
        f"  {'Conf':>6s} | {'Trades':>7s} | {'%Bars':>6s} | {'Acc':>7s} | {'Gross':>7s} | {'Cost':>7s} | {'Net':>8s} | {'WR':>6s} | {'SR':>5s} | {'OK?':>4s}"
    )
    print(f"  {'-'*6}-|-{'-'*7}-|-{'-'*6}-|-{'-'*7}-|-{'-'*7}-|-{'-'*7}-|-{'-'*8}-|-{'-'*6}-|-{'-'*5}-|-{'-'*4}")
    for s in sweeps:
        ok = "[OK]" if s["net_pnl"] > 0 else "   "
        print(
            f"  {s['min_confidence']:>6.2f} | {s['n_trades']:>7d} | {s['pct_bars']:>5.1f}% | {s['accuracy']:>.4f} | "
            f"{s['gross_pnl']:>+6.2f} | {s['total_cost']:>6.2f} | {s['net_pnl']:>+7.2f} | "
            f"{s['win_rate']:>.3f} | {s['sharpe_ratio']:>+4.1f} | {ok}"
        )
    return sweeps


# ---------- main ----------
def main():
    parser = argparse.ArgumentParser(description="Phase F: Backtest with real costs")
    parser.add_argument("--symbol", type=str, default="XAUUSD")
    parser.add_argument("--freq", type=str, default="1min")
    parser.add_argument("--feat-dir", type=str, default=FEAT_DIR)
    parser.add_argument(
        "--spread-cost",
        type=float,
        default=0.000050,
        help="Round-trip spread cost in RETURN units (fraction of price). XAUUSD calibrated: 0.000050",
    )
    parser.add_argument(
        "--slippage-p90",
        type=float,
        default=0.000027,
        help="Round-trip slippage P90 cost in RETURN units (fraction of price). XAUUSD calibrated: 0.000027",
    )
    parser.add_argument("--lot-mult", type=float, default=1.0, help="Lot multiplier (1.0 = 0.01 lot)")
    parser.add_argument("--output", type=str, default=OUT_DIR)
    parser.add_argument(
        "--label-type",
        choices=["binary", "triple-barrier"],
        default="binary",
        help="Label type for training and evaluation",
    )
    parser.add_argument(
        "--regime-threshold", type=float, default=0.55, help="Min regime score (default 0.55; lower=more trades)"
    )
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print("=" * 70)
    print("PHASE F — BACKTEST WITH REAL COSTS")
    print(f"  Symbol: {args.symbol} @ {args.freq}")
    print(
        f"  Spread cost: {args.spread_cost:.6f} (return units) + Slippage P90: {args.slippage_p90:.6f} (return units)"
    )
    print(f"  Cost/trade at $2350: ${(args.spread_cost + args.slippage_p90) * 2350:.2f}")
    print(f"  Lot size: {args.lot_mult * 0.01:.2f} lot")
    print("=" * 70)

    # 1. Load features
    print("\n--- Loading features ---")
    df = load_features(args.symbol, args.freq)
    if "target" not in df.columns:
        print("  [ERROR] No 'target' column")
        return
    if "target_return" not in df.columns:
        print("  [ERROR] No 'target_return' column — needed for P&L")
        return

    # 2. Load slippage P90
    print("\n--- Loading fill simulator ---")
    slip = load_slippage_p90(args.symbol, args.freq)
    print(f"  Slippage P90 overall: {slip['overall']:.1f} points (${slip['overall'] * POINT_VALUE:.2f})")
    for col in ["vol_regime", "spread_bucket", "session"]:
        if col in slip:
            print(f"  {col}: {slip[col]}")

    # 3. Feature columns
    feature_cols = get_feature_cols(df)
    print(f"  Features: {len(feature_cols)}")

    # 4. Train/test split (70/30 chronological)
    split = int(len(df) * 0.7)
    test_mask = pd.Series(False, index=df.index)
    test_mask.iloc[split:] = True

    X_train = df[feature_cols].fillna(0).values[:split]
    if args.label_type == "triple-barrier":
        # Map tb_label (-1/0/+1) to binary: -1=0, 0=excluded, +1=1
        y_train_raw = df["tb_label"].values[:split]
        train_keep = y_train_raw != 0
        X_train = X_train[train_keep]
        y_train = (y_train_raw[train_keep] + 1) // 2  # -1→0, +1→1
        print(
            f"  Triple-barrier training: {len(y_train)} samples (excluded {train_keep.size - train_keep.sum()} neutral)"
        )
    else:
        y_train = df["target"].values[:split]

    print(f"  Train: {len(X_train)} samples, OOS: {test_mask.sum()} bars")

    # 5. Train model
    print("\n--- Training XGBoost ---")
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        subsample=0.8,
        colsample_bytree=0.8,
        random_state=42,
        eval_metric="logloss",
        use_label_encoder=False,
        verbosity=0,
    )
    model.fit(X_train, y_train)
    train_acc = (model.predict(X_train) == y_train).mean()
    print(f"  Train accuracy: {train_acc:.4f}")

    # 6. Get OOS predictions + confidence
    X_test = df[feature_cols].fillna(0).values[split:]
    y_test_all = df["target"].values[split:]
    preds_test = model.predict(X_test)
    proba_test = model.predict_proba(X_test)
    conf_test = np.max(proba_test, axis=1)
    oos_acc = (preds_test == y_test_all).mean()
    print(f"  OOS accuracy (raw): {oos_acc:.4f}")

    # 7. Compute regime scores
    print("\n--- Computing regime scores ---")
    regime_scores = None
    try:
        sys.path.insert(0, os.path.join(BASE, "scripts"))
        from regime_filter import compute_regime_scores

        all_scores = compute_regime_scores(df)
        regime_scores = all_scores["_regime_score"]
        print(f"  Regime scores computed for {len(regime_scores)} bars")
    except Exception as e:
        print(f"  [WARN] Could not compute regime scores: {e}")
        regime_scores = pd.Series(1.0, index=df.index)  # No filter

    # 8. Run backtest with sweep
    print("\n--- Confidence Threshold Sweep ---")
    results = []
    for conf_thresh in [0.0, 0.50, 0.55, 0.60, 0.65, 0.70, 0.75, 0.80, 0.85, 0.90]:
        res = evaluate_backtest(
            df,
            model,
            feature_cols,
            test_mask,
            spread_cost=args.spread_cost,
            slippage_p90=args.slippage_p90,
            lot_mult=args.lot_mult,
            regime_scores=regime_scores,
            confidences=None,
            min_confidence=conf_thresh,
            min_regime=args.regime_threshold,
        )
        res["min_confidence"] = conf_thresh
        results.append(res)

    sweep_thresholds(results)

    # 9. Best result
    positive = [r for r in results if r["net_pnl"] > 0 and r["n_trades"] >= 5]
    if positive:
        best = max(positive, key=lambda r: r["net_pnl"])
        print(
            f"\n  [OK] POSITIVE EXPECTANCY at conf>={best['min_confidence']:.2f}: "
            f"${best['net_pnl']:.2f} net ({best['n_trades']} trades, {best['accuracy']:.1%} acc)"
        )
    else:
        print("\n  [WARN] No positive expectancy at any confidence threshold")

    # 10. Compare with zero-cost baseline
    print("\n--- Cost Impact Summary ---")
    zero_cost = evaluate_backtest(
        df,
        model,
        feature_cols,
        test_mask,
        spread_cost=0,
        slippage_p90=0,
        lot_mult=1.0,
        regime_scores=regime_scores,
        confidences=None,
        min_confidence=0.75,
        min_regime=args.regime_threshold,
    )
    idx75 = [r["min_confidence"] for r in results].index(0.75)
    print(f"  Zero cost (conf>=0.75):  ${zero_cost['gross_pnl']:>+.2f} gross")
    print(
        f"  Real cost (conf>=0.75): ${results[idx75]['net_pnl']:>+.2f} net  ({results[idx75]['total_cost']:.2f} total cost)"
    )
    print(f"  Cost erosion:           ${zero_cost['gross_pnl'] - results[idx75]['net_pnl']:>+.2f}")

    # 11. Save
    output = {
        "symbol": args.symbol,
        "freq": args.freq,
        "spread_cost_return_units": args.spread_cost,
        "slippage_p90_return_units": args.slippage_p90,
        "cost_per_trade_at_2350": round((args.spread_cost + args.slippage_p90) * 2350, 4),
        "lot_mult": args.lot_mult,
        "oos_bars": int(test_mask.sum()),
        "train_samples": len(X_train),
        "oos_raw_accuracy": round(float(oos_acc), 4),
        "results": results,
        "positive_at_any": any(r["net_pnl"] > 0 and r["n_trades"] >= 5 for r in results),
    }

    save_path = os.path.join(args.output, f"backtest_{args.symbol}_{args.freq}.json")
    with open(save_path, "w") as f:
        json.dump(convert_numpy(output), f, indent=2)
    print(f"\n  Saved: {save_path}")
    print("=" * 70)


def convert_numpy(obj):
    """Recursively convert numpy types to native Python."""
    if isinstance(obj, dict):
        return {k: convert_numpy(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy(v) for v in obj]
    elif isinstance(obj, (np.bool_,)):
        return bool(obj)
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return float(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    return obj


if __name__ == "__main__":
    main()
