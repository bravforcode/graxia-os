#!/usr/bin/env python3
"""
train_live_model.py — Train live-compatible model from mega features
=====================================================================
Trains XGBoost + LightGBM + CatBoost + Ensemble using ONLY features
computable from OHLCV data (100 M15 bars the bot fetches from MT5).

Input:  artifacts/features_v3/features_v3_mega_XAUUSD_15min.parquet
Output: artifacts/mega_model/*_live_*.pkl
        ml/models/xgboost_live_*.pkl (for paper_trade_bot)

DEPRECATED: walk_forward_split(), walk_forward_cv(), and walk_forward_evaluate()
here are superseded by validation.walk_forward.simple_train_test_split,
validation.walk_forward.purged_cv, and validation.walk_forward.run_walk_forward.
This script remains as a CLI entry-point; import from validation.walk_forward or
core.walk_forward instead.
"""

import json
import pickle
import time
import warnings
from datetime import datetime
from pathlib import Path

import catboost as cb
import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd
import xgboost as xgb
from optuna.samplers import TPESampler
from sklearn.feature_selection import mutual_info_classif
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
)

warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

# ──────────────────────────── PATHS ────────────────────────────
BASE = Path(__file__).resolve().parent.parent
FEAT_PATH = BASE / "artifacts" / "features_v3" / "features_v3_mega_XAUUSD_15min.parquet"
OUT_DIR = BASE / "artifacts" / "mega_model"
OUT_DIR.mkdir(parents=True, exist_ok=True)
ML_DIR = BASE / "ml" / "models"
ML_DIR.mkdir(parents=True, exist_ok=True)

TIMESTAMP = datetime.now().strftime("%Y%m%d")
RANDOM_STATE = 42
N_TRIALS = 100
N_TRIALS_LGB = 50
N_TRIALS_CB = 30
EARLY_STOP = 50


def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════
# SECTION 1: LIVE-COMPATIBLE FEATURE DEFINITIONS
# ══════════════════════════════════════════════════════════════

LIVE_FEATURES = [
    # Price returns
    "ret_1bar",
    "ret_5bar",
    "ret_10bar",
    "ret_15bar",
    "ret_30bar",
    "ret_60bar",
    # Volatility
    "atr_7",
    "atr_14",
    "atr_21",
    "rvol_10",
    "rvol_20",
    "rvol_60",
    "bb_width",
    "bb_pctb",
    "bb_squeeze",
    # Momentum
    "rsi_7",
    "rsi_14",
    "rsi_21",
    "stoch_k",
    "stoch_d",
    "cci_20",
    "willr_14",
    # Trend
    "ema_5_dist",
    "ema_10_dist",
    "ema_20_dist",
    "ema_50_dist",
    "ema_100_dist",
    "ema_200_dist",
    "sma_20_50_cross",
    "sma_50_200_cross",
    "adx_14",
    # Volume
    "obv_slope_20",
    "vwap_dist",
    "vol_ratio_20",
    # Candlestick
    "body_ratio",
    "upper_shadow",
    "lower_shadow",
    "is_doji",
    "is_hammer",
    "is_bull_engulf",
    "is_bear_engulf",
    # Calendar (computable from datetime)
    "hour",
    "day_of_week",
    "day_of_month",
    "month",
    "is_london_session",
    "is_ny_session",
    "is_asian_session",
]

EXCLUDE_COLS = {
    # Targets / leakage
    "is_long",
    "next_bar_return",
    "target",
    "target_return",
    "target_3class",
    "target_class",
    "fwd_ret_1bar",
    "fwd_ret_5bar",
    "fwd_ret_10bar",
    "fwd_ret_15bar",
    # Triple-barrier labels
    "tb_label",
    "tb_bar_hit",
    "tb_side",
    "tb_ret",
    "tb_k_upper",
    "tb_k_lower",
    # OHLCV raw
    "open",
    "high",
    "low",
    "close",
    "volume",
    "tick_count",
    # Identifiers
    "symbol",
    "freq",
    # Non-live features
    "datetime",
    "date",
    "log_return",
    # Cross-asset
    "gold_silver_ratio",
    "gold_silver_ratio_pct",
    "gold_dxy_corr_20",
    "gold_dxy_corr_60",
    "gold_oil_ratio",
    "gold_oil_ratio_pct",
    "gold_vix_corr_20",
    "vix_level",
    "gold_tlt_corr_20",
    "gold_sp500_corr_20",
    "gold_usdjpy_corr_20",
    "gold_btc_corr_20",
    # Macro (FRED)
    "real_yield_10y",
    "real_yield_10y_chg5d",
    "real_yield_10y_chg20d",
    "breakeven_10y",
    "breakeven_10y_chg5d",
    "yield_curve_10y2y",
    "yield_curve_10y2y_chg5d",
    "dollar_trade_weighted",
    "dollar_tw_chg5d",
    "dollar_tw_chg20d",
    "hy_spread",
    "hy_spread_chg5d",
    "hy_spread_zscore",
    "fed_balance_sheet",
    "fed_bs_chg_20d",
    "fed_bs_chg_60d",
    "rrp_level",
    "rrp_chg_20d",
    "ted_spread",
    "baa10y_spread",
    "fred_unrate",
    "fred_cpiaucsl",
    "fred_fedfunds",
    "fred_indpro",
    "fred_umcsent",
    # COT
    "cot_commercials_net_pct",
    "cot_managed_money_net_pct",
    "cot_managed_money_long_pct",
    "cot_managed_money_short_pct",
    "cot_managed_money_spread_pct",
    "cot_large_spec_net_pct",
    "cot_commercials_net_pct_chg1w",
    "cot_commercials_net_pct_chg4w",
    "cot_managed_money_net_pct_chg1w",
    "cot_managed_money_net_pct_chg4w",
    "cot_large_spec_net_pct_chg1w",
    "cot_large_spec_net_pct_chg4w",
    "cot_oi_change",
    "cot_commercials_net_pct_extreme_high",
    "cot_commercials_net_pct_extreme_low",
    "cot_managed_money_net_pct_extreme_high",
    "cot_managed_money_net_pct_extreme_low",
    # Cross-asset momentum
    "dxy_mom_5d",
    "dxy_mom_10d",
    "dxy_mom_20d",
    "dxy_vol_20d",
    "vix_mom_5d",
    "vix_mom_10d",
    "vix_mom_20d",
    "vix_vol_20d",
    "tlt_mom_5d",
    "tlt_mom_10d",
    "tlt_mom_20d",
    "tlt_vol_20d",
    "oil_mom_5d",
    "oil_mom_10d",
    "oil_mom_20d",
    "oil_vol_20d",
    "silver_mom_5d",
    "silver_mom_10d",
    "silver_mom_20d",
    "silver_vol_20d",
    "sp500_mom_5d",
    "sp500_mom_10d",
    "sp500_mom_20d",
    "sp500_vol_20d",
    "usdjpy_mom_5d",
    "usdjpy_mom_10d",
    "usdjpy_mom_20d",
    "usdjpy_vol_20d",
    "btc_mom_5d",
    "btc_mom_10d",
    "btc_mom_20d",
    "btc_vol_20d",
    "term_premium_10y5y",
    "term_premium_chg5d",
    # Regime
    "regime_vix_low",
    "regime_vix_high",
    "regime_vix_extreme",
    "regime_yieldcurve_inverted",
    "regime_yieldcurve_flat",
    "regime_dollar_strong",
    "regime_dollar_weak",
    "regime_credit_stressed",
    "regime_gold_bull",
    "regime_gold_bear",
}


# ══════════════════════════════════════════════════════════════
# SECTION 2: LOAD & PREPARE DATA
# ══════════════════════════════════════════════════════════════


def load_data() -> pd.DataFrame:
    log(f"Loading mega features from {FEAT_PATH.name}...")
    df = pd.read_parquet(FEAT_PATH)

    # Handle index
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    elif "datetime" in df.columns:
        df["datetime"] = pd.to_datetime(df["datetime"], utc=True)
        df = df.set_index("datetime")
    df = df.sort_index()

    log(f"  Raw shape: {df.shape[0]} rows x {df.shape[1]} cols")
    return df


def get_live_features(df: pd.DataFrame) -> list:
    """Get live-compatible feature columns present in the dataset."""
    available = []
    for col in LIVE_FEATURES:
        if col in df.columns and df[col].dtype in (np.float64, np.float32, np.int64, np.int32):
            nan_pct = df[col].isna().mean() * 100
            if nan_pct < 5.0 and df[col].nunique() > 1:
                available.append(col)
            else:
                log(f"  SKIP {col}: NaN={nan_pct:.1f}%, unique={df[col].nunique()}")
        elif col in df.columns:
            log(f"  SKIP {col}: dtype={df[col].dtype}")
        else:
            log(f"  SKIP {col}: not in dataset")

    log(f"  Live-compatible features: {len(available)}")
    return available


def get_all_features(df: pd.DataFrame) -> list:
    """Get ALL numeric features (for mega model comparison)."""
    return [
        c
        for c in df.columns
        if c not in EXCLUDE_COLS and df[c].dtype in (np.float64, np.float32, np.int64, np.int32) and df[c].nunique() > 1
    ]


def select_features_mi(X: np.ndarray, y: np.ndarray, feature_names: list, k: int) -> list:
    """Select top-k features by mutual information."""
    log(f"Selecting top {min(k, len(feature_names))} features by mutual information...")
    if len(feature_names) <= k:
        log(f"  Only {len(feature_names)} features available, using all")
        return feature_names

    mi_scores = mutual_info_classif(X, y, random_state=RANDOM_STATE, n_neighbors=5)
    mi_ranking = sorted(zip(feature_names, mi_scores, strict=False), key=lambda x: -x[1])

    log("  Top 15 MI scores:")
    for name, score in mi_ranking[:15]:
        log(f"    {name:40s} {score:.4f}")

    selected = [name for name, _ in mi_ranking[:k]]
    log(f"  Selected {len(selected)} features (MI range: {mi_ranking[k-1][1]:.4f} — {mi_ranking[0][1]:.4f})")
    return selected


# ══════════════════════════════════════════════════════════════
# SECTION 3: WALK-FORWARD SPLIT
# ══════════════════════════════════════════════════════════════


def walk_forward_split(n: int, train_ratio: float = 0.8):
    """Time-ordered 80/20 split — NO look-ahead.

    DEPRECATED: Use validation.walk_forward.simple_train_test_split instead.
    """
    split_idx = int(n * train_ratio)
    train_idx = np.arange(0, split_idx)
    test_idx = np.arange(split_idx, n)
    log(
        f"  Walk-forward split: train={len(train_idx)} ({train_ratio*100:.0f}%), test={len(test_idx)} ({(1-train_ratio)*100:.0f}%)"
    )
    return train_idx, test_idx


def walk_forward_cv(n: int, n_folds: int = 5, embargo: int = 12):
    """Purged walk-forward CV for Optuna inner loop.

    DEPRECATED: Use validation.walk_forward.purged_cv instead.
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
# SECTION 4: OPTUNA OBJECTIVES
# ══════════════════════════════════════════════════════════════


def make_xgb_objective(X, y):
    """Create Optuna objective for XGBoost."""

    def objective(trial):
        params = {
            "max_depth": trial.suggest_int("max_depth", 3, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 100, 1000, step=50),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "gamma": trial.suggest_float("gamma", 0, 5),
            "reg_alpha": trial.suggest_float("reg_alpha", 0, 10),
            "reg_lambda": trial.suggest_float("reg_lambda", 0, 10),
            "scale_pos_weight": trial.suggest_float("scale_pos_weight", 0.5, 2.0),
        }
        fold_accs = []
        for train_idx, test_idx in walk_forward_cv(len(X), n_folds=3, embargo=12):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            model = xgb.XGBClassifier(
                **params,
                random_state=RANDOM_STATE,
                eval_metric="logloss",
                verbosity=0,
                n_jobs=1,
                tree_method="hist",
            )
            model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
            y_pred = model.predict(X_test)
            fold_accs.append(accuracy_score(y_test, y_pred))
        return np.mean(fold_accs)

    return objective


def make_lgb_objective(X, y):
    """Create Optuna objective for LightGBM."""

    def objective(trial):
        params = {
            "num_leaves": trial.suggest_int("num_leaves", 20, 150),
            "max_depth": trial.suggest_int("max_depth", 3, 12),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "n_estimators": trial.suggest_int("n_estimators", 100, 1000, step=50),
            "subsample": trial.suggest_float("subsample", 0.5, 1.0),
            "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
            "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
            "reg_alpha": trial.suggest_float("reg_alpha", 0, 10),
            "reg_lambda": trial.suggest_float("reg_lambda", 0, 10),
        }
        fold_accs = []
        for train_idx, test_idx in walk_forward_cv(len(X), n_folds=3, embargo=12):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            model = lgb.LGBMClassifier(
                **params,
                random_state=RANDOM_STATE,
                verbosity=-1,
                n_jobs=1,
                deterministic=True,
            )
            model.fit(
                X_train, y_train, eval_set=[(X_test, y_test)], callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)]
            )
            y_pred = model.predict(X_test)
            fold_accs.append(accuracy_score(y_test, y_pred))
        return np.mean(fold_accs)

    return objective


def make_cb_objective(X, y):
    """Create Optuna objective for CatBoost."""

    def objective(trial):
        params = {
            "depth": trial.suggest_int("depth", 4, 10),
            "learning_rate": trial.suggest_float("learning_rate", 0.01, 0.3, log=True),
            "iterations": trial.suggest_int("iterations", 100, 1000, step=50),
            "l2_leaf_reg": trial.suggest_float("l2_leaf_reg", 1, 10),
            "bagging_temperature": trial.suggest_float("bagging_temperature", 0, 1),
            "random_strength": trial.suggest_float("random_strength", 0, 10),
        }
        fold_accs = []
        for train_idx, test_idx in walk_forward_cv(len(X), n_folds=3, embargo=12):
            X_train, X_test = X[train_idx], X[test_idx]
            y_train, y_test = y[train_idx], y[test_idx]
            model = cb.CatBoostClassifier(
                **params,
                random_seed=RANDOM_STATE,
                verbose=0,
                early_stopping_rounds=EARLY_STOP,
            )
            model.fit(X_train, y_train, eval_set=(X_test, y_test), verbose=0)
            y_pred = model.predict(X_test)
            fold_accs.append(accuracy_score(y_test, y_pred))
        return np.mean(fold_accs)

    return objective


# ══════════════════════════════════════════════════════════════
# SECTION 5: TRAIN MODELS
# ══════════════════════════════════════════════════════════════


def train_xgboost(X_train, y_train, X_test, y_test, best_params):
    """Train XGBoost with best params + early stopping."""
    log("Training XGBoost...")
    model = xgb.XGBClassifier(
        **best_params,
        random_state=RANDOM_STATE,
        eval_metric="logloss",
        verbosity=0,
        n_jobs=1,
        tree_method="hist",
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)
    log(f"  XGBoost: train_acc={train_acc:.4f} test_acc={test_acc:.4f}")
    return model, train_acc, test_acc


def train_lightgbm(X_train, y_train, X_test, y_test, best_params):
    """Train LightGBM with best params."""
    log("Training LightGBM...")
    model = lgb.LGBMClassifier(
        **best_params,
        random_state=RANDOM_STATE,
        verbosity=-1,
        n_jobs=1,
        deterministic=True,
    )
    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], callbacks=[lgb.early_stopping(EARLY_STOP, verbose=False)])
    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)
    log(f"  LightGBM: train_acc={train_acc:.4f} test_acc={test_acc:.4f}")
    return model, train_acc, test_acc


def train_catboost(X_train, y_train, X_test, y_test, best_params):
    """Train CatBoost with best params."""
    log("Training CatBoost...")
    model = cb.CatBoostClassifier(
        **best_params,
        random_seed=RANDOM_STATE,
        verbose=0,
        early_stopping_rounds=EARLY_STOP,
    )
    model.fit(X_train, y_train, eval_set=(X_test, y_test), verbose=0)
    train_pred = model.predict(X_train)
    test_pred = model.predict(X_test)
    train_acc = accuracy_score(y_train, train_pred)
    test_acc = accuracy_score(y_test, test_pred)
    log(f"  CatBoost: train_acc={train_acc:.4f} test_acc={test_acc:.4f}")
    return model, train_acc, test_acc


def soft_vote_ensemble(models, X_test, y_test, weights=None):
    """Soft voting ensemble — average predicted probabilities."""
    if weights is None:
        weights = [1.0 / len(models)] * len(models)
    probas = []
    for model, w in zip(models, weights, strict=False):
        proba = model.predict_proba(X_test)[:, 1]
        probas.append(proba * w)
    avg_proba = np.sum(probas, axis=0)
    preds = (avg_proba >= 0.5).astype(int)
    acc = accuracy_score(y_test, preds)
    return preds, avg_proba, acc


# ══════════════════════════════════════════════════════════════
# SECTION 6: METRICS
# ══════════════════════════════════════════════════════════════


def compute_trading_metrics(y_true, y_pred, next_bar_returns):
    """Compute trading-relevant metrics."""
    correct = y_true == y_pred
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

    if len(returns) > 1 and np.std(returns) > 0:
        sharpe = np.mean(returns) / np.std(returns) * np.sqrt(35040)
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


def walk_forward_evaluate(X, y, n_folds=5, embargo=12):
    """Evaluate model with walk-forward CV.

    DEPRECATED: Use validation.walk_forward.run_walk_forward instead.
    """
    fold_accs = []
    for train_idx, test_idx in walk_forward_cv(len(X), n_folds=n_folds, embargo=embargo):
        X_tr, X_te = X[train_idx], X[test_idx]
        y_tr, y_te = y[train_idx], y[test_idx]
        m = xgb.XGBClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=RANDOM_STATE,
            eval_metric="logloss",
            verbosity=0,
            n_jobs=1,
            tree_method="hist",
        )
        m.fit(X_tr, y_tr, verbose=False)
        y_pred = m.predict(X_te)
        fold_accs.append(accuracy_score(y_te, y_pred))
    return fold_accs


def aggregate_feature_importance(models, feature_names):
    """Aggregate feature importance across all 3 models."""
    importance_dict = {name: 0.0 for name in feature_names}
    for model in models:
        if hasattr(model, "feature_importances_"):
            imp = model.feature_importances_
            imp = imp / imp.sum() if imp.sum() > 0 else imp
            for name, score in zip(feature_names, imp, strict=False):
                importance_dict[name] += score / len(models)
    ranked = sorted(importance_dict.items(), key=lambda x: -x[1])
    return ranked


# ══════════════════════════════════════════════════════════════
# SECTION 7: TRAINING PIPELINE
# ══════════════════════════════════════════════════════════════


def train_model_pipeline(
    df: pd.DataFrame,
    feature_cols: list,
    model_type: str,
    label: str,
    report_lines: list,
):
    """Train one complete model pipeline."""
    log(f"\n{'='*70}")
    log(f"TRAINING {label} MODEL — {len(feature_cols)} features")
    log(f"{'='*70}")

    report_lines.append(f"\n{'='*70}")
    report_lines.append(f"{label} MODEL — {len(feature_cols)} features")
    report_lines.append(f"{'='*70}")

    # Create targets
    df_train = df.copy()
    df_train["next_bar_return"] = df_train["close"].shift(-1) / df_train["close"] - 1
    df_train["is_long"] = (df_train["next_bar_return"] > 0).astype(int)
    df_train = df_train.dropna(subset=["next_bar_return", "is_long"])

    X_all = df_train[feature_cols].fillna(0).values.astype(np.float32)
    y_all = df_train["is_long"].values.astype(int)
    returns_all = df_train["next_bar_return"].values
    X_all = np.nan_to_num(X_all, nan=0.0, posinf=0.0, neginf=0.0)

    log(f"  Data: {len(X_all)} rows, {len(feature_cols)} features")
    log(f"  is_long distribution: {dict(pd.Series(y_all).value_counts())}")

    # Walk-forward split
    train_idx, test_idx = walk_forward_split(len(X_all), train_ratio=0.8)
    X_train, X_test = X_all[train_idx], X_all[test_idx]
    y_train, y_test = y_all[train_idx], y_all[test_idx]
    returns_test = returns_all[test_idx]

    # Feature selection if too many features
    if len(feature_cols) > 40:
        selected = select_features_mi(X_train, y_train, feature_cols, min(40, len(feature_cols)))
        feat_idx = [feature_cols.index(f) for f in selected]
        X_train = X_train[:, feat_idx]
        X_test = X_test[:, feat_idx]
        feature_names = selected
    else:
        feature_names = feature_cols

    log(f"  Training features: {len(feature_names)}")

    # Optuna tuning
    log(f"\n  OPTUNA TUNING — {N_TRIALS} trials")
    if model_type == "xgboost":
        study = optuna.create_study(direction="maximize", sampler=TPESampler(seed=RANDOM_STATE))
        objective_fn = make_xgb_objective(X_train, y_train)
    elif model_type == "lightgbm":
        study = optuna.create_study(direction="maximize", sampler=TPESampler(seed=RANDOM_STATE))
        objective_fn = make_lgb_objective(X_train, y_train)
    elif model_type == "catboost":
        study = optuna.create_study(direction="maximize", sampler=TPESampler(seed=RANDOM_STATE))
        objective_fn = make_cb_objective(X_train, y_train)

    def progress_callback(study, trial):
        if (trial.number + 1) % 10 == 0 or trial.number == 0:
            best = study.best_trial.value if study.best_trial else 0
            log(f"    Trial {trial.number+1:3d}/{N_TRIALS}: value={trial.value:.4f} (best={best:.4f})")

    study.optimize(objective_fn, n_trials=N_TRIALS, show_progress_bar=False, callbacks=[progress_callback])
    best_params = study.best_params
    log(f"  Best CV accuracy: {study.best_trial.value:.4f}")

    report_lines.append(f"\n  Optuna best CV: {study.best_trial.value:.4f}")
    report_lines.append(f"  Best params: {json.dumps(best_params, indent=4)}")

    # Train all three models with their own best params
    log(f"\n  Training all models with {model_type}-tuned hyperparameters...")
    xgb_model, xgb_train, xgb_test = train_xgboost(X_train, y_train, X_test, y_test, best_params)

    # Re-tune LightGBM and CatBoost too
    log("\n  Tuning LightGBM...")
    study_lgb = optuna.create_study(direction="maximize", sampler=TPESampler(seed=RANDOM_STATE))
    study_lgb.optimize(
        make_lgb_objective(X_train, y_train),
        n_trials=N_TRIALS_LGB,
        show_progress_bar=False,
        callbacks=[progress_callback],
    )
    lgb_params = study_lgb.best_params
    lgb_model, lgb_train, lgb_test = train_lightgbm(X_train, y_train, X_test, y_test, lgb_params)

    log("\n  Tuning CatBoost...")
    study_cb = optuna.create_study(direction="maximize", sampler=TPESampler(seed=RANDOM_STATE))
    study_cb.optimize(
        make_cb_objective(X_train, y_train),
        n_trials=N_TRIALS_CB,
        show_progress_bar=False,
        callbacks=[progress_callback],
    )
    cb_params = study_cb.best_params
    cb_model, cb_train, cb_test = train_catboost(X_train, y_train, X_test, y_test, cb_params)

    # Ensemble
    log("\n  ENSEMBLE — Soft Voting")
    models = [xgb_model, lgb_model, cb_model]
    model_names = ["XGBoost", "LightGBM", "CatBoost"]
    test_accs = [xgb_test, lgb_test, cb_test]
    total_acc = sum(test_accs)
    weights = [a / total_acc for a in test_accs]
    log(f"  Weights: {', '.join(f'{n}={w:.3f}' for n, w in zip(model_names, weights, strict=False))}")

    ens_preds, ens_proba, ens_acc = soft_vote_ensemble(models, X_test, y_test, weights)
    log(f"  Ensemble test accuracy: {ens_acc:.4f}")

    # Detailed metrics
    log("\n  DETAILED METRICS")
    all_metrics = {}
    for name, model, train_acc, test_acc in [
        ("XGBoost", xgb_model, xgb_train, xgb_test),
        ("LightGBM", lgb_model, lgb_train, lgb_test),
        ("CatBoost", cb_model, cb_train, cb_test),
    ]:
        preds = model.predict(X_test)
        metrics = compute_trading_metrics(y_test, preds, returns_test)
        metrics["train_accuracy"] = train_acc
        metrics["test_accuracy"] = test_acc
        all_metrics[name] = metrics
        log(f"\n    {name}:")
        for k, v in metrics.items():
            log(f"      {k:20s}: {v}")

    ens_metrics = compute_trading_metrics(y_test, ens_preds, returns_test)
    ens_metrics["test_accuracy"] = ens_acc
    all_metrics["Ensemble"] = ens_metrics
    log("\n    Ensemble:")
    for k, v in ens_metrics.items():
        log(f"      {k:20s}: {v}")

    # Walk-forward CV
    log("\n  WALK-FORWARD CV (5 folds)")
    wf_accs = walk_forward_evaluate(X_train, y_train, n_folds=5)
    for i, acc in enumerate(wf_accs):
        log(f"    Fold {i+1}: {acc:.4f}")
    log(f"    Mean WF accuracy: {np.mean(wf_accs):.4f} (±{np.std(wf_accs):.4f})")

    # Feature importance
    log("\n  FEATURE IMPORTANCE (Top 15)")
    importance = aggregate_feature_importance(models, feature_names)
    for i, (name, score) in enumerate(importance[:15]):
        log(f"    {i+1:2d}. {name:40s} {score:.4f}")

    # Write to report
    report_lines.append("\n  MODEL RESULTS:")
    for name in ["XGBoost", "LightGBM", "CatBoost", "Ensemble"]:
        m = all_metrics[name]
        report_lines.append(f"\n    {name}:")
        for k, v in m.items():
            report_lines.append(f"      {k:20s}: {v}")

    report_lines.append("\n  WALK-FORWARD CV (5 folds):")
    for i, acc in enumerate(wf_accs):
        report_lines.append(f"    Fold {i+1}: {acc:.4f}")
    report_lines.append(f"    Mean: {np.mean(wf_accs):.4f} (±{np.std(wf_accs):.4f})")

    report_lines.append("\n  FEATURE IMPORTANCE (Top 15):")
    for i, (name, score) in enumerate(importance[:15]):
        report_lines.append(f"    {i+1:2d}. {name:40s} {score:.4f}")

    return {
        "xgb_model": xgb_model,
        "lgb_model": lgb_model,
        "cb_model": cb_model,
        "feature_names": feature_names,
        "weights": dict(zip(model_names, weights, strict=False)),
        "xgb_params": best_params,
        "lgb_params": lgb_params,
        "cb_params": cb_params,
        "metrics": all_metrics,
        "wf_mean": np.mean(wf_accs),
        "wf_std": np.std(wf_accs),
        "importance": importance,
    }


# ══════════════════════════════════════════════════════════════
# SECTION 8: MAIN
# ══════════════════════════════════════════════════════════════


def main():
    start_time = time.time()
    report_lines = []

    log("=" * 70)
    log("LIVE MODEL TRAINING — OHLCV-Only Features")
    log("=" * 70)
    report_lines.append("=" * 70)
    report_lines.append("LIVE MODEL TRAINING REPORT")
    report_lines.append(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report_lines.append("=" * 70)

    # Load data
    df = load_data()

    # Get live features
    live_features = get_live_features(df)
    report_lines.append("\nDATA")
    report_lines.append(f"  Source: {FEAT_PATH.name}")
    report_lines.append(f"  Total rows: {len(df)}")
    report_lines.append(f"  Live-compatible features: {len(live_features)}")
    report_lines.append(f"  Features: {live_features}")

    # Train live model
    result = train_model_pipeline(df, live_features, "xgboost", "LIVE", report_lines)

    # Save live models
    log(f"\n{'='*70}")
    log("SAVING LIVE MODELS")
    log(f"{'='*70}")

    # XGBoost live
    xgb_path = OUT_DIR / f"mega_xgboost_live_{TIMESTAMP}.pkl"
    with open(xgb_path, "wb") as f:
        pickle.dump(
            {
                "model": result["xgb_model"],
                "feature_names": result["feature_names"],
                "type": "xgboost",
                "train_acc": result["metrics"]["XGBoost"]["train_accuracy"],
                "test_acc": result["metrics"]["XGBoost"]["test_accuracy"],
            },
            f,
        )
    log(f"  XGBoost: {xgb_path.name}")

    # LightGBM live
    lgb_path = OUT_DIR / f"mega_lightgbm_live_{TIMESTAMP}.pkl"
    with open(lgb_path, "wb") as f:
        pickle.dump(
            {
                "model": result["lgb_model"],
                "feature_names": result["feature_names"],
                "type": "lightgbm",
                "train_acc": result["metrics"]["LightGBM"]["train_accuracy"],
                "test_acc": result["metrics"]["LightGBM"]["test_accuracy"],
            },
            f,
        )
    log(f"  LightGBM: {lgb_path.name}")

    # CatBoost live
    cb_path = OUT_DIR / f"mega_catboost_live_{TIMESTAMP}.pkl"
    with open(cb_path, "wb") as f:
        pickle.dump(
            {
                "model": result["cb_model"],
                "feature_names": result["feature_names"],
                "type": "catboost",
                "train_acc": result["metrics"]["CatBoost"]["train_accuracy"],
                "test_acc": result["metrics"]["CatBoost"]["test_accuracy"],
            },
            f,
        )
    log(f"  CatBoost: {cb_path.name}")

    # Ensemble live
    ens_path = OUT_DIR / f"mega_ensemble_live_{TIMESTAMP}.pkl"
    with open(ens_path, "wb") as f:
        pickle.dump(
            {
                "xgboost": result["xgb_model"],
                "lightgbm": result["lgb_model"],
                "catboost": result["cb_model"],
                "feature_names": result["feature_names"],
                "weights": result["weights"],
                "xgb_params": result["xgb_params"],
                "lgb_params": result["lgb_params"],
                "cb_params": result["cb_params"],
                "trained": TIMESTAMP,
            },
            f,
        )
    log(f"  Ensemble: {ens_path.name}")

    # Copy best model to ml/models for paper_trade_bot
    # Use XGBoost as primary (bot loads xgboost*.pkl)
    best_model_path = ML_DIR / f"xgboost_live_{TIMESTAMP}.pkl"
    with open(best_model_path, "wb") as f:
        pickle.dump(
            {
                "model": result["xgb_model"],
                "feature_names": result["feature_names"],
                "train_acc": result["metrics"]["XGBoost"]["train_accuracy"],
                "test_acc": result["metrics"]["XGBoost"]["test_accuracy"],
                "symbol": "XAUUSD",
                "trained": TIMESTAMP,
            },
            f,
        )
    log(f"  Paper-trade compatible: {best_model_path.name}")

    # Feature importance CSV
    fi_path = OUT_DIR / "feature_importance_live.csv"
    fi_df = pd.DataFrame(result["importance"], columns=["feature", "importance"])
    fi_df["rank"] = range(1, len(fi_df) + 1)
    fi_df.to_csv(fi_path, index=False)
    log(f"  Feature importance: {fi_path.name}")

    # Write report
    elapsed = time.time() - start_time
    report_lines.append(f"\n{'='*70}")
    report_lines.append("OUTPUT FILES")
    report_lines.append(f"{'='*70}")
    report_lines.append(f"  {xgb_path.name}")
    report_lines.append(f"  {lgb_path.name}")
    report_lines.append(f"  {cb_path.name}")
    report_lines.append(f"  {ens_path.name}")
    report_lines.append(f"  {fi_path.name}")
    report_lines.append(f"  {best_model_path.name} (for paper_trade_bot)")

    report_path = OUT_DIR / "live_model_report.txt"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    log(f"  Report: {report_path.name}")

    log(f"\n{'='*70}")
    log(f"COMPLETE — {elapsed:.1f}s total")
    log(f"{'='*70}")


if __name__ == "__main__":
    main()
