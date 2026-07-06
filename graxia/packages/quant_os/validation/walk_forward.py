"""Walk-forward validation engine — canonical implementation.

Single source of truth for walk-forward splitting, fold evaluation, and
P&L computation.  All scripts MUST import from here instead of inlining
their own walk_forward functions.

Supersedes:
  - scripts/walk_forward.py::walk_forward
  - scripts/wf_patched.py::walk_forward
  - scripts/run_multi_symbol_wf.py::walk_forward_split
  - scripts/retrain_calibrated.py::walk_forward_split / purged_cv
  - scripts/train_live_model.py::walk_forward_split / walk_forward_cv
  - scripts/train_mega_model.py::walk_forward_split / walk_forward_cv
  - core/cross_validation.py::walk_forward_cpcv  (kept as CPCV variant)
"""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# ── data classes ────────────────────────────────────────────────────────


@dataclass
class WalkForwardFold:
    """Result of a single walk-forward fold."""

    fold_index: int
    train_start: int
    train_end: int
    test_start: int
    test_end: int
    in_sample_metrics: dict[str, Any] = field(default_factory=dict)
    out_of_sample_metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class WalkForwardResult:
    """Aggregated walk-forward results across all folds."""

    params: dict[str, Any]
    aggregate: dict[str, Any]
    folds: list[dict[str, Any]]
    per_trade_records: list[dict[str, Any]] = field(default_factory=list)


# ── split generators ────────────────────────────────────────────────────


def walk_forward_split(
    n_bars: int,
    n_folds: int = 5,
    train_ratio: float = 0.7,
    embargo_bars: int = 12,
) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Generate walk-forward train/test splits.

    Returns list of ((train_start, train_end), (test_start, test_end)).
    Embargo: gap between train_end and test_start to prevent leakage.
    """
    fold_size = n_bars // n_folds
    train_size = int(fold_size * train_ratio)

    splits = []
    for i in range(n_folds):
        fold_start = i * fold_size
        train_start = fold_start
        train_end = fold_start + train_size
        test_start = train_end + embargo_bars
        test_end = min(fold_start + fold_size, n_bars)

        if test_start < test_end:
            splits.append(((train_start, train_end), (test_start, test_end)))

    return splits


def purged_cv(
    n: int,
    n_folds: int = 5,
    embargo: int = 12,
) -> Generator[tuple[np.ndarray, np.ndarray], None, None]:
    """Purged walk-forward CV — yields (train_idx, test_idx) arrays.

    Each fold: train on [0, train_end-embargo], test on [test_start, test_end].
    Used by Optuna inner loops and calibrated retrain scripts.
    """
    fold_size = n // (n_folds + 1)
    for i in range(n_folds):
        train_end = (i + 1) * fold_size
        test_start = train_end + embargo
        test_end = test_start + fold_size
        if test_end > n:
            break
        train_idx = np.arange(0, train_end - embargo)
        test_idx = np.arange(test_start, min(test_end, n))
        yield train_idx, test_idx


def simple_train_test_split(
    n: int,
    train_ratio: float = 0.8,
) -> tuple[np.ndarray, np.ndarray]:
    """Time-ordered train/test split — no look-ahead.

    Returns (train_idx, test_idx) as integer arrays.
    """
    split_idx = int(n * train_ratio)
    return np.arange(0, split_idx), np.arange(split_idx, n)


def sliding_window_splits(
    n: int,
    train_window: int,
    test_window: int,
    step: int,
    purge_bars: int = 7,
    embargo_bars: int = 7,
) -> list[tuple[int, int, int, int]]:
    """Sliding-window walk-forward splits with purge+embargo.

    Returns list of (train_start, train_end, test_start, test_end).
    Used by scripts/walk_forward.py style validation.
    """
    splits = []
    fold_idx = 0
    while True:
        train_start = fold_idx * step
        train_end = train_start + train_window
        test_start = train_end + purge_bars + embargo_bars
        test_end = test_start + test_window
        if test_end > n:
            break
        splits.append((train_start, train_end, test_start, test_end))
        fold_idx += 1
    return splits


# ── fold evaluation ─────────────────────────────────────────────────────


def evaluate_fold(
    train_data: tuple,
    test_data: tuple,
    strategy_fn: Callable,
    metrics_fn: Callable,
) -> WalkForwardFold:
    """Evaluate a single walk-forward fold with strategy/metrics callables."""
    train_metrics = metrics_fn(strategy_fn, train_data)
    test_metrics = metrics_fn(strategy_fn, test_data)

    return WalkForwardFold(
        fold_index=0,
        train_start=train_data[0],
        train_end=train_data[1],
        test_start=test_data[0],
        test_end=test_data[1],
        in_sample_metrics=train_metrics,
        out_of_sample_metrics=test_metrics,
    )


# ── P&L computation ────────────────────────────────────────────────────


def compute_fold_pnl(
    returns: np.ndarray,
    preds: np.ndarray,
    confs: np.ndarray,
    spread_cost: float,
    slippage_p90: float,
    min_confidence: float = 0.85,
    mask: np.ndarray | None = None,
    close_prices: np.ndarray | None = None,
    bars_per_year: int = 252 * 1440,
    label_mode: str = "binary",
) -> dict[str, Any]:
    """Compute net P&L for a single fold's test predictions.

    Args:
        returns: Forward returns array (fractional).
        preds: Predictions (binary: 0/1 or 3-class: 0/1/2).
        confs: Prediction confidence scores.
        spread_cost: Spread cost in return units.
        slippage_p90: Slippage cost in return units (P90 estimate).
        min_confidence: Minimum confidence threshold for trade entry.
        mask: Optional pre-computed trade selection mask.
        close_prices: Bar close prices for dollar PnL conversion. Required.
        bars_per_year: Annualization factor (inferred from data frequency).
        label_mode: "binary" (0/1) or "3class" (0=short,1=skip,2=long).

    Returns:
        Dict with n_trades, accuracy, gross_pnl, total_cost, net_pnl,
        win_rate, avg_win, avg_loss, max_drawdown, sharpe_ratio, etc.
    """
    if close_prices is None:
        raise ValueError("close_prices is required for accurate PnL calculation")

    if label_mode == "3class":
        direction = np.array([-1.0, 0.0, 1.0])[preds.astype(int)]
        if mask is None:
            mask = (confs >= min_confidence) & (direction != 0.0)
    else:
        direction = 2 * preds.astype(float) - 1  # 0→-1 (short), 1→+1 (long)
        if mask is None:
            mask = confs >= min_confidence

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
    sharpe = sr_mean / sr_std * np.sqrt(bars_per_year) if sr_std > 1e-10 else 0.0

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


# ── full walk-forward runner ────────────────────────────────────────────


def run_walk_forward(
    df: pd.DataFrame,
    feature_cols: list[str],
    model_params: dict[str, Any],
    train_window: int,
    test_window: int,
    step: int,
    spread_cost: float,
    slippage_p90: float,
    min_confidence: float = 0.85,
    min_expected_profit: float = 0.0005,
    purge_bars: int = 14,
    embargo_bars: int = 0,
    per_trade_path: str | None = None,
    label_mode: str = "binary",
    purge_gap: int | None = None,
) -> dict[str, Any]:
    """Run full walk-forward validation with purge/embargo.

    This is the canonical walk-forward runner.  It replaces the inline
    walk_forward() functions in scripts/walk_forward.py, scripts/wf_patched.py,
    and similar.

    Args:
        df: DataFrame with features, target, target_return, close columns.
        feature_cols: List of feature column names.
        model_params: XGBoost classifier parameters dict.
        train_window: Number of bars per training window.
        test_window: Number of bars per test window.
        step: Step size between folds.
        spread_cost: Spread cost in return units.
        slippage_p90: Slippage cost in return units.
        min_confidence: Minimum model confidence to take a trade.
        min_expected_profit: Minimum expected profit to take a trade.
        purge_bars: Gap between train end and test start (default 14).
        embargo_bars: Additional embargo after purge (default 0).
        per_trade_path: Optional path to save per-trade parquet.
        label_mode: "binary" or "3class" (triple-barrier).
        purge_gap: Alias for purge_bars (for backward compatibility).

    Returns:
        Dict with params, aggregate, and folds keys.
    """
    # purge_gap alias for backward compatibility
    if purge_gap is not None:
        purge_bars = purge_gap

    import xgboost as xgb

    n = len(df)
    folds = []
    data = df[feature_cols].fillna(0).values
    targets = df["target"].values
    returns = df["target_return"].values
    close_array = df["close"].values if "close" in df.columns else None
    y_reg_col = "tb_ret" if "tb_ret" in df.columns else "target_return"
    y_reg = df[y_reg_col].values

    # Infer bars_per_year from data frequency
    bars_per_year = 252 * 24  # default: daily
    if len(df.index) > 1:
        avg_gap = (df.index[-1] - df.index[0]).total_seconds() / (len(df.index) - 1)
        if avg_gap < 120:
            bars_per_year = 252 * 1440
        elif avg_gap < 3600:
            bars_per_year = 252 * int(1440 / max(1, avg_gap / 60))

    splits = sliding_window_splits(
        n,
        train_window,
        test_window,
        step,
        purge_bars,
        embargo_bars,
    )

    per_trade_records: list[dict] = []

    for fold_idx, (train_start, train_end, test_start, test_end) in enumerate(splits):
        X_train = data[train_start:train_end]
        y_train_cls = targets[train_start:train_end]
        y_train_reg = y_reg[train_start:train_end]
        X_test = data[test_start:test_end]
        y_test_cls = targets[test_start:test_end]
        ret_test = returns[test_start:test_end]

        # Train classifier
        model = xgb.XGBClassifier(**model_params)
        model.fit(X_train, y_train_cls)
        train_acc = (model.predict(X_train) == y_train_cls).mean()

        # Train magnitude regressor
        mag_model = xgb.XGBRegressor(
            n_estimators=model_params.get("n_estimators", 100),
            max_depth=model_params.get("max_depth", 5),
            learning_rate=0.1,
            random_state=model_params.get("random_state", 42),
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
        if label_mode == "3class":
            direction = np.array([-1.0, 0.0, 1.0])[preds.astype(int)]
            combined_mask = (conf >= min_confidence) & (direction != 0.0)
        else:
            direction = 2 * preds.astype(float) - 1
            expected_profit = direction * mag_pred * conf
            combined_mask = (conf >= min_confidence) & (expected_profit > min_expected_profit)

        # Collect per-trade data
        test_times = df.index[test_start:test_end]
        for t_bar in range(len(X_test)):
            per_trade_records.append(
                {
                    "fold": fold_idx,
                    "timestamp": test_times[t_bar],
                    "direction": int(direction[t_bar]),
                    "confidence": float(conf[t_bar]),
                    "mag_pred": float(mag_pred[t_bar]),
                    "realized_return": float(ret_test[t_bar]),
                    "trade_selected": bool(combined_mask[t_bar]),
                    "target": int(y_test_cls[t_bar]),
                }
            )

        # Evaluate
        test_close = close_array[test_start:test_end] if close_array is not None else None
        result = compute_fold_pnl(
            ret_test,
            preds,
            conf,
            spread_cost=spread_cost,
            slippage_p90=slippage_p90,
            min_confidence=0.0,
            mask=combined_mask,
            close_prices=test_close,
            bars_per_year=bars_per_year,
            label_mode=label_mode,
        )

        result["fold"] = fold_idx
        result["train_start"] = str(df.index[train_start])
        result["train_end"] = str(df.index[train_end - 1])
        result["test_start"] = str(df.index[test_start])
        result["test_end"] = str(df.index[test_end - 1])
        result["train_acc"] = round(float(train_acc), 4)
        result["oos_acc"] = round(float(oos_acc), 4)

        folds.append(result)

    # Save per-trade data
    if per_trade_path and per_trade_records:
        pt_df = pd.DataFrame(per_trade_records)
        out_dir = __import__("os").path.dirname(per_trade_path)
        if out_dir:
            __import__("os").makedirs(out_dir, exist_ok=True)
        pt_df.to_parquet(per_trade_path, index=False)

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

    return {
        "params": {
            "train_window": train_window,
            "test_window": test_window,
            "step": step,
            "purge_bars": purge_bars,
            "purge_gap": purge_bars,  # alias for backward compatibility
            "embargo_bars": embargo_bars,
            "n_folds": len(folds),
            "spread_cost": spread_cost,
            "slippage_p90": slippage_p90,
            "min_confidence": min_confidence,
            "min_expected_profit": min_expected_profit,
            "label_mode": label_mode,
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
        "per_trade_records": per_trade_records,
    }


def infer_bars_per_year(df: pd.DataFrame) -> int:
    """Infer annualization factor from DataFrame index frequency."""
    if len(df.index) < 2:
        return 252 * 24
    avg_gap = (df.index[-1] - df.index[0]).total_seconds() / (len(df.index) - 1)
    if avg_gap < 120:
        return 252 * 1440
    elif avg_gap < 3600:
        return 252 * int(1440 / max(1, avg_gap / 60))
    return 252 * 24
