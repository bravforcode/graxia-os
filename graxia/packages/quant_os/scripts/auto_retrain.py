"""
Auto-Retrain Cron — Drift detection → walk-forward retrain → model replacement.

Monitors DriftDetector, triggers retrain when accuracy drops below threshold.
Writes new model to ml/models/ and logs the event.

Usage:
  python scripts/auto_retrain.py                    # one-shot check
  python scripts/auto_retrain.py --loop             # continuous (every 1h)
  python scripts/auto_retrain.py --force            # force retrain
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import structlog
from graxia.packages.quant_os.core.safe_pickle import safe_load_model

sys.path.insert(0, str(Path(__file__).parent.parent))

from ml.labeling import label_from_source
from ml.pipeline import FeatureEngineer, FeatureSet, MLTrainer

logger = structlog.get_logger(__name__)

# Load .env
ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

DRIFT_THRESHOLD = 0.10  # 10% accuracy drop triggers retrain
MIN_SAMPLES = 500  # Minimum samples for retrain
MODEL_DIR = Path(__file__).parent.parent / "ml" / "models"
CHAMPION_PATH = MODEL_DIR / "champion.pkl"
RETRAIN_LOG = MODEL_DIR / "retrain_history.jsonl"


def load_latest_model():
    """Load the most recent model from ml/models/."""
    model_files = sorted(MODEL_DIR.glob("xgboost_*.pkl"), key=lambda p: p.stat().st_mtime)
    if not model_files:
        return None, None
    latest = model_files[-1]
    data = safe_load_model(latest)
    return data, latest.name


def load_champion():
    """Load the champion model from CHAMPION_PATH. Returns None if not found."""
    if not CHAMPION_PATH.exists():
        return None
    return safe_load_model(CHAMPION_PATH)


def save_champion(model_data: dict) -> None:
    """Save model to CHAMPION_PATH using joblib (compatible with safe_load_model)."""
    import joblib

    CHAMPION_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(model_data, CHAMPION_PATH)


def evaluate_model(model_data: dict):
    """Evaluate a model on labeled data and return real metrics."""
    from dataclasses import dataclass

    import numpy as np

    @dataclass
    class ModelMetrics:
        deflated_sharpe: float = 0.0
        oos_max_drawdown: float = 0.0

    model = model_data.get("model")
    feature_names = model_data.get("feature_names", [])

    if model is None:
        logger.error("evaluate_model.no_model_in_data")
        return ModelMetrics()

    try:
        labeled = label_from_source("warehouse")
        if len(labeled) < MIN_SAMPLES:
            return ModelMetrics()

        engineer = FeatureEngineer()
        feature_set = engineer.generate_features(labeled)

        X = np.array([[f.get(name, 0.0) for name in feature_names] for f in feature_set.features])
        y_true = np.array(feature_set.labels)

        if len(X) == 0 or len(feature_names) == 0:
            return ModelMetrics()

        y_pred = model.predict(X)
        correct = (y_true == y_pred).astype(int)
        returns = np.where(correct, np.abs(feature_set.labels), -np.abs(feature_set.labels) * 0.5)

        if len(returns) >= 30 and np.std(returns) > 0:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252 * 96)
        elif len(returns) > 1 and np.std(returns) > 0:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(len(returns))
        else:
            sharpe = 0.0

        cumulative = np.cumsum(returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = running_max - cumulative
        max_dd = float(np.max(drawdowns)) if len(drawdowns) > 0 else 0.0

        n_trials = max(1, len(feature_names))
        deflated = sharpe * (1 - 0.05 * np.log(n_trials + 1))

        return ModelMetrics(
            deflated_sharpe=round(deflated, 4),
            oos_max_drawdown=round(max_dd, 4),
        )
    except Exception as e:
        logger.error("evaluate_model.failed", error=str(e))
        return ModelMetrics()


def hot_swap(challenger_data: dict, challenger_metrics) -> bool:
    """
    Compare challenger to champion. Swap if strictly better.
    Rules: Sharpe > 1.05x champion, drawdown < champion.
    """
    champion_data = load_champion()
    if champion_data is None:
        save_champion(challenger_data)
        return True
    champion_metrics = evaluate_model(champion_data)
    if challenger_metrics.deflated_sharpe <= champion_metrics.deflated_sharpe * 1.05:
        return False
    if challenger_metrics.oos_max_drawdown >= champion_metrics.oos_max_drawdown:
        return False
    save_champion(challenger_data)
    return True


def log_retrain(entry: dict) -> None:
    """Append a retrain entry to RETRAIN_LOG (JSONL format)."""
    import json

    RETRAIN_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(RETRAIN_LOG, "a") as f:
        f.write(json.dumps(entry) + "\n")


def check_drift() -> dict:
    """Check if model has drifted by comparing recent vs historical accuracy."""
    model_data, model_name = load_latest_model()
    if model_data is None:
        return {"drifted": False, "reason": "no_model", "model": None}

    # Load labeled data
    try:
        labeled = label_from_source("warehouse")
        if len(labeled) < MIN_SAMPLES:
            return {"drifted": False, "reason": "insufficient_data", "samples": len(labeled)}
    except Exception as e:
        return {"drifted": False, "reason": f"data_error: {e}"}

    # Build features
    engineer = FeatureEngineer()
    feature_set = engineer.generate_features(labeled)

    # Split: recent vs historical
    split = len(feature_set.features) // 2
    recent = FeatureSet(
        features=feature_set.features[split:],
        labels=feature_set.labels[split:],
        timestamps=feature_set.timestamps[split:],
        feature_names=feature_set.feature_names,
    )
    historical = FeatureSet(
        features=feature_set.features[:split],
        labels=feature_set.labels[:split],
        timestamps=feature_set.timestamps[:split],
        feature_names=feature_set.feature_names,
    )

    # Evaluate both
    model = model_data["model"]
    import numpy as np

    X_recent = np.array([list(f.values()) for f in recent.features])
    y_recent = np.array(recent.labels)
    X_hist = np.array([list(f.values()) for f in historical.features])
    y_hist = np.array(historical.labels)

    recent_acc = float(np.mean(model.predict(X_recent) == y_recent))
    hist_acc = float(np.mean(model.predict(X_hist) == y_hist))

    drop = hist_acc - recent_acc
    drifted = drop > DRIFT_THRESHOLD

    return {
        "drifted": drifted,
        "model": model_name,
        "recent_accuracy": recent_acc,
        "historical_accuracy": hist_acc,
        "drop": drop,
        "threshold": DRIFT_THRESHOLD,
    }


def retrain_model() -> dict:
    """Retrain model with walk-forward validation."""
    trainer = MLTrainer(model_dir=str(MODEL_DIR))

    try:
        labeled = label_from_source("warehouse")
        if len(labeled) < MIN_SAMPLES:
            return {"success": False, "reason": f"insufficient_data: {len(labeled)}"}
    except Exception as e:
        return {"success": False, "reason": f"data_error: {e}"}

    engineer = FeatureEngineer()
    feature_set = engineer.generate_features(labeled)

    # Walk-forward training
    results = trainer.train_walk_forward(feature_set, model_type="xgboost", n_windows=3)

    if not results:
        return {"success": False, "reason": "training_failed"}

    best = max(results, key=lambda r: r.oos_accuracy or r.accuracy)

    return {
        "success": True,
        "model_path": best.model_path,
        "version": best.version,
        "accuracy": best.accuracy,
        "oos_accuracy": best.oos_accuracy,
        "f1_score": best.f1_score,
        "training_samples": best.training_samples,
    }


def check_drift_monitor() -> dict:
    """Check drift using the DriftMonitor from ml/drift_monitor.py.

    Instantiates a DriftMonitor, loads persisted state, and checks for
    accuracy or feature drift across tracked model/symbol combinations.
    """
    try:
        from ml.drift_monitor import DriftMonitor

        monitor = DriftMonitor()
        reports = monitor.get_drift_stats()

        if not reports:
            return {"drifted": False, "reason": "no_monitor_state"}

        for report in reports:
            if report.accuracy_window < 0.45:
                logger.warning(
                    "drift_monitor.accuracy_low",
                    model=report.model_version,
                    symbol=report.symbol,
                    accuracy=report.accuracy_window,
                )
                return {"drifted": True, "reason": "accuracy_drop", "accuracy": report.accuracy_window}
            for alert in report.alerts:
                if alert.severity in ("warning", "critical"):
                    logger.warning(
                        "drift_monitor.alert",
                        alert_type=alert.alert_type,
                        severity=alert.severity,
                        message=alert.message,
                    )
                    return {"drifted": True, "reason": alert.alert_type, "message": alert.message}

        return {"drifted": False, "reason": "within_thresholds", "reports": len(reports)}
    except Exception as e:
        logger.warning("drift_monitor.check_failed", error=str(e))
        return {"drifted": False, "reason": f"monitor_error: {e}"}


async def run_auto_retrain(force: bool = False) -> dict:
    """Run auto-retrain cycle."""
    if not force:
        drift = check_drift()
        logger.info("retrain.drift_check", **drift)

        monitor_drift = check_drift_monitor()
        logger.info("retrain.drift_monitor_check", **monitor_drift)

        if not drift["drifted"] and not monitor_drift["drifted"]:
            return {"action": "skipped", "reason": "no_drift", **drift}

    logger.info("retrain.start", force=force)
    start = time.monotonic()
    result = retrain_model()
    latency = time.monotonic() - start

    if result["success"]:
        logger.info(
            "retrain.complete",
            model_path=result["model_path"],
            accuracy=result["accuracy"],
            oos_accuracy=result["oos_accuracy"],
            latency_s=round(latency, 1),
        )
    else:
        logger.warning("retrain.failed", reason=result["reason"])

    return result


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Auto-Retrain Cron")
    parser.add_argument("--loop", action="store_true")
    parser.add_argument("--interval", type=int, default=3600)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.loop:
        logger.info("retrain.loop_start", interval=args.interval)
        while True:
            try:
                result = await run_auto_retrain(force=args.force)
                logger.info("retrain.cycle", **result)
            except Exception as e:
                logger.exception("retrain.cycle_error", error=str(e))
            await asyncio.sleep(args.interval)
    else:
        result = await run_auto_retrain(force=args.force)
        print(f"\n{'='*60}")
        for k, v in result.items():
            print(f"  {k}: {v}")
        print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
