"""2B.5b — Real retrain of XAUUSD/H1 using TripleBoostEnsemble.

One frozen methodology, one run, honest report. See task instructions
(2B.5b) for the full firewall — this script does not search for a better
result; it runs the pipeline once and prints whatever comes out.

Pipeline:
  1. Load real XAUUSD/H1 OHLCV via backtest.data_loader.load_ohlcv (source
     decided in scripts/auto_retrain.py::RETRAIN_DATA_SOURCE == "duckdb" —
     see that constant's comment for why warehouse was rejected).
  2. Generate features via ml.pipeline.FeatureEngineer (the SAME feature
     engineer scripts/auto_retrain.py::evaluate_model() uses).
  3. Split via ml.pipeline.purge_embargo_split_indices (same call,
     test_ratio=0.2, gap=12 — the third consumer of this function, after
     MLTrainer.train() and evaluate_model()). Train ONLY on the train
     portion so the OOS fold evaluate_model() scores is never seen in
     training.
  4. Binarize triple-barrier labels ({-1,0,1} -> {0,1}, win=1) via
     ml.ensemble.binarize_triple_barrier_labels() and fit
     ml.ensemble.TripleBoostEnsemble on the train split.
  5. Register the trained model via ml.model_registry.ModelRegistry
     (signed if MODEL_SIGNING_KEY is set) for audit/versioning.
  6. Build the {"model": ..., "feature_names": ...} dict
     scripts/auto_retrain.py::evaluate_model()/hot_swap() expect (wrapping
     the ensemble in ml.ensemble.RowwisePredictAdapter so
     model.predict(X) returns a per-row array, not the aggregated
     EnsemblePrediction TripleBoostEnsemble.predict() returns natively),
     run evaluate_model() over the real OOS fold, and run hot_swap()
     against whatever champion currently exists (if any).

Usage:
  TRADING_MODE=PAPER python scripts/retrain_triple_boost_xauusd.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np

_QUANT_OS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_QUANT_OS_ROOT))

# ml/pipeline.py (imported transitively by every ml.* module below, via
# ml/__init__.py) does `from graxia.packages.quant_os.core.safe_pickle
# import ...` at module scope. That dotted path only resolves with the
# monorepo root (parent of the `graxia` namespace package) on sys.path.
# Under pytest this is inserted automatically by a plugin; a standalone
# script (this one) has no such plugin, so it must be inserted explicitly.
# Computed from _QUANT_OS_ROOT (itself derived from this file's own path)
# rather than hardcoded, so it doesn't silently break if the checkout moves:
# quant_os -> packages -> graxia -> repo root is 2 more ".parent" hops up.
_REPO_ROOT = _QUANT_OS_ROOT.parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ml.ensemble import RowwisePredictAdapter, TripleBoostEnsemble, binarize_triple_barrier_labels
from ml.labeling import label_from_source
from ml.model_registry import ModelRegistry
from ml.pipeline import FeatureEngineer, purge_embargo_split_indices

sys.path.insert(0, str(_QUANT_OS_ROOT / "scripts"))
import auto_retrain as _auto_retrain  # scripts/ has no __init__.py; needs its own dir on sys.path

SYMBOL = _auto_retrain.SYMBOL
DATA_SOURCE = _auto_retrain.RETRAIN_DATA_SOURCE


def main() -> dict:
    report: dict = {}

    # --- Step 1+2: load + feature engineer -------------------------------
    t0 = time.monotonic()
    labeled = label_from_source(symbol=SYMBOL, source=DATA_SOURCE)
    report["symbol"] = SYMBOL
    report["data_source"] = DATA_SOURCE
    report["raw_labeled_rows"] = len(labeled)

    engineer = FeatureEngineer()
    feature_set = engineer.generate_features(labeled)
    report["feature_rows"] = len(feature_set.features)
    report["n_features"] = len(feature_set.feature_names)

    labels_arr = np.array(feature_set.labels)
    label_counts = {int(k): int(v) for k, v in zip(*np.unique(labels_arr, return_counts=True))}
    report["raw_label_distribution"] = label_counts

    # --- Step 3: identical purge/embargo split evaluate_model() uses -----
    split_idx, test_start = purge_embargo_split_indices(len(feature_set.features), test_ratio=0.2, gap=12)
    report["split_idx"] = split_idx
    report["test_start"] = test_start
    report["n_train"] = split_idx
    report["n_oos"] = len(feature_set.features) - test_start

    train_features = feature_set.features[:split_idx]
    train_labels_raw = feature_set.labels[:split_idx]

    X_train = np.array([[f[name] for name in feature_set.feature_names] for f in train_features])
    y_train_raw = np.array(train_labels_raw)
    y_train_bin = binarize_triple_barrier_labels(y_train_raw)
    bin_counts = {int(k): int(v) for k, v in zip(*np.unique(y_train_bin, return_counts=True))}
    report["train_binarized_label_distribution"] = bin_counts

    # --- Step 4: fit TripleBoostEnsemble on the train split only ----------
    ensemble = TripleBoostEnsemble()
    ensemble.fit(X_train, y_train_bin)
    report["fit_seconds"] = round(time.monotonic() - t0, 1)

    adapter = RowwisePredictAdapter(ensemble)

    # --- Step 5: register via ModelRegistry (signed if key configured) ---
    registry = ModelRegistry()
    train_preds = adapter.predict(X_train)
    train_accuracy = float(np.mean(train_preds == y_train_bin))
    metadata = registry.register_model(
        adapter,
        model_name=f"triple_boost_ensemble_{SYMBOL}",
        model_type="triple_boost_ensemble",
        symbol=SYMBOL,
        timeframe="H1",
        feature_list=feature_set.feature_names,
        metrics={"train_accuracy": train_accuracy},
        training_samples=len(X_train),
        description="2B.5b real retrain — binarized (meta-labeling) TripleBoostEnsemble",
    )
    report["registry_version_id"] = metadata.version_id
    report["registry_feature_list_hash"] = metadata.feature_list_hash

    # Verify the registry round-trip honestly — report what actually happens,
    # don't assume it works just because register_model() didn't raise.
    try:
        reloaded = registry.load_model(metadata.version_id)
        report["registry_load_back"] = f"OK: {type(reloaded).__name__}"
    except Exception as exc:  # noqa: BLE001 — this is a diagnostic, not a control-flow gate
        report["registry_load_back"] = f"FAILED: {type(exc).__name__}: {exc}"

    # --- Step 6: real evaluate_model() + hot_swap() -----------------------
    model_data = {
        "model": adapter,
        "feature_names": feature_set.feature_names,
        "model_type": "triple_boost_ensemble",
        "version": metadata.version_id,
    }

    metrics = _auto_retrain.evaluate_model(model_data)
    report["evaluate_model"] = {
        "deflated_sharpe": metrics.deflated_sharpe,
        "oos_max_drawdown": metrics.oos_max_drawdown,
        "n_trades": getattr(metrics, "n_trades", None),
    }

    champion_existed_before = _auto_retrain.CHAMPION_PATH.exists()
    report["champion_existed_before_this_run"] = champion_existed_before

    promoted = _auto_retrain.hot_swap(model_data, metrics)
    report["hot_swap_promoted"] = promoted

    return report


if __name__ == "__main__":
    result = main()
    print(json.dumps(result, indent=2, default=str))
