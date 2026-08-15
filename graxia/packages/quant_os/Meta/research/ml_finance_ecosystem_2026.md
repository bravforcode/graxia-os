# ML/AI Ecosystem for Financial Time Series — Deep Research (July 2026)

> **Researcher**: Ruflow researcher agent  
> **Date**: 2026-07-25  
> **Scope**: Every useful Python library for algorithmic trading ML across 8 categories  
> **Evidence Quality**: A (verified PyPI/GitHub live) / B (known, last checked <6mo) / C (community, indirect)

---

## 📊 Existing quant_os Dependencies

quant_os `pyproject.toml` already includes in its `[ml]` optional deps:

```toml
ml = ["scikit-learn>=1.3", "xgboost>=2.0"]
```

quant_os already has 50+ strategy modules including `ensemble.py`, `mlmr.py`, `mlb.py`, `walk_forward.py`, `factor_signals.py`, `vol_regime_sizing.py`, and `momentum_factor_rotation.py` — strong foundation for ML integration.

---

## 1. Best ML Libraries for Financial Time Series

### Gradient Boosting (Tabular King)
| Library | URL | What | Evidence |
|---------|-----|------|----------|
| **XGBoost** | https://github.com/dmlc/xgboost | Gradient boosting, GPU-accelerated, built-in time-series CV. Already in quant_os `[ml]` deps. | A |
| **LightGBM** | https://github.com/microsoft/LightGBM | Leaf-wise boosting, faster than XGBoost on large data, native categorical support. | A |
| **CatBoost** | https://github.com/catboost/catboost | Ordered boosting avoids target leakage, excellent for financial features with many categories (sector, exchange). | A |
| **TabNet** | https://github.com/dreamquark-ai/tabnet | PyTorch deep NN for tabular data, attention-based feature selection — good for catching non-linear interactions. | A |

### Deep Learning for Time Series
| Library | URL | What | Evidence |
|---------|-----|------|----------|
| **PyTorch Forecasting** | https://github.com/sktime/pytorch-forecasting | N-BEATS, TFT (Temporal Fusion Transformer), NHiTS, DeepAR — state-of-the-art deep TS models with built-in interpretability. | A |
| **Darts** | https://github.com/unit8co/darts | User-friendly TS forecasting + anomaly detection. Supports N-BEATS, TFT, Transformer, NHiTS, LightGBM, CatBoost, Prophet, ARIMA — all via unified API. | A |
| **NeuralForecast** | https://github.com/Nixtla/neuralforecast | N-BEATS, NHiTS, TFT, TimesNet, PatchTST, Informer, Autoformer — focused on neural methods, GPU-accelerated. | A |
| **StatsForecast** | https://github.com/Nixtla/statsforecast | ARIMA, ETS, Theta, CES, MSTL — lightning-fast statistical models. 100x faster than statsmodels. | A |
| **MLForecast** | https://github.com/Nixtla/mlforecast | Scalable ML-based forecasting — wraps XGBoost, LightGBM, Scikit-learn for time series with proper lags, rolling windows, cross-validation. **v1.1.0 (July 2026)**. | A |
| **sktime** | https://github.com/sktime/sktime | Unified sklearn-compatible API for time series — forecasting, classification, regression, clustering. **v1.0.1 (June 2026)**. | A |

### RL for Trading
| Library | URL | What | Evidence |
|---------|-----|------|----------|
| **FinRL** | https://github.com/AI4Finance-Foundation/FinRL | Full RL pipeline for financial trading — gym-style envs, DRL agents (PPO, DDPG, SAC, TD3), backtesting integration. | A |
| **FinGPT** | https://github.com/AI4Finance-Foundation/FinGPT | Open-source financial LLMs — sentiment analysis, market prediction, robo-advisor. 14k+ stars. | A |

### LLM + Finance (2024-2026)
| Library | URL | What | Evidence |
|---------|-----|------|----------|
| **Qlib** | https://github.com/microsoft/qlib | Microsoft's AI-oriented quant platform. Now has **RD-Agent** to automate R&D. Supports supervised, market dynamics, and RL modeling. | A |
| **FinGPT** | see above | Fine-tuned LLaMA/Bloom on financial data for sentiment, news analysis, report generation. | A |

---

## 2. Feature Engineering Tools for OHLCV Data

| Library | URL | What | Evidence |
|---------|-----|------|----------|
| **pandas-ta** | https://github.com/twopirllc/pandas-ta | 130+ technical indicators as pandas DataFrame extensions. `.ta` accessor. Latest: **v0.4.71b0 (Sep 2025)**. | A |
| **ta-lib** | https://github.com/ta-lib/ta-lib-python | C-based technical analysis — 200+ indicators. Performance king for real-time. | A |
| **tsfresh** | https://github.com/blue-yonder/tsfresh | Automated feature extraction from time series — 1200+ features, statistical hypothesis testing for relevance. **v0.21.2 (May 2026)**. | A |
| **featuretools** | https://github.com/alteryx/featuretools | Automated deep feature synthesis — creates features across relational data (e.g., multiple assets, sectors). **v1.31.0 (May 2024)**. | A |
| **mlfinlab** | https://github.com/hudson-and-thames/mlfinlab | **Marcos López de Prado's tools**: fractional differencing, microstructure features (VPIN, tick rule), labeling (triple-barrier, trend-scanning), bet-sizes, bagging. **Gold standard for quant finance ML.** | A |

### quant_os Integration
- `mlfinlab` → Use triple-barrier labeling for strategy signals, fractional differencing for stationarity, and bet-sizing (de Prado's methods are directly applicable to `strategies/mlmr.py`, `strategies/mlb.py`)
- `tsfresh` → Auto-extract features from OHLCV candles, TA indicators, orderbook depth
- `pandas-ta` → Replace hand-coded indicators across `strategies/factor_signals.py`

---

## 3. Regime Detection Methods

### Libraries & Techniques
| Tool | URL | What | Evidence |
|------|-----|------|----------|
| **hmmlearn** | https://github.com/hmmlearn/hmmlearn | Hidden Markov Models with sklearn-compatible API. GaussianHMM, GMMHMM, MultinomialHMM. **v0.3.3 (Oct 2024)**. | A |
| **sktime** | (see above) | Time series clustering: TimeSeriesKMeans, TimeSeriesKShape — directly cluster market regimes. | A |
| **statsmodels** | https://www.statsmodels.org | Markov switching dynamic regression (`statsmodels.tsa.MarkovRegression`) — probabilistic regime transitions with macro variables. | A |
| **pyRMT** | https://github.com/GGiecold/pyRMT | Random Matrix Theory for market regime detection — eigenvalue analysis of correlation matrices. | B |
| **TrendScanner** (mlfinlab) | (see above) | de Prado's trend-scanning labels — identifies structural breaks and regime shifts. | A |

### Techniques
- **HMM/Gaussian HMM**: Classic 2-3 state (bull/bear/sideways) classification on returns + volatility
- **Markov Switching**: Include macro factors (VIX, yield curve, credit spreads) as exogenous regressors
- **K-Means / K-Shape**: Cluster on rolling windows of returns, vol, correlation structure
- **PCA + eigenvalue**: Detect regime shifts via correlation matrix eigenvalue dynamics (Random Matrix Theory)
- **Deep regime models**: Temporal Fusion Transformer (TFT) learns regime transitions implicitly via attention

### quant_os Integration
- Connect `hmmlearn` to `strategies/vol_regime_sizing.py` and `strategies/macro_regime_mr.py`
- Build a `core/regime_detector.py` module wrapping HMM + Markov switching

---

## 4. Walk-Forward Validation Best Practices

### Libraries & Methods
| Library | URL | What | Evidence |
|---------|-----|------|----------|
| **mlfinlab** | (see above) | Purged K-Fold CV, embargo, combinatorial purged CV — **de Prado's exact implementation**. | A |
| **scikit-learn** `TimeSeriesSplit` | (already in deps) | Basic expanding-window split — good start, no purging. | A |
| **vectorbt** | https://github.com/polakowo/vectorbt | Built-in walk-forward optimization with hyperparameter sweeps. | A |
| **backtesting.py** | https://github.com/kernc/backtesting.py | Simple walk-forward backtesting with optimization heatmaps. | B |

### Key Concepts (de Prado, *Advances in Financial ML*, Ch. 7 & 11-13)
1. **Purged K-Fold**: Remove overlapping labels between train/test folds
2. **Embargo**: Gap between training end and testing start to avoid information leakage from overlapping return windows
3. **Combinatorial Purged CV**: For small datasets — generate many train/test splits by combinatorially walking forward
4. **Deflated Sharpe Ratio (DSR)**: Account for multiple testing when optimizing parameters across many folds
5. **Probabilistic Sharpe Ratio (PSR)**: Test whether estimated Sharpe is statistically significant

### quant_os Implementation
- `strategies/walk_forward.py` already exists — extend with PurgedCV from mlfinlab
- Build `validation/purged_cv.py` wrapping mlfinlab's `PurgedKFold`

---

## 5. Anomaly Detection for Market Data

| Library | URL | What | Evidence |
|---------|-----|------|----------|
| **PyOD** | https://github.com/yzhao062/pyod | **61 detectors** including Isolation Forest, LOF, AutoEncoder, VAE, DeepSVDD, COPOD, ECOD. **v3.6.2 (Jul 2026)**. New: ADEngine orchestration + agentic workflow. | A |
| **scikit-learn** | (already in deps) | IsolationForest, LocalOutlierFactor, OneClassSVM, EllipticEnvelope. | A |
| **Darts** | (see above) | Built-in anomaly detection scorers + models (autoencoders, forecasting-error-based). | A |
| **Alibi Detect** | https://github.com/SeldonIO/alibi-detect | Drift detection, outlier detection, adversarial detection — good for detecting distribution shift in live trading. | B |

### Techniques
| Method | Use Case | Strength |
|--------|----------|----------|
| **Isolation Forest** | Flash crash / fat-finger detection | Fast, interpretable, no need for labeled anomalies |
| **LOF (Local Outlier Factor)** | Unusual volume/price patterns | Density-based, finds local anomalies |
| **Autoencoder (AE/VAE)** | Multi-asset anomaly detection | Learns normal patterns, flags reconstruction error spikes |
| **COPOD** | Copula-based outlier detection | Parameter-free, works on high-dim financial correlation data |
| **ECOD** | Empirical CDF outlier detection | Ultra-fast, interpretable per-feature scores |
| **Drift Detection (Alibi)** | Live model decay detection | Catches regime shifts as "concept drift" |

### quant_os Integration
- PyOD's `IsolationForest` for pre-trade anomaly gating in `risk/` module
- Darts' anomaly scorers for live data quality monitoring
- Alibi Detect for detecting when ML models go stale (concept drift)

---

## 6. Model Interpretability Tools

| Library | URL | What | Evidence |
|---------|-----|------|----------|
| **SHAP** | https://github.com/shap/shap | Game-theoretic feature attribution (Shapley values). Works with XGBoost, LightGBM, CatBoost, sklearn, PyTorch, TF. Waterfall, beeswarm, dependence plots. | A |
| **LIME** | https://github.com/marcotcr/lime | Local interpretable model-agnostic explanations. | A |
| **eli5** | https://github.com/TeamHG-Memex/eli5 | Inspect sklearn model weights, feature permutation importance. | B |
| **Captum** | https://github.com/pytorch/captum | PyTorch model interpretability — integrated gradients, DeepLIFT, GradCAM. | A |
| **treeinterpreter** | https://github.com/andosa/treeinterpreter | Decompose tree model predictions into bias + feature contributions. | B |
| **feature_engine** | https://github.com/feature-engine/feature_engine | Feature selection methods (DropConstant, DropCorrelated, SmartCorrelation, RecursiveFeatureElimination). | A |

### Financial-Specific
- **TFT attention weights**: PyTorch Forecasting's TFT has built-in variable selection + attention — see *which* features drive predictions at *which* time steps
- **N-BEATS interpretability**: Decomposes forecasts into trend + seasonality components
- **SHAP force plots**: Explain individual trade signals to compliance/regulators
- **Permutation importance with purged CV**: mlfinlab provides purged feature importance (avoids leakage)

---

## 7. Hyperparameter Optimization

| Library | URL | What | Evidence |
|---------|-----|------|----------|
| **Optuna** | https://github.com/optuna/optuna | Define-by-run, pruning, visualization dashboard, built-in integration with XGBoost/LightGBM/CatBoost/sklearn/PyTorch. **Industry standard.** | A |
| **Hyperopt** | https://github.com/hyperopt/hyperopt | Bayesian optimization (TPE), simpler API. Used by mlfinlab. | A |
| **Ray Tune** | https://github.com/ray-project/ray | Distributed HPO, scales across GPUs/nodes. Integrates with Optuna, Hyperopt, etc. Good for large parameter sweeps. | A |
| **FLAML** | https://github.com/microsoft/FLAML | Microsoft's fast AutoML — finds good models quickly with low budget. | A |
| **scikit-optimize** | https://github.com/scikit-optimize/scikit-optimize | Gaussian process-based Bayesian optimization, sklearn API. | B |

### Financial-Specific Considerations
- **Walk-forward HPO**: Optimize on purged train folds, evaluate on embargoed test — NOT random CV
- **Optuna with TimeSeriesSplit**: Use `optuna.integration.OptunaSearchCV` + `TimeSeriesSplit`
- **Multi-objective**: Optimize Sharpe + max drawdown simultaneously via Optuna multi-objective (MOTPE)
- **Early stopping / pruning**: Optuna's `MedianPruner` stops unpromising trials early → saves compute
- **Deflated Sharpe**: Use DSR/PSR as objective, not raw Sharpe (de Prado)

---

## 8. Ensemble Methods for Financial Data

### Libraries
| Library | URL | What | Evidence |
|---------|-----|------|----------|
| **mlfinlab** | (see above) | Bagging with purged sequential bootstrapping — de Prado's method for time series ensemble. | A |
| **scikit-learn** | (already in deps) | VotingClassifier, StackingClassifier, BaggingClassifier, RandomForest, GradientBoosting. | A |
| **combo** | https://github.com/yzhao062/combo | Ensemble of anomaly detectors — combines PyOD detectors for consensus-based anomaly scores. | A |
| **vecstack** | https://github.com/vecxoz/vecstack | Stacking for sklearn models with out-of-fold predictions. | B |

### Techniques
| Method | Why for Finance | Implementation |
|--------|-----------------|----------------|
| **Purged Bagging** (de Prado) | Avoids overlapping samples across bags — standard bagging leaks in time series | `mlfinlab.ensemble.SequentialBootstrappedBagging` |
| **Stacking** | Combine signals from different strategies (trend, mean-reversion, carry) | L2 meta-model over base strategy predictions |
| **Voting (soft/hard)** | Consensus across ML models (XGBoost + LightGBM + CatBoost + TabNet) | sklearn `VotingClassifier` |
| **Dynamic Weighting** | Adjust ensemble weights based on recent performance (rolling Sharpe of each model) | Custom implementation |
| **Conformal Prediction** | Prediction intervals with coverage guarantee — know when ensemble is uncertain | `MAPIE` library |

### quant_os Integration
- `strategies/ensemble.py` already exists — extend with mlfinlab's purged bagging
- Build `strategies/meta_ensemble.py` combining signals from momentum, mean-reversion, and carry strategies via stacking

---

## 9. Performance, Backtesting & Factor Analysis

| Library | URL | What | Evidence |
|---------|-----|------|----------|
| **quantstats** | https://github.com/ranaroussi/quantstats | Tearsheet reports (Sharpe, drawdowns, monthly returns, rolling stats). HTML output. **v0.0.81 (Jan 2026)**. | A |
| **pyfolio** | https://github.com/quantopian/pyfolio | Portfolio risk/return tear sheets. **Last release 2019** — use quantstats instead. | C |
| **alphalens** | https://github.com/quantopian/alphalens | Factor analysis: IC analysis, quantile returns, turnover, factor auto-correlation. Still maintained by community fork (`stefan-jansen/alphalens-reloaded`). | A |
| **vectorbt** | https://github.com/polakowo/vectorbt | **Vectorized backtesting** — test 1000s of strategies simultaneously. Built-in optimization, indicator generation, plotting. | A |
| **zipline-reloaded** | https://github.com/stefan-jansen/zipline-reloaded | Event-driven backtesting framework. Maintained fork of Quantopian's Zipline. | A |
| **backtesting.py** | https://github.com/kernc/backtesting.py | Interactive backtesting with browser-based charts. Good for quick prototyping. | B |
| **bt (backtest)** | https://github.com/pmorissette/bt | Flexible backtesting for portfolio strategies — tree-structured Algo-based logic. | B |
| **empyrical** | https://github.com/quantopian/empyrical | Common financial risk metrics (Sharpe, Sortino, Calmar, omega, max drawdown). Used by pyfolio. | B |

---

## 10. New & Emerging (2024-2026)

| Library | URL | What | Year |
|---------|-----|------|------|
| **PyOD v3.6** | https://github.com/yzhao062/pyod | 61 detectors, ADEngine orchestration, agentic workflow for AI agents | 2026 |
| **sktime v1.0** | https://github.com/sktime/sktime | Stable v1.0 with full sklearn compatibility for TS | 2026 |
| **MLForecast v1.1** | https://github.com/Nixtla/mlforecast | Scalable ML forecasting with proper time-series CV | 2026 |
| **Darts** | (see above) | Now supports Diffusion models for probabilistic forecasting | 2025-2026 |
| **timeseriesAI/tsai** | https://github.com/timeseriesAI/tsai | Deep learning for time series classification/regression — InceptionTime, TST, XCM, OmniScaleCNN | 2024 |
| **NeuralProphet** | https://github.com/ourownstory/neural_prophet | Prophet + neural networks, better for financial data with seasonality | 2024 |
| **PatchTST** | (in NeuralForecast) | Patch-based transformer — SOTA on long-horizon financial forecasting | 2023-2024 |
| **TimesNet** | (in NeuralForecast) | 2D convolution on times series — captures intra-period and inter-period variations | 2023-2024 |
| **Lag-Llama** | https://github.com/time-series-foundation-models/lag-llama | Foundation model for time series — zero-shot forecasting | 2024 |
| **Chronos** | https://github.com/amazon-science/chronos-forecasting | Amazon's pretrained TS foundation model (T5-based) | 2024 |
| **MOIRA** | https://github.com/SalesforceAIResearch/moirai | Salesforce's unified TS forecasting foundation model | 2024 |
| **TimesFM** | https://github.com/google-research/timesfm | Google's decoder-only foundation model for TS | 2024 |

---

## 🔧 Recommended quant_os Integration Roadmap

### Phase 1 — Foundation (Low Effort, High Impact)
1. **Add to `ml` optional deps**: `lightgbm`, `catboost`, `shap`, `optuna`, `pandas-ta`, `hmmlearn`
2. **Replace hand-coded indicators**: Use `pandas-ta` `.ta` accessor across strategy modules
3. **Add SHAP explainability**: After every XGBoost/LightGBM train, log SHAP summary to `reports/`
4. **Add Optuna HPO**: Wrap existing `strategies/mlmr.py` with Optuna hyperparameter search

### Phase 2 — Advanced (Medium Effort)
5. **Integrate mlfinlab**: Triple-barrier labeling (`core/labeling.py`), purged CV (`validation/purged_cv.py`), bet-sizing
6. **Regime detection module**: `core/regime_detector.py` using `hmmlearn` + Markov switching
7. **Anomaly gating**: PyOD `IsolationForest` in pre-trade risk pipeline
8. **Walk-forward overhaul**: Extend `strategies/walk_forward.py` with PurgedKFold + embargo

### Phase 3 — Deep (High Effort)
9. **Deep learning forecasting**: Darts or PyTorch Forecasting for TFT/N-BEATS signals
10. **RL agent**: FinRL integration for continuous action space trading
11. **Foundation models**: Experiment with Chronos/Lag-Llama for zero-shot financial forecasting
12. **LLM sentiment**: FinGPT for news-based signal augmentation

---

## 📚 Key References

- de Prado, M.L. (2018). *Advances in Financial Machine Learning*. Wiley.  
- de Prado, M.L. (2020). *Machine Learning for Asset Managers*. Cambridge.  
- Jansen, S. (2020). *Machine Learning for Algorithmic Trading*. Packt. (2nd ed. 2023)  
- Chan, E. (2009). *Quantitative Trading*. Wiley.  

---

*End of research. Evidence quality: A = live PyPI/GitHub verified Jul 2026. B = known ecosystem status. C = legacy/unmaintained.*
