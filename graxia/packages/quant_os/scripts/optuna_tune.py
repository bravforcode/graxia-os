#!/usr/bin/env python3
"""Optuna hyperparameter tuning for XGBoost on XAUUSD M15 data."""

import json, os, time, warnings
import numpy as np
import pandas as pd
import xgboost as xgb
import optuna
from optuna.samplers import TPESampler
from optuna.pruners import MedianPruner
from sklearn.metrics import accuracy_score, f1_score, confusion_matrix
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(BASE, "artifacts", "optuna")
FEAT_PATH = os.path.join(BASE, "artifacts", "features_v2", "features_v2_XAUUSD_15min.parquet")
os.makedirs(OUT_DIR, exist_ok=True)


def load_and_prep():
    df = pd.read_parquet(FEAT_PATH)
    if "timestamp" in df.columns:
        df = df.set_index("timestamp")
    df.index = pd.to_datetime(df.index, utc=True)
    df = df.sort_index()

    # Binary target: remove 0, map -1→0
    df = df[df["target"] != 0].copy()
    df["target"] = df["target"].replace({-1: 0, 1: 1})

    # Last 20000 bars
    df = df.tail(20000)
    return df


def get_feature_cols(df):
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


class TimeSeriesCV:
    """Standalone PurgedKFold: sequential folds, no lookahead."""
    def __init__(self, n_folds=5, embargo=12):
        self.n_folds = n_folds
        self.embargo = embargo

    def split(self, X, y=None):
        n = len(X)
        fold_size = n // (self.n_folds + 1)
        for i in range(self.n_folds):
            train_end = (i + 1) * fold_size
            test_start = train_end
            test_end = test_start + fold_size
            if test_end > n:
                break
            # Apply embargo: remove last embargo samples from train
            train_start = 0
            train_end_embargoed = train_end - self.embargo
            train_idx = list(range(train_start, train_end_embargoed))
            test_idx = list(range(test_start, min(test_end, n)))
            yield train_idx, test_idx


def objective(trial, X, y, cv):
    params = {
        "max_depth": trial.suggest_int("max_depth", 3, 8),
        "learning_rate": trial.suggest_float("learning_rate", 0.005, 0.3, log=True),
        "n_estimators": trial.suggest_int("n_estimators", 50, 500),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.3, 1.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 50, log=True),
        "gamma": trial.suggest_float("gamma", 0.0, 5.0),
        "reg_alpha": trial.suggest_float("reg_alpha", 1e-5, 10, log=True),
        "reg_lambda": trial.suggest_float("reg_lambda", 1e-5, 10, log=True),
    }

    accs = []
    for fold, (train_idx, test_idx) in enumerate(cv.split(X)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        model = xgb.XGBClassifier(
            **params,
            random_state=42,
            eval_metric="logloss",
            use_label_encoder=False,
            verbosity=0,
            tree_method="hist",
            early_stopping_rounds=50,
        )
        model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)
        preds = model.predict(X_test)
        acc = accuracy_score(y_test, preds)
        accs.append(acc)

        trial.report(acc, fold)
        if trial.should_prune():
            raise optuna.TrialPruned()

    return float(np.mean(accs))


def train_eval(params, X_train, y_train, X_test, y_test, label=""):
    model = xgb.XGBClassifier(
        **params,
        random_state=42,
        eval_metric="logloss",
        use_label_encoder=False,
        verbosity=0,
        tree_method="hist",
    )
    model.fit(X_train, y_train)
    preds = model.predict(X_test)
    acc = accuracy_score(y_test, preds)
    f1 = f1_score(y_test, preds)
    cm = confusion_matrix(y_test, preds)
    print(f"\n  [{label}]")
    print(f"    Accuracy:  {acc:.4f}")
    print(f"    F1 Score:  {f1:.4f}")
    print("    Confusion Matrix:")
    print(f"      TN={cm[0,0]:>4d}  FP={cm[0,1]:>4d}")
    print(f"      FN={cm[1,0]:>4d}  TP={cm[1,1]:>4d}")
    return {"accuracy": acc, "f1": f1, "confusion_matrix": cm.tolist()}


def plot_feature_importance(model, feature_names, path):
    importance = model.feature_importances_
    idx = np.argsort(importance)[::-1][:20]
    top_names = [feature_names[i] for i in idx]
    top_vals = importance[idx]

    fig, ax = plt.subplots(figsize=(10, 8))
    bars = ax.barh(range(len(top_names)), top_vals[::-1])
    ax.set_yticks(range(len(top_names)))
    ax.set_yticklabels(top_names[::-1])
    ax.set_xlabel("Importance")
    ax.set_title("XGBoost Feature Importance (Optuna Best)")
    ax.invert_yaxis()
    for bar, val in zip(bars, top_vals[::-1]):
        ax.text(bar.get_width() + 0.001, bar.get_y() + bar.get_height() / 2,
                f"{val:.4f}", va="center", fontsize=8)
    plt.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
    print(f"  Saved feature importance plot: {path}")


def main():
    t0 = time.time()
    print("=" * 60)
    print("OPTUNA XGBOOST TUNING — XAUUSD M15")
    print("=" * 60)

    df = load_and_prep()
    print(f"\nData: {len(df)} rows, {df['target'].value_counts().to_dict()}")

    feature_cols = get_feature_cols(df)
    print(f"Features: {len(feature_cols)}")

    X = df[feature_cols].fillna(0).values.astype(np.float32)
    y = df["target"].values.astype(np.int32)

    # Holdout set: last 20% for final comparison
    split_idx = int(len(X) * 0.8)
    X_train_cv, X_holdout = X[:split_idx], X[split_idx:]
    y_train_cv, y_holdout = y[:split_idx], y[split_idx:]
    print(f"CV train: {len(X_train_cv)}, Holdout: {len(X_holdout)}")

    cv = TimeSeriesCV(n_folds=5, embargo=12)

    # --- Default XGBoost baseline ---
    default_params = {
        "max_depth": 6,
        "learning_rate": 0.3,
        "n_estimators": 100,
        "subsample": 1.0,
        "colsample_bytree": 1.0,
        "min_child_weight": 1,
        "gamma": 0.0,
        "reg_alpha": 0.0,
        "reg_lambda": 1.0,
    }
    print("\n--- DEFAULT PARAMS BASELINE ---")
    default_result = train_eval(default_params, X_train_cv, y_train_cv,
                                X_holdout, y_holdout, label="Default")

    # --- Optuna Study ---
    print("\n--- OPTUNA STUDY (50 trials) ---")
    study = optuna.create_study(
        direction="maximize",
        sampler=TPESampler(seed=42),
        pruner=MedianPruner(n_startup_trials=10, n_warmup_steps=2),
    )
    study.optimize(
        lambda trial: objective(trial, X_train_cv, y_train_cv, cv),
        n_trials=50,
        show_progress_bar=True,
    )

    print(f"\nBest trial: #{study.best_trial.number}")
    print(f"Best CV accuracy: {study.best_trial.value:.4f}")
    print(f"Best params: {study.best_trial.params}")

    # --- Best model evaluation ---
    best_params = study.best_trial.params.copy()
    best_model = xgb.XGBClassifier(
        **best_params,
        random_state=42,
        eval_metric="logloss",
        use_label_encoder=False,
        verbosity=0,
        tree_method="hist",
    )
    best_model.fit(X_train_cv, y_train_cv)
    print("\n--- BEST PARAMS EVALUATION ---")
    best_result = train_eval(best_params, X_train_cv, y_train_cv,
                             X_holdout, y_holdout, label="Best")

    # --- Save results ---
    with open(os.path.join(OUT_DIR, "best_params.json"), "w") as f:
        json.dump(best_params, f, indent=2)
    print("\n  Saved: best_params.json")

    df_study = study.trials_dataframe()
    df_study.to_csv(os.path.join(OUT_DIR, "study_results.csv"), index=False)
    print(f"  Saved: study_results.csv ({len(df_study)} trials)")

    plot_feature_importance(best_model, feature_cols,
                            os.path.join(OUT_DIR, "feature_importance.png"))

    # --- Top 5 trials ---
    sorted_trials = sorted(study.trials, key=lambda t: t.value if t.value else 0, reverse=True)

    # --- Report ---
    elapsed = time.time() - t0
    print("\n" + "=" * 60)
    print("FINAL REPORT")
    print("=" * 60)
    print(f"\nTotal time: {elapsed:.1f}s ({elapsed / 60:.1f} min)")

    print("\n--- TOP 5 TRIALS ---")
    for i, t in enumerate(sorted_trials[:5]):
        print(f"  #{i + 1}: Trial {t.number:>3d} | CV Acc: {t.value:.4f} | Params: {t.params}")

    print("\n--- BEST HYPERPARAMETERS ---")
    for k, v in best_params.items():
        print(f"  {k}: {v}")

    print("\n--- IMPROVEMENT OVER DEFAULT ---")
    acc_imp = best_result["accuracy"] - default_result["accuracy"]
    f1_imp = best_result["f1"] - default_result["f1"]
    print(f"  Accuracy: {default_result['accuracy']:.4f} → {best_result['accuracy']:.4f} ({acc_imp:+.4f})")
    print(f"  F1 Score: {default_result['f1']:.4f} → {best_result['f1']:.4f} ({f1_imp:+.4f})")

    print("\n--- FEATURE IMPORTANCE TOP 10 ---")
    importance = best_model.feature_importances_
    idx = np.argsort(importance)[::-1][:10]
    for rank, i in enumerate(idx, 1):
        print(f"  {rank:>2d}. {feature_cols[i]:25s} {importance[i]:.4f}")

    print("=" * 60)


if __name__ == "__main__":
    main()
