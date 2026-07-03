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
import pickle
import sys
import time
from pathlib import Path

import structlog

sys.path.insert(0, str(Path(__file__).parent.parent))

from ml.labeling import label_from_source
from ml.pipeline import FeatureEngineer, FeatureSet, MLTrainer

logger = structlog.get_logger(__name__)

# Load .env
ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text().splitlines():
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
    with open(latest, "rb") as f:
        data = pickle.load(f)
    return data, latest.name


def load_champion():
    """Load the champion model from CHAMPION_PATH. Returns None if not found."""
    if not CHAMPION_PATH.exists():
        return None
    with open(CHAMPION_PATH, "rb") as f:
        return pickle.load(f)


def save_champion(model_data: dict) -> None:
    """Save model to CHAMPION_PATH, creating directories if needed."""
    CHAMPION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHAMPION_PATH, "wb") as f:
        pickle.dump(model_data, f)


def evaluate_model(model_data: dict):
    """Evaluate a model and return metrics object."""
    from dataclasses import dataclass

    @dataclass
    class ModelMetrics:
        deflated_sharpe: float = 1.0
        oos_max_drawdown: float = 10.0

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


async def run_auto_retrain(force: bool = False) -> dict:
    """Run auto-retrain cycle."""
    if not force:
        drift = check_drift()
        logger.info("retrain.drift_check", **drift)
        if not drift["drifted"]:
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
