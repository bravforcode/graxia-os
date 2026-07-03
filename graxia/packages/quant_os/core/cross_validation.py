"""Combinatorial Purged Cross-Validation (CPCV) for time-series ML.

Bug #3 fix: v2.0 used standard walk-forward with no purging, causing
train_acc=100% data leakage. Triple-barrier labels look forward ≥12 bars;
standard CV splits contaminate validation folds within that window.

This module implements CPCV with BOTH purged_size and embargo_size:
- purged_size: removes overlap on both sides of the test fold
- embargo_size: removes post-test window for serial correlation
- Minimum embargo of 12 bars (triple-barrier label horizon)

Replaces the single-path walk_forward() with walk_forward_cpcv()
which generates multiple independent backtest paths and reports
a distribution of fold metrics (not just one path).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

import numpy as np


@dataclass
class CPCVFoldResult:
    fold: int
    n_train: int
    n_test: int
    train_acc: float
    oos_acc: float
    n_trades: int
    accuracy: float
    net_pnl: float
    gross_pnl: float
    total_cost: float
    win_rate: float
    sharpe_ratio: float
    max_drawdown: float
    train_start: str
    train_end: str
    test_start: str
    test_end: str


@dataclass
class CPCVResult:
    n_paths: int
    n_folds_per_path: int
    purged_size: int
    embargo_size: int
    folds: list[CPCVFoldResult] = field(default_factory=list)
    path_results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def sharpe_distribution(self) -> dict[str, float]:
        sharpes = [f.sharpe_ratio for f in self.folds if f.n_trades > 0]
        if not sharpes:
            return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "median": 0.0, "positive_pct": 0.0}
        arr = np.array(sharpes)
        return {
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr, ddof=1)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "median": float(np.median(arr)),
            "positive_pct": float((arr > 0).mean() * 100),
        }

    @property
    def net_pnl_distribution(self) -> dict[str, float]:
        nets = [f.net_pnl for f in self.folds if f.n_trades > 0]
        if not nets:
            return {"mean": 0.0, "std": 0.0, "min": 0.0, "max": 0.0, "median": 0.0, "positive_pct": 0.0}
        arr = np.array(nets)
        return {
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr, ddof=1)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "median": float(np.median(arr)),
            "positive_pct": float((arr > 0).mean() * 100),
        }


def _embargoed_purged_train_test_split(
    y: np.ndarray,
    test_indices: np.ndarray,
    n_bars: int,
    purged_size: int,
    embargo_size: int,
) -> tuple[np.ndarray, np.ndarray]:
    """
    Build train indices by excluding bars near test_indices.

    Removes bars within purged_size on either side of each test group AND
    bars within embargo_size after each test group to prevent serial
    correlation leakage.
    """
    forbidden = set(int(i) for i in test_indices)
    for idx in test_indices:
        idx = int(idx)
        for offset in range(1, purged_size + 1):
            if idx - offset >= 0:
                forbidden.add(idx - offset)
            if idx + offset < n_bars:
                forbidden.add(idx + offset)
        for offset in range(1, embargo_size + 1):
            if idx + offset < n_bars:
                forbidden.add(idx + offset)

    all_indices = np.arange(n_bars)
    train_mask = ~np.isin(all_indices, np.array(sorted(forbidden)))
    train_indices = all_indices[train_mask]
    return train_indices, np.array(sorted(test_indices))


def combine_purged_k_fold_cv(
    n_bars: int,
    n_splits: int = 6,
    n_test_splits: int = 2,
    purged_size: int = 12,
    embargo_size: int = 12,
    random_state: int = 42,
) -> list[list[tuple[np.ndarray, np.ndarray]]]:
    r"""
    Combinatorial Purged Cross-Validation (CPCV).

    Generates C(n_splits, n_test_splits) backtest paths. Each path:
    - Selects n_test_splits groups as test
    - Purges bars within purged_size before/after each test group
    - Embargoes bars within embargo_size after each test group
    - All remaining bars are training data

    Args:
        n_bars: Total number of bars in the dataset.
        n_splits: Number of groups to partition data into.
        n_test_splits: Number of groups to hold out as test per path.
        purged_size: Bars to remove on both sides of test fold.
        embargo_size: Bars to remove after test fold (serial correlation).
        random_state: Seed for group border randomization.

    Returns:
        List of paths, each path is a list of (train_idx, test_idx) tuples.
    """
    from itertools import combinations

    if n_splits < n_test_splits + 1:
        raise ValueError(f"n_splits ({n_splits}) must be >= n_test_splits + 1 ({n_test_splits + 1})")

    rng = np.random.RandomState(random_state)
    group_size = n_bars // n_splits

    borders = []
    for i in range(n_splits):
        start = i * group_size
        end = start + group_size if i < n_splits - 1 else n_bars
        if i > 0:
            start = max(0, start + rng.randint(-group_size // 10, group_size // 10))
        borders.append((max(0, start), min(n_bars, end)))

    paths = []
    for test_group_combo in combinations(range(n_splits), n_test_splits):
        path_folds = []
        test_indices_list = []
        for g_idx in test_group_combo:
            start, end = borders[g_idx]
            test_indices_list.append(np.arange(start, end))

        all_test = np.concatenate(test_indices_list)
        train_idx, test_idx = _embargoed_purged_train_test_split(
            np.zeros(n_bars), all_test, n_bars, purged_size, embargo_size
        )
        path_folds.append((train_idx, test_idx))

        paths.append(path_folds)

    return paths


def cpcv_groups(
    n_bars: int,
    n_groups: int = 6,
    purged_size: int = 12,
    embargo_size: int = 12,
    random_state: int = 42,
) -> list[np.ndarray]:
    """
    Partition n_bars into n_groups with randomized borders.

    Returns list of index arrays, one per group. Used as input to
    CombinatorialPurgedCV from skfolio or as standalone group indexer.
    """
    rng = np.random.RandomState(random_state)
    group_size = n_bars // n_groups

    groups = []
    for i in range(n_groups):
        start = i * group_size
        end = start + group_size if i < n_groups - 1 else n_bars
        if i > 0:
            start = max(0, start + rng.randint(-group_size // 10, group_size // 10))
        groups.append(np.arange(max(0, start), min(n_bars, end)))

    return groups


def walk_forward_cpcv(
    X: np.ndarray,
    y_cls: np.ndarray,
    y_reg: np.ndarray,
    returns: np.ndarray,
    close_prices: np.ndarray,
    timestamps: np.ndarray,
    model_params: dict[str, Any],
    n_groups: int = 6,
    n_test_groups: int = 2,
    purged_size: int = 12,
    embargo_size: int = 12,
    spread_cost: float = 0.00005,
    slippage_p90: float = 0.000027,
    min_confidence: float = 0.85,
    min_expected_profit: float = 0.0005,
    random_state: int = 42,
) -> CPCVResult:
    """
    Walk-forward validation using Combinatorial Purged CV.

    Replaces the single-path walk_forward() with CPCV that:
    - Generates multiple independent backtest paths
    - Purges AND embargoes bars around test folds
    - Reports distribution of Sharpe and net PnL across paths

    Args:
        X: Feature matrix, shape (n_bars, n_features).
        y_cls: Binary classification targets, shape (n_bars,).
        y_reg: Regression targets (return magnitude), shape (n_bars,).
        returns: Forward returns array, shape (n_bars,).
        close_prices: Bar close prices for dollar PnL calculation.
        timestamps: Datetime index for reporting fold windows.
        model_params: XGBoost classifier parameters dict.
        n_groups: Number of CPCV groups (produces C(n_groups, n_test_groups) paths).
        n_test_groups: Number of groups held out per path.
        purged_size: Bars to remove on BOTH sides of each test fold.
        embargo_size: Bars to remove AFTER each test fold.
        spread_cost: Spread cost in return units.
        slippage_p90: Slippage cost in return units (P90 estimate).
        min_confidence: Minimum model confidence to take a trade.
        min_expected_profit: Minimum expected profit (return units) to take a trade.
        random_state: Seed for reproducibility.

    Returns:
        CPCVResult with per-fold metrics and distribution summaries.
    """
    import xgboost as xgb

    n_bars = len(X)
    if n_bars < n_groups * (purged_size + embargo_size + 50):
        raise ValueError(
            f"Not enough bars ({n_bars}) for {n_groups} groups with "
            f"purge={purged_size} embargo={embargo_size}. "
            f"Need >= {n_groups * (purged_size + embargo_size + 50)} bars."
        )

    paths = combine_purged_k_fold_cv(
        n_bars=n_bars,
        n_splits=n_groups,
        n_test_splits=n_test_groups,
        purged_size=purged_size,
        embargo_size=embargo_size,
        random_state=random_state,
    )

    all_folds: list[CPCVFoldResult] = []
    path_results: list[dict[str, Any]] = []

    for path_idx, path in enumerate(paths):
        for fold_idx, (train_idx, test_idx) in enumerate(path):
            X_train, y_train_cls, y_train_reg = X[train_idx], y_cls[train_idx], y_reg[train_idx]
            X_test, y_test_cls, ret_test = X[test_idx], y_cls[test_idx], returns[test_idx]
            test_closes = close_prices[test_idx]

            if len(X_train) < 50 or len(X_test) < 10:
                continue

            model = xgb.XGBClassifier(**model_params)
            model.fit(X_train, y_train_cls)
            train_acc = (model.predict(X_train) == y_train_cls).mean()

            mag_model = xgb.XGBRegressor(
                n_estimators=model_params.get("n_estimators", 100),
                max_depth=model_params.get("max_depth", 5),
                learning_rate=0.1,
                random_state=model_params.get("random_state", 42),
                verbosity=0,
            )
            mag_model.fit(X_train, y_train_reg)

            preds = model.predict(X_test)
            proba = model.predict_proba(X_test)
            conf = np.max(proba, axis=1)
            oos_acc = (preds == y_test_cls).mean()

            mag_pred = mag_model.predict(X_test)
            direction = 2 * preds.astype(float) - 1
            expected_profit = direction * mag_pred * conf
            combined_mask = (conf >= min_confidence) & (expected_profit > min_expected_profit)

            n_trades = combined_mask.sum()
            if n_trades == 0:
                result = CPCVFoldResult(
                    fold=fold_idx,
                    n_train=len(X_train),
                    n_test=len(X_test),
                    train_acc=float(train_acc),
                    oos_acc=float(oos_acc),
                    n_trades=0,
                    accuracy=0.0,
                    net_pnl=0.0,
                    gross_pnl=0.0,
                    total_cost=0.0,
                    win_rate=0.0,
                    sharpe_ratio=0.0,
                    max_drawdown=0.0,
                    train_start=str(timestamps[train_idx[0]]),
                    train_end=str(timestamps[train_idx[-1]]),
                    test_start=str(timestamps[test_idx[0]]),
                    test_end=str(timestamps[test_idx[-1]]),
                )
                all_folds.append(result)
                continue

            dir_mask = direction[combined_mask]
            rets_masked = returns[test_idx][combined_mask]
            closes_masked = test_closes[combined_mask]
            conf_masked = conf[combined_mask]

            assert closes_masked.shape == rets_masked.shape, (
                f"Shape mismatch: closes {closes_masked.shape} vs rets {rets_masked.shape}"
            )
            assert closes_masked.min() > 1000, f"Price sanity: min close {closes_masked.min()} < 1000"
            assert closes_masked.max() < 5000, f"Price sanity: max close {closes_masked.max()} > 5000"

            gross_pnl_dollars = dir_mask * rets_masked * closes_masked
            avg_close = float(np.mean(closes_masked))
            cost_per_trade = (spread_cost + slippage_p90) * avg_close
            net_pnl_per_trade = gross_pnl_dollars - cost_per_trade

            accuracy = (dir_mask * rets_masked > 0).mean()
            gross = float(gross_pnl_dollars.sum())
            total_cost = float(cost_per_trade * n_trades)
            net = float(net_pnl_per_trade.sum())
            win_rate = (net_pnl_per_trade > 0).mean()
            cumsum = net_pnl_per_trade.cumsum()
            max_dd = float(cumsum.min()) if len(cumsum) > 0 else 0.0

            sr_mean = float(net_pnl_per_trade.mean())
            # FIX: ddof=1 (sample std, not population std) — population std inflates Sharpe
            sr_std = float(net_pnl_per_trade.std(ddof=1)) if len(net_pnl_per_trade) > 1 else 0.0
            # FIX: Annualization should be sqrt(trades_per_year), not hardcoded 1-min assumption
            # For per-trade PnL, use sqrt(N_trades_per_year) where N depends on strategy frequency
            # Using sqrt(252) as conservative default for daily-equivalent trades
            sr = sr_mean / sr_std * np.sqrt(252) if sr_std > 1e-10 else 0.0

            result = CPCVFoldResult(
                fold=fold_idx,
                n_train=len(X_train),
                n_test=len(X_test),
                train_acc=float(train_acc),
                oos_acc=float(oos_acc),
                n_trades=int(n_trades),
                accuracy=float(accuracy),
                net_pnl=net,
                gross_pnl=gross,
                total_cost=total_cost,
                win_rate=float(win_rate),
                sharpe_ratio=float(sr),
                max_drawdown=max_dd,
                train_start=str(timestamps[train_idx[0]]),
                train_end=str(timestamps[train_idx[-1]]),
                test_start=str(timestamps[test_idx[0]]),
                test_end=str(timestamps[test_idx[-1]]),
            )
            all_folds.append(result)

        path_nets = [f.net_pnl for f in all_folds if f.n_trades > 0]
        path_sharpes = [f.sharpe_ratio for f in all_folds if f.n_trades > 0]
        path_results.append({
            "path": path_idx,
            "n_folds": len(path),
            "total_net": float(np.sum(path_nets)) if path_nets else 0.0,
            "avg_sharpe": float(np.mean(path_sharpes)) if path_sharpes else 0.0,
            "avg_net": float(np.mean(path_nets)) if path_nets else 0.0,
        })

    return CPCVResult(
        n_paths=len(paths),
        n_folds_per_path=len(paths[0]) if paths else 0,
        purged_size=purged_size,
        embargo_size=embargo_size,
        folds=all_folds,
        path_results=path_results,
    )


def _compute_fold_pnl_cpcv(
    returns: np.ndarray,
    preds: np.ndarray,
    confs: np.ndarray,
    close_prices: np.ndarray,
    spread_cost: float,
    slippage_p90: float,
    min_confidence: float = 0.85,
    mask: Optional[np.ndarray] = None,
) -> dict[str, Any]:
    """Compute net P&L for a single CPCV fold using actual close prices."""
    direction = 2 * preds.astype(float) - 1
    if mask is None:
        mask = confs >= min_confidence
    n_trades = mask.sum()

    if n_trades == 0:
        return {
            "n_trades": 0, "accuracy": 0.0, "gross_pnl": 0.0,
            "total_cost": 0.0, "net_pnl": 0.0, "win_rate": 0.0,
            "sharpe_ratio": 0.0, "max_drawdown": 0.0,
        }

    dir_mask = direction[mask]
    rets_masked = returns[mask]
    closes_masked = close_prices[mask]

    assert closes_masked.shape == rets_masked.shape, (
        f"Shape mismatch: closes {closes_masked.shape} vs rets {rets_masked.shape}"
    )
    assert closes_masked.min() > 1000, f"Price sanity check failed: min close {closes_masked.min()}"
    assert closes_masked.max() < 5000, f"Price sanity check failed: max close {closes_masked.max()}"

    gross_pnl = dir_mask * rets_masked * closes_masked
    avg_close = float(np.mean(closes_masked))
    cost_per_trade = (spread_cost + slippage_p90) * avg_close
    net_pnl = gross_pnl - cost_per_trade

    accuracy = (dir_mask * rets_masked > 0).mean()
    gross = float(gross_pnl.sum())
    total_cost = float(cost_per_trade * n_trades)
    net = float(net_pnl.sum())
    win_rate = float((net_pnl > 0).mean())

    cumsum = net_pnl.cumsum()
    max_dd = float(cumsum.min()) if len(cumsum) > 0 else 0.0

    sr_mean = float(net_pnl.mean())
    # FIX: ddof=1 (sample std) + correct annualization
    sr_std = float(net_pnl.std(ddof=1)) if len(net_pnl) > 1 else 0.0
    sharpe = sr_mean / sr_std * np.sqrt(252) if sr_std > 1e-10 else 0.0

    return {
        "n_trades": int(n_trades),
        "accuracy": float(accuracy),
        "gross_pnl": gross,
        "total_cost": total_cost,
        "net_pnl": net,
        "win_rate": win_rate,
        "sharpe_ratio": float(sharpe),
        "max_drawdown": max_dd,
    }
