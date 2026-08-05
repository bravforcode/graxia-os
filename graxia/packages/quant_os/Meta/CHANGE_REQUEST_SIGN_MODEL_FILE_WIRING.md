# Change Request: Wire sign_model_file + signing_key into signal_service.py (P0-API-4)

**Date:** 2026-07-24
**Author:** builder-agent (evidence-driven)
**Status:** PROPOSED
**Priority:** P0 (model integrity — unsigned pickle = arbitrary code execution surface)

---

## Problem

`api/signal_service.py:247-257` saves a retrained XGBoost model via raw `pickle.dump()` with no integrity signature. The load path (line 106) calls `safe_load_model(path)` **without** `signing_key`, so it:

1. Skips HMAC verification entirely (`.sig` sidecar never created).
2. Uses `RestrictedUnpickler` (not `TrustedUnpickler`), which only allows a hardcoded class allowlist — safe-ish, but not cryptographically signed.

The function `sign_model_file()` already exists in `core/safe_pickle.py:129` and is tested (`tests/test_safe_pickle.py`), but is never called anywhere in the production codebase. The signing key config field `model_signing_key` exists in `core/config.py:48` (env: `MODEL_SIGNING_KEY`) but signal_service.py doesn't read it.

**Consequence:** Any process with write access to `/app/artifacts/strategy_model/` can swap the `.pkl` file with a malicious pickle. On next restart (or retrain), it will be loaded and executed. The `.sig` sidecar mechanism exists to prevent exactly this.

---

## Current Code

### Save path (line 241-257)

```python
# Save retrained model to disk for faster restart
try:
    import pickle
    model_save_dir = Path("/app/artifacts/strategy_model")
    model_save_dir.mkdir(parents=True, exist_ok=True)
    save_path = model_save_dir / f"xgboost_{SYMBOL}_live_features.pkl"
    with open(save_path, "wb") as f:
        pickle.dump(
            {
                "model": _model,
                "feature_names": _feature_names,
                "model_type": "xgboost",
                "version": datetime.now(UTC).strftime("%Y%m%d_%H%M%S"),
                "training_samples": len(X_train),
            },
            f,
        )
    logger.info("model.saved_to_disk", path=str(save_path))
```

### Load path (line 104-106)

```python
for path in ordered:
    try:
        raw = safe_load_model(path)
```

### Config field (core/config.py:48, 202)

```python
model_signing_key: str = ""
# ...
self.model_signing_key = os.getenv("MODEL_SIGNING_KEY", self.model_signing_key)
```

---

## Proposed Fix

### 1. Import `sign_model_file` (line 30)

```python
from graxia.packages.quant_os.core.safe_pickle import safe_load_model, sign_model_file
```

### 2. Read signing key from env (near line 58, alongside other env vars)

```python
MODEL_SIGNING_KEY = os.getenv("MODEL_SIGNING_KEY", "")
```

### 3. Sign after save (after line 257)

```python
    logger.info("model.saved_to_disk", path=str(save_path))
    if MODEL_SIGNING_KEY:
        sign_model_file(save_path, MODEL_SIGNING_KEY)
        logger.info("model.signed", path=str(save_path))
    else:
        logger.warning("model.save_unsigned", reason="MODEL_SIGNING_KEY not set")
```

### 4. Verify on load (line 106)

```python
raw = safe_load_model(path, signing_key=MODEL_SIGNING_KEY or None)
```

Using `or None` so that an empty string behaves the same as before (no HMAC check), allowing unsigned models to still load during transition. Once `MODEL_SIGNING_KEY` is set in production, all new saves will be signed and all loads will verify.

---

## Behavioral Impact

### Going forward
- **With `MODEL_SIGNING_KEY` set:** Every retrain produces a `.pkl` + `.sig` pair. On load, HMAC is verified; tampered files rejected with `ValueError`. `TrustedUnpickler` used (allows sklearn/XGBoost objects).
- **Without `MODEL_SIGNING_KEY`:** Behavior identical to today (unsigned, `RestrictedUnpickler`). Warning logged.

### Transition
- Existing unsigned `.pkl` files continue to load fine (no `signing_key` → no HMAC check).
- After `MODEL_SIGNING_KEY` is set in the environment, the next retrain produces signed files. Loads from that point onward verify signatures.
- No forced re-signing of historical models needed.

### Historical results caveat
- None. This change is pure integrity enforcement; it does not alter model output, feature computation, or signal logic.

---

## Scope of Impact

| File | Change | Risk |
|------|--------|------|
| `api/signal_service.py` | Import `sign_model_file`; read `MODEL_SIGNING_KEY` env; sign after save; pass `signing_key` on load | Low — additive only |
| `core/config.py` | No change needed (field already exists) | None |
| `tests/test_safe_pickle.py` | No change needed (already covers sign + verify) | None |
| `tests/test_signal_service.py` (if exists) | Add test for signed save/unsigned-load/signed-load paths | Medium — needs new test |

---

## Risk Assessment

- **Low risk:** Three small additions to one file. No change to model training, feature computation, or signal logic.
- **Correctness:** `sign_model_file` and `safe_load_model(signing_key=...)` are already implemented and tested in `core/safe_pickle.py`. This is purely wiring.
- **Regression:** Load path remains backward-compatible: `signing_key=None` (default) skips HMAC, same as today.
- **Rollback:** Remove the three additions; behavior reverts to current state.

---

## Approval

| Approver | Role | Date | Decision |
|----------|------|------|----------|
| — | Human Reviewer | — | **PENDING** |
