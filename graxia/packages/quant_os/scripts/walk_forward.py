#!/usr/bin/env python3
"""
WALK-FORWARD VALIDATION — N sequential folds, single 70/30 split not enough.
Self-contained: trains XGBoost, evaluates with real costs, aggregates across folds.
"""

import argparse, json, os, warnings
import numpy as np
import pandas as pd
import xgboost as xgb

warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, "artifacts", "walk_forward")
FEAT_DIR = os.path.join(BASE, "artifacts", "features_v2")


def load_features(symbol: str, freq: str) -> pd.DataFrame:
    # Try v2 naming first, then fallback to v1 naming
    path_v2 = os.path.join(FEAT_DIR, f"features_v2_{symbol}_{freq}.parquet")
    path_v1 = os.path.join(FEAT_DIR, f"features_{symbol}_{freq}.parquet")
    path = path_v2 if os.path.exists(path_v2) else path_v1
    df = pd.read_parquet(path)
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    # Ensure target is int binary
    if df["target"].dtype in (np.float64, np.float32):
        df["target"] = df["target"].astype(int)
    # Handle {-1, 0, 1} → {0, 1} if needed
    if df["target"].min() < 0:
        df = df[df["target"] != 0].copy()
        df["target"] = df["target"].replace({-1: 0, 1: 1})
    print(f"  [OK] {len(df)} rows x {len(df.columns)} cols")
    return df


def get_feature_cols(df: pd.DataFrame) -> list[str]:
    exclude = {
        "target", "target_return", "symbol", "freq",
        "tb_label", "tb_bar_hit", "tb_side", "tb_ret",
        "tb_k_upper", "tb_k_lower", "open", "high", "low", "close",
        "volume", "tick_count",
    }
    available = set(df.columns)
    exclude &= available
    return [c for c in df.columns if c not in exclude
            and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)]


def compute_fold_pnl(
    returns: np.ndarray, preds: np.ndarray, confs: np.ndarray,
    spread_cost: float, slippage_p90: float,
    min_confidence: float = 0.85,
    mask: np.ndarray | None = None,
    close_prices: np.ndarray | None = None,
) -> dict:
    """
    Compute net P&L for a single fold's test predictions.

    Uses actual bar close prices for dollar PnL conversion.
    Requires close_prices to be provided (no hardcoded fallback).

    Args:
        returns: Forward returns array (fractional), same shape as preds.
        preds: Binary predictions (0=short, 1=long).
        confs: Prediction confidence scores.
        spread_cost: Spread cost in return units (fractional).
        slippage_p90: Slippage cost in return units (P90 estimate).
        min_confidence: Minimum confidence threshold for trade entry.
        mask: Optional pre-computed trade selection mask.
        close_prices: Bar close prices for dollar conversion (same shape as returns).
                      Required parameter - no fallback.
    """
    if close_prices is None:
        raise ValueError("close_prices is required for accurate PnL calculation")

    direction = 2 * preds.astype(float) - 1  # 0→-1 (short), 1→+1 (long)
    if mask is None:
        mask = confs >= min_confidence
    n_total = len(preds)
    n_trades = mask.sum()

    if n_trades == 0:
        return {
            "n_trades": 0, "pct_bars": 0.0, "accuracy": 0.0,
            "wins": 0, "losses": 0, "gross_pnl": 0.0,
            "total_cost": 0.0, "net_pnl": 0.0,
            "win_rate": 0.0, "avg_win": 0.0, "avg_loss": 0.0,
            "max_drawdown": 0.0, "sharpe_ratio": 0.0, "avg_move_points": 0.0,
        }

    dir_mask = direction[mask]
    rets = returns[mask]
    confs_masked = confs[mask]

    closes_masked = close_prices[mask]
    assert closes_masked.shape == rets.shape, (
        f"Shape mismatch: close_prices {closes_masked.shape} vs returns {rets.shape}"
    )
    assert closes_masked.min() > 1000, (
        f"Price sanity check failed: min close {closes_masked.min():.2f} < $1000"
    )
    assert closes_masked.max() < 10000, (
        f"Price sanity check failed: max close {closes_masked.max():.2f} > $10000"
    )
    price_mult = float(np.mean(closes_masked))

    raw_pnl_dollars = dir_mask * rets * closes_masked
    cost_per_dollars = (spread_cost + slippage_p90) * price_mult

    net_pnl = raw_pnl_dollars - cost_per_dollars

    accuracy = (dir_mask * rets > 0).mean()
    gross = raw_pnl_dollars.sum()
    total_cost = cost_per_dollars * n_trades
    net = net_pnl.sum()
    win_rate = (net_pnl > 0).mean()
    avg_win = net_pnl[net_pnl > 0].mean() if (net_pnl > 0).sum() > 0 else 0.0
    avg_loss = net_pnl[net_pnl < 0].mean() if (net_pnl < 0).sum() > 0 else 0.0
    cumsum = net_pnl.cumsum()
    max_dd = cumsum.min() if len(cumsum) > 0 else 0.0

    sr_mean = net_pnl.mean() if len(net_pnl) > 0 else 0.0
    sr_std = net_pnl.std() if len(net_pnl) > 1 else 1e-10
    # Use 1440 for FX 24h markets (not 390 which is equity hours)
    sharpe = sr_mean / sr_std * np.sqrt(252 * 1440) if sr_std > 1e-10 else 0.0

    avg_move_points = round(float(np.abs(rets).mean() * price_mult * 100), 1) if len(rets) > 0 else 0.0

    return {
        "n_trades": int(n_trades),
        "pct_bars": round(n_trades / n_total * 100, 2),
        "accuracy": round(float(accuracy), 4),
        "wins": int((dir_mask * rets > 0).sum()),
        "losses": int((dir_mask * rets <= 0).sum()),
        "gross_pnl": round(float(gross), 2),
        "total_cost": round(float(total_cost), 2),
        "net_pnl": round(float(net), 2),
        "win_rate": round(float(win_rate), 4),
        "avg_win": round(float(avg_win), 2),
        "avg_loss": round(float(avg_loss), 2),
        "max_drawdown": round(float(max_dd), 2),
        "sharpe_ratio": round(float(sharpe), 2),
        "avg_move_points": avg_move_points,
    }


def walk_forward(
    df: pd.DataFrame, feature_cols: list[str],
    model_params: dict,
    train_window: int, test_window: int, step: int,
    spread_cost: float, slippage_p90: float,
    min_confidence: float = 0.85,
    min_expected_profit: float = 0.0005,
    per_trade_path: str | None = None,
) -> dict:
    """Run walk-forward. Each fold: train on window, predict on next window."""
    n = len(df)
    folds = []
    data = df[feature_cols].fillna(0).values
    targets = df["target"].values
    returns = df["target_return"].values
    close_array = df["close"].values if "close" in df.columns else None
    y_reg_col = "tb_ret" if "tb_ret" in df.columns else "target_return"
    y_reg = df[y_reg_col].values

    per_trade_records: list[dict] = []
    fold_idx = 0
    while True:
        train_start = fold_idx * step
        train_end = train_start + train_window
        test_end = train_end + test_window
        if test_end > n:
            break

        X_train = data[train_start:train_end]
        y_train_cls = targets[train_start:train_end]
        y_train_reg = y_reg[train_start:train_end]
        X_test = data[train_end:test_end]
        y_test_cls = targets[train_end:test_end]
        ret_test = returns[train_end:test_end]

        # Train classifier
        model = xgb.XGBClassifier(**model_params)
        model.fit(X_train, y_train_cls)
        train_acc = (model.predict(X_train) == y_train_cls).mean()

        # Train magnitude regressor
        mag_model = xgb.XGBRegressor(
            n_estimators=model_params["n_estimators"],
            max_depth=model_params["max_depth"],
            learning_rate=0.1,
            random_state=model_params["random_state"],
            verbosity=0,
        )
        mag_model.fit(X_train, y_train_reg)

        # Predict
        preds = model.predict(X_test)
        proba = model.predict_proba(X_test)
        conf = np.max(proba, axis=1)
        oos_acc = (preds == y_test_cls).mean()

        # Magnitude filter
        mag_pred = mag_model.predict(X_test)
        direction = 2 * preds.astype(float) - 1
        expected_profit = direction * mag_pred * conf
        combined_mask = (conf >= min_confidence) & (expected_profit > min_expected_profit)

        # Collect per-trade data for Gate #2 (mag_pred quality) and #3 (conf accuracy)
        test_times = df.index[train_end:test_end]
        for t_bar in range(len(X_test)):
            per_trade_records.append({
                "fold": fold_idx,
                "timestamp": test_times[t_bar],
                "direction": int(direction[t_bar]),
                "confidence": float(conf[t_bar]),
                "mag_pred": float(mag_pred[t_bar]),
                "realized_return": float(ret_test[t_bar]),
                "expected_profit": float(expected_profit[t_bar]),
                "trade_selected": bool(combined_mask[t_bar]),
                "target": int(y_test_cls[t_bar]),
            })

        # Evaluate
        test_close = close_array[train_end:test_end] if close_array is not None else None
        result = compute_fold_pnl(
            ret_test, preds, conf,
            spread_cost=spread_cost,
            slippage_p90=slippage_p90,
            min_confidence=0.0,
            mask=combined_mask,
            close_prices=test_close,
        )

        result["fold"] = fold_idx
        result["train_start"] = str(df.index[train_start])
        result["train_end"] = str(df.index[train_end - 1])
        result["test_start"] = str(df.index[train_end])
        result["test_end"] = str(df.index[test_end - 1])
        result["train_acc"] = round(float(train_acc), 4)
        result["oos_acc"] = round(float(oos_acc), 4)

        folds.append(result)
        fold_idx += 1

    # Save per-trade data (for Gate #2 mag_pred quality, Gate #3 conf accuracy)
    if per_trade_path and per_trade_records:
        import pandas as pd
        pt_df = pd.DataFrame(per_trade_records)
        out_dir = os.path.dirname(per_trade_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        pt_df.to_parquet(per_trade_path, index=False)
        print(f"  Saved per-trade data: {per_trade_path} ({len(pt_df)} rows)")

    # Aggregate
    total_trades = sum(f["n_trades"] for f in folds)
    total_net = sum(f["net_pnl"] for f in folds)
    positive_folds = sum(1 for f in folds if f["net_pnl"] > 0 and f["n_trades"] >= 3)

    if total_trades > 0:
        weighted_acc = sum(f["accuracy"] * f["n_trades"] for f in folds) / total_trades
    else:
        weighted_acc = 0.0

    fold_nets = [f["net_pnl"] for f in folds]
    mean_net = np.mean(fold_nets) if fold_nets else 0.0
    std_net = np.std(fold_nets) if len(fold_nets) > 1 else 1e-10
    t_stat = mean_net / (std_net / np.sqrt(len(fold_nets))) if std_net > 1e-10 else 0.0

    aggregate = {
        "params": {
            "train_window": train_window,
            "test_window": test_window,
            "step": step,
            "n_folds": len(folds),
            "spread_cost": spread_cost,
            "slippage_p90": slippage_p90,
            "min_confidence": min_confidence,
            "min_expected_profit": min_expected_profit,
        },
        "aggregate": {
            "n_folds": len(folds),
            "positive_folds": int(positive_folds),
            "negative_folds": int(len(folds) - positive_folds),
            "total_trades": int(total_trades),
            "total_net": round(float(total_net), 2),
            "weighted_accuracy": round(float(weighted_acc), 4),
            "avg_net_per_fold": round(float(mean_net), 4),
            "net_stability_t": round(float(t_stat), 4),
            "stable": bool(positive_folds > len(folds) / 2 and total_net > 0),
        },
        "folds": folds,
    }
    return aggregate


def print_results(agg: dict):
    p, a = agg["params"], agg["aggregate"]
    print("=" * 70)
    print("WALK-FORWARD VALIDATION RESULTS")
    print("=" * 70)
    print(f"  Folds: {a['n_folds']}  Windows: train={p['train_window']} test={p['test_window']} step={p['step']}")
    print(f"  Cost: ${p['spread_cost']+p['slippage_p90']:.3f}/trade  Conf>={p['min_confidence']}")
    print()
    print(f"  {'Fold':>4s} | {'TrainAcc':>8s} | {'OOSAcc':>7s} | {'Trades':>6s} | {'Acc':>6s} | {'Gross':>7s} | {'Net':>8s} | {'SR':>6s} |")
    print(f"  {'----':>4s}-+-{'--------':>8s}-+-{'-------':>7s}-+-{'------':>6s}-+-{'------':>6s}-+-{'-------':>7s}-+-{'--------':>8s}-+-{'------':>6s}-+")
    for f in agg["folds"]:
        ok = "*" if f["net_pnl"] > 0 and f["n_trades"] >= 3 else " "
        print(f"  {f['fold']:>4d}{ok} | {f['train_acc']:>.4f}   | {f['oos_acc']:>.4f}  | {f['n_trades']:>6d} | {f['accuracy']:>.4f} | {f['gross_pnl']:>+6.2f}  | {f['net_pnl']:>+7.2f}  | {f['sharpe_ratio']:>+5.1f}  |")

    print()
    print("  === AGGREGATE ===")
    print(f"  Total net:     ${a['total_net']:>+.2f}  ({a['positive_folds']}/{a['n_folds']} folds positive)")
    print(f"  Total trades:  {a['total_trades']}")
    print(f"  Weighted acc:  {a['weighted_accuracy']:.4f}")
    print(f"  Net stability: t={a['net_stability_t']:.2f}")
    if a["stable"]:
        print(f"\n  [OK] EDGE STABLE — {a['positive_folds']}/{a['n_folds']} folds positive, net=${a['total_net']:.2f}")
    else:
        print(f"\n  [WARN] EDGE NOT STABLE — {a['positive_folds']}/{a['n_folds']} folds positive, net=${a['total_net']:.2f}")
    print("=" * 70)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="EURUSD")
    parser.add_argument("--freq", default="1min")
    parser.add_argument("--train-window", type=int, default=500)
    parser.add_argument("--test-window", type=int, default=200)
    parser.add_argument("--step", type=int, default=200)
    parser.add_argument("--spread-cost", type=float, default=0.024)
    parser.add_argument("--slippage-p90", type=float, default=0.02)
    parser.add_argument("--min-confidence", type=float, default=0.85)
    parser.add_argument("--min-expected-profit", type=float, default=0.0005,
        help="Minimum expected profit (return units) to take a trade")
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--n-estimators", type=int, default=100)
    parser.add_argument("--output", default=OUT_DIR)
    parser.add_argument("--cost-config", type=str, default=None,
        help="Path to cost calibration JSON. If provided, overrides --spread-cost and --slippage-p90 per symbol.")
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print("=" * 70)
    print("WALK-FORWARD VALIDATION")
    print(f"  {args.symbol} @ {args.freq}")
    print(f"  Windows: train={args.train_window} test={args.test_window} step={args.step}")
    print(f"  Cost: ${args.spread_cost+args.slippage_p90:.3f}/trade  Conf>={args.min_confidence}")
    print("=" * 70)

    if args.cost_config:
        with open(args.cost_config) as f:
            config = json.load(f)
        if args.symbol in config:
            sym_cfg = config[args.symbol]
            args.spread_cost = sym_cfg["spread_cost_recommended"]
            args.slippage_p90 = sym_cfg["slippage_p90_recommended"]
            print(f"  [Calibrated cost] {args.symbol}: spread={args.spread_cost:.6f}, slippage={args.slippage_p90:.6f}")

    df = load_features(args.symbol, args.freq)
    if "target" not in df.columns or "target_return" not in df.columns:
        print("  [ERROR] Missing target/target_return")
        return

    feature_cols = get_feature_cols(df)
    print(f"  Features: {len(feature_cols)}")

    model_params = {
        "n_estimators": args.n_estimators,
        "max_depth": args.max_depth,
        "learning_rate": 0.1,
        "subsample": 0.8,
        "colsample_bytree": 0.8,
        "random_state": 42,
        "eval_metric": "logloss",
        "use_label_encoder": False,
        "verbosity": 0,
    }

    # Run multiple confidence thresholds if sweep requested
    for conf in [args.min_confidence]:
        print(f"\n--- Conf >= {conf} ---")
        per_trade_path = os.path.join(args.output,
            f"per_trade_{args.symbol}_{args.freq}_{args.train_window}w_{args.test_window}t_conf{conf}.parquet")
        agg = walk_forward(
            df, feature_cols, model_params,
            args.train_window, args.test_window, args.step,
            args.spread_cost, args.slippage_p90,
            min_confidence=conf,
            min_expected_profit=args.min_expected_profit,
            per_trade_path=per_trade_path,
        )
        print_results(agg)

        path = os.path.join(args.output,
            f"wf_{args.symbol}_{args.freq}_{args.train_window}w_{args.test_window}t_conf{conf}.json")
        with open(path, "w") as f:
            json.dump(convert_numpy(agg), f, indent=2)
        print(f"  Saved: {path}")


def convert_numpy(obj):
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
