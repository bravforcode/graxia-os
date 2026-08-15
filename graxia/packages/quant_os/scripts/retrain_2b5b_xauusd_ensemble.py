"""2B.5b — One-shot XAUUSD retrain using TripleBoostEnsemble, evaluated
through the real evaluate_model()/hot_swap() gate.

This is a single frozen run, not part of the production auto-retrain path
(scripts/auto_retrain.py::retrain_model() still does its own walk-forward
XGBoost training and is unchanged). It exists to answer one question: does
a TripleBoostEnsemble challenger, trained on the deduplicated warehouse
XAUUSD/H1 data with binarized triple-barrier labels, clear the real
promotion gate?

Methodology is fixed before results are inspected:
  1. label_from_source(symbol=SYMBOL, source=RETRAIN_DATA_SOURCE) --
     RETRAIN_DATA_SOURCE is read from scripts/auto_retrain.py itself (not
     hardcoded), so training draws from the exact same source
     evaluate_model() uses for its OOS fold (not "auto", not a different
     symbol) -- whatever that source is at run time.
  2. purge_embargo_split_indices(n, test_ratio=0.2, gap=12) -- the shared
     split function, called (not re-derived).
  3. Train ONLY on features[:split_idx] (never the embargo gap or the OOS
     fold) -- the same boundary _train_on() in tests/test_auto_retrain.py
     uses, and the guard against the leakage that produced the earlier
     deflated_sharpe=31.39 artifact.
  4. Labels binarized only for the TRAINING fold
     (ml.ensemble.binarize_triple_barrier_labels) -- the OOS fold keeps its
     real 3-class {-1,0,1} labels, which evaluate_model()'s P&L simulation
     needs.
  5. model_data["model"] is a RowwisePredictAdapter wrapping the fitted
     TripleBoostEnsemble, so evaluate_model()'s ``model.predict(x_oos)``
     gets a per-row 0/1 array.

Raw evaluate_model() numbers are written to RESULT_PATH immediately after
computation, before hot_swap() (the only step with a side effect) runs.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import numpy as np

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# ml.pipeline imports `graxia.packages.quant_os.core.safe_pickle` at module
# level, which needs the repo root (parent of the `graxia` namespace
# package) on sys.path -- conftest.py does this for pytest runs, but this
# script runs standalone (`python scripts/...`), so it must do the same
# thing itself. quant_os -> packages -> graxia -> repo root.
_REPO_ROOT = _ROOT.parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from ml.ensemble import RowwisePredictAdapter, TripleBoostEnsemble, binarize_triple_barrier_labels  # noqa: E402
from ml.labeling import label_from_source  # noqa: E402
from ml.pipeline import FeatureEngineer, purge_embargo_split_indices  # noqa: E402

# Load scripts/auto_retrain.py exactly the way tests/test_auto_retrain.py
# does (scripts/ has no __init__.py, so this is a standalone file import).
_SPEC = importlib.util.spec_from_file_location("auto_retrain", _ROOT / "scripts" / "auto_retrain.py")
assert _SPEC is not None and _SPEC.loader is not None
_auto_retrain = importlib.util.module_from_spec(_SPEC)
sys.modules["auto_retrain"] = _auto_retrain
_SPEC.loader.exec_module(_auto_retrain)

SYMBOL = _auto_retrain.SYMBOL
evaluate_model = _auto_retrain.evaluate_model
hot_swap = _auto_retrain.hot_swap

# Mirror whatever data source evaluate_model() itself actually uses right
# now -- read from auto_retrain.py rather than hardcoded, so training and
# evaluation can never silently draw from two different datasets (that
# would be a worse bug than the one this task fixes: guaranteed
# train/OOS distribution mismatch, not just a leakage risk). At the time
# this script was written, scripts/auto_retrain.py's own
# ``RETRAIN_DATA_SOURCE`` constant documents that "warehouse" was checked
# and rejected in favor of "duckdb" for this exact task (2B.5b) -- see
# that file's comment for the reasoning (the warehouse 6x-duplication bug
# this task also fixes defensively at load time, independent of which
# source evaluate_model() ends up using here).
RETRAIN_DATA_SOURCE = getattr(_auto_retrain, "RETRAIN_DATA_SOURCE", "warehouse")

RESULT_PATH = _ROOT / "research" / "retrain_2b5b_xauusd_ensemble_result.json"


def main() -> dict:
    print(f"[2b5b] symbol={SYMBOL!r} source={RETRAIN_DATA_SOURCE!r} timeframe=H1 (default)")

    labeled = label_from_source(symbol=SYMBOL, source=RETRAIN_DATA_SOURCE)
    print(f"[2b5b] label_from_source rows={len(labeled)}")

    engineer = FeatureEngineer()
    feature_set = engineer.generate_features(labeled)
    print(
        f"[2b5b] feature rows={len(feature_set.features)} "
        f"n_features={len(feature_set.feature_names)}"
    )

    split_idx, test_start = purge_embargo_split_indices(len(feature_set.features), test_ratio=0.2, gap=12)
    print(f"[2b5b] split_idx={split_idx} test_start={test_start} total={len(feature_set.features)}")

    train_features = feature_set.features[:split_idx]
    train_labels_raw = feature_set.labels[:split_idx]
    y_train = binarize_triple_barrier_labels(train_labels_raw)
    x_train = np.array([list(f.values()) for f in train_features])

    uniq, counts = np.unique(y_train, return_counts=True)
    print(f"[2b5b] training rows={len(x_train)} binarized label counts={dict(zip(uniq.tolist(), counts.tolist()))}")

    ensemble = TripleBoostEnsemble()
    ensemble.fit(x_train, y_train)
    adapter = RowwisePredictAdapter(ensemble)

    model_data = {
        "model": adapter,
        "feature_names": feature_set.feature_names,
        "model_type": "triple_boost_ensemble",
        "version": "2b5b_xauusd_h1",
    }

    # --- Required correctness check: per-row 0/1 array, not one aggregate object ---
    oos_features = feature_set.features[test_start:]
    x_oos = np.array([[f.get(name, 0) for name in feature_set.feature_names] for f in oos_features])
    check_preds = model_data["model"].predict(x_oos)
    assert isinstance(check_preds, np.ndarray), f"predict() must return ndarray, got {type(check_preds)}"
    assert check_preds.shape == (len(x_oos),), f"predict() shape {check_preds.shape} != {(len(x_oos),)}"
    assert set(np.unique(check_preds)).issubset({0, 1}), f"predict() values not 0/1: {set(np.unique(check_preds))}"
    print(f"[2b5b] predict() sanity check OK: shape={check_preds.shape} values={set(np.unique(check_preds).tolist())}")

    # --- Real evaluation via the REAL evaluate_model() (re-derives its own split internally) ---
    metrics = evaluate_model(model_data)
    n_trades = getattr(metrics, "n_trades", None)
    print(
        f"[2b5b] evaluate_model() -> deflated_sharpe={metrics.deflated_sharpe} "
        f"oos_max_drawdown={metrics.oos_max_drawdown} n_trades={n_trades}"
    )

    result = {
        "symbol": SYMBOL,
        "n_labeled_rows": len(labeled),
        "n_feature_rows": len(feature_set.features),
        "split_idx": split_idx,
        "test_start": test_start,
        "n_train_rows": len(x_train),
        "n_oos_rows": len(oos_features),
        "deflated_sharpe": metrics.deflated_sharpe,
        "oos_max_drawdown": metrics.oos_max_drawdown,
        "n_trades": n_trades,
    }

    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(result, indent=2))
    print(f"[2b5b] wrote raw evaluation result to {RESULT_PATH}")

    if math.isnan(metrics.deflated_sharpe) or not n_trades or n_trades < _auto_retrain._MIN_EVAL_TRADES:
        result["verdict"] = "INSUFFICIENT_DATA"
        RESULT_PATH.write_text(json.dumps(result, indent=2))
        print("[2b5b] VERDICT: INSUFFICIENT_DATA")
        return result

    champion_existed_before = _auto_retrain.CHAMPION_PATH.exists()
    promoted = hot_swap(model_data, metrics)
    verdict = "GO" if promoted else "NO-GO"

    result["champion_existed_before"] = champion_existed_before
    result["promoted"] = promoted
    result["verdict"] = verdict
    RESULT_PATH.write_text(json.dumps(result, indent=2))

    print(
        f"[2b5b] VERDICT: {verdict} "
        f"(promoted={promoted}, champion_existed_before={champion_existed_before})"
    )
    return result


if __name__ == "__main__":
    main()
