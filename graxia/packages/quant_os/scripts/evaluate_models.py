"""Phase 5 — Evaluate Trained Dual-Head Models (Out-of-Sample).

Loads trained direction + magnitude models, runs on test data,
computes OOS metrics, generates equity curve plots (if matplotlib available).

Usage:
    python scripts/evaluate_models.py --symbol XAUUSD
    python scripts/evaluate_models.py --symbol ALL
"""

from __future__ import annotations

import argparse
import json
import logging
import pickle
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    precision_score,
    r2_score,
    recall_score,
)

from graxia.packages.quant_os.core.safe_pickle import safe_load_model

warnings.filterwarnings("ignore")

# ── Path setup ──────────────────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT))

DATA_DIR = PROJECT_ROOT / "data"
FEATURES_DIR = PROJECT_ROOT / "artifacts" / "features_v3"
MODELS_DIR = PROJECT_ROOT / "artifacts" / "models"
REPORTS_DIR = PROJECT_ROOT / "reports"
PLOTS_DIR = PROJECT_ROOT / "reports" / "plots"

REPORTS_DIR.mkdir(parents=True, exist_ok=True)
PLOTS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

TARGET_SYMBOLS = ["XAUUSD", "EURUSD", "BTCUSD", "ETHUSD"]


# ── Label creation (mirrors train script) ───────────────────────────────────


def create_labels(df: pd.DataFrame) -> pd.DataFrame:
    """Add direction and magnitude labels."""
    df = df.copy()
    close = df["close"].to_numpy()
    next_return = np.empty(len(close))
    next_return[:-1] = (close[1:] - close[:-1]) / close[:-1]
    next_return[-1] = np.nan
    df["target_direction"] = (next_return > 0).astype(float)
    df["target_magnitude"] = next_return
    df = df.dropna(subset=["target_direction", "target_magnitude"]).reset_index(drop=True)
    return df


# ── Feature columns ─────────────────────────────────────────────────────────

EXCLUDE_COLS = {
    "target",
    "target_return",
    "target_direction",
    "target_magnitude",
    "symbol",
    "time",
    "freq",
    "timestamp",
    "tb_label",
    "tb_bar_hit",
    "tb_side",
    "tb_ret",
    "tb_k_upper",
    "tb_k_lower",
    # Raw OHLCV — not predictive features
    "open",
    "high",
    "low",
    "close",
    "volume",
}


def get_feature_columns(df: pd.DataFrame) -> list[str]:
    cols = []
    for c in df.columns:
        if c in EXCLUDE_COLS:
            continue
        if pd.api.types.is_numeric_dtype(df[c]):
            cols.append(c)
    return cols


# ── JSON-safe ───────────────────────────────────────────────────────────────


def to_serializable(obj):
    if isinstance(obj, dict):
        return {k: to_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [to_serializable(v) for v in obj]
    elif isinstance(obj, tuple):
        return tuple(to_serializable(v) for v in obj)
    elif hasattr(obj, "item"):
        return obj.item()
    elif isinstance(obj, (np.integer,)):
        return int(obj)
    elif isinstance(obj, (np.floating,)):
        return round(float(obj), 6)
    return obj


# ── Equity curve ────────────────────────────────────────────────────────────


def generate_equity_curve(
    symbol: str,
    y_true_dir: np.ndarray,
    y_pred_dir: np.ndarray,
    y_true_mag: np.ndarray,
    y_pred_mag: np.ndarray,
    timestamps: pd.Series | None = None,
) -> Path | None:
    """Generate equity curve plot. Returns path or None if matplotlib unavailable."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.dates as mdates
        import matplotlib.pyplot as plt
    except ImportError:
        logger.warning("  matplotlib not available, skipping plot generation")
        return None

    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle(f"{symbol} — Dual-Head Model Evaluation", fontsize=14, fontweight="bold")

    # 1. Cumulative return (actual vs predicted direction)
    actual_ret = np.where(y_true_dir == 1, y_true_mag, -y_true_mag)
    pred_ret = np.where(y_pred_dir == 1, y_true_mag, -y_true_mag)

    cum_actual = np.cumsum(actual_ret)
    cum_pred = np.cumsum(pred_ret)

    x = np.arange(len(cum_actual))

    axes[0].plot(x, cum_actual, label="Actual (buy & hold)", alpha=0.7, linewidth=1.2)
    axes[0].plot(x, cum_pred, label="Model signal", alpha=0.7, linewidth=1.2)
    axes[0].set_ylabel("Cumulative Return")
    axes[0].legend(loc="upper left")
    axes[0].set_title("Equity Curve")
    axes[0].grid(True, alpha=0.3)

    # 2. Direction accuracy (rolling window)
    window = min(100, len(y_pred_dir) // 5)
    if window > 1:
        correct = (y_true_dir == y_pred_dir).astype(float)
        rolling_acc = pd.Series(correct).rolling(window, min_periods=1).mean()
        axes[1].plot(x, rolling_acc, color="green", linewidth=1.2)
        axes[1].axhline(y=0.5, color="red", linestyle="--", alpha=0.5, label="50% baseline")
        axes[1].set_ylabel(f"Rolling Accuracy ({window}-bar)")
        axes[1].set_ylim(0, 1)
        axes[1].legend(loc="lower left")
        axes[1].set_title("Direction Accuracy (Rolling)")
        axes[1].grid(True, alpha=0.3)

    # 3. Magnitude prediction vs actual (scatter-style line plot)
    axes[2].plot(x, y_true_mag, label="Actual return", alpha=0.5, linewidth=0.8)
    axes[2].plot(x, y_pred_mag, label="Predicted magnitude", alpha=0.5, linewidth=0.8)
    axes[2].set_ylabel("Return / Predicted Magnitude")
    axes[2].legend(loc="upper left")
    axes[2].set_title("Magnitude Head: Actual vs Predicted")
    axes[2].grid(True, alpha=0.3)

    if timestamps is not None and len(timestamps) == len(x):
        try:
            dates = pd.to_datetime(timestamps)
            tick_positions = np.linspace(0, len(x) - 1, min(8, len(x)), dtype=int)
            axes[2].set_xticks(tick_positions)
            axes[2].set_xticklabels(
                [dates.iloc[i].strftime("%Y-%m-%d") for i in tick_positions],
                rotation=45,
                ha="right",
            )
        except Exception:
            pass

    axes[2].set_xlabel("Bar Index")

    plt.tight_layout()
    plot_path = PLOTS_DIR / f"{symbol}_evaluation.png"
    fig.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    logger.info("  Saved equity curve: %s", plot_path.name)
    return plot_path


# ── Main evaluation ─────────────────────────────────────────────────────────


def evaluate_symbol(symbol: str, timeframe: str = "M15") -> dict:
    """Evaluate dual-head models for a single symbol."""
    logger.info("=" * 60)
    logger.info("EVALUATING MODELS: %s %s", symbol, timeframe)
    logger.info("=" * 60)

    # 1. Load model
    dir_model_path = MODELS_DIR / f"{symbol}_direction.pkl"
    mag_model_path = MODELS_DIR / f"{symbol}_magnitude.pkl"

    if not dir_model_path.exists():
        raise FileNotFoundError(f"Direction model not found: {dir_model_path}")
    if not mag_model_path.exists():
        raise FileNotFoundError(f"Magnitude model not found: {mag_model_path}")

    with open(dir_model_path, "rb") as f:
        dir_artifact = safe_load_model(dir_model_path)
    with open(mag_model_path, "rb") as f:
        mag_artifact = safe_load_model(mag_model_path)

    dir_model = dir_artifact["model"]
    mag_model = mag_artifact["model"]
    feature_cols = dir_artifact["feature_columns"]

    logger.info("  Direction model loaded (trained: %s)", dir_artifact.get("trained_at", "unknown"))
    logger.info("  Magnitude model loaded (trained: %s)", mag_artifact.get("trained_at", "unknown"))

    # 2. Load features
    parquet_path = FEATURES_DIR / f"features_v3_{symbol}_{timeframe}.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(f"Feature parquet not found: {parquet_path}. Run train_dual_head.py first.")

    df = pd.read_parquet(parquet_path)
    logger.info("  Loaded features: %d rows", len(df))

    # 3. Create labels
    df = create_labels(df)
    # Impute NaN features (must match training behavior)
    df[feature_cols] = df[feature_cols].ffill()
    df[feature_cols] = df[feature_cols].fillna(0)

    X = df[feature_cols].values
    y_dir = df["target_direction"].values.astype(int)
    y_mag = df["target_magnitude"].values.astype(float)

    # 4. Extract test set (last 15% — same split as training)
    test_start = int(len(X) * 0.85)
    X_test = X[test_start:]
    y_dir_test = y_dir[test_start:]
    y_mag_test = y_mag[test_start:]
    timestamps = df["time"].iloc[test_start:] if "time" in df.columns else None

    logger.info("  Test set: %d samples", len(X_test))

    # 5. Predictions
    y_dir_pred = dir_model.predict(X_test)
    y_mag_pred = mag_model.predict(X_test)

    # 6. Direction metrics
    dir_metrics = {
        "accuracy": round(float(accuracy_score(y_dir_test, y_dir_pred)), 4),
        "precision": round(float(precision_score(y_dir_test, y_dir_pred, zero_division=0)), 4),
        "recall": round(float(recall_score(y_dir_test, y_dir_pred, zero_division=0)), 4),
        "f1": round(float(f1_score(y_dir_test, y_dir_pred, zero_division=0)), 4),
        "n_samples": int(len(y_dir_test)),
        "n_up_true": int(y_dir_test.sum()),
        "n_down_true": int(len(y_dir_test) - y_dir_test.sum()),
        "n_up_pred": int(y_dir_pred.sum()),
        "n_down_pred": int(len(y_dir_pred) - y_dir_pred.sum()),
    }
    logger.info(
        "  Direction: acc=%.4f | prec=%.4f | rec=%.4f | f1=%.4f",
        dir_metrics["accuracy"],
        dir_metrics["precision"],
        dir_metrics["recall"],
        dir_metrics["f1"],
    )

    # 7. Magnitude metrics
    mag_metrics = {
        "rmse": round(float(np.sqrt(mean_squared_error(y_mag_test, y_mag_pred))), 6),
        "mae": round(float(mean_absolute_error(y_mag_test, y_mag_pred)), 6),
        "r2": round(float(r2_score(y_mag_test, y_mag_pred)), 4),
        "n_samples": int(len(y_mag_test)),
        "mean_true": round(float(y_mag_test.mean()), 6),
        "std_true": round(float(y_mag_test.std()), 6),
        "mean_pred": round(float(y_mag_pred.mean()), 6),
        "std_pred": round(float(y_mag_pred.std()), 6),
    }
    logger.info(
        "  Magnitude: rmse=%.6f | mae=%.6f | r2=%.4f", mag_metrics["rmse"], mag_metrics["mae"], mag_metrics["r2"]
    )

    # 8. Combined strategy metrics
    # Simulate: go long when direction=1, short when direction=0
    strategy_returns = np.where(y_dir_pred == 1, y_mag_test, -y_mag_test)
    cum_return = float(np.sum(strategy_returns))
    sharpe = (
        float(np.mean(strategy_returns) / np.std(strategy_returns) * np.sqrt(252 * 96))
        if np.std(strategy_returns) > 0
        else 0.0
    )
    win_rate = float(np.mean(strategy_returns > 0))
    cum_curve = np.cumsum(strategy_returns)
    max_dd = float(np.max(np.maximum.accumulate(cum_curve) - cum_curve))

    # Buy-and-hold for comparison
    bh_returns = np.where(y_dir_test == 1, y_mag_test, -y_mag_test)
    bh_cum = float(np.sum(bh_returns))

    strategy_metrics = {
        "cumulative_return": round(cum_return * 100, 4),
        "sharpe_ratio": round(sharpe, 4),
        "win_rate": round(win_rate, 4),
        "max_drawdown": round(max_dd * 100, 4),
        "buy_hold_return": round(bh_cum * 100, 4),
        "n_trades": int(len(strategy_returns)),
    }
    logger.info(
        "  Strategy: return=%.2f%% | sharpe=%.2f | win_rate=%.2f%% | max_dd=%.2f%%",
        strategy_metrics["cumulative_return"],
        strategy_metrics["sharpe_ratio"],
        strategy_metrics["win_rate"] * 100,
        strategy_metrics["max_drawdown"],
    )

    # 9. Generate equity curve
    plot_path = generate_equity_curve(
        symbol,
        y_dir_test,
        y_dir_pred,
        y_mag_test,
        y_mag_pred,
        timestamps,
    )

    # 10. Save evaluation report
    report = {
        "symbol": symbol,
        "timeframe": timeframe,
        "evaluated_at": datetime.now(UTC).isoformat(),
        "model_trained_at": dir_artifact.get("trained_at", "unknown"),
        "n_features": len(feature_cols),
        "test_samples": len(X_test),
        "direction_metrics": dir_metrics,
        "magnitude_metrics": mag_metrics,
        "strategy_metrics": strategy_metrics,
        "classification_report": classification_report(
            y_dir_test,
            y_dir_pred,
            output_dict=True,
            zero_division=0,
        ),
    }

    eval_path = REPORTS_DIR / f"model_evaluation_{symbol}.json"
    with open(eval_path, "w") as f:
        json.dump(to_serializable(report), f, indent=2)
    logger.info("  Saved evaluation: %s", eval_path.name)

    # Summary
    logger.info("\n" + "=" * 60)
    logger.info("EVALUATION SUMMARY: %s", symbol)
    logger.info("  Direction — Accuracy: %.4f | F1: %.4f", dir_metrics["accuracy"], dir_metrics["f1"])
    logger.info("  Magnitude — RMSE: %.6f | R²: %.4f", mag_metrics["rmse"], mag_metrics["r2"])
    logger.info(
        "  Strategy  — Return: %.2f%% | Sharpe: %.2f | MaxDD: %.2f%%",
        strategy_metrics["cumulative_return"],
        strategy_metrics["sharpe_ratio"],
        strategy_metrics["max_drawdown"],
    )
    logger.info("  Buy&Hold  — Return: %.2f%%", strategy_metrics["buy_hold_return"])
    if plot_path:
        logger.info("  Plot: %s", plot_path)
    logger.info("=" * 60)

    return report


# ── CLI ─────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate trained dual-head models (out-of-sample)",
    )
    parser.add_argument(
        "--symbol",
        required=True,
        help="Symbol to evaluate, or ALL for all 4 target symbols",
    )
    parser.add_argument("--timeframe", default="M15", help="Timeframe (default M15)")
    return parser.parse_args(argv)


def main() -> int:
    args = parse_args()
    symbols = TARGET_SYMBOLS if args.symbol.upper() == "ALL" else [args.symbol.upper()]

    results = {}
    for symbol in symbols:
        try:
            report = evaluate_symbol(symbol, args.timeframe)
            results[symbol] = "OK"
        except Exception as e:
            logger.error("FAILED %s: %s", symbol, e, exc_info=True)
            results[symbol] = f"FAILED: {e}"

    # Final summary
    print("\n" + "=" * 60)
    print("BATCH EVALUATION COMPLETE")
    for sym, status in results.items():
        print(f"  {sym}: {status}")
    print("=" * 60)

    return 0 if all(v == "OK" for v in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
