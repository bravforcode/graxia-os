#!/usr/bin/env python3
"""
retrain_calibrated.py — Calibrated XGBoost for XAUUSD M15
===========================================================
Retrains with:
  1. Probability-weighted target (sample_weight = abs(5-bar forward return))
  2. Optuna tuning (150 trials) seeded from previous best_params
  3. 40 live-compatible features only
  4. Walk-forward purged CV (5 folds)
  5. Platt scaling calibration via CalibratedClassifierCV
"""

import json, pickle, time, warnings
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
import optuna
from optuna.samplers import TPESampler
from sklearn.calibration import CalibratedClassifierCV, calibration_curve
from sklearn.metrics import (
    accuracy_score, precision_score, brier_score_loss,
)
import warnings
warnings.filterwarnings("ignore")
optuna.logging.set_verbosity(optuna.logging.WARNING)

# ──── PATHS ────
BASE = Path(__file__).resolve().parent.parent
FEAT_PATH = BASE / "artifacts" / "features_v3" / "features_v3_mega_XAUUSD_15min.parquet"
OPTUNA_PATH = BASE / "artifacts" / "optuna" / "best_params.json"
ML_DIR = BASE / "ml" / "models"
OUT_MEGA = BASE / "artifacts" / "mega_model"
ML_DIR.mkdir(parents=True, exist_ok=True)
OUT_MEGA.mkdir(parents=True, exist_ok=True)

TIMESTAMP = "20260626"
N_TRIALS = 150
RANDOM_STATE = 42
FWD_BARS = 5
CV_FOLDS = 5
CV_EMBARGO = 12

LIVE_FEATURES = [
    "lower_shadow", "is_london_session", "rvol_20", "vol_ratio_20", "obv_slope_20",
    "stoch_d", "rsi_14", "month", "ret_1bar", "day_of_month", "atr_7",
    "is_ny_session", "ema_5_dist", "day_of_week", "is_asian_session", "is_bull_engulf",
    "ret_60bar", "is_doji", "cci_20", "upper_shadow", "bb_squeeze", "atr_21",
    "is_hammer", "ret_10bar", "ema_200_dist", "ema_20_dist", "sma_20_50_cross",
    "ema_10_dist", "rvol_10", "ret_5bar", "ret_15bar", "ret_30bar", "atr_14",
    "rvol_60", "bb_width", "bb_pctb", "rsi_7", "rsi_21", "stoch_k", "willr_14",
]

def log(msg: str):
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# ══════════════════════════════════════════════════════════════
# SECTION 1: LOAD DATA + BUILD CALIBRATED TARGET
# ══════════════════════════════════════════════════════════════

def load_data() -> pd.DataFrame:
    log(f"Loading {FEAT_PATH.name}...")
    df = pd.read_parquet(FEAT_PATH)
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    elif "datetime" in df.columns:
        df = df.set_index("datetime")
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()
    log(f"  Raw shape: {df.shape}")

    missing = [f for f in LIVE_FEATURES if f not in df.columns]
    if missing:
        raise ValueError(f"Missing live features: {missing}")

    # Build 5-bar forward return
    df["fwd_return_5bar"] = df["close"].shift(-FWD_BARS) / df["close"] - 1
    df = df.dropna(subset=["fwd_return_5bar"])

    # Binary label: 1 if forward return > 0
    df["target_calibrated"] = (df["fwd_return_5bar"] > 0).astype(int)

    log(f"  Rows after target: {len(df)}")
    log(f"  Target dist: {df['target_calibrated'].value_counts().to_dict()}")
    log(f"  fwd_return_5bar mean={df['fwd_return_5bar'].mean():.6f} std={df['fwd_return_5bar'].std():.6f}")
    return df


# ══════════════════════════════════════════════════════════════
# SECTION 2: WALK-FORWARD UTILS
# ══════════════════════════════════════════════════════════════

def walk_forward_split(n: int, train_ratio: float = 0.8):
    split_idx = int(n * train_ratio)
    train_idx = np.arange(0, split_idx)
    test_idx = np.arange(split_idx, n)
    log(f"  Split: train={len(train_idx)} test={len(test_idx)}")
    return train_idx, test_idx


def purged_cv(n: int, n_folds: int = 5, embargo: int = 12):
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
# SECTION 3: OPTUNA OBJECTIVE (seeded from prior best)
# ══════════════════════════════════════════════════════════════

def make_optuna_objective(X, y, sample_weights, prior_best):
    """Optuna objective: maximize mean CV accuracy."""
    center = prior_best

    def objective(trial):
        params = {
            "max_depth": trial.suggest_int("max_depth",
                max(3, center["max_depth"] - 2), min(12, center["max_depth"] + 3)),
            "learning_rate": trial.suggest_float("learning_rate",
                max(0.01, center["learning_rate"] * 0.3),
                min(0.5, center["learning_rate"] * 2.0), log=True),
            "n_estimators": trial.suggest_int("n_estimators",
                max(80, center["n_estimators"] - 100),
                min(800, center["n_estimators"] + 300), step=10),
            "subsample": trial.suggest_float("subsample",
                max(0.5, center["subsample"] - 0.2),
                min(1.0, center["subsample"] + 0.2)),
            "colsample_bytree": trial.suggest_float("colsample_bytree",
                max(0.2, center["colsample_bytree"] - 0.15),
                min(1.0, center["colsample_bytree"] + 0.3)),
            "gamma": trial.suggest_float("gamma",
                max(0.0, center["gamma"] - 2.0),
                min(8.0, center["gamma"] + 3.0)),
            "reg_alpha": trial.suggest_float("reg_alpha", 1e-4, 10, log=True),
            "reg_lambda": trial.suggest_float("reg_lambda", 1e-4, 10, log=True),
        }

        fold_accs = []
        for tr_i, te_i in purged_cv(len(X), CV_FOLDS, CV_EMBARGO):
            X_tr, X_te = X[tr_i], X[te_i]
            y_tr, y_te = y[tr_i], y[te_i]
            sw_tr = sample_weights[tr_i]

            model = xgb.XGBClassifier(**params, random_state=RANDOM_STATE,
                eval_metric="logloss", verbosity=0, n_jobs=-1)
            model.fit(X_tr, y_tr, sample_weight=sw_tr, verbose=False)
            preds = model.predict(X_te)
            fold_accs.append(accuracy_score(y_te, preds))

        return float(np.mean(fold_accs))

    return objective


# ══════════════════════════════════════════════════════════════
# SECTION 4: METRICS
# ══════════════════════════════════════════════════════════════

def compute_metrics(y_true, y_pred, y_proba, returns, label=""):
    acc = accuracy_score(y_true, y_pred)
    brier = brier_score_loss(y_true, y_proba)
    precision = precision_score(y_true, y_pred, zero_division=0)

    # Sharpe from directional returns
    correct = (y_true == y_pred)
    strat_returns = np.where(correct, returns, -returns * 0.5)
    if len(strat_returns) >= 30 and np.std(strat_returns) > 0:
        sharpe = np.mean(strat_returns) / np.std(strat_returns) * np.sqrt(35040)
    else:
        sharpe = 0.0
    cum = np.cumsum(strat_returns)
    running_max = np.maximum.accumulate(cum)
    max_dd = float(np.max(running_max - cum)) if len(cum) > 0 else 0.0
    win_rate = float(np.mean(strat_returns > 0)) if len(strat_returns) > 0 else 0.0

    return {
        "accuracy": round(acc, 4),
        "brier_score": round(brier, 6),
        "precision": round(precision, 4),
        "sharpe_ratio": round(float(sharpe), 4),
        "max_drawdown": round(max_dd, 6),
        "win_rate": round(win_rate, 4),
    }


def threshold_metrics(y_true, y_proba, thresholds=(0.50, 0.55, 0.60, 0.65, 0.70, 0.75)):
    results = {}
    for thr in thresholds:
        preds = (y_proba >= thr).astype(int)
        n_signals = int(preds.sum())
        if n_signals == 0:
            results[thr] = {"threshold": thr, "signals": 0, "precision": None, "win_rate": None}
            continue
        # For long-only: signals where we go long (pred=1)
        mask = preds == 1
        precision = float(y_true[mask].mean()) if mask.sum() > 0 else 0.0
        # Win rate among signals: did those bars actually go up?
        win_rate = float(y_true[mask].mean()) if mask.sum() > 0 else 0.0
        results[thr] = {
            "threshold": thr,
            "signals": n_signals,
            "signal_pct": round(n_signals / len(y_true) * 100, 1),
            "precision": round(precision, 4),
            "win_rate": round(win_rate, 4),
        }
    return results


def calibration_data(y_true, y_proba, n_bins=10):
    prob_true, prob_pred = calibration_curve(y_true, y_proba, n_bins=n_bins, strategy="uniform")
    return prob_true.tolist(), prob_pred.tolist()


# ══════════════════════════════════════════════════════════════
# SECTION 5: MAIN
# ══════════════════════════════════════════════════════════════

def main():
    t0 = time.time()
    log("=" * 70)
    log("CALIBRATED XGBOOST RETRAIN — XAUUSD M15")
    log("=" * 70)

    # 1. Load
    df = load_data()
    X = df[LIVE_FEATURES].fillna(0).values.astype(np.float32)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    y = df["target_calibrated"].values.astype(int)
    fwd_returns = df["fwd_return_5bar"].values
    # Sample weights = abs(forward return) — higher conviction → higher weight
    # CRITICAL: normalize so mean=1.0, otherwise effective n is tiny and gamma kills splits
    raw_weights = np.abs(fwd_returns).astype(np.float32)
    sample_weights = raw_weights / raw_weights.mean()

    log(f"  sample_weight (raw): mean={raw_weights.mean():.6f} max={raw_weights.max():.6f}")
    log(f"  sample_weight (norm): mean={sample_weights.mean():.4f} max={sample_weights.max():.4f}")

    # 2. Train/test split
    train_idx, test_idx = walk_forward_split(len(X))
    X_train, X_test = X[train_idx], X[test_idx]
    y_train, y_test = y[train_idx], y[test_idx]
    sw_train = sample_weights[train_idx]
    returns_test = fwd_returns[test_idx]

    # 3. Load prior Optuna best
    with open(OPTUNA_PATH) as f:
        prior_best = json.load(f)
    log(f"  Prior best params: {json.dumps(prior_best, indent=2)}")

    # 4. Optuna tuning
    log(f"\n{'='*70}")
    log(f"OPTUNA TUNING — {N_TRIALS} trials")
    log(f"{'='*70}")

    study = optuna.create_study(direction="maximize",
        sampler=TPESampler(seed=RANDOM_STATE))
    obj = make_optuna_objective(X_train, y_train, sw_train, prior_best)

    def progress(study, trial):
        if (trial.number + 1) % 25 == 0 or trial.number == 0:
            best = study.best_trial.value if study.best_trial else 0
            log(f"  Trial {trial.number+1:3d}/{N_TRIALS}: val={trial.value:.4f} best={best:.4f}")

    study.optimize(obj, n_trials=N_TRIALS, show_progress_bar=False, callbacks=[progress])
    best_params = study.best_params
    log(f"\n  Best CV accuracy: {study.best_trial.value:.4f}")
    log(f"  Best params:\n{json.dumps(best_params, indent=2)}")

    # 5. Train final XGBoost
    log(f"\n{'='*70}")
    log("TRAINING FINAL XGBOOST")
    log(f"{'='*70}")

    xgb_model = xgb.XGBClassifier(**best_params, random_state=RANDOM_STATE,
        eval_metric="logloss", verbosity=0, n_jobs=-1)
    xgb_model.fit(X_train, y_train, sample_weight=sw_train, verbose=False)

    # Raw (uncalibrated) metrics
    raw_train_pred = xgb_model.predict(X_train)
    raw_test_pred = xgb_model.predict(X_test)
    raw_train_acc = accuracy_score(y_train, raw_train_pred)
    raw_test_acc = accuracy_score(y_test, raw_test_pred)
    log(f"  Raw train_acc={raw_train_acc:.4f} test_acc={raw_test_acc:.4f}")

    # 6. Platt calibration (cv=5 on train)
    log(f"\n{'='*70}")
    log("PROBABILITY CALIBRATION (Platt scaling, cv=5)")
    log(f"{'='*70}")

    calibrated = CalibratedClassifierCV(xgb_model, method="sigmoid", cv=5)
    calibrated.fit(X_train, y_train, sample_weight=sw_train)

    # Calibrated predictions
    cal_train_proba = calibrated.predict_proba(X_train)[:, 1]
    cal_test_proba = calibrated.predict_proba(X_test)[:, 1]
    cal_train_pred = (cal_train_proba >= 0.5).astype(int)
    cal_test_pred = (cal_test_proba >= 0.5).astype(int)
    cal_train_acc = accuracy_score(y_train, cal_train_pred)
    cal_test_acc = accuracy_score(y_test, cal_test_pred)
    log(f"  Calibrated train_acc={cal_train_acc:.4f} test_acc={cal_test_acc:.4f}")

    # 7. Walk-forward CV (5 folds)
    log(f"\n{'='*70}")
    log("WALK-FORWARD CV (5 folds, calibrated retrain per fold)")
    log(f"{'='*70}")

    wf_accs = []
    for i, (tr_i, te_i) in enumerate(purged_cv(len(X), CV_FOLDS, CV_EMBARGO)):
        X_tr, X_te = X[tr_i], X[te_i]
        y_tr, y_te = y[tr_i], y[te_i]
        sw_tr = sample_weights[tr_i]

        m = xgb.XGBClassifier(**best_params, random_state=RANDOM_STATE,
            eval_metric="logloss", verbosity=0, n_jobs=-1)
        m.fit(X_tr, y_tr, sample_weight=sw_tr, verbose=False)
        # Calibrate each fold
        cal_m = CalibratedClassifierCV(m, method="sigmoid", cv=3)
        cal_m.fit(X_tr, y_tr, sample_weight=sw_tr)
        preds = (cal_m.predict_proba(X_te)[:, 1] >= 0.5).astype(int)
        acc = accuracy_score(y_te, preds)
        wf_accs.append(acc)
        log(f"  Fold {i+1}: {acc:.4f}")

    log(f"  Mean WF accuracy: {np.mean(wf_accs):.4f} (±{np.std(wf_accs):.4f})")

    # 8. Full metrics
    log(f"\n{'='*70}")
    log("METRICS")
    log(f"{'='*70}")

    test_metrics = compute_metrics(y_test, cal_test_pred, cal_test_proba, returns_test, "Test")
    test_metrics["train_accuracy"] = round(cal_train_acc, 4)
    test_metrics["test_accuracy"] = round(cal_test_acc, 4)
    test_metrics["wf_mean_accuracy"] = round(float(np.mean(wf_accs)), 4)
    test_metrics["wf_std_accuracy"] = round(float(np.std(wf_accs)), 4)

    log(f"  Train accuracy:  {cal_train_acc:.4f}")
    log(f"  Test accuracy:   {cal_test_acc:.4f}")
    log(f"  WF CV accuracy:  {np.mean(wf_accs):.4f} (±{np.std(wf_accs):.4f})")
    log(f"  Brier score:     {test_metrics['brier_score']:.6f}")
    log(f"  Sharpe ratio:    {test_metrics['sharpe_ratio']:.4f}")
    log(f"  Max drawdown:    {test_metrics['max_drawdown']:.6f}")

    # Threshold analysis
    thr_metrics = threshold_metrics(y_test, cal_test_proba)
    log("\n  Threshold analysis:")
    for thr, m in thr_metrics.items():
        if m.get("signals", 0) > 0:
            log(f"    @{m['threshold']:.2f}: signals={m['signals']} ({m['signal_pct']}%) "
                f"precision={m['precision']:.4f} win_rate={m['win_rate']:.4f}")

    # Calibration curve
    prob_true, prob_pred = calibration_data(y_test, cal_test_proba, n_bins=10)
    log("\n  Calibration curve (uncal → cal):")
    for pt, pp in zip(prob_true, prob_pred):
        log(f"    mean_pred={pp:.3f} → actual={pt:.3f}")

    # 9. Feature importance
    log(f"\n{'='*70}")
    log("FEATURE IMPORTANCE (Top 20)")
    log(f"{'='*70}")
    imp = xgb_model.feature_importances_
    ranked = sorted(zip(LIVE_FEATURES, imp), key=lambda x: -x[1])
    for i, (name, score) in enumerate(ranked[:20]):
        log(f"  {i+1:2d}. {name:30s} {score:.4f}")

    # 10. Save model (calibrated, dict format)
    log(f"\n{'='*70}")
    log("SAVING ARTIFACTS")
    log(f"{'='*70}")

    # Main pickle: calibrated model + feature_names
    model_path = ML_DIR / f"xgboost_live_{TIMESTAMP}.pkl"
    with open(model_path, "wb") as f:
        pickle.dump({"model": calibrated, "feature_names": LIVE_FEATURES}, f)
    log(f"  Model: {model_path.name}")

    # Optuna best params
    optuna_out = OUT_MEGA / "calibrated_optuna_best.json"
    with open(optuna_out, "w") as f:
        json.dump(best_params, f, indent=2)
    log(f"  Optuna params: {optuna_out.name}")

    # Report
    report_path = OUT_MEGA / "calibrated_retrain_report.txt"
    elapsed = time.time() - t0
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("=" * 70 + "\n")
        f.write("CALIBRATED XGBOOST RETRAIN REPORT\n")
        f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Elapsed: {elapsed:.1f}s\n")
        f.write("=" * 70 + "\n\n")

        f.write("CONFIG\n")
        f.write(f"  Data: {FEAT_PATH.name}\n")
        f.write(f"  Rows: {len(df)}\n")
        f.write(f"  Features: {len(LIVE_FEATURES)} live-compatible\n")
        f.write("  Target: 5-bar forward return > 0\n")
        f.write("  Sample weights: abs(forward_return)\n")
        f.write(f"  Train: {len(train_idx)} | Test: {len(test_idx)}\n")
        f.write(f"  Optuna trials: {N_TRIALS}\n")
        f.write("  Calibration: Platt scaling (sigmoid), cv=5\n\n")

        f.write("BEST OPTUNA PARAMS\n")
        f.write(json.dumps(best_params, indent=2) + "\n\n")

        f.write("WALK-FORWARD CV (5 folds)\n")
        for i, acc in enumerate(wf_accs):
            f.write(f"  Fold {i+1}: {acc:.4f}\n")
        f.write(f"  Mean: {np.mean(wf_accs):.4f} (±{np.std(wf_accs):.4f})\n\n")

        f.write("TEST METRICS (calibrated)\n")
        for k, v in test_metrics.items():
            f.write(f"  {k:25s}: {v}\n")
        f.write("\n")

        f.write("THRESHOLD ANALYSIS\n")
        f.write(f"  {'Threshold':>10s} {'Signals':>8s} {'Sig%':>6s} {'Precision':>10s} {'WinRate':>10s}\n")
        for thr, m in thr_metrics.items():
            if m.get("signals", 0) > 0:
                f.write(f"  {m['threshold']:>10.2f} {m['signals']:>8d} {m['signal_pct']:>5.1f}% "
                        f"{m['precision']:>10.4f} {m['win_rate']:>10.4f}\n")
        f.write("\n")

        f.write("CALIBRATION CURVE\n")
        f.write(f"  {'Pred_Prob':>12s} {'Actual_Prob':>12s}\n")
        for pt, pp in zip(prob_true, prob_pred):
            f.write(f"  {pp:>12.4f} {pt:>12.4f}\n")
        f.write("\n")

        f.write("FEATURE IMPORTANCE (Top 30)\n")
        for i, (name, score) in enumerate(ranked[:30]):
            f.write(f"  {i+1:2d}. {name:30s} {score:.4f}\n")
        f.write("\n")

        f.write("OUTPUT FILES\n")
        f.write(f"  {model_path}\n")
        f.write(f"  {optuna_out}\n")
        f.write(f"  {report_path}\n")

    log(f"  Report: {report_path.name}")
    log(f"\n{'='*70}")
    log(f"DONE — {elapsed:.1f}s")
    log(f"{'='*70}")


if __name__ == "__main__":
    main()
