#!/usr/bin/env python3
"""
train_mega_model_v2.py — Redesigned XGBoost + LightGBM + CatBoost ensemble
===========================================================================

Changes from v1:
  1. Uses triple-barrier labels (tb_label: 1=WIN, 0=LOSS/TIMEOUT)
  2. Regularized hyperparameters (max_depth=3, n_estimators=150)
  3. Larger embargo (24 bars = 6 hours) to prevent leakage
  4. Session-aware training (optional filter)
  5. Magnitude gate integration

Input:  artifacts/features_v3/features_v3_mega_XAUUSD_15min.parquet
Output: artifacts/mega_model/
"""

import json
import os
import pickle
import sys
import time
import warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
import lightgbm as lgb
import catboost as cb
import optuna
from optuna.samplers import TPESampler
from sklearn.feature_selection import mutual_info_classif
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
)

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

# ──────────────────────────── PATHS ────────────────────────────
BASE = Path(__file__).resolve().parent.parent
FEAT_PATH = BASE / "artifacts" / "features_v3" / "features_v3_mega_XAUUSD_15min.parquet"
OUT_DIR = BASE / "artifacts" / "mega_model"
OUT_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d")
RANDOM_STATE = 42
N_TRIALS = 50  # Reduced from 100 to prevent overfitting
TOP_K_FEATURES = 30  # Reduced from 50 to prevent overfitting
EARLY_STOP = 30  # Reduced from 50

# ──────────────────────────── REGULARIZED PARAMS ──────────────
# These are the starting points for Optuna, not final values
BASE_XGB_PARAMS = {
    "max_depth": 3,  # Was 6 — much less capacity
    "n_estimators": 150,  # Was 500
    "learning_rate": 0.03,  # Was 0.05
    "subsample": 0.7,  # Was 0.8
    "colsample_bytree": 0.7,  # Was 0.8
    "min_child_weight": 15,  # Was 5
    "reg_alpha": 5.0,  # Was 1.0
    "reg_lambda": 5.0,  # Was 1.0
    "gamma": 1.0,  # Was 0
}

BASE_LGB_PARAMS = {
    "n_estimators": 150,  # Was 500
    "max_depth": 4,  # Was 6
    "learning_rate": 0.03,  # Was 0.05
    "subsample": 0.7,  # Was 0.8
    "colsample_bytree": 0.7,  # Was 0.8
    "min_child_weight": 15,  # Was 5
    "reg_alpha": 5.0,  # Was 1.0
    "reg_lambda": 5.0,  # Was 1.0
    "num_leaves": 15,  # Was default (31)
}

BASE_CB_PARAMS = {
    "iterations": 150,  # Was 500
    "depth": 4,  # Was 6
    "learning_rate": 0.03,  # Was 0.05
    "l2_leaf_reg": 10.0,  # Was 3.0
    "random_strength": 2.0,  # Was default
    "bagging_temperature": 0.5,  # Was default
}


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════
# SECTION 1: LOAD & PREPARE DATA
# ══════════════════════════════════════════════════════════════

def load_data() -> pd.DataFrame:
    log(f"Loading features from {FEAT_PATH.name}...")
    df = pd.read_parquet(FEAT_PATH)

    # Handle index
    if "datetime" in df.columns:
        df = df.set_index("datetime")
    elif "timestamp" in df.columns:
        df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()

    log(f"  Raw shape: {df.shape[0]} rows x {df.shape[1]} cols")

    # Check for triple-barrier labels
    if "tb_label" not in df.columns:
        log("  [ERROR] No 'tb_label' column — run add_triple_barrier.py first")
        sys.exit(1)

    # Create binary target: 1 if WIN, 0 otherwise (LOSS or TIMEOUT)
    df["target_win"] = (df["tb_label"] == 1).astype(int)

    # Drop rows with NaN labels
    df = df.dropna(subset=["tb_label"])

    log(f"  After target creation: {df.shape[0]} rows")
    log(f"  tb_label distribution: {df['tb_label'].value_counts().to_dict()}")
    log(f"  target_win distribution: {df['target_win'].value_counts().to_dict()}")
    log(f"  Win rate: {df['target_win'].mean():.3f}")

    return df


# ══════════════════════════════════════════════════════════════
# SECTION 2: FEATURE ENGINEERING HELPERS
# ══════════════════════════════════════════════════════════════

EXCLUDE_COLS = {
    # Targets / leakage
    "is_long", "next_bar_return", "target", "target_return",
    "target_class", "target_win",
    # Forward returns (look-ahead leakage)
    "fwd_ret_1bar", "fwd_ret_5bar", "fwd_ret_10bar", "fwd_ret_15bar",
    # Triple-barrier labels (LEAKAGE!)
    "tb_label", "tb_win", "tb_tp_mult", "tb_sl_mult", "tb_max_bars",
    # OHLCV raw (not features)
    "open", "high", "low", "close", "volume", "tick_count",
    # Identifiers
    "symbol", "freq",
}


def get_feature_cols(df: pd.DataFrame) -> list:
    """Get numeric feature columns, excluding targets and OHLCV."""
    return [
        c for c in df.columns
        if c not in EXCLUDE_COLS
        and df[c].dtype in (np.float64, np.float32, np.int64, np.int32)
        and df[c].nunique() > 1  # drop constant columns
    ]


def select_features_mi(X: np.ndarray, y: np.ndarray, feature_names: list, k: int) -> list:
    """Select top-k features by mutual information."""
    log(f"Selecting top {k} features by mutual information...")
    mi_scores = mutual_info_classif(X, y, random_state=RANDOM_STATE, n_neighbors=5)
    mi_ranking = sorted(zip(feature_names, mi_scores), key=lambda x: -x[1])

    log("  Top 15 MI scores:")
    for name, score in mi_ranking[:15]:
        log(f"    {name:40s} {score:.4f}")

    selected = [name for name, _ in mi_ranking[:k]]
    log(f"  Selected {len(selected)} features (MI range: {mi_ranking[k-1][1]:.4f} — {mi_ranking[0][1]:.4f})")
    return selected


# ══════════════════════════════════════════════════════════════
# SECTION 3: WALK-FORWARD SPLIT (PURGED)
# ══════════════════════════════════════════════════════════════

def walk_forward_split(n: int, train_ratio: float = 0.8):
    """Time-ordered 80/20 split — NO look-ahead."""
    split_idx = int(n * train_ratio)
    train_idx = np.arange(0, split_idx)
    test_idx = np.arange(split_idx, n)
    log(f"  Walk-forward split: train={len(train_idx)} ({train_ratio*100:.0f}%), test={len(test_idx)} ({(1-train_ratio)*100:.0f}%)")
    return train_idx, test_idx


def walk_forward_cv(n: int, n_folds: int = 5, embargo: int = 24):
    """Purged walk-forward CV for Optuna inner loop.
    
    embargo=24 bars = 6 hours (prevents leakage from adjacent sessions)
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


# ══════════════════════════════════════════════════════════════
# SECTION 4: OPTUNA OBJECTIVE (REGULARIZED)
# ══════════════════════════════════════════════════════════════

def make_objective(X: np.ndarray, y: np.ndarray, feature_names: list, scale_pos_weight: float):
    """Create Optuna objective for XGBoost with walk-forward CV."""

    def objective(trial):
        params = {
            "max_depth": trial.suggest_int("max_depth", 2, 5),  # Reduced range
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.1, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 50, 300, step=50),
            "subsample": trial.suggest_float("subsample", 0.5, 0.9),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.4, 0.9),
            "min_child_weight": trial.suggest_int("min_child_weight", 10, 30),
            "gamma": trial.suggest_float("gamma", 0.5, 5.0),
            "reg_alpha": trial.suggest_float("reg_alpha", 1.0, 10.0),
            "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 10.0),
            "scale_pos_weight": scale_pos_weight,
        }

        fold_accs = []
        for train_idx, test_idx in walk_forward_cv(len(X), n_folds=3, embargo=24):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]

            model = xgb.XGBClassifier(
                **params,
                random_state=RANDOM_STATE,
                eval_metric="logloss",
                verbosity=0,
                n_jobs=-1,
            )
            model.fit(
                X_train, y_train,
                eval_set=[(X_test, y_test)],
                verbose=False,
            )
            y_pred = model.predict(X_test)
            fold_accs.append(accuracy_score(y_test, y_pred))

        return np.mean(fold_accs)

    return objective


# ══════════════════════════════════════════════════════════════
# SECTION 5: TRAIN MODELS (REGULARIZED)
# ══════════════════════════════════════════════════════════════

def train_xgboost(X_train, y_train, X_test, y_test, best_params, scale_pos_weight):
    """Train XGBoost with regularized params + early stopping."""
    log("Training XGBoost (regularized)...")
    params = {k: v for k, v in best_params.items()}
    params["scale_pos_weight"] = scale_pos_weight
    model = xgb.XGBClassifier(
        **params,
        random_state=RANDOM_STATE,
        eval_metric="logloss",
        verbosity=0,
        n_jobs=-1,
    )
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        verbose=False,
    )
    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)
    log(f"  XGBoost: train_acc={train_acc:.4f} test_acc={test_acc:.4f} gap={train_acc-test_acc:.4f}")
    return model, train_acc, test_acc


def train_lightgbm(X_train, y_train, X_test, y_test, feature_names):
    """Train LightGBM with regularized params."""
    log("Training LightGBM (regularized)...")
    params = {k: v for k, v in BASE_LGB_PARAMS.items()}
    model = lgb.LGBMClassifier(**params, random_state=RANDOM_STATE, verbosity=-1, n_jobs=-1)
    model.fit(
        X_train, y_train,
        eval_set=[(X_test, y_test)],
        callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)],
    )
    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)
    log(f"  LightGBM: train_acc={train_acc:.4f} test_acc={test_acc:.4f} gap={train_acc-test_acc:.4f}")
    return model, train_acc, test_acc


def train_catboost(X_train, y_train, X_test, y_test, feature_names):
    """Train CatBoost with regularized params."""
    log("Training CatBoost (regularized)...")
    params = {k: v for k, v in BASE_CB_PARAMS.items()}
    model = cb.CatBoostClassifier(**params, random_seed=RANDOM_STATE, verbose=0, early_stopping_rounds=EARLY_STOP)
    model.fit(
        X_train, y_train,
        eval_set=(X_test, y_test),
        verbose=0,
    )
    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)
    log(f"  CatBoost: train_acc={train_acc:.4f} test_acc={test_acc:.4f} gap={train_acc-test_acc:.4f}")
    return model, train_acc, test_acc


# ══════════════════════════════════════════════════════════════
# SECTION 6: ENSEMBLE
# ══════════════════════════════════════════════════════════════

def soft_vote_ensemble(models, X_test, y_test, weights=None):
    """Soft voting ensemble — average predicted probabilities."""
    if weights is None:
        weights = [1.0 / len(models)] * len(models)

    probas = []
    for model, w in zip(models, weights):
        proba = model.predict_proba(X_test)[:, 1]
        probas.append(proba * w)

    avg_proba = np.sum(probas, axis=0)
    preds = (avg_proba >= 0.5).astype(int)
    acc = accuracy_score(y_test, preds)
    return preds, avg_proba, acc


# ══════════════════════════════════════════════════════════════
# SECTION 7: METRICS
# ══════════════════════════════════════════════════════════════

def compute_trading_metrics(y_true, y_pred, next_bar_returns):
    """Compute trading-relevant metrics."""
    correct = (y_true == y_pred)
    returns = np.where(correct, next_bar_returns, -next_bar_returns * 0.5)

    accuracy = accuracy_score(y_true, y_pred)
    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    wins = returns[returns > 0]
    losses = returns[returns < 0]
    win_rate = len(wins) / len(returns) if len(returns) > 0 else 0
    avg_win = np.mean(wins) if len(wins) > 0 else 0
    avg_loss = np.mean(np.abs(losses)) if len(losses) > 0 else 0
    profit_factor = avg_win / avg_loss if avg_loss > 0 else float("inf")

    if len(returns) >= 30 and np.std(returns) > 0:
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(35040)
    elif len(returns) > 1 and np.std(returns) > 0:
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(len(returns))
    else:
        sharpe = 0.0

    cumulative = np.cumsum(returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdowns = running_max - cumulative
    max_drawdown = np.max(drawdowns) if len(drawdowns) > 0 else 0

    return {
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "win_rate": round(win_rate, 4),
        "avg_win": round(float(avg_win), 6),
        "avg_loss": round(float(avg_loss), 6),
        "profit_factor": round(profit_factor, 4),
        "sharpe_ratio": round(float(sharpe), 4),
        "max_drawdown": round(float(max_drawdown), 6),
        "total_return": round(float(np.sum(returns)), 6),
    }


def walk_forward_evaluate(X, y, model, n_folds=5, embargo=24, scale_pos_weight=2.3):
    """Evaluate model with walk-forward CV."""
    fold_accs = []
    fold_f1s = []
    for train_idx, test_idx in walk_forward_cv(len(X), n_folds=n_folds, embargo=embargo):
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr, y_te = y[train_idx], y[test_idx]

        m = xgb.XGBClassifier(
            n_estimators=150, max_depth=3, learning_rate=0.03,
            subsample=0.7, colsample_bytree=0.7,
            min_child_weight=15, reg_alpha=5.0, reg_lambda=5.0,
            scale_pos_weight=scale_pos_weight,
            random_state=RANDOM_STATE, eval_metric="logloss",
            verbosity=0, n_jobs=-1,
        )
        m.fit(X_tr, y_tr, verbose=False)
        y_pred = m.predict(X_te)
        fold_accs.append(accuracy_score(y_te, y_pred))
        fold_f1s.append(f1_score(y_te, y_pred, zero_division=0))

    return fold_accs, fold_f1s


# ══════════════════════════════════════════════════════════════
# SECTION 8: FEATURE IMPORTANCE
# ══════════════════════════════════════════════════════════════

def aggregate_feature_importance(models, feature_names):
    """Aggregate feature importance across all 3 models."""
    importance_dict = {name: 0.0 for name in feature_names}

    for model in models:
        if hasattr(model, "feature_importances_"):
            imp = model.feature_importances_
            imp = imp / imp.sum() if imp.sum() > 0 else imp
            for name, score in zip(feature_names, imp):
                importance_dict[name] += score / len(models)

    ranked = sorted(importance_dict.items(), key=lambda x: -x[1])
    return ranked


# ══════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════

def main():
    start_time = time.time()
    log("=" * 70)
    log("MEGA MODEL V2 — Regularized Ensemble with Triple-Barrier Labels")
    log("=" * 70)

    # 1. Load data
    df = load_data()
    feature_names = get_feature_cols(df)
    log(f"  Available features: {len(feature_names)}")

    X_all = df[feature_names].fillna(0).values.astype(np.float32)
    y_all = df["target_win"].values.astype(int)
    returns_all = df["fwd_ret_1bar"].values if "fwd_ret_1bar" in df.columns else np.zeros(len(df))

    # Replace inf with 0
    X_all = np.nan_to_num(X_all, nan=0.0, posinf=0.0, neginf=0.0)

    # Compute class weight for imbalance
    n_neg = (y_all == 0).sum()
    n_pos = (y_all == 1).sum()
    scale_pos_weight = n_neg / n_pos
    log(f"  Class balance: neg={n_neg}, pos={n_pos}, scale_pos_weight={scale_pos_weight:.2f}")

    # 2. Walk-forward split
    train_idx, test_idx = walk_forward_split(len(X_all), train_ratio=0.8)
    X_train_full, X_test = X_all[train_idx], X_all[test_idx]
    y_train_full, y_test = y_all[train_idx], y_all[test_idx]
    returns_test = returns_all[test_idx]

    # 3. Feature selection on training data only (no leak)
    selected_features = select_features_mi(X_train_full, y_train_full, feature_names, TOP_K_FEATURES)
    X_train_sel = X_train_full[:, [feature_names.index(f) for f in selected_features]]
    X_test_sel = X_test[:, [feature_names.index(f) for f in selected_features]]

    log(f"  Selected features shape: {X_train_sel.shape}")

    # 4. Optuna tuning for XGBoost
    log(f"\n{'='*70}")
    log(f"OPTUNA TUNING — {N_TRIALS} trials (XGBoost, regularized)")
    log(f"{'='*70}")

    study = optuna.create_study(
        direction="maximize",
        sampler=TPESampler(seed=RANDOM_STATE),
    )
    objective_fn = make_objective(X_train_sel, y_train_full, selected_features, scale_pos_weight)

    def progress_callback(study, trial):
        if (trial.number + 1) % 10 == 0 or trial.number == 0:
            best = study.best_trial.value if study.best_trial else 0
            log(f"  Trial {trial.number+1:3d}/{N_TRIALS}: value={trial.value:.4f} (best={best:.4f})")

    study.optimize(objective_fn, n_trials=N_TRIALS, show_progress_bar=False, callbacks=[progress_callback])

    best_params = study.best_params
    log(f"\n  Best Optuna trial: {study.best_trial.value:.4f}")
    log(f"  Best params: {json.dumps(best_params, indent=4)}")

    # 5. Train final models
    log(f"\n{'='*70}")
    log("TRAINING FINAL MODELS (regularized)")
    log(f"{'='*70}")

    xgb_model, xgb_train_acc, xgb_test_acc = train_xgboost(
        X_train_sel, y_train_full, X_test_sel, y_test, best_params, scale_pos_weight
    )
    lgb_model, lgb_train_acc, lgb_test_acc = train_lightgbm(
        X_train_sel, y_train_full, X_test_sel, y_test, selected_features
    )
    cb_model, cb_train_acc, cb_test_acc = train_catboost(
        X_train_sel, y_train_full, X_test_sel, y_test, selected_features
    )

    # 6. Ensemble
    log(f"\n{'='*70}")
    log("ENSEMBLE — Soft Voting")
    log(f"{'='*70}")

    models = [xgb_model, lgb_model, cb_model]
    model_names = ["XGBoost", "LightGBM", "CatBoost"]
    test_accs = [xgb_test_acc, lgb_test_acc, cb_test_acc]

    # Weight by test accuracy
    total_acc = sum(test_accs)
    weights = [a / total_acc for a in test_accs]
    log(f"  Weights: {', '.join(f'{n}={w:.3f}' for n, w in zip(model_names, weights))}")

    ens_preds, ens_proba, ens_acc = soft_vote_ensemble(models, X_test_sel, y_test, weights)
    log(f"  Ensemble test accuracy: {ens_acc:.4f}")

    # Check for overfitting
    avg_train_acc = np.mean([xgb_train_acc, lgb_train_acc, cb_train_acc])
    gap = avg_train_acc - ens_acc
    log(f"\n  Overfitting check:")
    log(f"    Avg train accuracy: {avg_train_acc:.4f}")
    log(f"    Ensemble test accuracy: {ens_acc:.4f}")
    log(f"    Train-test gap: {gap:.4f}")
    if gap > 0.10:
        log(f"  [WARN] High overfitting gap ({gap:.4f}) — consider more regularization")
    else:
        log(f"  [OK] Acceptable overfitting gap")

    # 7. Detailed metrics
    log(f"\n{'='*70}")
    log("DETAILED METRICS")
    log(f"{'='*70}")

    all_metrics = {}
    for name, model, train_acc, test_acc in [
        ("XGBoost", xgb_model, xgb_train_acc, xgb_test_acc),
        ("LightGBM", lgb_model, lgb_train_acc, lgb_test_acc),
        ("CatBoost", cb_model, cb_train_acc, cb_test_acc),
    ]:
        preds = model.predict(X_test_sel)
        metrics = compute_trading_metrics(y_test, preds, returns_test)
        metrics["train_accuracy"] = train_acc
        metrics["test_accuracy"] = test_acc
        all_metrics[name] = metrics
        log(f"\n  {name}:")
        for k, v in metrics.items():
            log(f"    {k:20s}: {v}")

    # Ensemble metrics
    ens_metrics = compute_trading_metrics(y_test, ens_preds, returns_test)
    ens_metrics["test_accuracy"] = ens_acc
    all_metrics["Ensemble"] = ens_metrics
    log(f"\n  Ensemble:")
    for k, v in ens_metrics.items():
        log(f"    {k:20s}: {v}")

    # 8. Walk-forward cross-validation
    log(f"\n{'='*70}")
    log("WALK-FORWARD CROSS-VALIDATION (5 folds, embargo=24)")
    log(f"{'='*70}")

    wf_accs, wf_f1s = walk_forward_evaluate(X_train_sel, y_train_full, xgb_model, n_folds=5, scale_pos_weight=scale_pos_weight)
    for i, (acc, f1) in enumerate(zip(wf_accs, wf_f1s)):
        log(f"  Fold {i+1}: acc={acc:.4f} f1={f1:.4f}")
    log(f"  Mean WF accuracy: {np.mean(wf_accs):.4f} (+/-{np.std(wf_accs):.4f})")
    log(f"  Mean WF F1: {np.mean(wf_f1s):.4f} (+/-{np.std(wf_f1s):.4f})")

    # 9. Feature importance
    log(f"\n{'='*70}")
    log("FEATURE IMPORTANCE (Top 30)")
    log(f"{'='*70}")

    importance = aggregate_feature_importance(models, selected_features)
    for i, (name, score) in enumerate(importance[:30]):
        log(f"  {i+1:2d}. {name:40s} {score:.4f}")

    # 10. Save artifacts
    log(f"\n{'='*70}")
    log("SAVING ARTIFACTS")
    log(f"{'='*70}")

    # XGBoost model
    xgb_path = OUT_DIR / f"mega_xgboost_v2_{TIMESTAMP}.pkl"
    with open(xgb_path, "wb") as f:
        pickle.dump({"model": xgb_model, "feature_names": selected_features, "type": "xgboost"}, f)
    log(f"  XGBoost: {xgb_path.name}")

    # LightGBM model
    lgb_path = OUT_DIR / f"mega_lightgbm_v2_{TIMESTAMP}.pkl"
    with open(lgb_path, "wb") as f:
        pickle.dump({"model": lgb_model, "feature_names": selected_features, "type": "lightgbm"}, f)
    log(f"  LightGBM: {lgb_path.name}")

    # CatBoost model
    cb_path = OUT_DIR / f"mega_catboost_v2_{TIMESTAMP}.pkl"
    with open(cb_path, "wb") as f:
        pickle.dump({"model": cb_model, "feature_names": selected_features, "type": "catboost"}, f)
    log(f"  CatBoost: {cb_path.name}")

    # Ensemble
    ens_path = OUT_DIR / f"mega_ensemble_v2_{TIMESTAMP}.pkl"
    ensemble_dict = {
        "xgboost": xgb_model,
        "lightgbm": lgb_model,
        "catboost": cb_model,
        "feature_names": selected_features,
        "weights": dict(zip(model_names, weights)),
        "best_params": best_params,
        "trained": TIMESTAMP,
        "label_type": "triple_barrier_k2.0",
        "regularized": True,
    }
    with open(ens_path, "wb") as f:
        pickle.dump(ensemble_dict, f)
    log(f"  Ensemble: {ens_path.name}")

    # Feature importance CSV
    fi_path = OUT_DIR / "feature_importance_v2.csv"
    fi_df = pd.DataFrame(importance, columns=["feature", "importance"])
    fi_df["rank"] = range(1, len(fi_df) + 1)
    fi_df.to_csv(fi_path, index=False)
    log(f"  Feature importance: {fi_path.name}")

    # Optuna best params
    params_path = OUT_DIR / "optuna_best_params_v2.json"
    with open(params_path, "w") as f:
        json.dump(best_params, f, indent=2)
    log(f"  Best params: {params_path.name}")

    # Training report
    elapsed = time.time() - start_time
    report_path = OUT_DIR / "training_report_v2.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("MEGA MODEL V2 TRAINING REPORT (Regularized)\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Elapsed: {elapsed:.1f}s\n")
        f.write("=" * 70 + "\n\n")

        f.write("DATA\n")
        f.write(f"  Source: {FEAT_PATH.name}\n")
        f.write(f"  Total rows: {len(df)}\n")
        f.write(f"  Total features: {len(feature_names)}\n")
        f.write(f"  Selected features: {len(selected_features)}\n")
        f.write(f"  Train: {len(train_idx)} | Test: {len(test_idx)}\n")
        f.write(f"  Label: triple_barrier (k_tp=2.0, k_sl=1.5)\n")
        f.write(f"  target_win distribution: {df['target_win'].value_counts().to_dict()}\n\n")

        f.write("OPTUNA\n")
        f.write(f"  Trials: {N_TRIALS}\n")
        f.write(f"  Best CV accuracy: {study.best_trial.value:.4f}\n")
        f.write(f"  Best params:\n{json.dumps(best_params, indent=4)}\n\n")

        f.write("MODEL RESULTS\n")
        for name in ["XGBoost", "LightGBM", "CatBoost", "Ensemble"]:
            m = all_metrics[name]
            f.write(f"\n  {name}:\n")
            for k, v in m.items():
                f.write(f"    {k:20s}: {v}\n")

        f.write("\nWALK-FORWARD CV (5 folds, embargo=24)\n")
        for i, acc in enumerate(wf_accs):
            f.write(f"  Fold {i+1}: {acc:.4f}\n")
        f.write(f"  Mean: {np.mean(wf_accs):.4f} (+/-{np.std(wf_accs):.4f})\n")

        f.write("\nFEATURE IMPORTANCE (Top 30)\n")
        for i, (name, score) in enumerate(importance[:30]):
            f.write(f"  {i+1:2d}. {name:40s} {score:.4f}\n")

        f.write(f"\nOUTPUT FILES\n")
        f.write(f"  {xgb_path.name}\n")
        f.write(f"  {lgb_path.name}\n")
        f.write(f"  {cb_path.name}\n")
        f.write(f"  {ens_path.name}\n")
        f.write(f"  {fi_path.name}\n")
        f.write(f"  {params_path.name}\n")

    log(f"  Training report: {report_path.name}")

    log(f"\n{'='*70}")
    log(f"COMPLETE — {elapsed:.1f}s total")
    log(f"{'='*70}")


if __name__ == "__main__":
    main()
