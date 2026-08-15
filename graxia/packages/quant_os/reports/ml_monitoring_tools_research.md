# Production ML Monitoring & Drift Detection — Deep Research Report

**Date:** 2026-07-25
**Target System:** quant_os (Graxia OS)
**Status:** Research Complete

---

## Executive Summary

This report evaluates 7 production ML monitoring tools for use in a Python quant trading system. The key finding: **evidently + alibi-detect** provides the strongest open-source combination for trading, with NannyML offering unique value where ground truth is delayed. SageMaker Model Monitor is being **sunset (July 2026)** and should be avoided for new deployments.

| Tool | Stars | License | Best For | Trading Fit | Integration Effort |
|------|-------|---------|----------|-------------|-------------------|
| **Evidently** | 7.7k | Apache 2.0 | Drift detection, data quality, reporting | ⭐⭐⭐⭐⭐ | 2/5 |
| **NannyML** | 2.1k | Apache 2.0 | Performance estimation w/o ground truth | ⭐⭐⭐⭐ | 2/5 |
| **Alibi-Detect** | 2.5k | Apache 2.0 | Advanced drift/outlier algorithms (TF/PyTorch) | ⭐⭐⭐⭐⭐ | 3/5 |
| **Whylogs** | ~2k | Apache 2.0 | Data logging, statistical profiling, WhyLabs cloud | ⭐⭐⭐ | 2/5 |
| **Deepchecks** | ~3.5k | AGPL 3.0 | CI/CD validation, model testing suites | ⭐⭐⭐ | 3/5 |
| **Phoenix (Arize)** | ~9k | Elastic 2.0 | LLM observability, tracing, experiments | ⭐⭐ | 3/5 |
| **SageMaker Monitor** | N/A | AWS | Managed drift monitoring | ⭐ (sunsetting) | N/A |

---

## 1. Data Drift Detection Methods

### Statistical Tests (Univariate Drift)

| Method | Use Case | Available In |
|--------|----------|-------------|
| **Kolmogorov-Smirnov (KS)** | Compares CDFs of reference vs current distributions. Non-parametric. Best for continuous features. Sensitive to location shifts. | Evidently, Alibi-Detect, NannyML |
| **Population Stability Index (PSI)** | Industry standard in credit risk. Symmetric, interpretable. Thresholds: <0.1 (no shift), 0.1–0.25 (moderate), >0.25 (significant). | Evidently |
| **Wasserstein Distance** | Earth Mover's Distance. Measures cost of transforming one distribution to another. Better than KS for multimodal distributions. | Evidently, Alibi-Detect |
| **Maximum Mean Discrepancy (MMD)** | Kernel-based two-sample test. Detects any distributional difference (not just location). Can be computationally expensive. | Alibi-Detect (core), Evidently |
| **Jensen-Shannon Divergence** | Symmetrized KL-divergence. Bounded [0,1]. Good for comparing probability distributions. | NannyML, Evidently |
| **Cramér-von Mises** | Alternative to KS, often more powerful for detecting shifts in tails. | Alibi-Detect |
| **Chi-Squared** | For categorical features. Tests independence/homogeneity. | Evidently, Alibi-Detect |
| **Fisher's Exact Test** | Alternative to Chi² for small sample sizes. | Alibi-Detect |

### Multivariate Drift Detection

- **PCA Reconstruction Error** (NannyML): Projects data onto PCA basis from reference; monitors reconstruction error over time. Simple, interpretable.
- **MMD with learned kernels** (Alibi-Detect): Uses deep kernel learning for more powerful two-sample testing.
- **Classifier-based drift** (Alibi-Detect): Trains classifier to distinguish reference from current; accuracy > 0.5 indicates drift.

### Online/Streaming Drift Detection

- **Online MMD** (Alibi-Detect): Maintains sliding window, updates incrementally.
- **Online LSDD** (Alibi-Detect): Least-squares density difference with online updates.
- **ADWIN** (scikit-multiflow): Adaptive sliding window algorithm. Detects concept drift in streaming data.
- **DDM/EDDM** (scikit-multiflow): Drift Detection Method. Monitors error rate online.

### Trading-Specific Guidance

For quant_os, **Wasserstein distance** is recommended for continuous features (OHLCV data) because it captures multimodal regime shifts that KS would miss. **PSI** provides interpretable thresholds for downstream alerting. **MMD** is best for detecting joint distribution shifts across all features simultaneously.

---

## 2. Model Drift Detection

### Prediction Distribution Shift

Monitor the distribution of model outputs (predictions, scores) over time. When the output distribution changes while inputs remain stable, it suggests the model itself is degrading (e.g., due to stale parameters, upstream changes).

**Methods:**
- KS test on prediction scores
- Wasserstein on output distributions
- PSI on binned predictions

### Calibration Drift

For probability-output models (classification), calibration measures how well predicted probabilities match observed frequencies. Expected Calibration Error (ECE) tracks this over time:

```
ECE = Σ(|B_m|/n) × |accuracy(B_m) - confidence(B_m)|
```

Where B_m are probability bins. Available in Evidently.

### Performance Estimation Without Ground Truth

**NannyML CBPE (Confidence-Based Performance Estimation):**
- Uses model confidence scores to estimate performance metrics (ROC AUC, accuracy, etc.)
- Key insight: when models are well-calibrated, confidence correlates with correctness
- Works for **binary and multi-class classification**
- Minimum ~500 samples per chunk for reliable estimates

**NannyML DLE (Direct Loss Estimation):**
- Estimates regression metrics (RMSE, MAE, R²) without targets
- Trains a separate model to predict the loss value from features
- Requires sufficient feature variation to learn the loss function

**Why this matters for trading:** In quant finance, ground truth (actual PnL, true direction) is often delayed by hours to days. NannyML can estimate whether your model is degrading *before* you see the losses in your account.

---

## 3. Concept Drift (The PnL Killer)

### Market Regime Change Detection

Concept drift occurs when the relationship P(y|X) changes — the same feature values now predict different outcomes. This is the most dangerous type of drift in trading because it's invisible to feature-only monitoring.

**Detection Methods:**
- **Hidden Markov Models (HMMs):** Classic approach for regime detection. Models market states as latent variables.
- **Jump Models** (`jumpmodels`): Statistical Jump Model (JM), Continuous JM (CJM), Sparse JM (SJM). scikit-learn-compatible. `.predict_online()` for live use. Published research (Nystrup 2020, Aydınhan/Kolm/Mulvey/Shu 2024–2025).
- **Classifier uncertainty drift** (Alibi-Detect): Monitor model uncertainty; sudden increases suggest concept drift.
- **Spot-the-diff** (Alibi-Detect): Adaptively identifies regions where distributions differ most.
- **ADWIN on model residuals**: Slide adaptive window over prediction errors; expanding window = concept drift.
- **Chow test / CUSUM:** Classical econometric tests for structural breaks in time series.

### Trading Strategy

1. **Monitor feature drift** (Evidently/alibi-detect): What changed in the inputs?
2. **Monitor prediction drift** (NannyML): What changed in the outputs?
3. **Monitor PnL residuals**: The delta between expected and actual PnL
4. **Regime classifier overlay**: Train a regime detector (trending/ranging/crisis) and trigger different monitoring thresholds per regime.

---

## 4. Tool-by-Tool Deep Dive

### 4.1 Evidently AI (`evidentlyai/evidently`)

**Repo:** github.com/evidentlyai/evidently
**Stars:** 7.7k | **License:** Apache 2.0 | **40M+ downloads**
**Install:** `pip install evidently`

**Key Capabilities:**
- **100+ built-in metrics** for data quality, data drift, classification, regression, ranking, recommendations, LLM evals
- **Reports**: Compute and visualize evals. Export as HTML, JSON, Python dict, Jupyter inline.
- **Test Suites**: Add pass/fail conditions to any report. Auto-generate thresholds from reference data.
- **Monitoring UI**: Self-hosted dashboard (OSS) or Evidently Cloud. Visit `localhost:8000`.
- **Data Drift Presets**: `DataDriftPreset(method="psi")` — supports PSI, KS, Wasserstein, Jensen-Shannon, and more.
- **20+ statistical tests** and distance metrics for distribution comparison.
- **Generative AI support**: Text descriptors (sentiment, toxicity, length), LLM judges for RAG evaluation.
- **Custom metrics**: Python interface for defining your own evals.
- **Docker support**: Deploy monitoring service via Docker.

**Drift Detection Methods Supported:**
- Population Stability Index (PSI)
- Kolmogorov-Smirnov test
- Wasserstein distance
- Jensen-Shannon divergence
- Kullback-Leibler divergence
- And more (20+ total)

**Cloud (Evidently Cloud):**
- Generous free tier
- Extra features: dataset management, user management, alerting, no-code evals
- Managed monitoring dashboards

**Trading Fit:** ⭐⭐⭐⭐⭐
Best overall choice for quant_os. Covers data quality validation, all major drift tests, and has a monitoring dashboard. The Test Suites API is perfect for CI/CD-style checks before deploying strategy updates.

**Integration Effort:** 2/5 — `pip install evidently`, create DataFrame with reference + current, run preset, get results. ~5 lines of code for basic drift report.

---

### 4.2 NannyML (`NannyML/nannyml`)

**Repo:** github.com/NannyML/nannyml
**Stars:** 2.1k | **License:** Apache 2.0
**Install:** `pip install nannyml` (depends on LightGBM)

**Key Capabilities:**
- **CBPE (Confidence-Based Performance Estimation):** Estimate ROC AUC, accuracy, F1 *without ground truth labels*. This is NannyML's killer feature.
- **DLE (Direct Loss Estimation):** Estimate regression metrics (RMSE, MAE, R²) without targets.
- **Univariate drift detection:** KS, Chi², Jensen-Shannon, L-infinity, Wasserstein, Hellinger distance, and more.
- **Multivariate drift detection:** PCA-based data reconstruction error. Single metric to monitor joint distribution shift.
- **Model output drift:** Same statistical tests applied to prediction distributions.
- **Target distribution drift:** When ground truth eventually arrives, monitor target drift.
- **Intelligent alerting:** Links data drift alerts to estimated performance impact. Ranker prioritizes alerts by severity.
- **Interactive visualizations:** Joy plots, stacked distribution charts, drift-over-time line charts.
- **Docker deployment:** `docker run nannyml/nannyml nml run`

**Why It's Different:**
NannyML's core innovation is performance estimation *without waiting for ground truth*. In trading, you might not know the true PnL for hours (or the true direction until the bar closes). CBPE/DLE gives you an early warning system.

**Trading Fit:** ⭐⭐⭐⭐
If your quant_os models have delayed ground truth (common in trading), NannyML's CBPE/DLE fills a gap no other open-source tool addresses. Combine with Evidently for a complete picture.

**Integration Effort:** 2/5 — Simple API: `.fit()`, `.estimate()`, `.compare()`. Requires LightGBM dependency.

---

### 4.3 Alibi-Detect (`SeldonIO/alibi-detect`)

**Repo:** github.com/SeldonIO/alibi-detect
**Stars:** 2.5k | **License:** Apache 2.0
**Install:** `pip install alibi-detect` (TF/PyTorch backends optional)

**Key Capabilities — The Most Comprehensive Algorithm Library:**

**Drift Detection (13 algorithms):**
| Detector | Modalities | Online? | Trading Use |
|----------|-----------|---------|-------------|
| Kolmogorov-Smirnov | Tabular, Image, TS, Text | ❌ | Feature-level drift |
| Cramér-von Mises | Tabular, Image, TS, Text | ❌ | Feature-level (better tails) |
| Fisher's Exact Test | Tabular, TS | ❌ | Categorical features |
| Maximum Mean Discrepancy (MMD) | Tabular, Image, TS, Text | ❌ | Multivariate drift |
| Learned Kernel MMD | Tabular, Image, TS, Text | ❌ | High-dim drift |
| Context-aware MMD | Tabular, TS, Text | ❌ | Conditional drift |
| Least-Squares Density Difference | Tabular, Image, TS, Text | ❌ | Density-based |
| Chi-Squared | Tabular, Image, TS | ❌ | Categorical |
| Mixed-type tabular | Tabular | ❌ | All feature types |
| Classifier drift | Tabular, Image, TS, Text | ❌ | Concept drift |
| Spot-the-diff | Tabular, Image, TS, Text | ❌ | Localized drift regions |
| Classifier/Regressor Uncertainty | Tabular, Image, TS | ❌ | Model uncertainty drift |
| **Online MMD** | Tabular, Image | ✅ | Streaming drift |
| **Online LSDD** | Tabular, Image | ✅ | Streaming drift |

**Outlier Detection (10 algorithms):**
Isolation Forest, Mahalanobis Distance, AE, VAE, AEGMM, VAEGMM, Likelihood Ratios, Prophet (time series), Spectral Residual (time series), Seq2Seq (time series).

**Adversarial Detection (2 algorithms):**
Adversarial AE, Model Distillation.

**Backend Support:**
- TensorFlow backend
- PyTorch backend
- KeOps backend (GPU-accelerated kernel operations)

**Preprocessing Pipeline:**
- Hidden layer outputs from TF/PyTorch models
- Pretrained text embeddings (HuggingFace transformers)
- Random encoders for dimensionality reduction

**Integrations:**
- Seldon Core (Kubernetes model deployment)
- KFServing (Kubeflow model serving)

**Trading Fit:** ⭐⭐⭐⭐⭐
The best choice if you need sophisticated drift algorithms. Online MMD and online LSDD are ideal for streaming market data. The uncertainty drift detectors directly address concept drift. Classification drift is perfect for directional prediction models.

**Integration Effort:** 3/5 — More complex API than Evidently/NannyML. Requires understanding of backends (TF vs PyTorch vs KeOps). But the algorithm library is unmatched.

---

### 4.4 Whylogs (`whylabs/whylogs`)

**Repo:** github.com/whylabs/whylogs
**Stars:** ~2k | **License:** Apache 2.0
**Install:** `pip install whylogs`

**Key Capabilities:**
- **Data logging via statistical profiles:** Generates compact, mergeable summaries of datasets instead of storing raw data.
- **Profiles are mergeable:** Enable logging for distributed and streaming systems. Combine profiles across time windows.
- **Data constraints:** Define expectations (ranges, types, formats). Fail CI/CD if constraints violated.
- **Profile visualizer:** Interactive drift reports and distribution comparison in Jupyter.
- **WhyLabs platform integration:** Upload profiles to WhyLabs SaaS for managed monitoring, alerting, and dashboards.

**WhyLabs Platform:**
- Free Starter tier (no credit card required)
- Managed monitoring with automatic drift detection
- Data quality and data change monitoring
- Privacy-preserving: profiles are statistical summaries, not raw data

**Trading Fit:** ⭐⭐⭐
Excellent for data pipeline monitoring (checking feature freshness, missing values, ranges). Less strong on model-specific drift detection than Evidently or Alibi-Detect. Best used as a complement for data quality enforcement.

**Integration Effort:** 2/5 — `why.log(df)` generates a profile. Write to WhyLabs with a few lines. Very low friction.

---

### 4.5 Deepchecks (`deepchecks/deepchecks`)

**Repo:** github.com/deepchecks/deepchecks
**Stars:** ~3.5k | **License:** AGPL 3.0 (OSS) + Commercial (EE features)
**Install:** `pip install deepchecks`

**Key Capabilities:**
- **Testing (OSS):** Built-in checks for tabular, NLP, and vision data. Covers data integrity, data drift, model performance, train-test validation.
- **CI/CD Integration:** Run test suites in CI pipelines. HTML reports, JSON output, pass/fail conditions.
- **Monitoring (OSS + Commercial):** Single-model monitoring via Docker. Premium features (multi-model, advanced alerting) require commercial license.
- **Suite-based approach:** Pre-defined suites like `model_evaluation()`, `data_integrity()`, `train_test_validation()`.
- **Custom checks:** Extensible framework for writing your own checks.

**OSS vs Commercial:**
- Testing library: Fully open source (AGPL)
- Monitoring: OSS version supports single model. Enterprise (EE) for multi-model, advanced features.
- Commercial license required for EE features under `backend/deepchecks_monitoring/ee/`

**Trading Fit:** ⭐⭐⭐
Strong for CI/CD validation of models before deployment. The monitoring component is less mature than Evidently. AGPL license may be restrictive depending on deployment model.

**Integration Effort:** 3/5 — Requires understanding Suite/Check concepts. Docker for monitoring.

---

### 4.6 Phoenix / Arize AI (`Arize-ai/phoenix`)

**Repo:** github.com/Arize-ai/phoenix
**Stars:** ~9k | **License:** Elastic License 2.0
**Install:** `pip install arize-phoenix`

**Key Capabilities:**
- **Tracing:** OpenTelemetry-based LLM application tracing. Auto-instrument 20+ frameworks.
- **Evaluation:** LLM-as-a-judge evaluations for RAG relevance, answer quality, retrieval quality.
- **Datasets & Experiments:** Version datasets, track prompt/LLM changes, A/B test prompts.
- **Playground:** Optimize prompts, compare models, replay traced calls.
- **Prompt Management:** Version control, tagging, experimentation for prompts.
- **MCP Server:** Connect Claude Code, Cursor, etc. to Phoenix for trace/debug queries.
- **PXI (Phoenix Intelligence):** AI engineering agent built into Phoenix.

**Primary Focus:** LLM/Generative AI observability. The tooling is heavily oriented toward RAG systems, chatbot evaluation, and prompt engineering.

**Trading Fit:** ⭐⭐
Designed for LLM applications, not classical ML/tabular models. If quant_os uses LLMs for sentiment analysis or report generation, Phoenix is relevant. For core ML model monitoring, Evidently/Alibi-Detect/NannyML are better fits.

**Integration Effort:** 3/5 — Easy to get started (`uvx arize-phoenix serve`), but tracing setup requires framework-specific instrumentation.

---

### 4.7 Amazon SageMaker Model Monitor

**Status:** ⚠️ **SUNSETTING — New customer access closing July 30, 2026**

**Key Facts:**
- Monitors data quality, model quality, bias drift, and feature attribution drift.
- Works with SageMaker real-time endpoints, batch transform jobs, async batch jobs.
- Prebuilt containers for no-code monitoring.
- CloudWatch integration for alerts.
- **Only supports tabular data** for metrics computation.
- **Single model per endpoint** only.
- **Does NOT support multi-model endpoints** or individual containers in inference pipelines.

**Verdict:** Do NOT use for new deployments. AWS is closing new customer access and not adding new features. Existing customers can continue but should plan migration.

---

## 5. Recommended Stack for quant_os

### Tier 1: Core Monitoring

```
pip install evidently alibi-detect nannyml
```

| Component | Tool | Purpose |
|-----------|------|---------|
| Data drift detection | Evidently | PSI, KS, Wasserstein reports. HTML dashboards. |
| Advanced drift algorithms | Alibi-Detect | MMD, online drift, classifier drift for streaming data. |
| Performance estimation | NannyML | CBPE/DLE for pre-PnL model degradation alerts. |
| Data quality | Evidently + Whylogs | Missing values, range checks, feature freshness. |

### Tier 2: Operational Integration

| Component | Tool | Purpose |
|-----------|------|---------|
| CI/CD validation | Deepchecks | Run test suites before deploying strategy updates. |
| Alerting | Prometheus + Grafana | Export drift metrics to Prometheus, visualize in Grafana. |
| Alert routing | Alertmanager/PagerDuty | Escalation policies for critical drift alerts. |

### Tier 3: Cloud/Managed (Optional)

| Component | Tool | Purpose |
|-----------|------|---------|
| Managed monitoring | Evidently Cloud or WhyLabs | Offload dashboard hosting if self-hosting is too heavy. |
| LLM monitoring | Phoenix (if using LLMs) | Trace LLM calls for sentiment/signal generation. |

---

## 6. Alerting Best Practices

### Threshold Setting
1. **Reference-based:** Auto-generate thresholds from reference data statistics (Evidently supports this).
2. **Percentile-based:** Alert when drift metric exceeds 95th/99th percentile of historical drift values.
3. **Regime-aware:** Different thresholds for different market regimes (volatile regimes have naturally higher drift).
4. **Compound signals:** Don't alert on single-feature drift alone. Require multiple features drifting + performance degradation signal.

### Escalation Policy
1. **Level 1 (Info):** Single feature drift detected. Log, no alert. Investigate at next review.
2. **Level 2 (Warning):** Multiple features drifting or single critical feature. Slack notification.
3. **Level 3 (Critical):** Performance estimation (NannyML) shows degradation. PagerDuty alert. Human investigation required.
4. **Level 4 (Emergency):** Multiple signals + PnL degradation. Auto-pause trading. Immediate human intervention.

### Avoiding Alert Fatigue
- **NannyML's key advantage:** Only alert when drift actually impacts performance, not on every statistical anomaly.
- **Hysteresis:** Require drift to persist for N consecutive windows before alerting.
- **Rate limiting:** Maximum 1 critical alert per hour, 1 warning per 15 minutes.
- **Correlation filtering:** Group correlated features; alert once per group, not per feature.

---

## 7. Retraining Triggers

### Auto-Retrain Conditions (with human override)
1. **Drift threshold exceeded** AND **performance estimate degraded** → trigger retrain pipeline.
2. **Scheduled retraining** (e.g., weekly) as baseline. Drift-triggered as override.
3. **Calendar-based:** Retrain after FOMC, NFP, CPI releases. Known regime-shift catalysts.

### Human-in-the-Loop Gates
- All auto-retrained models go through **shadow deployment** (run in parallel, no real money).
- **A/B test** shadow model vs production for N days before promotion.
- **Witness/attestation**: New model must pass Deepchecks test suite before deployment.

### Online Learning Considerations
- Online learning (incremental updates) is **dangerous** in trading: feedback loops, adversarial markets.
- Prefer **batch retraining** with holdout validation.
- If online learning is used, combine with **anomaly detection** on weight updates.

---

## 8. Feature Monitoring

### Detecting Broken Pipelines
- **Missing value rate** over time: Sudden spike = pipeline break.
- **Stale data detection**: Compare last update timestamp to expected frequency.
- **Range violations**: Feature values outside historical min/max.
- **New categorical values**: Unseen categories appearing in production.
- **Distribution shift in upstream sources**: Monitor data at ingestion point, not just at model input.

### Implementation with Whylogs
```python
# Define constraints
from whylogs.core.constraints.factories import greater_than_number, smaller_than_number, no_missing_values

builder.add_constraint(no_missing_values(column_name="close"))
builder.add_constraint(greater_than_number(column_name="volume", number=0))
```

---

## 9. Prediction Monitoring

### Output Distribution
- Monitor prediction mean, variance, quantiles over time.
- Sudden shifts in mean prediction → possible regime change.
- Sudden increase in prediction variance → model uncertainty increasing.

### Confidence Calibration
- For probability-output models, monitor Expected Calibration Error (ECE).
- Recalibrate using Platt scaling or isotonic regression when ECE exceeds threshold.

---

## 10. PnL Attribution

### Decomposing PnL Changes
```
ΔPnL = ΔPnL(drift) + ΔPnL(noise) + ΔPnL(model_degradation)
```

**Approach:**
1. **Counterfactual simulation:** Re-run backtest with drifted features vs reference features. Difference = drift contribution.
2. **Shapley values:** Attribute PnL changes to individual features. Spikes in attribution → check that feature's data pipeline.
3. **Residual monitoring:** Track PnL - expected PnL (from model). Increasing residual variance = model degradation.
4. **Walk-forward validation:** Run walk-forward test on recent data. Compare walk-forward Sharpe to production Sharpe.

### Signal-Noise Decomposition
- **Bootstrap confidence intervals:** Resample returns to estimate how much PnL variation is noise.
- **Permutation tests:** Shuffle prediction order to estimate noise floor of strategy.

---

## 11. Implementation Roadmap for quant_os

### Phase 1: Baseline Drift Monitoring (Week 1-2)
1. Install `evidently` + `alibi-detect`
2. Integrate with existing `drift_monitor.py`
3. Set up daily drift reports (HTML/JSON)
4. Define reference windows (last 30 trading days)
5. Export metrics to Prometheus/Grafana

### Phase 2: Performance Estimation (Week 3-4)
1. Install `nannyml`
2. Implement CBPE/DLE for key strategy models
3. Wire performance estimates to alerting pipeline
4. Validate estimates against realized performance

### Phase 3: Automated Response (Week 5-6)
1. Define alert thresholds and escalation policies
2. Implement shadow deployment for auto-retrained models
3. Deepchecks test suite for model validation
4. PnL attribution dashboard

### Phase 4: Production Hardening (Week 7-8)
1. Docker deployment of monitoring service
2. Persistent metric storage (PostgreSQL or S3)
3. Runbook documentation
4. Chaos engineering: simulate feature pipeline failures

---

## Appendix: Quick Install Commands

```bash
# Core monitoring
pip install evidently alibi-detect nannyml

# Data logging
pip install whylogs

# CI/CD validation
pip install deepchecks

# Streaming drift (optional)
pip install scikit-multiflow  # ADWIN, DDM, EDDM

# Jump models for regime detection
pip install jumpmodels

# Visualization
pip install evidently[viz] whylogs[viz]
```

---

## References

- Evidently: https://github.com/evidentlyai/evidently | docs: https://docs.evidentlyai.com
- NannyML: https://github.com/NannyML/nannyml | docs: https://nannyml.readthedocs.io
- Alibi-Detect: https://github.com/SeldonIO/alibi-detect | docs: https://docs.seldon.io/projects/alibi-detect
- Whylogs: https://github.com/whylabs/whylogs | docs: https://whylogs.readthedocs.io
- Deepchecks: https://github.com/deepchecks/deepchecks | docs: https://docs.deepchecks.com
- Phoenix: https://github.com/Arize-ai/phoenix | docs: https://arize.com/docs/phoenix
- SageMaker Model Monitor: https://docs.aws.amazon.com/sagemaker/latest/dg/model-monitor.html (⚠️ sunsetting)
