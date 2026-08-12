# PHASE 16 — MODEL LIFECYCLE AUDIT (ML-SPECIFIC, CONDITIONAL)
*Per R1–R18. Tier 3.*

> The system uses ML (`ml/`, `xgboost`, `scikit-learn` in requirements; `SUMMARY.md` references XGBoost OOS predictions). This phase is **NOT N/A**.

---

## 16.1 — Model Identity & Versioning
- `ml/model_registry.py`, `ml/models/` (artifact dir), `fin_model/fin_model.tar.gz` exist → **registry infrastructure present**.
- Does the live system log which model version (hash/timestamp) generated each signal? `[UNVERIFIED — registry exists, call-site logging not traced]`. → P2.
- Is "the model" a single unversioned `.pkl`/`.joblib` silently overwritten? `ml/models/` contents `[not inspected]`; `.gitignore:14` excludes `*.pkl` → **model artifacts are NOT in version control**, so there is no git-level model provenance. → P2.

## 16.2 — Training/Validation Discipline
- Nested CV: `[NOT FOUND]`. `scripts/cross_validate.py`, `core/cross_validation.py` exist (k-fold / walk-forward), but **not nested** (inner tune + outer honest eval). → P2 (overstates performance).
- Reproducible training script: `run_ml_train.py`, `scripts/train_*.py` exist → scripts present. Whether training is partly manual/interactive (notebook) `[partially — notebooks exist: dashboard.ipynb]`. → P2.

## 16.3 — Retraining Cadence & Staleness
- `core/config.py:83` `ml_retrain_interval_days=7`. **Cadence is configured.** Whether a scheduler actually triggers retraining every 7 days `[UNVERIFIED]`. → P2.
- Last-retrained-vs-now check: `[NOT FOUND]`. → P2.

## 16.4 — Input Drift Detection
- `ml/drift_monitor.py`, `core/drift_monitor.py` exist → **infrastructure present**. `core/config.py:84` `ml_drift_threshold=0.10`. Whether PSI/KS is actually computed on live features vs training `[UNVERIFIED]`. → P2 (Phase 22-adjacent).

## 16.5 — Reproducibility of the Exact Live Model
- Seeds: `[UNVERIFIED repo-wide]` (Phase 17.2/19). XGBoost with `n_jobs>1` can be non-deterministic without `threadpoolctl` controls; `threadpoolctl` IS in requirements (`requirements.txt:69`). → plausible but unverified.

---

## Phase 16 — Verdict

**STATUS: PARTIAL.** ML lifecycle *infrastructure* is broadly present (registry, drift monitor, retrain cadence config, threadpoolctl). But model artifacts are gitignored (no provenance), nested CV absent, retrain trigger unverified, drift-detection invocation unverified. None of these block paper trading, but all should be closed before live capital.
