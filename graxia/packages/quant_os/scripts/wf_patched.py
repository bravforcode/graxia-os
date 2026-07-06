#!/usr/bin/env python3
"""
WALK-FORWARD VALIDATION — patched for 3-class triple-barrier labels.

DEPRECATED: Use validation.walk_forward.run_walk_forward with label_mode="3class".
This inline implementation will be removed in a future phase.
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

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, "artifacts", "walk_forward")
FEAT_DIR = os.path.join(BASE, "artifacts", "features_v2")


def load_features(symbol: str, freq: str) -> pd.DataFrame:
    path = os.path.join(FEAT_DIR, f"features_v2_{symbol}_{freq}_TB.parquet")
    df = pd.read_parquet(path)
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    print(f"  [OK] {len(df)} rows x {len(df.columns)} cols")
    return df


def get_feature_cols(df: pd.DataFrame) -> list[str]:
    """Get numeric feature columns, excluding centralized EXCLUDE_COLS."""
    available = set(df.columns) & EXCLUDE_COLS
    return [c for c in df.columns if c not in available and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)]


def compute_fold_pnl(
    returns: np.ndarray,
    preds: np.ndarray,
    confs: np.ndarray,
    spread_cost: float,
    slippage_p90: float,
    min_confidence: float = 0.85,
    close_prices: np.ndarray | None = None,
) -> dict:
    """3-class TB labels: 0→-1 short, 1→0 neutral/skip, 2→+1 long.

    DEPRECATED: Use validation.walk_forward.compute_fold_pnl with label_mode="3class".
    """
    if close_prices is None:
        raise ValueError("close_prices is required for accurate PnL calculation")

    direction = np.array([-1.0, 0.0, 1.0])[preds.astype(int)]
    mask = (confs >= min_confidence) & (direction != 0.0)
    n_total = len(preds)
    n_trades = mask.sum()

    if n_trades == 0:
        return {
            "n_trades": 0,
            "pct_bars": 0.0,
            "accuracy": 0.0,
            "wins": 0,
            "losses": 0,
            "gross_pnl": 0.0,
            "total_cost": 0.0,
            "net_pnl": 0.0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "max_drawdown": 0.0,
            "sharpe_ratio": 0.0,
            "avg_move_points": 0.0,
        }

    dir_mask = direction[mask]
    rets = returns[mask]
    closes_masked = close_prices[mask]

    price_mult = float(np.mean(closes_masked))
    raw_pnl_dollars = dir_mask * rets * closes_masked
    cost_per = (spread_cost + slippage_p90) * price_mult

    net_pnl = raw_pnl_dollars - cost_per

    accuracy = (dir_mask * rets > 0).mean()
    gross = raw_pnl_dollars.sum()
    total_cost = cost_per * n_trades
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
        "avg_move_points": round(float(np.abs(rets).mean() * price_mult * 100), 1) if len(rets) > 0 else 0.0,
    }


def walk_forward(
    df: pd.DataFrame,
    feature_cols: list[str],
    model_params: dict,
    train_window: int,
    test_window: int,
    step: int,
    spread_cost: float,
    slippage_p90: float,
    min_confidence: float = 0.85,
) -> dict:
    """Run walk-forward for 3-class triple-barrier labels.

    DEPRECATED: Use validation.walk_forward.run_walk_forward with label_mode="3class".
    """
    n = len(df)
    folds = []
    data = df[feature_cols].fillna(0).values
    targets = df["target"].values
    returns = df["target_return"].values
    close_prices = df["close"].values if "close" in df.columns else None

    fold_idx = 0
    while True:
        train_start = fold_idx * step
        train_end = train_start + train_window
        test_end = train_end + test_window
        if test_end > n:
            break

        X_train = data[train_start:train_end]
        y_train = targets[train_start:train_end]
        X_test = data[train_end:test_end]
        y_test = targets[train_end:test_end]
        ret_test = returns[train_end:test_end]
        test_close = close_prices[train_end:test_end] if close_prices is not None else None

        model = xgb.XGBClassifier(**model_params)
        model.fit(X_train, y_train)
        train_acc = (model.predict(X_train) == y_train).mean()

        preds = model.predict(X_test)
        proba = model.predict_proba(X_test)
        conf = np.max(proba, axis=1)
        oos_acc = (preds == y_test).mean()

        result = compute_fold_pnl(
            ret_test,
            preds,
            conf,
            spread_cost=spread_cost,
            slippage_p90=slippage_p90,
            min_confidence=min_confidence,
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
    print(
        f"  {'Fold':>4s} | {'TrainAcc':>8s} | {'OOSAcc':>7s} | {'Trades':>6s} | {'Acc':>6s} | {'Gross':>7s} | {'Net':>8s} | {'SR':>6s} |"
    )
    print(
        f"  {'----':>4s}-+-{'--------':>8s}-+-{'-------':>7s}-+-{'------':>6s}-+-{'------':>6s}-+-{'-------':>7s}-+-{'--------':>8s}-+-{'------':>6s}-+"
    )
    for f in agg["folds"]:
        ok = "*" if f["net_pnl"] > 0 and f["n_trades"] >= 3 else " "
        print(
            f"  {f['fold']:>4d}{ok} | {f['train_acc']:>.4f}   | {f['oos_acc']:>.4f}  | {f['n_trades']:>6d} | {f['accuracy']:>.4f} | {f['gross_pnl']:>+6.2f}  | {f['net_pnl']:>+7.2f}  | {f['sharpe_ratio']:>+5.1f}  |"
        )

    print()
    print("  === AGGREGATE ===")
    print(f"  Total net:     ${a['total_net']:>+.2f}  ({a['positive_folds']}/{a['n_folds']} folds positive)")
    print(f"  Total trades:  {a['total_trades']}")
    print(f"  Weighted acc:  {a['weighted_accuracy']:.4f}")
    print(f"  Net stability: t={a['net_stability_t']:.2f}")
    if a["stable"]:
        print(f"\n  [OK] EDGE STABLE — {a['positive_folds']}/{a['n_folds']} folds positive, net=${a['total_net']:.2f}")
    else:
        print(
            f"\n  [WARN] EDGE NOT STABLE — {a['positive_folds']}/{a['n_folds']} folds positive, net=${a['total_net']:.2f}"
        )
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
    parser.add_argument("--max-depth", type=int, default=5)
    parser.add_argument("--n-estimators", type=int, default=100)
    parser.add_argument("--output", default=OUT_DIR)
    args = parser.parse_args()

    os.makedirs(args.output, exist_ok=True)

    print("=" * 70)
    print("WALK-FORWARD VALIDATION (PATCHED — 3-class TB labels)")
    print(f"  {args.symbol} @ {args.freq}")
    print(f"  Windows: train={args.train_window} test={args.test_window} step={args.step}")
    print(f"  Cost: ${args.spread_cost+args.slippage_p90:.3f}/trade  Conf>={args.min_confidence}")
    print("=" * 70)

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

    for conf in [args.min_confidence]:
        print(f"\n--- Conf >= {conf} ---")
        agg = walk_forward(
            df,
            feature_cols,
            model_params,
            args.train_window,
            args.test_window,
            args.step,
            args.spread_cost,
            args.slippage_p90,
            min_confidence=conf,
        )
        print_results(agg)

        path = os.path.join(
            args.output, f"wf_{args.symbol}_{args.freq}_{args.train_window}w_{args.test_window}t_conf{conf}.json"
        )
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
