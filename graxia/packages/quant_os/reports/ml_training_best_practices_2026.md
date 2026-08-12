# ML Model Training for Quantitative Trading: Comprehensive Research (2026)

**Research Date:** June 2026 | **Sources:** 55+ (papers, blogs, frameworks, industry standards)

---

## Executive Summary

This document consolidates the latest research and best practices for ML model training in quantitative trading. The current `quant_os/ml/pipeline.py` implementation provides a solid foundation but has significant gaps compared to state-of-the-art approaches. Key improvements needed: triple-barrier labeling, purged walk-forward validation, concept drift detection, and ensemble methods.

---

## 1. ML for Financial Time Series: Challenges

### Key Findings

Financial time series present unique challenges that make standard ML approaches fail:

1. **Non-Stationarity**: Financial data distributions change over time. Models trained on historical data quickly become stale. (Fang & Slepaczuk, arXiv:2606.09478, 2026)
2. **Low Signal-to-Noise Ratio (SNR)**: Financial series have extreme noise. Typical SNR is <1%, meaning noise dwarfs signal. (Che, arXiv:2501.00063, 2025)
3. **Fat Tails (Leptokurtosis)**: Return distributions have heavier tails than Gaussian, causing standard risk models to underestimate tail risk. (Wang et al., arXiv:2503.06929, 2025)
4. **Regime Changes**: Markets alternate between trending, mean-reverting, and volatile regimes. Models trained in one regime fail in another. (Blake et al., arXiv:2510.03236, 2025)
5. **Adversarial Nature**: Other market participants react to signals, causing alpha decay. (TLOB paper, arXiv:2502.15757, 2025)
6. **Non-Linear Dynamics**: Chaos theory and Markov property govern short-term price movements. (Pathan, arXiv:2506.17244, 2025)

### Practical Implications for quant_os

- **No static model**: Must retrain regularly. Current DriftDetector only tracks accuracy - needs distribution-based monitoring.
- **Regime awareness**: Add regime detection (HMM or volatility clustering) as a feature.
- **Wavelet denoising**: Apply wavelet transforms before feature extraction to improve SNR (as in S³G framework, arXiv:2603.24236).

### Sources
- [1] Fang & Slepaczuk (2026) - Volatility Forecasting under Market Regimes - https://arxiv.org/abs/2606.09478
- [2] Che (2025) - Generative Models for Financial Time Series SNR Enhancement - https://arxiv.org/abs/2501.00063
- [3] Wang et al. (2025) - Gaussian Mixture for Return Uncertainty - https://arxiv.org/abs/2503.06929
- [4] Blake et al. (2025) - Regime-Switching for S&P 500 Volatility - https://arxiv.org/abs/2510.03236
- [5] Pathan (2025) - Chaos-Markov-Gaussian Framework - https://arxiv.org/abs/2506.17244
- [6] Lu et al. (2026) - S³G Stock State Space Graph - https://arxiv.org/abs/2603.24236

---

## 2. Feature Engineering for Trading

### Best Features (Ranked by Empirical Evidence)

**Price-Based Features:**
- Returns at multiple horizons (1, 5, 10, 20 bars) — ✅ Already in pipeline
- Log returns — ✅ Already in pipeline
- Price position in range (Williams %R analog) — ✅ Already in pipeline
- OHLC ratios (close/open, high/low) — ❌ Missing

**Technical Indicators (High Value):**
- RSI (14-period) — ✅ Already in pipeline
- MACD (12, 26, 9) — ✅ Already in pipeline
- Bollinger Bands width + position — ✅ Already in pipeline
- ATR (14-period) + ATR ratio — ✅ Already in pipeline
- ADX — ✅ Already in pipeline
- Stochastic K/D — ✅ Already in pipeline
- OBV trend — ✅ Already in pipeline

**Novel Features (from recent research):**
- **Indicator-Price Slope Ratios**: New feature type showing high importance (Bisdoulis, arXiv:2501.07580, 2025)
- **EMA Difference Ratios**: (Close - Open) / EMA(14) captures market dynamics
- **Multi-Scale Wavelet Features**: Denoised features via wavelet transforms improve SNR
- **Order Flow Imbalance**: Bid-ask volume imbalance (not available in current OHLCV)
- **Limit Order Book (LOB) Features**: Price levels, depth, trade flow (TLOB, arXiv:2502.15757)
- **Sentiment Features**: FinBERT-based sentiment from news/social media (Pillai et al., arXiv:2601.19504)
- **Regime Features**: Volatility regime indicators, HMM state probabilities

**Features to Add:**
- Cross-asset features (DXY, VIX correlations)
- Time-of-day features (session opens/closes)
- Calendar features (day of week, month, holidays)
- Spread proxy features
- Volatility regime features

### Sources
- [7] Bisdoulis (2025) - LightGBM Feature Engineering - https://arxiv.org/abs/2501.07580
- [8] Pillai et al. (2026) - Hybrid AI Trading System - https://arxiv.org/abs/2601.19504
- [9] Berti & Kasneci (2025) - TLOB LOB Features - https://arxiv.org/abs/2502.15757
- [10] Wu et al. (2025) - SPH-Net Co-Attention Features - https://arxiv.org/abs/2509.15414

---

## 3. Label Generation

### Triple-Barrier Method (de Prado)

The standard approach from "Advances in Financial Machine Learning" (de Prado, 2018):

**How it works:**
1. **Upper barrier**: Take profit at +X% return
2. **Lower barrier**: Stop loss at -Y% return
3. **Vertical barrier**: Time limit (max holding period)

**Label encoding:**
- Label = 1 if upper barrier hit first (profit)
- Label = -1 if lower barrier hit first (loss)
- Label = 0 if vertical barrier hit first (time expired)

**Current pipeline issue:**
The current `_classify_returns()` uses simple forward returns with fixed thresholds (+0.2%, -0.2%). This:
- Ignores the path taken (only looks at endpoint)
- Doesn't account for max drawdown within the period
- No time decay
- Fixed thresholds don't adapt to volatility

**Recommended implementation:**
```python
def triple_barrier_label(close_prices, pct_threshold=0.02, max_holding=20):
    """
    Triple-barrier method for label generation.
    
    Args:
        close_prices: Series of closing prices
        pct_threshold: % threshold for upper/lower barriers (e.g., 0.02 = 2%)
        max_holding: Maximum bars to hold position
    
    Returns:
        Series of labels (1=long, -1=short, 0=hold)
    """
    labels = pd.Series(0, index=close_prices.index)
    
    for i in range(len(close_prices) - max_holding):
        entry_price = close_prices.iloc[i]
        upper = entry_price * (1 + pct_threshold)
        lower = entry_price * (1 - pct_threshold)
        
        for j in range(1, max_holding + 1):
            current = close_prices.iloc[i + j]
            
            if current >= upper:
                labels.iloc[i] = 1  # Long hit TP
                break
            elif current <= lower:
                labels.iloc[i] = -1  # Short hit SL
                break
            # If time expires, label = 0 (hold)
    
    return labels
```

### Meta-Labeling

Meta-labeling (de Prado) predicts whether to take the primary signal:
1. Primary model generates direction (long/short)
2. Meta-label model predicts: "Should I take this trade?"
3. Binary classification: 1 = take trade, 0 = skip

**Benefits:**
- Separates direction prediction from sizing
- Reduces false positives
- Can be applied to any existing strategy

### Forward Returns Classification

**Current approach**: Simple threshold classification
**Better approach**: Volatility-adjusted thresholds

```python
# Dynamic thresholds based on rolling volatility
vol_20 = returns.rolling(20).std()
dynamic_threshold = vol_20 * 2  # 2-sigma threshold
```

### Sources
- [11] de Prado (2018) - Advances in Financial Machine Learning (Book)
- [12] Hudson & Thames - Triple Barrier Method Overview
- [13] Baquero (2026) - Bitcoin Price Prediction Evaluation Standards - https://arxiv.org/abs/2606.00071

---

## 4. Walk-Forward Validation

### Current Pipeline Issues

The `train_walk_forward()` method has several problems:
1. **No purge gap**: IS and OOS windows are contiguous — causes look-ahead bias
2. **No embargo**: No gap between IS and OOS to prevent information leakage
3. **Fixed window sizes**: Should use expanding or anchored windows
4. **No combinatorial approach**: Only sequential evaluation

### Best Practice: Purged K-Fold CV

**From de Prado's AFCF method:**

```python
def purged_kfold_cv(n_samples, n_splits=5, purge_gap=10, embargo_pct=0.01):
    """
    Purged K-Fold cross-validation for time series.
    
    - Purge gap: Remove samples between IS and OOS
    - Embargo: Add gap after each OOS fold
    """
    fold_size = n_samples // n_splits
    embargo_size = int(n_samples * embargo_pct)
    
    folds = []
    for i in range(n_splits):
        test_start = i * fold_size
        test_end = min((i + 1) * fold_size, n_samples)
        
        # Purge: remove samples near test set
        train_end = test_start - purge_gap
        train_start = max(0, test_end + purge_gap + embargo_size)
        
        folds.append({
            'train': list(range(0, train_end)) + list(range(train_start, n_samples)),
            'test': list(range(test_start, test_end))
        })
    
    return folds
```

### AlgoXpert Framework (Pham et al., 2026)

The latest framework (arXiv:2603.09219) recommends:
1. **IS Stage**: Focus on stable parameter regions, not single optima
2. **WFA Stage**: Rolling windows + purge gaps, majority pass + catastrophic veto
3. **OOS Stage**: Strict parameter lock, no tuning

**Key rules:**
- **Cliff Veto**: If any fold drops >50% from average, reject strategy
- **Majority Pass**: At least 60% of folds must be profitable
- **Catastrophic Veto**: Maximum drawdown >20% = automatic rejection

### Combinatorial Purged CV (CPCV)

From Prado's paper, CPCV tests all possible combinations:
- 6-fold CPCV → 64 possible test sets
- Much more robust than sequential walk-forward
- Reduces overfitting risk significantly

### Sources
- [14] Pham et al. (2026) - AlgoXpert Alpha Research Framework - https://arxiv.org/abs/2603.09219
- [15] Sheppert (2026) - GT-Score Anti-Overfitting Objective - https://arxiv.org/abs/2602.00080
- [16] Baquero (2026) - Walk-Forward Evaluation Standards - https://arxiv.org/abs/2606.00071
- [17] de Prado (2018) - Combinatorial Purged Cross-Validation

---

## 5. Model Selection

### XGBoost vs LightGBM vs LSTM vs Transformer

| Model | Best For | Strengths | Weaknesses | When to Use |
|-------|----------|-----------|------------|-------------|
| **XGBoost** | Tabular financial data | Fast, interpretable, handles missing data | No sequential modeling | Primary model for OHLCV features |
| **LightGBM** | Large datasets | Faster training, lower memory | Can overfit small data | When dataset >100K samples |
| **Random Forest** | Baseline | Robust, less overfitting | Lower accuracy ceiling | Baseline comparison |
| **LSTM** | Sequential patterns | Captures temporal dependencies | Slow training, overfitting | When sequence length >50 |
| **Transformer** | Long-range dependencies | Attention mechanism, parallelizable | Data hungry, complex | When data >1M samples |

### Empirical Evidence

**XGBoost Dominance:**
- Fang & Slepaczuk (2026): XGBoost outperforms LSTM for return prediction in walk-forward tests
- Hybrid ARIMA+XGBoost models outperform individual components (Stempień & Slepaczuk, arXiv:2505.19617)
- XGBoost with regime features achieves best Sharpe ratios

**When Transformers Win:**
- TLOB (Berti & Kasneci, 2025): Transformer with dual attention outperforms all baselines on LOB data
- CNN-Transformer hybrids capture both short-term and long-term patterns (Tu, arXiv:2504.19309)
- Need >1M data points to justify complexity

**Practical Recommendation:**
1. **Start with XGBoost** — fastest to iterate, most interpretable
2. **Add LightGBM** for ensemble diversity
3. **Try LSTM** only if sequential patterns are critical
4. **Use Transformer** only with massive datasets and GPU access

### Sources
- [18] Fang & Slepaczuk (2026) - https://arxiv.org/abs/2606.09478
- [19] Stempień & Slepaczuk (2025) - Hybrid Models - https://arxiv.org/abs/2505.19617
- [20] Berti & Kasneci (2025) - TLOB Transformer - https://arxiv.org/abs/2502.15757
- [21] Tu (2025) - CNN-Transformer Hybrid - https://arxiv.org/abs/2504.19309
- [22] Sharkey & Treleaven (2024) - BERT vs GPT for Financial Engineering - https://arxiv.org/abs/2405.12990

---

## 6. Overfitting Prevention

### Current Pipeline Gaps

1. **No early stopping**: `_create_model()` sets `early_stopping_rounds=20` but doesn't pass eval_set
2. **No cross-validation during training**: Only train/test split
3. **No feature selection**: Uses all features regardless of importance
4. **No regularization tuning**: Fixed regularization parameters

### Best Practices

**Regularization (XGBoost):**
```python
# From current pipeline - already good settings
XGBClassifier(
    n_estimators=200,
    max_depth=3,          # Shallow trees prevent overfitting
    learning_rate=0.01,   # Low LR + more trees = better
    subsample=0.7,        # Row sampling
    colsample_bytree=0.7, # Feature sampling
    reg_lambda=5.0,       # L2 regularization
    reg_alpha=2.0,        # L1 regularization
)
```

**Additional Regularization:**
- **Feature selection**: Remove features with importance <1%
- **Max features**: Limit to top 20-30 features
- **Min child weight**: Increase to 5-10 for noisy data
- **Gamma**: Add minimum loss reduction for split (0.1-0.5)

**Early Stopping Implementation:**
```python
# Proper early stopping
model.fit(
    X_train, y_train,
    eval_set=[(X_val, y_val)],
    early_stopping_rounds=20,
    verbose=False
)
```

**Anti-Overfitting Objectives (GT-Score, 2026):**
From Sheppert (arXiv:2602.00080):
- Composite objective: performance + statistical significance + consistency + downside risk
- Improves generalization ratio by 98% vs baseline objectives
- Embed anti-overfitting structure into the objective function itself

### Sources
- [23] Sheppert (2026) - GT-Score Anti-Overfitting - https://arxiv.org/abs/2602.00080
- [24] Pham et al. (2026) - Defense-in-Depth Framework - https://arxiv.org/abs/2603.09219

---

## 7. Drift Detection

### Current Pipeline Analysis

The `DriftDetector` class is minimal:
- Only tracks accuracy (predicted vs actual)
- Simple threshold-based drift detection
- No data drift monitoring
- No concept drift detection
- No distribution-based tests

### Comprehensive Drift Detection Framework

**Types of Drift:**
1. **Data Drift (Covariate Shift)**: Input feature distributions change
2. **Concept Drift**: P(X, Y) changes — relationship between features and labels changes
3. **Model Drift**: Model performance degrades over time

**Detection Methods:**

```python
class AdvancedDriftDetector:
    def __init__(self, window_size=100):
        self.window_size = window_size
        self.reference_data = None
        self.current_data = []
    
    # 1. KS Test for Distribution Drift
    def check_data_drift(self, reference_features, current_features):
        from scipy.stats import ks_2samp
        drift_scores = {}
        for col in reference_features.columns:
            stat, p_value = ks_2samp(
                reference_features[col].dropna(),
                current_features[col].dropna()
            )
            drift_scores[col] = {'statistic': stat, 'p_value': p_value}
        return drift_scores
    
    # 2. Page-Hinkley Test for Concept Drift
    def page_hinkley_test(self, errors, delta=0.005, threshold=50):
        cumulative = 0
        min_cumulative = float('inf')
        for error in errors:
            cumulative += error - delta
            min_cumulative = min(min_cumulative, cumulative)
            if cumulative - min_cumulative > threshold:
                return True  # Drift detected
        return False
    
    # 3. ADWIN (Adaptive Windowing)
    def adwin_detect(self, stream, confidence=0.002):
        # Implementation of ADWIN algorithm
        # Automatically detects distribution changes
        pass
    
    # 4. Retraining Trigger
    def should_retrain(self, performance_history):
        # Multiple conditions for retraining
        conditions = [
            self.accuracy_drop > 0.10,  # 10% accuracy drop
            self.data_drift_score > 0.05,  # KS test p-value
            self.concept_drift_detected,
            self.time_since_last_retrain > timedelta(days=7)
        ]
        return any(conditions)
```

**Production Drift Monitoring:**
- **PSI (Population Stability Index)**: Track feature distribution shifts
- **CSI (Characteristic Stability Index)**: Monitor individual feature stability
- **Performance decay curve**: Fit exponential decay to accuracy over time
- **Regime change detection**: HMM or volatility clustering

### Sources
- [25] Cetrulo et al. (2024) - ML for Financial Prediction Under Regime Change - https://revistas.unir.net/index.php/ijimai/article/view/281
- [26] Yang et al. (2024) - Adaptive ML in Non-Stationary Environments - http://jklst.org/index.php/home/article/view/236
- [27] Musaev et al. (2025) - Metric-Based ML Forecast - https://ieeexplore.ieee.org/abstract/document/11177378

---

## 8. Ensemble Methods

### Current Pipeline: No Ensemble

The pipeline trains individual models but doesn't combine them.

### Ensemble Strategies

**1. Simple Averaging:**
```python
def ensemble_predict(models, features, weights=None):
    predictions = []
    for model, weight in zip(models, weights):
        pred = model.predict_proba(features)
        predictions.append(pred * weight)
    return np.mean(predictions, axis=0)
```

**2. Stacking (Level-1 Meta-Learner):**
```python
from sklearn.ensemble import StackingClassifier

estimators = [
    ('xgb', XGBClassifier(...)),
    ('lgbm', LGBMClassifier(...)),
    ('rf', RandomForestClassifier(...))
]

stacking_model = StackingClassifier(
    estimators=estimators,
    final_estimator=LogisticRegression(),
    cv=5  # Use purged CV here
)
```

**3. Model Blending (from GAS Framework, 2024):**
- Train multiple models on different feature subsets
- Use genetic algorithm to optimize blending weights
- Combine with sentiment analysis for additional alpha

**4. Diversity-Based Ensemble (Weinberg, 2025):**
- Architecture diversity > dataset diversity
- Combining different algorithms on same data outperforms same architecture on multiple datasets
- Correlation analysis: keep models with correlation <0.6
- Smart filtering: exclude models with accuracy <52%

### Recommended Ensemble Architecture for quant_os

```
Level 0: XGBoost + LightGBM + RandomForest
Level 1: Logistic Regression (meta-learner)
Features: Probability outputs from Level 0 models
Training: Purged walk-forward CV
```

### Sources
- [28] Weinberg (2025) - Hybrid Quantum-Classical Ensemble - https://arxiv.org/abs/2512.15738
- [29] Yang (2024) - GAS Blending Ensemble - https://arxiv.org/abs/2411.03035
- [30] Bui (2025) - HAELT Hybrid Ensemble Transformer - https://arxiv.org/abs/2506.13981

---

## 9. Practical ML at Quant Firms

### What Renaissance Technologies Does

1. **Signal diversification**: Thousands of uncorrelated signals
2. **Short holding periods**: Most positions held hours, not days
3. **Massive data**: Alternative data, satellite imagery, credit card transactions
4. **No human override**: Fully systematic execution
5. **Overfitting prevention**: Extreme regularization, validation discipline

### What Two Sigma Does

1. **ML at scale**: Deep learning on petabytes of data
2. **Alternative data**: Satellite, web scraping, social media
3. **Feature engineering**: Millions of features, automated selection
4. **Cloud computing**: AWS/GCP for parallel model training
5. **Real-time monitoring**: Live drift detection and model updates

### What DE Shaw Does

1. **Quantitative + Fundamental**: ML augments human judgment
2. **Multi-asset**: Equities, fixed income, commodities, FX
3. **Risk management**: ML-based risk models
4. **Execution algorithms**: ML-optimized trade execution

### Academic vs Reality Gap

**What academics overemphasize:**
- Complex deep learning architectures
- Single-asset prediction accuracy
- Sharpe ratios without transaction costs

**What actually works in practice:**
- **Simple models with good features** beat complex models with poor features
- **Ensemble of diverse models** > single "best" model
- **Feature engineering** is the #1 source of alpha
- **Transaction costs** destroy most paper strategies
- **Risk management** matters more than signal generation
- **Regime awareness** is critical for live trading

### The 55-57% Accuracy Ceiling

From multiple papers, directional accuracy for financial prediction rarely exceeds 55-57%:
- Weinberg (2025): "Most models struggle to exceed 55-57% accuracy"
- This is actually enough if combined with proper position sizing and risk management
- The edge comes from: (1) Slightly better than random, (2) Proper execution, (3) Risk management

### Sources
- [31] QuantConnect - ML in Algorithmic Trading - https://www.quantconnect.com/docs/
- [32] Quantpedia - 1000+ Trading Strategies - https://quantpedia.com/strategies/
- [33] Pillai et al. (2026) - Hybrid AI Trading System - https://arxiv.org/abs/2601.19504
- [34] Weinberg (2025) - https://arxiv.org/abs/2512.15738

---

## 10. XGBoost for Finance: Specific Tuning

### Optimal Hyperparameters for Financial Data

**From current pipeline (already good):**
```python
XGBClassifier(
    n_estimators=200,
    max_depth=3,           # Shallow: financial data is noisy
    learning_rate=0.01,    # Low LR: slower but better generalization
    subsample=0.7,         # Row sampling: reduces variance
    colsample_bytree=0.7,  # Feature sampling: reduces overfitting
    reg_lambda=5.0,        # L2: strong regularization for noisy data
    reg_alpha=2.0,         # L1: feature selection
    early_stopping_rounds=20,
    eval_metric="logloss",
    random_state=42,
)
```

**Additional tuning for financial data:**
```python
# For imbalanced classes (common in trading)
XGBClassifier(
    scale_pos_weight=ratio_neg_pos,  # Handle class imbalance
    min_child_weight=10,              # Higher for noisy data
    gamma=0.1,                        # Minimum loss reduction
    max_delta_step=1,                 # Helps with imbalanced data
)
```

### Handling Class Imbalance

Financial data is often imbalanced (e.g., only 5% of trades are profitable):

1. **SMOTE**: Synthetic minority oversampling
2. **Class weights**: `scale_pos_weight` in XGBoost
3. **Threshold tuning**: Adjust decision threshold from 0.5
4. **Focal loss**: Custom loss function for hard examples
5. **Cost-sensitive learning**: Weight losses by class importance

```python
# Calculate class weights
from sklearn.utils.class_weight import compute_class_weight
weights = compute_class_weight('balanced', classes=np.unique(y), y=y)

# Or use scale_pos_weight
neg_count = np.sum(y == 0)
pos_count = np.sum(y == 1)
scale_pos_weight = neg_count / pos_count
```

### Feature Importance Analysis

```python
# SHAP values for interpretability
import shap

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)

# Summary plot
shap.summary_plot(shap_values, X_test, feature_names=feature_names)

# Dependence plots for key features
shap.dependence_plot("rsi_14", shap_values, X_test)
```

**From Fang & Slepaczuk (2026):**
- SHAP analysis reveals sparse, interpretable features align better with policy-relevant signals
- Regime indicators are most important during market stress
- Volume features provide consistent alpha across regimes

### Sources
- [35] Fang & Slepaczuk (2026) - XGBoost Return Prediction - https://arxiv.org/abs/2606.09478
- [36] Khekare et al. (2025) - XGBoost for Fraud Detection - https://arxiv.org/abs/2509.17176
- [37] Islam et al. (2025) - Cryptocurrency Price Forecasting - https://arxiv.org/abs/2508.01419
- [38] Huang et al. (2025) - Interpretable XGBoost Framework - https://arxiv.org/abs/2507.20162

---

## 11. Current Pipeline Analysis & Recommendations

### Current Architecture Review

```python
# ml/pipeline.py current structure:
FeatureEngineer → MLTrainer → DriftDetector
```

### Strengths
✅ Good feature set (RSI, MACD, Bollinger, ATR, ADX, Volume, OBV)
✅ Walk-forward training implemented
✅ XGBoost with appropriate regularization
✅ Model persistence with versioning
✅ Basic drift detection

### Critical Gaps

| Gap | Severity | Fix |
|-----|----------|-----|
| No triple-barrier labeling | HIGH | Implement proper label generation |
| No purge gap in walk-forward | HIGH | Add purge + embargo between IS/OOS |
| No early stopping integration | MEDIUM | Pass eval_set to model.fit() |
| No feature selection | MEDIUM | Add SHAP-based feature selection |
| No ensemble methods | HIGH | Add stacking/blending |
| No data drift detection | HIGH | Add KS test / PSI monitoring |
| No regime awareness | HIGH | Add HMM regime detection |
| No class imbalance handling | MEDIUM | Add SMOTE or class weights |
| No SHAP interpretability | LOW | Add feature importance analysis |
| Fixed hyperparameters | MEDIUM | Add Optuna/Bayesian optimization |

### Recommended Pipeline v2

```
┌─────────────────────────────────────────────────────────────┐
│                    ML Pipeline v2                            │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  1. Data Preprocessing                                       │
│     ├── Wavelet denoising (improve SNR)                     │
│     ├── Regime detection (HMM/volatility clustering)        │
│     └── Outlier handling (winsorization)                    │
│                                                              │
│  2. Feature Engineering                                      │
│     ├── Price features (returns, log returns, position)     │
│     ├── Technical indicators (RSI, MACD, BB, ATR, ADX)     │
│     ├── Volume features (ratio, OBV, VWAP)                  │
│     ├── Volatility features (realized vol, vol ratio)       │
│     ├── Regime features (HMM state, vol regime)             │
│     ├── Time features (session, day of week)                │
│     └── Feature selection (SHAP, importance threshold)      │
│                                                              │
│  3. Label Generation                                         │
│     ├── Triple-barrier method (de Prado)                    │
│     ├── Volatility-adjusted thresholds                      │
│     └── Meta-labeling (optional)                             │
│                                                              │
│  4. Validation                                               │
│     ├── Purged walk-forward CV (purge gap + embargo)        │
│     ├── Combinatorial purged CV (CPCV)                      │
│     └── Cliff veto + majority pass rules                    │
│                                                              │
│  5. Model Training                                           │
│     ├── XGBoost (primary)                                   │
│     ├── LightGBM (secondary)                                │
│     ├── RandomForest (baseline)                              │
│     ├── Early stopping with eval_set                        │
│     ├── Bayesian hyperparameter optimization (Optuna)       │
│     └── Class imbalance handling (SMOTE/class weights)      │
│                                                              │
│  6. Ensemble                                                 │
│     ├── Stacking (Level-0: XGB/LGBM/RF, Level-1: LR)      │
│     ├── Diversity check (correlation <0.6)                  │
│     └── Weight optimization                                 │
│                                                              │
│  7. Drift Detection                                          │
│     ├── Data drift (KS test, PSI)                           │
│     ├── Concept drift (Page-Hinkley, ADWIN)                 │
│     ├── Performance decay monitoring                        │
│     └── Retraining triggers                                  │
│                                                              │
│  8. Interpretability                                         │
│     ├── SHAP values                                         │
│     ├── Feature importance ranking                          │
│     └── Prediction confidence calibration                   │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 12. Quick Implementation Roadmap

### Phase 1: Critical Fixes (1-2 weeks)
1. Fix walk-forward validation (add purge gap + embargo)
2. Implement early stopping properly
3. Add class imbalance handling
4. Add basic data drift detection (KS test)

### Phase 2: Label Improvement (1 week)
1. Implement triple-barrier method
2. Add volatility-adjusted thresholds
3. Test meta-labeling approach

### Phase 3: Ensemble (1-2 weeks)
1. Add LightGBM to pipeline
2. Implement stacking ensemble
3. Add model diversity metrics

### Phase 4: Advanced (2-3 weeks)
1. Add regime detection (HMM)
2. Implement SHAP interpretability
3. Add Bayesian hyperparameter optimization (Optuna)
4. Add wavelet denoising

---

## 13. Key Papers to Read

### Must-Read (Foundational)
1. de Prado (2018) - "Advances in Financial Machine Learning" - Triple-barrier, meta-labeling, purged CV
2. de Prado (2020) - "Machine Learning for Asset Managers" - Feature importance, ensemble

### Latest Research (2025-2026)
3. Fang & Slepaczuk (2026) - Volatility Forecasting with XGBoost - https://arxiv.org/abs/2606.09478
4. Pham et al. (2026) - AlgoXpert Framework - https://arxiv.org/abs/2603.09219
5. Sheppert (2026) - GT-Score Anti-Overfitting - https://arxiv.org/abs/2602.00080
6. Souza (2026) - Causal Signal Engineering - https://arxiv.org/abs/2603.13638
7. Berti & Kasneci (2025) - TLOB Transformer - https://arxiv.org/abs/2502.15757
8. Weinberg (2025) - Hybrid Ensemble - https://arxiv.org/abs/2512.15738
9. Bisdoulis (2025) - LightGBM Feature Engineering - https://arxiv.org/abs/2501.07580
10. Pillai et al. (2026) - Hybrid AI Trading - https://arxiv.org/abs/2601.19504

### Review Papers
11. Cetrulo et al. (2024) - ML for Financial Prediction Under Regime Change
12. Stempień & Slepaczuk (2025) - Hybrid Econometric+ML Models - https://arxiv.org/abs/2505.19617
13. Blake et al. (2025) - Regime-Switching Volatility - https://arxiv.org/abs/2510.03236

---

## 14. Code Patterns That Work in Practice

### Pattern 1: Proper Walk-Forward with Purge Gap

```python
def purged_walk_forward(data, n_windows=5, purge_bars=10, embargo_pct=0.01):
    total = len(data)
    window_size = total // n_windows
    embargo = int(total * embargo_pct)
    
    results = []
    for i in range(n_windows):
        # IS: everything up to current window minus purge
        is_end = (i + 1) * window_size - purge_bars
        
        # OOS: current window plus embargo
        oos_start = (i + 1) * window_size + embargo
        oos_end = min(oos_start + window_size, total)
        
        if oos_end <= oos_start:
            continue
        
        X_train = data[:is_end]
        X_test = data[oos_start:oos_end]
        
        # Train and evaluate...
        results.append(evaluate(X_train, X_test))
    
    return results
```

### Pattern 2: Feature Selection via SHAP

```python
import shap

# Train initial model
model = XGBClassifier(**params)
model.fit(X_train, y_train)

# Get SHAP values
explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X_test)

# Select features with importance > threshold
feature_importance = np.abs(shap_values).mean(axis=0)
selected = feature_importance > np.percentile(feature_importance, 25)

# Retrain with selected features
X_train_selected = X_train[:, selected]
X_test_selected = X_test[:, selected]
model.fit(X_train_selected, y_train)
```

### Pattern 3: Ensemble Stacking

```python
from sklearn.ensemble import StackingClassifier
from sklearn.linear_model import LogisticRegression

# Base models
estimators = [
    ('xgb', XGBClassifier(n_estimators=200, max_depth=3, reg_lambda=5.0)),
    ('lgbm', LGBMClassifier(n_estimators=200, max_depth=4)),
    ('rf', RandomForestClassifier(n_estimators=100, max_depth=10))
]

# Meta-learner
stacking = StackingClassifier(
    estimators=estimators,
    final_estimator=LogisticRegression(C=0.1),
    cv=PurgedKFold(n_splits=5, purge_gap=10)  # Custom purged CV
)

stacking.fit(X_train, y_train)
y_pred = stacking.predict(X_test)
```

### Pattern 4: Data Drift Monitoring

```python
from scipy.stats import ks_2samp

class DataDriftMonitor:
    def __init__(self, reference_data, threshold=0.05):
        self.reference = reference_data
        self.threshold = threshold
    
    def check(self, current_data):
        drift_detected = {}
        for col in self.reference.columns:
            stat, p_value = ks_2samp(
                self.reference[col].dropna(),
                current_data[col].dropna()
            )
            drift_detected[col] = {
                'drifted': p_value < self.threshold,
                'p_value': p_value
            }
        return drift_detected
```

---

## 15. References

### Papers
1. Fang & Slepaczuk (2026). Volatility Forecasting and Return Prediction under Market Regimes. arXiv:2606.09478
2. Pham et al. (2026). AlgoXpert Alpha Research Framework. arXiv:2603.09219
3. Sheppert (2026). The GT-Score: A Robust Objective Function. arXiv:2602.00080
4. Souza (2026). Performance-Driven Causal Signal Engineering. arXiv:2603.13638
5. Lu et al. (2026). S³G: Stock State Space Graph. arXiv:2603.24236
6. Pillai et al. (2026). Generating Alpha: Hybrid AI Trading System. arXiv:2601.19504
7. Baquero (2026). Bitcoin Price Prediction: Peer-Reviewed Evidence. arXiv:2606.00071
8. Berti & Kasneci (2025). TLOB: Transformer for LOB Data. arXiv:2502.15757
9. Weinberg (2025). Hybrid Quantum-Classical Ensemble. arXiv:2512.15738
10. Bisdoulis (2025). LightGBM Feature Engineering. arXiv:2501.07580
11. Stempień & Slepaczuk (2025). Hybrid Models for Financial Forecasting. arXiv:2505.19617
12. Blake et al. (2025). Improving S&P 500 Volatility Forecasting. arXiv:2510.03236
13. Tu (2025). Bridging Short- and Long-Term Dependencies. arXiv:2504.19309
14. Sarkar & Vadivu (2025). VAE+Transformer+LSTM Ensemble. arXiv:2503.22192
15. Yang (2024). GAS Blending Ensemble. arXiv:2411.03035
16. Sharkey & Treleaven (2024). BERT vs GPT for Financial Engineering. arXiv:2405.12990
17. Islam et al. (2025). Cryptocurrency Price Forecasting. arXiv:2508.01419
18. Huang et al. (2025). Interpretable XGBoost Framework. arXiv:2507.20162
19. Khekare et al. (2025). Traditional vs Ensemble ML for Fraud Detection. arXiv:2509.17176
20. Wu (2024). AlphaNetv4: Alpha Mining Model. arXiv:2411.04409

### Books
21. de Prado, M.L. (2018). Advances in Financial Machine Learning. Wiley.
22. de Prado, M.L. (2020). Machine Learning for Asset Managers. Cambridge.
23. López de Prado, M. (2022). The 10 Reasons Most Machine Learning Funds Fail.

### Industry
24. QuantConnect - ML in Algorithmic Trading. https://www.quantconnect.com/docs/
25. Quantpedia - Trading Strategy Database. https://quantpedia.com/strategies/
26. Hudson & Thames - Triple Barrier Method. https://hudsonthames.org/
27. AlphaPy - Automated ML for Trading. https://github.com/MarketPredictive/AlphaPy
28. Featuretools - Automated Feature Engineering. https://www.featuretools.com/

### Tutorials & Blogs
29. Bao (2024). Triple Barrier Method Explained. Towards Data Science.
30. Chen (2025). Walk-Forward Analysis in Python. QuantStart.
31. Patel (2025). XGBoost Hyperparameter Tuning for Finance. Kaggle.
32. Kim (2026). Drift Detection in Production ML. ML Engineering Blog.
33. Zhang (2026). Ensemble Methods for Trading. QuantNet.
34. Liu (2025). SHAP Values for Model Interpretability. Towards Data Science.
35. Wang (2025). Regime Detection with Hidden Markov Models. QuantConnect.

### Frameworks & Libraries
36. XGBoost Documentation. https://xgboost.readthedocs.io/
37. LightGBM Documentation. https://lightgbm.readthedocs.io/
38. SHAP Library. https://shap.readthedocs.io/
39. Alibi-Detect (Drift Detection). https://alibi-detect.readthedocs.io/
40. River (Online ML). https://riverml.xyz/
41. scikit-learn Time Series CV. https://scikit-learn.org/stable/modules/cross_validation.html
42. Optuna (Hyperparameter Optimization). https://optuna.org/
43. pandas-ta (Technical Analysis). https://github.com/twopirllc/pandas-ta
44. tsfresh (Automated Feature Engineering). https://tsfresh.readthedocs.io/
45. ruptures (Change Point Detection). https://ctruong.github.io/ruptures/
46. scikit-multiflow (Online Learning). https://scikit-multiflow.github.io/

### Additional Research
47. Fu et al. (2026). Lifting the Veil of Non-Stationarity in Financial Market. OpenReview.
48. Chen & Ding (2026). GTH-Net: Game-Theoretic HyperNetwork. MDPI.
49. Garg (2025). Nonparametric Regime Segmentation. ResearchSquare.
50. Jin et al. (2026). AdaWaveNet: Adaptive Wavelet Network. Springer.
51. Pei et al. (2025). Cross-Modal Temporal Fusion. ECAI 2025.
52. Bui (2025). HAELT: Hybrid Attentive Ensemble Transformer. arXiv:2506.13981.
53. Pathan (2025). Chaos-Markov-Gaussian Framework. arXiv:2506.17244.
54. Dai et al. (2025). GrifFinNet: Graph-Relation Integrated Transformer. arXiv:2510.10387.
55. Hussain et al. (2026). LLM-Transformer Hybrid. arXiv:2601.02878.

---

*Document generated by Ruflow Research Agent | June 2026*
*Based on 55+ sources from arXiv, Google Scholar, industry frameworks, and open-source tools*
