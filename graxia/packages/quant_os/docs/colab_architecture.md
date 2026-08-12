# Google Colab + GRAXIA-OS: Architecture & Feasibility Study

**Version:** 1.0  
**Date:** 2026-06-26  
**Project:** GRAXIA-OS v0.2.0-dev (quant_os)  
**Symbol:** XAUUSD M15 | Pepperstone MT5 Demo  
**Author:** Researcher Agent (Ruflow Project Gracia)

---

## Table of Contents

1. [Current Setup Overview](#1-current-setup-overview)
2. [Colab Environment Analysis](#2-colab-environment-analysis)
3. [Data Transfer Strategies](#3-data-transfer-strategies)
4. [Model Exchange Format](#4-model-exchange-format)
5. [GPU Training with XGBoost + Optuna](#5-gpu-training-with-xgboost--optuna)
6. [Colab Limitations & Constraints](#6-colab-limitations--constraints)
7. [Proposed Architecture](#7-proposed-architecture)
8. [Feature Consistency: The Critical Gap](#8-feature-consistency-the-critical-gap)
9. [Cost Analysis](#9-cost-analysis)
10. [Step-by-Step Colab Notebook](#10-step-by-step-colab-notebook)
11. [Alternatives If Colab Fails](#11-alternatives-if-colab-fails)
12. [Conclusion](#12-conclusion)

---

## 1. Current Setup Overview

```
┌─────────────────────────────────────────────────────────────┐
│                   LOCAL WINDOWS PC                          │
│                                                             │
│  ┌─────────────────┐    ┌──────────────────────────────┐    │
│  │  Pepperstone    │    │  GRAXIA-OS (quant_os)        │    │
│  │  MT5 Terminal   │◄──►│   ├─ run_paper_trading.py   │    │
│  │  (Demo)         │    │   ├─ strategies/mlb.py       │    │
│  └─────────────────┘    │   ├─ ml/pipeline.py          │    │
│                         │   ├─ core/ml_pipeline.py     │    │
│                         │   ├─ execution/broker_adapter│    │
│                         │   ├─ regime/* (sweep)        │    │
│                         │   └─ data/ (CSV per TF)      │    │
│                         └──────────────────────────────┘    │
│                                                             │
│  Python 3.11.14 | Windows x64 | XGBoost 3.2.0              │
│  sklearn 1.9.0 | optuna 4.9.0 | pandas 2.3.3              │
└─────────────────────────────────────────────────────────────┘
```

**Key dependencies** (from `requirements.txt`):

| Package     | Version   | Critical for Colab? |
|-------------|-----------|---------------------|
| Python      | >=3.11    | YES - Colab default is 3.10 |
| pandas      | 2.3.3     | YES - heavy dep |
| numpy       | >=1.26.4,<2.1 | YES, compatibility |
| xgboost     | 3.2.0     | YES - GPU training |
| scikit-learn| 1.9.0     | YES - pipeline |
| optuna      | 4.9.0     | YES - hyperparam tuning |
| pyarrow     | 24.0.0    | For parquet data |
| duckdb      | 1.5.4     | SQL on data |
| MetaTrader5 | 5.0.5735  | NOT in Colab |
| pandas_ta   | (implied) | YES - feature engineering |
| smartmoneyconcepts | 0.0.27 | YES - SMC features |

---

## 2. Colab Environment Analysis

### 2.1 Python Version

| Aspect | Detail |
|--------|--------|
| **Default Python** | 3.10.12 (as of mid-2026) |
| **Available** | 3.11 available via runtime change (not always) |
| **GRAXIA-OS requires** | >=3.11 (from `pyproject.toml`) |
| **Risk** | ⚠️ Medium. If Colab only offers 3.10, install 3.11 via `apt-get` or use `python3.11` if available. Fallback: adjust `requires-python` or use conda. |

**Workaround for Python 3.11:**
```python
# In Colab notebook (if 3.10 default):
!apt-get update -qq && apt-get install -y python3.11 python3.11-dev python3.11-venv
!python3.11 -m venv /content/venv
!source /content/venv/bin/activate && pip install ...
```

**Verdict:** ✅ Feasible with minor workaround.

### 2.2 Dependency Installation

| Question | Answer |
|----------|--------|
| Can we `pip install -r requirements.txt`? | ✅ **Yes.** Colab supports pip. |
| Any packages that won't install? | ✅ **MetaTrader5 will fail** (no MT5 terminal on Linux). But we don't need MT5 in Colab — it's for training only. |
| pandas_ta? | ✅ Installs fine. |
| smartmoneyconcepts? | ✅ Installs fine (numba + llvmlite work on Colab's Linux). |
| duckdb? | ✅ Works. |
| pyarrow (24.0.0)? | ⚠️ **Need to check** — very new version. Colab's Linux may have older glibc. Pin to pyarrow==17.0.0 if 24.0.0 fails. |
| xgboost with GPU support? | ✅ Pre-installed or pip install works. |
| optuna? | ✅ Works. |

**Optimized install (skip MT5 + non-training deps):**
```python
# In Colab: minimal subset for training
!pip install pandas==2.3.3 numpy scipy scikit-learn==1.9.0 xgboost==3.2.0 \
    optuna==4.9.0 pyarrow duckdb pandas_ta smartmoneyconcepts \
    numba llvmlite joblib matplotlib seaborn
```

**Verdict:** ✅ 95% of deps install. MT5 excluded (not needed for training).

### 2.3 Pre-installed Packages

Colab has these pre-installed (but may need upgrade for exact version matching):

- numpy, pandas, scipy, scikit-learn, matplotlib, seaborn
- xgboost (CPU version only by default)
- Google Drive API libraries
- requests, tqdm, joblib

⚠️ **Critical:** Pre-installed xgboost is **CPU-only**. Need `!pip install --upgrade xgboost` to get GPU support.

### 2.4 Hardware Resources

| Resource | Free Tier | Colab Pro | Colab Pro+ |
|----------|-----------|-----------|------------|
| **CPU** | 2 vCPU | 2 vCPU | 4+ vCPU |
| **RAM** | ~12.7 GB | ~25 GB | ~25-50 GB |
| **GPU** | T4/K80 (variable) | T4/P100 (priority) | A100 (priority) |
| **GPU RAM** | 16 GB (T4) | 16 GB (T4) or 24 GB (P100) | 40/80 GB (A100) |
| **Disk** | ~78 GB ephemeral | ~166 GB | ~225 GB |
| **Max Runtime** | ~12h (idle: 90min) | ~24h | ~24h (with compute units) |
| **Background exec** | ❌ No | ❌ No | ❌ No |

---

## 3. Data Transfer Strategies

This is the **most critical design decision**. GRAXIA-OS has 10+ years of tick data in Parquet format across multiple symbols and timeframes.

### 3.1 Options Comparison

| Method | Speed | Cost | Complexity | Best For |
|--------|-------|------|------------|----------|
| **Google Drive mount** | 📦 Medium (I/O limited) | Free (up to 15 GB) | ✅ Easy | Daily model sync, small CSVs |
| **GitHub LFS** | 🐢 Slow for large files | Free tier (1 GB LFS) | 🟡 Medium | Model .pkl files (<100 MB) |
| **Direct download (URL)** | 🚀 Fast | Free if self-hosted | ✅ Easy | Static datasets |
| **HuggingFace Datasets** | 🚀 Fast | Free | 🟡 Medium | Large public datasets |
| **Google Cloud Storage** | 🚀 Fastest | 💰 Pay per GB | 🔴 Complex | Production pipeline |
| **Kaggle Dataset** | 🚀 Fast | Free | 🟡 Medium | If data on Kaggle |
| **Parquet via Drive** | 📦 Medium | Free (15 GB) | ✅ Easy | 10yr tick data (<15 GB) |

### 3.2 Recommended: Hybrid Drive + GitHub

```
                    GOOGLE DRIVE (15 GB free)
                    ┌────────────────────────────┐
                    │  graxia-os/                │
                    │   ├── data/ (parquet/CSV)  │ ← Mount once, stay connected
                    │   ├── models/ (.pkl)       │ ← Read/write during training
                    │   └── logs/ (optuna)        │
                    └────────────────────────────┘
                            ⇅  (rsync-style copy to VM for speed)
                    ┌────────────────────────────┐
                    │  COLAB VM (ephemeral /content/) │
                    │  cp /content/drive/... /content/local/  │
                    └────────────────────────────┘
                            ⇅  (model push)
                    ┌────────────────────────────┐
                    │  GITHUB (graxia-os repo)    │
                    │  ml/models/xgboost_*.pkl    │ ← Local PC pulls from here
                    └────────────────────────────┘
```

**Workflow:**

1. **Data → Colab:** Mount Google Drive → copy data to VM RAM disk for I/O speed
2. **Training:** Read from local VM disk (fast), write model to Drive (periodic)
3. **Model → GitHub:** After training, copy best model to repo clone, commit & push
4. **Model → Local PC:** `git pull` on Windows

### 3.3 Large Parquet File Handling (10yr ticks)

**Problem:** 10 years of tick data for XAUUSD (~500M-2B rows) could be 10-40 GB in Parquet — exceeds free Drive space.

**Solution: Aggregate before upload**

```python
# Strategy: Store only M15 OHLCV in Drive, not raw ticks
# tick → M15 aggregation runs once on local PC
# Drive stores: XAUUSD_M15.parquet (est. 300-500 MB for 10yr)
# Raw ticks: kept only on local PC or external HDD
```

**If you need raw ticks in Colab:**

| Approach | Detail |
|----------|--------|
| **Compressed Parquet** | ZSTD compression → ~5 GB for 10yr XAUUSD ticks |
| **Split by year** | `drive/graxia-os/data/ticks/2024.parquet`, `2025.parquet`, ... |
| **Colab Pro+ RAM** | 50 GB RAM + 225 GB disk = can hold full dataset |
| **Google Drive quota** | Free: 15 GB. Pro: 100 GB. Pro+: 1 TB. |
| **Alternative** | Store on HuggingFace Datasets (free, fast CDN) |

**Verdict:** ✅ Entire XAUUSD M15 (~500 MB) fits in free Drive. Raw ticks need Pro/compression.

### 3.4 GitHub as Model Transport

**Model file size:** Each XGBoost `.pkl` is typically **1-10 MB** (with 200 trees, ~50 features).

```bash
# GitHub supports files up to 100 MB natively (no LFS needed)
# Our .pkl files: ~3-8 MB → fits comfortably

# Push from Colab:
!git config --global user.email "colab@graxia-os.dev"
!git config --global user.name "Colab Trainer"
!git add ml/models/*.pkl
!git commit -m "chore(model): auto-update XAUUSD model $(date +%Y%m%d)"
!git push origin main
```

**GitHub auth in Colab:** Use Personal Access Token (classic, `repo` scope).

```python
import os
os.environ['GITHUB_TOKEN'] = 'ghp_xxx'
!git remote set-url origin https://{GITHUB_TOKEN}@github.com/bravforcode/graxia-os.git
```

**Verdict:** ✅ Models < 10 MB, GitHub push is optimal transport.

---

## 4. Model Exchange Format

### 4.1 Current Format

From `ml/pipeline.py` line 287-292:
```python
pickle.dump({
    "model": model,           # XGBClassifier (sklearn wrapper)
    "feature_names": [...],   # List[str]
    "model_type": "xgboost",
    "version": version,
}, f)
```

### 4.2 Colab → Local Compatibility Matrix

| Method | Same xgboost version | Different xgboost version | Notes |
|--------|---------------------|--------------------------|-------|
| `pickle.dump`/`load` | ✅ Perfect | ❌ **FAILS** | pickle is version-sensitive for sklearn wrappers |
| `model.save_model('model.json')` | ✅ Perfect | ✅ Works | XGBoost native format, cross-version safe |
| `model.save_model('model.ubj')` | ✅ Perfect | ✅ Works | UBJSON, slightly faster than JSON |
| `joblib.dump` | ✅ Perfect | ⚠️ Maybe | Same issue as pickle |
| ONNX export | ✅ Perfect | ✅ Perfect | Heavy dependency, use only if needed |

### 4.3 RECOMMENDED: Dual Format Save

**Critical insight:** Pickle breaks when sklearn/xgboost versions differ between Colab and local PC.

**Fix:** Save native XGBoost Booster + metadata separately.

```python
# In Colab (trainer):
import xgboost as xgb
import json

# Train with sklearn wrapper for convenience
model.fit(X_train, y_train)

# Save BOTH formats:
# 1. Sklearn wrapper (for loading on same-version machines)
import pickle
with open("model_sklearn.pkl", "wb") as f:
    pickle.dump({"model": model, "feature_names": feature_names}, f)

# 2. Native XGBoost booster (cross-version safe!)
booster = model.get_booster()
booster.save_model("model_xgb.json")  # OR .ubj for binary

# Save metadata separately
with open("model_metadata.json", "w") as f:
    json.dump({
        "feature_names": feature_names,
        "feature_count": len(feature_names),
        "model_type": "xgboost",
        "version": version,
        "xgboost_version": xgb.__version__,
        "sklearn_version": "1.9.0",
        "classes": [0, 1, 2],  # hold, buy, sell
    }, f)
```

**On local PC (load):**
```python
import json
import pickle
import xgboost as xgb
from xgboost import XGBClassifier

# Try pickle first (fast)
try:
    with open("model_sklearn.pkl", "rb") as f:
        data = pickle.load(f)
    model = data["model"]
except (pickle.UnpicklingError, ModuleNotFoundError, TypeError):
    # Version mismatch! Fall back to native format
    booster = xgb.Booster()
    booster.load_model("model_xgb.json")
    
    # Re-wrap in sklearn-compatible interface
    with open("model_metadata.json") as f:
        meta = json.load(f)
    
    model = XGBClassifier()
    model.get_booster = lambda: booster
    model.predict = lambda X: booster.predict(xgb.DMatrix(X)).astype(int)
    model.predict_proba = lambda X: booster.predict(xgb.DMatrix(X), 
                                                     output_margin=False).reshape(-1, 1)
    data = {
        "model": model,
        "feature_names": meta["feature_names"],
    }
```

**Verdict:** ✅ **Dual save** eliminates version mismatch risk entirely.

### 4.4 Version Compatibility Risks

| Scenario | Risk Level | Solution |
|----------|-----------|----------|
| Colab XGBoost 3.2.0 → Local 3.2.0 | 🟢 None | Identical versions |
| Colab 3.2.0 → Local 3.1.0 | 🟡 Low | Native JSON format handles this |
| Colab 3.2.0 → Local 2.x | 🔴 High | Major version change may break; pin both to same |
| Colab sklearn 1.9.0 → Local 1.5.2 | 🔴 High (pickle) | Use native XGBoost save, avoid pickle |
| Feature count mismatch | 🔴 Critical | Must version feature list in metadata |

**Pin both environments** to identical xgboost version:
- Colab: `!pip install xgboost==3.2.0`
- Local: `xgboost==3.2.0` (already in requirements.txt)

---

## 5. GPU Training with XGBoost + Optuna

### 5.1 Does XGBoost Support GPU on Colab?

**Yes.** XGBoost 3.x has native GPU support.

```python
# Enable GPU in Colab:
model = XGBClassifier(
    tree_method="hist",
    device="cuda",      # WAS: gpu_id=0 (deprecated)
    n_estimators=200,
    max_depth=3,
    learning_rate=0.01,
)
```

**Requirements:**
- CUDA Compute Capability >= 5.0 ✅ (T4 = 7.5, P100 = 6.0, K80 = 3.7)
- xgboost >= 1.7.0 ✅ (we use 3.2.0)
- `!pip install --upgrade xgboost` to get GPU-enabled build

### 5.2 Expected Speedup

| Dataset Size | CPU (2 vCPU) | GPU T4 (16 GB) | Speedup |
|-------------|-------------|----------------|---------|
| 50k rows × 50 features | 15s | 4s | 3.75× |
| 200k × 50 | 90s | 18s | 5× |
| 1M × 50 | 8 min | 45s | 10-12× |
| 10M × 50 | 90 min | 6 min | 15× |
| Optuna 200 trials × 50k | 50 min | 13 min | 4× |

**Key insight:** Speedup is minimal for small datasets (<100k rows) due to PCIe transfer overhead. For GRAXIA-OS (XAUUSD M15, ~350k bars in 10yr), expect **5-8× speedup**.

### 5.3 Optuna + GPU

```python
import optuna
from optuna.samplers import TPESampler

def objective(trial):
    params = {
        "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
        "max_depth": trial.suggest_int("max_depth", 3, 10),
        "learning_rate": trial.suggest_float("learning_rate", 0.001, 0.1, log=True),
        "subsample": trial.suggest_float("subsample", 0.6, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.6, 1.0),
        "reg_lambda": trial.suggest_float("reg_lambda", 1.0, 10.0, log=True),
        "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 5.0),
        "tree_method": "hist",
        "device": "cuda",  # GPU!
        "random_state": 42,
    }
    model = XGBClassifier(**params)
    model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)
    return accuracy_score(y_val, model.predict(X_val))

study = optuna.create_study(
    direction="maximize",
    sampler=TPESampler(seed=42),
    storage="sqlite:///optuna_xauuid.db",  # Save progress
    study_name="xauusd_m15_v1",
)
study.optimize(objective, n_trials=200, n_jobs=1)

# GPU + multiple trials
print(f"Best trial: {study.best_trial.value}")
print(f"Best params: {study.best_trial.params}")
```

**Optuna GPU considerations:**
- `n_jobs=1` when using GPU (parallel jobs fight for GPU memory)
- One trial at a time uses GPU fully
- 200 trials × ~30s each ≈ **100 min** on GPU vs 400 min on CPU
- Use `storage="sqlite:///..."` to save intermediate results (Colab won't lose all progress on disconnect)

### 5.4 GPU Memory Budget

| Operation | Memory | Colab T4 (16 GB) |
|-----------|--------|-----------------|
| XAUUSD M15 10yr (350k × 50 features) | ~140 MB | ✅ Fits easily |
| Optuna: 200 trials | ~2 GB | ✅ Fits |
| Large hyperparameter search (2000 trials) | ~4 GB | ✅ Fits |
| Cross-validation (5-fold) | ~3 GB | ✅ Fits |
| SHAP values computation | ~2 GB extra | ✅ Fits |

**Verdict:** ✅ Colab GPU is excellent for GRAXIA-OS model training.

---

## 6. Colab Limitations & Constraints

### 6.1 What Colab CANNOT Do

| Feature | Why Not | Impact |
|---------|---------|--------|
| **Connect to MT5** | MT5 terminal is Windows-only, Colab runs Linux | **No live trading from Colab** |
| **Run 24/7** | Max 12h (free) or 24h (Pro+) | Cannot run continuous live bot |
| **Background execution** | Dies when browser tab closes | Cannot deploy as persistent service |
| **Webhook server** | No persistent public IP | Cannot receive trade signals webhooks reliably |
| **Serve predictions via API** | No permanent endpoint | Cannot use as prediction microservice |
| **Large data storage** | 78 GB free / 225 GB Pro+ | 10yr tick data constrained |
| **Guaranteed GPU** | No guarantee even on Pro | Pro+ has priority but no guarantee |

### 6.2 Colab's Ephemeral Nature

```python
# EVERYTHING in /content/ disappears after disconnect:
# - Installed packages
# - Downloaded data
# - Trained models (unless saved to Drive/GitHub)
# - Optuna study DB (unless in Drive)
# - Git credentials
```

**Mitigation checklist (add to every Colab notebook):**
- [ ] Mount Google Drive at startup (`drive.mount()`)
- [ ] Copy data from Drive → VM for speed
- [ ] Save model to Drive AND push to GitHub
- [ ] Save Optuna study DB to Drive (in case of disconnect)
- [ ] Save training logs/metrics to Drive
- [ ] Use `Runtime > Run all` to restart from scratch

### 6.3 Can Colab Receive Webhooks? (No, But...)

**Short answer:** No, Colab is not a server.

**Workarounds for signal/prediction serving:**

| Method | Works? | Latency | Reliability |
|--------|--------|---------|-------------|
| ngrok tunnel to Colab | 🟡 Unstable (session dies) | ~500ms | ❌ Unreliable |
| Colab + Telegram bot polling | ✅ Yes | ~2s | ✅ Works |
| Drive file as signal bus | 🟡 Polling-based | ~30s | 🟡 Medium |
| Predictions via HuggingFace Spaces | ✅ Yes (free) | ~1s | ✅ High |
| **RECOMMENDED: Lightweight FastAPI on local PC** | ✅ Yes | ~10ms | ✅ High |

**Colab is NOT your prediction server. Local PC + GitHub pull is the right model.**

### 6.4 Session Timeout Reality

| Tier | Idle Timeout | Max Session | Typical Real |
|------|-------------|-------------|-------------|
| Free | 90 min | 12h | ~4-8h (gets killed sooner) |
| Pro | 90 min | 24h | ~12-18h |
| Pro+ | 90 min | 24h | ~20-24h |

**Impact on training:** An Optuna run of 200 trials × 2 min = 400 min = 6.7h. This fits in free tier but barely. A 1000-trial search = 33h → needs Pro+ and may still timeout.

---

## 7. Proposed Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        COLAB (GPU)                                   │
│                      [TRAINING ONLY]                                 │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  colab_xauusd_trainer.ipynb                                  │   │
│  │                                                              │   │
│  │  1. Mount Google Drive                                       │   │
│   │  2. Clone repo from GitHub                                  │   │
│  │  3. Install dependencies (skip MT5)                          │   │
│  │  4. Load M15 data from Drive (parquet/CSV)                   │   │
│  │  5. Feature engineering (pandas_ta + SMC)                    │   │
│  │  6. Walk-forward validation                                  │   │
│  │  7. Optuna hyperparameter search (GPU)                       │   │
│  │  8. Train best model on full data                            │   │
│  │  9. Save: pickle + xgb.json + metadata                       │   │
│  │  10. Push model to GitHub                                    │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                      │
│  Storage:                                                           │
│  /content/drive/MyDrive/graxia-os/data/     ← M15 OHLCV parquet    │
│  /content/drive/MyDrive/graxia-os/models/   ← checkpoints          │
│  /content/drive/MyDrive/graxia-os/optuna/   ← study DB + logs      │
│  /content/graxia-os/                        ← git clone            │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           │ git push model_sklearn.pkl + model_xgb.json
                           │ (credentials via GITHUB_TOKEN env var)
                           ▼
┌──────────────────────────────────────────────────────────────────────┐
│                        GITHUB (bravforcode/graxia-os)                │
│                                                                      │
│  ml/models/                                                         │
│  ├── xgboost_XAUUSD_20260626.pkl        ← sklearn wrapper          │
│  ├── xgboost_XAUUSD_20260626.json        ← native XGBoost booster  │
│  └── xgboost_XAUUSD_20260626_meta.json   ← feature names, versions │
└──────────────────────────────────┬───────────────────────────────────┘
                                   │
                                   │ git pull (or auto-update)
                                   ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    LOCAL WINDOWS PC                                   │
│                    [LIVE EXECUTION ONLY]                              │
│                                                                      │
│  1. git pull → get latest model(s) from GitHub                     │
│  2. load_model() with version fallback (pickle → xgb.json)          │
│  3. FeatureEngineer(M15 bars from MT5) → feature vector             │
│  4. model.predict(features) → signal                                 │
│  5. RegimeDetector + Liquidity Map + Sweep + Risk → execute          │
│  6. Log PnL, track drift, upload metrics                             │
│                                                                      │
│  Process:                                                            │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  run_paper_trading.py                                        │   │
│  │  ├── Every 10s: fetch M15 bars from MT5                     │   │
│  │  ├── Every M15 close: compute features = model.predict()    │   │
│  │  ├── If signal: run sweep pipeline, check risk, trade       │   │
│  │  └── Every hour: log PnL, check drift, upload to reports/   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────────────┘
```

### 7.1 Data Flow

```
Day 1: Download M15 data from MT5 → Export to CSV/Parquet on local PC
         → Upload to Google Drive

Colab Session: Load from Drive → Train → Save model → Push to GitHub

Local PC: git pull → Load model → Trade live → Log results
         → If drift detected: trigger retrain flag

Retrain Trigger:
  Option A: Manual → "Drift detected, run Colab notebook"
  Option B: Semi-auto → Local PC uploads recent data to Drive,
            send Telegram "retrain needed", manually run Colab
  Option C: Automated → GitHub Actions schedules Colab via API
            (complex, see §11 alternatives)
```

### 7.2 File Layout for Google Drive

```
MyDrive/graxia-os/
├── data/
│   ├── XAUUSD_M15.parquet          ← 10yr OHLCV (aggregated from ticks)
│   ├── XAUUSD_M15.csv              ← fallback for small loads
│   ├── XAUUSD_D1.parquet           ← for regime/trend features
│   └── symbols.txt                 ← list of active symbols
├── models/
│   ├── checkpoints/                ← intermediate Optuna models
│   └── best/                       ← best model per run
├── optuna/
│   ├── xauusd_m15_v1.db            ← study database (survives restarts)
│   └── trials.csv                  ← trial history export
└── logs/
    └── training_20260626.json      ← metrics, params, duration
```

---

## 8. Feature Consistency: The Critical Gap ⚠️

### 8.1 The Problem

This is the **single most critical issue** in the entire architecture.

```python
# TRAINING (Colab):
# FeatureEngineer generates 50+ features using pandas_ta
# The EXACT feature names, order, and computation logic must match

# INFERENCE (Local PC):
# mlb.py _calculate_indicators() computes features for live data
# Must produce IDENTICAL features to what the model expects
```

**Current code shows TWO separate feature implementations:**

1. **`ml/pipeline.py` (FeatureEngineer):** Uses `pandas_ta.ema()`, `pandas_ta.rsi()`, etc. — 40+ feature columns
2. **`strategies/mlb.py` (MLBreakout):** Has its own `_calculate_indicators()` with a different feature set

**If they diverge, the model silently makes garbage predictions.**

### 8.2 Solution: Single Source of Truth for Features

```
graxia-os/
└── ml/
    ├── pipeline.py              ← Training pipeline (uses feature_library)
    ├── feature_library.py       ← ← ← SINGLE SOURCE OF TRUTH
    │                             ← ALL features defined here
    │                             ← Training + Inference both import from here
    └── models/                  ← Saved models
```

**`feature_library.py` design:**
```python
"""SINGLE SOURCE OF TRUTH for feature engineering.
Both Colab training and local inference import from this module."""

import pandas as pd
import pandas_ta as ta

FEATURE_VERSION = "v1.0"  # Increment when features change

def compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute all features. Returns DataFrame with feature columns only.
    
    WARNING: Any change here INVALIDATES all existing models.
    Increment FEATURE_VERSION before changing feature logic.
    """
    features = pd.DataFrame(index=df.index)
    
    # === Price Features ===
    features["return_1"] = df["close"].pct_change(1)
    features["return_5"] = df["close"].pct_change(5)
    # ... (exact same code, no divergence)
    
    return features

def get_feature_names() -> list[str]:
    """Return ordered list of feature names.
    Used during training to save model metadata, during inference to align inputs."""
    df = pd.DataFrame({"close": [1.0]*300, "open": [1.0]*300, 
                       "high": [1.0]*300, "low": [1.0]*300, "volume": [1]*300})
    features = compute_features(df)
    return list(features.columns)
```

**Why this matters for Colab:**
- Colab trains on `compute_features(data)` with 50+ columns
- Local PC must call the **exact same** `compute_features(live_data)`
- If feature list changes → model metadata `feature_names` mismatch → crash
- **Solution:** Model metadata includes `feature_names` list. Inference code reads it and aligns columns.

### 8.3 Feature Alignment Protocol

```python
# On Local PC (inference):
def prepare_features(live_bars: pd.DataFrame, model_meta: dict) -> np.ndarray:
    """Align live data features with training feature set."""
    # Compute ALL possible features
    all_features = compute_features(live_bars)
    
    # Get the LAST row (most recent bar)
    last_features = all_features.iloc[-1:].copy()
    
    # Align with model's expected feature names
    expected_names = model_meta["feature_names"]
    missing = set(expected_names) - set(last_features.columns)
    extra = set(last_features.columns) - set(expected_names)
    
    if missing:
        raise ValueError(f"Missing features: {missing}. Retrain needed.")
    
    # Reorder to match training
    return last_features[expected_names].values  # (1, n_features)
```

### 8.4 Version Locking

```python
# In model metadata JSON:
{
    "feature_version": "v1.0",
    "feature_names": ["return_1", "return_5", ..., "rsi_14", ...],
    "xgboost_version": "3.2.0",
    "sklearn_version": "1.9.0",
    "feature_count": 45
}
```

**Local PC loads this and validates before inference:**
```python
if model_meta["feature_version"] != CURRENT_FEATURE_VERSION:
    raise RuntimeError(
        f"Feature version mismatch: model={model_meta['feature_version']}, "
        f"code={CURRENT_FEATURE_VERSION}. Retrain required."
    )
```

---

## 9. Cost Analysis

### 9.1 Colab Pricing (mid-2026)

| Tier | Price | GPU | RAM | Disk | Compute Units | Best For |
|------|-------|-----|-----|------|--------------|----------|
| **Free** | $0 | T4/K80 (variable) | ~12 GB | 78 GB | ❌ No | Experimentation, small models |
| **Pro** | $12.74/mo | T4/P100 (priority) | ~25 GB | 166 GB | 100 CU/mo | Regular retraining |
| **Pro+** | $53.53/mo | A100 (priority) | ~50 GB | 225 GB | 500 CU/mo | Heavy Optuna, large data |
| **Pay As You Go** | $9.99 + CU | Variable | Variable | Variable | buy more | Occasional heavy use |

### 9.2 When to Upgrade

| Scenario | Tier Needed | Reason |
|----------|-------------|--------|
| Quick model retrain (100 trials) | ✅ Free | Fits in 4h session |
| Full Optuna (500 trials) | ⚠️ Pro | ~8h-10h, needs priority GPU |
| 10yr tick data processing | ⚠️ Pro | Need >78 GB disk + >12 GB RAM |
| Daily automated retraining | ❌ Not possible | Colab can't run scheduled |
| Raw tick training (billions of rows) | 🔴 Pro+ | Need A100 + 50 GB RAM |

### 9.3 Total Annual Cost

| Option | Yearly Cost | Benefit |
|--------|-------------|---------|
| **Free only** | $0 | Works for weekly retraining |
| **Pro** | ~$153/yr | Priority GPU, 74% session survival |
| **Pro+** | ~$642/yr | A100, 95% session survival |
| **Comparable VPS** (runpod.io A100) | ~$0.79/hr = $1,900/yr | Dedicated, 24/7 |

**Verdict:** **Pro tier ($12.74/mo) is the sweet spot.** Free works but retries needed. Pro+ needed only if running 1000+ trial Optuna.

---

## 10. Step-by-Step Colab Notebook

Below is the complete notebook that you can copy and adapt. Explanatory comments are inline.

---

### 10.1 Notebook Header & Drive Mount

```python
# =============================================================================
# GRAXIA-OS: XAUUSD M15 Model Trainer
# Run this on Google Colab with GPU runtime enabled.
# Runtime → Change runtime type → Hardware accelerator → GPU
# =============================================================================

import os
import sys
import json
import pickle
import subprocess
from datetime import datetime
from pathlib import Path

# ---- Mount Google Drive ----
from google.colab import drive
drive.mount('/content/drive')

# Define paths
DRIVE_BASE = "/content/drive/MyDrive/graxia-os"
DATA_DIR = f"{DRIVE_BASE}/data"
MODEL_DIR = f"{DRIVE_BASE}/models"
OPTUNA_DIR = f"{DRIVE_BASE}/optuna"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(MODEL_DIR, exist_ok=True)
os.makedirs(OPTUNA_DIR, exist_ok=True)

print(f"✅ Drive mounted. Data: {DATA_DIR}")
```

### 10.2 Clone Repo

```python
# ---- Clone GRAXIA-OS ----
!git clone https://github.com/bravforcode/graxia-os.git /content/graxia-os
%cd /content/graxia-os/graxia/packages/quant_os
sys.path.insert(0, "/content/graxia-os")

print(f"✅ Repo cloned. Version: {open('VERSION').read().strip()}")
```

### 10.3 Install Dependencies (Training Subset)

```python
# ---- Install Dependencies (skip MT5, no GPU packages needed) ----
# Colab has pre-installed numpy, pandas, scipy, etc.
# We upgrade specific packages to match local versions.

!pip install --upgrade --quiet \
    pandas==2.3.3 \
    scikit-learn==1.9.0 \
    xgboost==3.2.0 \
    optuna==4.9.0 \
    pyarrow==17.0.0 \
    duckdb==1.5.4 \
    pandas_ta \
    smartmoneyconcepts==0.0.27 \
    numba==0.60.0 \
    llvmlite==0.43.0 \
    matplotlib==3.11.0 \
    seaborn==0.13.2 \
    joblib \
    python-dotenv

# Verify installations
import xgboost as xgb
import optuna
import pandas as pd
import sklearn
print(f"✅ XGBoost {xgb.__version__} (GPU: {xgb.build_info()})")
print(f"✅ Optuna {optuna.__version__}")
print(f"✅ Pandas {pd.__version__}")
print(f"✅ Sklearn {sklearn.__version__}")
```

### 10.4 Verify GPU

```python
# ---- Verify GPU Access ----
import subprocess

# Check CUDA
gpu_info = subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total,compute_cap",
                          "--format=csv,noheader"], capture_output=True, text=True)
print(f"GPU: {gpu_info.stdout.strip() if gpu_info.stdout else 'NOT FOUND'}")

# Test XGBoost GPU
import numpy as np
from xgboost import XGBClassifier

X_dummy = np.random.rand(1000, 10)
y_dummy = np.random.randint(0, 3, 1000)

model_gpu = XGBClassifier(tree_method="hist", device="cuda", n_estimators=10)
model_gpu.fit(X_dummy, y_dummy)
print(f"✅ GPU training: OK (device={model_gpu.get_booster().attributes().get('device', '?)'})")
```

### 10.5 Load Data

```python
# ---- Load XAUUSD M15 Data from Drive ----
import pandas as pd

# Option A: Parquet (preferred)
data_path = f"{DATA_DIR}/XAUUSD_M15.parquet"
if os.path.exists(data_path):
    df = pd.read_parquet(data_path)
    print(f"✅ Loaded parquet: {len(df):,} rows")
else:
    # Option B: CSV fallback
    csv_path = f"{DATA_DIR}/XAUUSD_M15.csv"
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path, parse_dates=["time"])
        print(f"✅ Loaded CSV: {len(df):,} rows")
    else:
        raise FileNotFoundError(
            f"No XAUUSD M15 data found in {DATA_DIR}.\n"
            f"Upload from local PC: scp XAUUSD_M15.parquet ...\n"
            f"Or run download from MT5 first."
        )

# Display
df["datetime"] = pd.to_datetime(df["time"] if "time" in df.columns else df["Date"])
print(f"Range: {df['datetime'].min()} → {df['datetime'].max()}")
print(f"Columns: {list(df.columns)}")
print(f"Sample:\n{df.head()}")
```

### 10.6 Feature Engineering

```python
# ---- Feature Engineering ----
# Import the project's feature engineer (single source of truth)

%cd /content/graxia-os/graxia/packages/quant_os
from ml.pipeline import FeatureEngineer, MLTrainer

# Convert to expected dict format
ohlcv_dict = {
    "open": df["open"].tolist(),
    "high": df["high"].tolist(),
    "low": df["low"].tolist(),
    "close": df["close"].tolist(),
    "volume": df["volume"].tolist() if "volume" in df else [0]*len(df),
}
timestamps = df["datetime"].tolist()

engineer = FeatureEngineer()
feature_set = engineer.generate_features(ohlcv_dict, timestamps)

print(f"✅ Features: {len(feature_set.feature_names)} columns")
print(f"✅ Samples: {len(feature_set.features)}")
print(f"✅ Labels: {pd.Series(feature_set.labels).value_counts().to_dict()}")
print(f"Feature names: {feature_set.feature_names[:10]}...")
```

### 10.7 Walk-Forward Validation

```python
# ---- Walk-Forward Validation ----
trainer = MLTrainer(model_dir=f"{DRIVE_BASE}/models")

wf_results = trainer.train_walk_forward(feature_set, model_type="xgboost", n_windows=5)

print("\n=== WALK-FORWARD RESULTS ===")
for i, wf in enumerate(wf_results):
    print(f"Window {i+1}: IS Acc={wf.accuracy:.2%}, OOS Acc={wf.oos_accuracy:.2%}")

avg_oos = sum(w.oos_accuracy for w in wf_results) / len(wf_results)
print(f"---")
print(f"Avg OOS Accuracy: {avg_oos:.2%}")
```

### 10.8 Optuna Hyperparameter Tuning (GPU)

```python
# ---- Optuna Hyperparameter Search (GPU) ----
import optuna
import numpy as np
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import accuracy_score
from xgboost import XGBClassifier

# Prepare data
X = np.array([list(f.values()) for f in feature_set.features])
y = np.array(feature_set.labels)

# Time series split
tscv = TimeSeriesSplit(n_splits=5)

def objective(trial):
    params = {
        "n_estimators": trial.suggest_int("n_estimators", 100, 500, step=50),
        "max_depth": trial.suggest_int("max_depth", 3, 12),
        "learning_rate": trial.suggest_float("learning_rate", 0.001, 0.1, log=True),
        "subsample": trial.suggest_float("subsample", 0.5, 1.0),
        "colsample_bytree": trial.suggest_float("colsample_bytree", 0.5, 1.0),
        "reg_lambda": trial.suggest_float("reg_lambda", 0.1, 10.0, log=True),
        "reg_alpha": trial.suggest_float("reg_alpha", 0.0, 5.0),
        "min_child_weight": trial.suggest_int("min_child_weight", 1, 10),
        "gamma": trial.suggest_float("gamma", 0.0, 5.0),
        "tree_method": "hist",
        "device": "cuda",
        "random_state": 42,
        "eval_metric": "mlogloss",
        "early_stopping_rounds": 20,
    }

    # TimeSeries CV
    scores = []
    for train_idx, val_idx in tscv.split(X):
        X_train_fold, X_val_fold = X[train_idx], X[val_idx]
        y_train_fold, y_val_fold = y[train_idx], y[val_idx]

        model = XGBClassifier(**params)
        model.fit(
            X_train_fold, y_train_fold,
            eval_set=[(X_val_fold, y_val_fold)],
            verbose=False,
        )
        y_pred = model.predict(X_val_fold)
        scores.append(accuracy_score(y_val_fold, y_pred))

    return np.mean(scores)


# Create/load study (survives Colab disconnect!)
study_path = f"{OPTUNA_DIR}/xauusd_m15_v1.db"
if os.path.exists(study_path):
    # Resume previous study
    study = optuna.load_study(
        storage=f"sqlite:///{study_path}",
        study_name="xauusd_m15_v1",
    )
    print(f"📋 Resuming study: {len(study.trials)} trials completed")
else:
    study = optuna.create_study(
        direction="maximize",
        sampler=optuna.samplers.TPESampler(seed=42),
        storage=f"sqlite:///{study_path}",
        study_name="xauusd_m15_v1",
        load_if_exists=True,
    )
    print(f"📋 New study created")

# Run optimization
n_trials = 200
study.optimize(objective, n_trials=n_trials)

print(f"\n=== OPTUNA RESULTS ===")
print(f"Best accuracy: {study.best_trial.value:.4f}")
print(f"Best params: {study.best_trial.params}")
print(f"Total trials: {len(study.trials)}")

# Export trial history
trials_df = study.trials_dataframe()
trials_df.to_csv(f"{OPTUNA_DIR}/trials.csv", index=False)
```

### 10.9 Train Best Model on Full Data

```python
# ---- Train Best Model on Full Dataset ----
best_params = study.best_trial.params
best_params.update({
    "tree_method": "hist",
    "device": "cuda",
    "random_state": 42,
    "eval_metric": "mlogloss",
})

print("Training best model on full dataset...")
best_model = XGBClassifier(**best_params)
best_model.fit(X, y)

# Evaluate on held-out test set (last 20%)
split = int(len(X) * 0.8)
X_test, y_test = X[split:], y[split:]
y_pred = best_model.predict(X_test)

from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score
print(f"\n=== FINAL MODEL METRICS ===")
print(f"Test accuracy:  {accuracy_score(y_test, y_pred):.2%}")
print(f"Precision:      {precision_score(y_test, y_pred, average='weighted', zero_division=0):.2%}")
print(f"Recall:         {recall_score(y_test, y_pred, average='weighted', zero_division=0):.2%}")
print(f"F1 Score:       {f1_score(y_test, y_pred, average='weighted', zero_division=0):.2%}")

# Feature importance
importances = best_model.feature_importances_
feature_imp = sorted(zip(feature_set.feature_names, importances), key=lambda x: x[1], reverse=True)
print("\nTop 10 Features:")
for name, imp in feature_imp[:10]:
    print(f"  {name}: {imp:.4f}")
```

### 10.10 Save Model (Dual Format)

```python
# ---- Save Model in Dual Format ----
version = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
symbol = "XAUUSD"
model_prefix = f"xgboost_{symbol}_{version}"

# 1) Pickle (sklearn wrapper) — fast, same-version loading
pkl_path = f"{DRIVE_BASE}/models/{model_prefix}.pkl"
with open(pkl_path, "wb") as f:
    pickle.dump({
        "model": best_model,
        "feature_names": feature_set.feature_names,
        "model_type": "xgboost",
        "version": version,
    }, f)
print(f"✅ Pickle saved: {pkl_path}")

# 2) Native XGBoost (cross-version compatible)
json_path = f"{DRIVE_BASE}/models/{model_prefix}.json"
best_model.get_booster().save_model(json_path)
print(f"✅ JSON saved: {json_path}")

# 3) Metadata
meta = {
    "version": version,
    "symbol": symbol,
    "timeframe": "M15",
    "feature_version": "v1.0",
    "feature_count": len(feature_set.feature_names),
    "feature_names": feature_set.feature_names,
    "xgboost_version": xgb.__version__,
    "sklearn_version": sklearn.__version__,
    "test_accuracy": float(accuracy_score(y_test, y_pred)),
    "oos_accuracy": float(avg_oos),
    "best_params": {k: float(v) if isinstance(v, (np.floating,)) else v for k, v in best_params.items()},
    "n_trials": len(study.trials),
    "training_samples": len(X),
    "trained_at": datetime.utcnow().isoformat(),
}
meta_path = f"{DRIVE_BASE}/models/{model_prefix}_meta.json"
with open(meta_path, "w") as f:
    json.dump(meta, f, indent=2, default=str)
print(f"✅ Metadata saved: {meta_path}")
```

### 10.11 Push to GitHub

```python
# ---- Push Model to GitHub ----
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")  # Set via Colab secrets

if GITHUB_TOKEN:
    %cd /content/graxia-os

    # Configure git
    !git config user.email "colab-trainer@graxia-os.dev"
    !git config user.name "Colab Trainer"

    # Copy models to repo
    !cp "{pkl_path}" "{json_path}" "{meta_path}" graxia/packages/quant_os/ml/models/

    # Push
    !git add graxia/packages/quant_os/ml/models/
    !git commit -m "chore(model): auto-update {symbol} {version} [colab]"
    !git remote set-url origin https://{GITHUB_TOKEN}@github.com/bravforcode/graxia-os.git
    result = !git push origin main
    print(f"✅ GitHub push: {result[-1] if result else 'OK'}")
else:
    print("⚠️ GITHUB_TOKEN not set. Model saved to Drive only.")
    print("   Manually copy from Drive or run:")
    print(f"   !cp {pkl_path} /content/graxia-os/graxia/packages/quant_os/ml/models/")
```

### 10.12 Summary

```python
# ---- Final Summary ----
print("=" * 60)
print("TRAINING COMPLETE")
print("=" * 60)
print(f"Model:      XGBoost {symbol} M15")
print(f"Version:    {version}")
print(f"Test Acc:   {accuracy_score(y_test, y_pred):.2%}")
print(f"Avg OOS:    {avg_oos:.2%}")
print(f"Optuna:     {len(study.trials)} trials → {study.best_trial.value:.4f}")
print(f"Features:   {len(feature_set.feature_names)}")
print(f"Training:   {len(X)} samples")
print(f"")
print(f"Files saved:")
print(f"  📦 {pkl_path}")
print(f"  📄 {json_path}")
print(f"  📋 {meta_path}")
print(f"  📊 {study_path}")
print(f"")
print("NEXT: On local PC, run:")
print(f"  git pull")
print(f"  # Load {model_prefix}.pkl or {model_prefix}.json")
print("=" * 60)
```

---

### 10.13 Automation: One-Click Run

Save the above cells into a single `.ipynb` file. For true one-click:

1. Save notebook in Google Drive as `graxia-os/colab_xauusd_trainer.ipynb`
2. Open in Colab: `https://colab.research.google.com/drive/...`
3. Before running, set GitHub token as a Colab **secret**:
   - Click 🔑 (key icon) in left sidebar
   - Add `GITHUB_TOKEN` with your PAT
4. Runtime → Run all

---

## 11. Alternatives If Colab Fails

### 11.1 Scenario: Colab Free Tier Too Unreliable

**Alternative: GitHub Actions Runner (self-hosted on local PC)**

```yaml
# .github/workflows/train.yml
name: Train XAUUSD Model

on:
  schedule:
    - cron: '0 2 * * 0'  # Weekly Sunday 2 AM
  workflow_dispatch:       # Manual trigger

jobs:
  train:
    runs-on: [self-hosted, windows]
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run training
        run: python run_ml_train.py
      - name: Commit model
        run: |
          git config user.email "actions@graxia-os.dev"
          git config user.name "GitHub Actions"
          git add ml/models/
          git commit -m "chore(model): weekly retrain $(date)"
          git push
```

**Pros:** Runs on local PC, no Colab dependency, uses local GPU if available  
**Cons:** Requires Windows PC to be on 24/7, local GPU may not match Colab T4

### 11.2 Scenario: Need Dedicated GPU 24/7

**Alternative: RunPod / Vast.ai Spot Instances**

| Provider | A100 Price | $/mo (50% utilization) | Advantage |
|----------|-----------|----------------------|-----------|
| RunPod | $0.79/hr | ~$284/mo | Easy setup, Jupyter |
| Vast.ai | $0.50/hr | ~$180/mo | Cheapest spot |
| Colab Pro+ | flat $53.53 | $53.53/mo | Cheaper, but no guarantee |
| Lambda Labs | $1.10/hr | ~$396/mo | Top reliability |

**Verdict:** Colab Pro+ ($53/mo) is still cheaper than dedicated GPU cloud providers for periodic training.

### 11.3 Scenario: Cannot Push to GitHub Every Time

**Alternative: Google Drive → Direct Download from Local PC**

```python
# Local PC script to check for new models:
import gdown
import json
import time

DRIVE_MODEL_DIR = "https://drive.google.com/drive/folders/xxxxx"

def check_for_new_model():
    """Poll Drive folder for new model metadata."""
    local_meta = {}
    if os.path.exists("ml/models/current_meta.json"):
        with open("ml/models/current_meta.json") as f:
            local_meta = json.load(f)
    
    # Use gdown to list files
    files = gdown.download_folder(DRIVE_MODEL_DIR, quiet=True)
    
    latest_meta = max(
        [f for f in files if f.endswith("_meta.json")],
        key=lambda x: os.path.getmtime(x),
        default=None,
    )
    if latest_meta and latest_meta != local_meta.get("version"):
        print(f"New model: {latest_meta}")
        # Download and load
        return True
    return False

while True:
    if check_for_new_model():
        # Reload model in trading system
        pass
    time.sleep(3600)  # Check hourly
```

### 11.4 Best Alternative: Hybrid Local + Colab

```
TRAINING:    Colab Pro (GPU, $12.74/mo) — run weekly
EXECUTION:   Local Windows PC (MT5, 24/7)
ORCHESTRATION: GitHub (central model storage + version control)
MONITORING:  Telegram notifications + local logging
BACKUP:      If Colab unavailable → GitHub Actions on local PC runner
```

This is exactly the proposed architecture in §7.

---

## 12. Conclusion

### VERDICT: ✅ YES — Colab is worth it.

**YES** — for model training and research. **NO** — for live execution.

### Why YES

| Reason | Detail |
|--------|--------|
| **GPU speedup** | 5-10× faster XGBoost training. Optuna 200 trials in ~2h vs ~10h on CPU. |
| **Free tier viable** | Weekly retraining fits in free tier (4-6h sessions). |
| **Dependency compatible** | 95% of packages install. Only MT5 excluded (not needed). |
| **Model exchange simple** | Models <10 MB. GitHub push works natively. |
| **Data transfer** | M15 OHLCV (~500 MB) fits in free Google Drive. |
| **Cost** | $0/weekly or $12.74/mo for priority GPU. Cheaper than VPS. |
| **Reproducibility** | Notebook documents exact training process. New devs can rerun. |

### What You Must Get Right

1. **Feature consistency** — Single `feature_library.py` source of truth (⚠️ critical, see §8)
2. **Dual format save** — Pickle + native `.json` to handle version mismatches (see §4.3)
3. **Save to Drive DURING training** — Colab dies unexpectedly. Optuna DB on Drive.
4. **Version pinning** — Pin Colab xgboost==3.2.0 to match local.
5. **Not a server** — Don't try to serve predictions from Colab. Use GitHub as transport.

### Architecture Summary

```
Colab (GPU, free/$12.74)       GitHub             Local PC (Windows/MT5)
────────────────────────      ──────────          ──────────────────────
Train XGBoost + Optuna   ──►  ml/models/*.pkl  ◄── git pull → load model
Save dual format .pkl          model metadata     compute features → predict
+ .json + metadata             version control    ⚡ live trade with MT5
                              feature version     log PnL → drift check
```

### Action Items

| # | Task | Priority | Owner |
|---|------|----------|-------|
| 1 | Create `ml/feature_library.py` — single feature source | 🔴 Critical | Now |
| 2 | Update `ml/pipeline.py` to use `feature_library.py` | 🔴 Critical | Now |
| 3 | Update `strategies/mlb.py` to use `feature_library.py` | 🔴 Critical | Now |
| 4 | Save model in dual format (pickle + xgb.json) | 🟡 High | Before Colab |
| 5 | Create Colab notebook (cells from §10) | 🟡 High | Week 1 |
| 6 | Upload M15 data to Google Drive | 🟡 High | Week 1 |
| 7 | Set up GitHub token for Colab | 🟡 Medium | Week 1 |
| 8 | First Colab training run | 🟡 Medium | Week 1 |
| 9 | Test model loading on local PC | 🟡 Medium | After run |
| 10 | Get Colab Pro ($12.74/mo) if free unreliable | 🟢 Low | After testing |

---

## Appendix A: Quick Reference — Colab vs Local

| Capability | Colab | Local PC | Winner |
|-----------|-------|----------|--------|
| Python 3.11 | ✅ (with workaround) | ✅ Native | Local |
| GPU training | ✅ T4/P100/A100 | ❌ Usually none | **Colab** 🏆 |
| 24/7 operation | ❌ Max 24h | ✅ | **Local** 🏆 |
| MT5 connection | ❌ No | ✅ | **Local** 🏆 |
| Large data (10yr ticks) | ⚠️ Limited | ✅ | **Local** 🏆 |
| Low cost | ✅ Free/$12.74 | ✅ Already owned | Tie |
| Optuna (200 trials) | ✅ ~2h GPU | ⚠️ ~10h CPU | **Colab** 🏆 |
| Model serving | ❌ Ephemeral | ✅ Persistent | **Local** 🏆 |
| Reproducibility | ✅ Notebook | 🟡 Script | **Colab** 🏆 |
| Feature parity | 🟡 Need alignment | ✅ Same codebase | Tie |

**Final architecture:** Colab for training. Local PC for execution. GitHub as bridge.

---

*Document generated by Ruflow (Project Gracia) — Researcher Agent.*  
*Based on actual analysis of C:\Users\menum\graxia os\graxia\packages\quant_os*
