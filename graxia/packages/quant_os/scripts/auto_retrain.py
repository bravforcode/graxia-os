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
import math
import os
import pickle
import sys
import time
from pathlib import Path

import structlog
from graxia.packages.quant_os.core.safe_pickle import safe_load_model

sys.path.insert(0, str(Path(__file__).parent.parent))

from ml.labeling import label_from_source
from ml.pipeline import FeatureEngineer, FeatureSet, MLTrainer, purge_embargo_split_indices


def _load_deflated_sharpe_ratio():
    """Direct file-import validation/deflated_sharpe.py, bypassing validation/__init__.py.

    That package __init__ eagerly imports native_runner.py, which needs the
    graxia.packages.quant_os.* dotted path — only resolvable under pytest's
    conftest.py sys.path setup, not when this script runs standalone
    (`python scripts/auto_retrain.py`). Same direct-import trick already used
    by ml.labeling.label_from_source for backtest/data_loader.py.
    """
    import importlib.util

    _path = Path(__file__).parent.parent / "validation" / "deflated_sharpe.py"
    _spec = importlib.util.spec_from_file_location("_deflated_sharpe", _path)
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
    return _mod.deflated_sharpe_ratio


deflated_sharpe_ratio = _load_deflated_sharpe_ratio()

logger = structlog.get_logger(__name__)

# Load .env
ENV_PATH = Path(__file__).parent.parent / ".env"
if ENV_PATH.exists():
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

SYMBOL = os.getenv("TRADE_SYMBOL", "XAUUSD")

# Data source decision (2B.5b): "warehouse" (data/warehouse/ohlcv Parquet)
# was checked and rejected BEFORE any training/evaluation was run — its
# get_ohlcv() has no DISTINCT/dedup in its SQL, and the underlying hive
# partitions for XAUUSD/H1 are exactly 6x-duplicated (300,000 raw rows for
# only 50,000 unique timestamps, byte-identical OHLCV per duplicate,
# confirmed empirically). "duckdb" (data/market_data.duckdb's flat ohlcv
# table) has 10,000 real, unique-timestamp XAUUSD/H1 rows and is used
# instead. Do not switch this back to "warehouse" without first fixing the
# duplication at the warehouse-loader level (out of scope here).
RETRAIN_DATA_SOURCE = "duckdb"

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
    data = safe_load_model(latest, allow_unsigned=True)
    return data, latest.name


def load_champion():
    """Load the champion model from CHAMPION_PATH. Returns None if not found."""
    if not CHAMPION_PATH.exists():
        return None
    return safe_load_model(CHAMPION_PATH, allow_unsigned=True)


def save_champion(model_data: dict) -> None:
    """Save model to CHAMPION_PATH, creating directories if needed."""
    CHAMPION_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CHAMPION_PATH, "wb") as f:
        pickle.dump(model_data, f)


# Minimum absolute improvement in deflated Sharpe required to promote a
# challenger. Additive, not multiplicative — this project currently has no
# confirmed edge (see reports/go_live_gate_corrected_sequencing.md), so real
# deflated-Sharpe values are frequently negative. A `champion * 1.05` style
# threshold inverts (becomes a *looser* bar) once champion is negative;
# a fixed additive margin stays correct regardless of sign.
MIN_SHARPE_IMPROVEMENT = 0.05

# Minimum OOS trades required for evaluate_model()'s Sharpe/drawdown to be
# meaningful at all.
_MIN_EVAL_TRADES = 10

# Minimum bar the very first model must clear before being promoted to
# champion when no champion exists yet. `deflated_sharpe` here is a real
# Sharpe-ratio-space number (raw OOS Sharpe minus the deflated_sharpe_ratio()
# multiple-testing haircut — see evaluate_model()), so "> 0" means "beats
# what you'd expect from a lucky null strategy after the haircut" — the
# same "not obviously terrible" floor the brief for this fix asks for.
# NaN (evaluation failed — no data, no model, vocabulary drift) also fails
# this floor since NaN comparisons are always False in Python.
_FIRST_CHAMPION_MIN_SHARPE = 0.0

# Barrier multiples must match FeatureEngineer.generate_features' own
# triple-barrier call (ml/pipeline.py) — the labels being evaluated here
# were generated with these exact multiples.
_TP_MULT = 1.5
_SL_MULT = 1.0


def _nan_metrics():
    from dataclasses import dataclass

    @dataclass
    class ModelMetrics:
        deflated_sharpe: float = float("nan")
        oos_max_drawdown: float = float("nan")

    return ModelMetrics()


def evaluate_model(model_data: dict):
    """Evaluate a model's real out-of-sample trading performance.

    Runs the model over a held-out fold of the current duckdb dataset (see
    RETRAIN_DATA_SOURCE below for why duckdb, not warehouse) — the SAME
    purge/embargo split MLTrainer.train() uses
    (ml.pipeline.purge_embargo_split_indices, test_ratio=0.2, gap=12 bars;
    called here, not re-derived, so the two can never silently drift out of
    sync) — takes the simulated trade only on bars the model predicts as a
    win (label 1), and realizes P&L from the *actual* triple-barrier
    outcome of that bar (win/loss/timeout, in ATR multiples) — not a
    fabricated proxy. Returns a deflated Sharpe (haircut for selection bias
    via validation.deflated_sharpe.deflated_sharpe_ratio, n_trials=1 since
    this evaluates one model, not a multi-strategy scan) and a real max
    drawdown from the resulting equity curve.

    Fails closed to NaN metrics (which can never win a promotion in
    hot_swap's comparisons) on any missing model/data/vocabulary condition
    — same discipline as the 2B.2 live-inference vocabulary-drift gate.
    """
    import numpy as np

    if not model_data:
        return _nan_metrics()

    model = model_data.get("model")
    feature_names = model_data.get("feature_names")
    if model is None or not feature_names:
        return _nan_metrics()

    try:
        labeled = label_from_source(symbol=SYMBOL, source=RETRAIN_DATA_SOURCE)
    except Exception as e:
        logger.warning("retrain.evaluate_model.data_error", error=str(e))
        return _nan_metrics()

    if len(labeled) < MIN_SAMPLES:
        return _nan_metrics()

    engineer = FeatureEngineer()
    try:
        feature_set = engineer.generate_features(labeled)
    except Exception as e:
        logger.warning("retrain.evaluate_model.feature_error", error=str(e))
        return _nan_metrics()

    # Fail closed on vocabulary drift: don't fabricate a score from
    # features the model was never trained on.
    live_vocab = set(feature_set.feature_names)
    if not set(feature_names).issubset(live_vocab):
        logger.warning(
            "retrain.evaluate_model.vocabulary_drift",
            missing=sorted(set(feature_names) - live_vocab),
        )
        return _nan_metrics()

    # Identical purge/embargo split MLTrainer.train() uses for its own
    # X_test/y_test — reused via the shared function, not re-derived, so
    # the OOS fold evaluate_model() scores can't silently drift out of
    # sync with what train() actually held out.
    _, test_start = purge_embargo_split_indices(len(feature_set.features), test_ratio=0.2, gap=12)
    oos_features = feature_set.features[test_start:]
    oos_labels = feature_set.labels[test_start:]
    if len(oos_features) < _MIN_EVAL_TRADES:
        return _nan_metrics()

    x_oos = np.array([[f.get(name, 0) for name in feature_names] for f in oos_features])

    try:
        predictions = model.predict(x_oos)
    except Exception as e:
        logger.warning("retrain.evaluate_model.predict_failed", error=str(e))
        return _nan_metrics()

    # Real per-bar P&L: only "take" bars the model predicts as a win;
    # realize the ATR-multiple return of the ACTUAL triple-barrier outcome.
    returns = []
    for pred, actual in zip(predictions, oos_labels, strict=False):
        if pred != 1:
            continue
        if actual == 1:
            returns.append(_TP_MULT)
        elif actual == -1:
            returns.append(-_SL_MULT)
        else:
            returns.append(0.0)

    if len(returns) < _MIN_EVAL_TRADES:
        return _nan_metrics()

    returns_arr = np.array(returns, dtype=float)
    n_trades = len(returns_arr)
    mean_r = float(returns_arr.mean())
    std_r = float(returns_arr.std(ddof=1)) if n_trades > 1 else 0.0
    raw_sharpe = (mean_r / std_r) * math.sqrt(n_trades) if std_r > 0 else 0.0

    dsr = deflated_sharpe_ratio(
        observed_sharpe=raw_sharpe,
        n_trials=1,
        n_observations=n_trades,
    )
    haircut_sharpe = raw_sharpe - dsr.multiple_testing_adjustment

    equity = np.cumsum(returns_arr)
    running_max = np.maximum.accumulate(equity)
    max_dd = float((running_max - equity).max())

    from dataclasses import dataclass

    @dataclass
    class ModelMetrics:
        deflated_sharpe: float
        oos_max_drawdown: float
        n_trades: int = 0

    return ModelMetrics(deflated_sharpe=haircut_sharpe, oos_max_drawdown=max_dd, n_trades=n_trades)


def hot_swap(challenger_data: dict, challenger_metrics) -> bool:
    """
    Compare challenger to champion. Swap only if the challenger clears
    every real gate: a genuine absolute improvement in deflated Sharpe
    over the champion, and a lower (or equal-and-smaller) OOS max
    drawdown. NaN on either side (evaluation failed — no model, no data,
    vocabulary drift) fails closed: no swap, since NaN comparisons are
    always False in Python and would otherwise silently bypass the gate.

    If there is no champion yet, the challenger still has to clear a real
    minimum bar (see _FIRST_CHAMPION_MIN_SHARPE) computed by the same real
    evaluate_model() used everywhere else in this function — previously
    this branch promoted the very first model unconditionally with zero
    evaluation at all.
    """
    champion_data = load_champion()
    if champion_data is None:
        if (
            math.isnan(challenger_metrics.deflated_sharpe)
            or challenger_metrics.deflated_sharpe <= _FIRST_CHAMPION_MIN_SHARPE
        ):
            return False
        save_champion(challenger_data)
        return True

    champion_metrics = evaluate_model(champion_data)

    if math.isnan(challenger_metrics.deflated_sharpe) or math.isnan(champion_metrics.deflated_sharpe):
        return False
    if math.isnan(challenger_metrics.oos_max_drawdown) or math.isnan(champion_metrics.oos_max_drawdown):
        return False

    if challenger_metrics.deflated_sharpe <= champion_metrics.deflated_sharpe + MIN_SHARPE_IMPROVEMENT:
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
        labeled = label_from_source(symbol=SYMBOL, source=RETRAIN_DATA_SOURCE)
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

    x_recent = np.array([list(f.values()) for f in recent.features])
    y_recent = np.array(recent.labels)
    x_hist = np.array([list(f.values()) for f in historical.features])
    y_hist = np.array(historical.labels)

    recent_acc = float(np.mean(model.predict(x_recent) == y_recent))
    hist_acc = float(np.mean(model.predict(x_hist) == y_hist))

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
        labeled = label_from_source(symbol=SYMBOL, source=RETRAIN_DATA_SOURCE)
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
