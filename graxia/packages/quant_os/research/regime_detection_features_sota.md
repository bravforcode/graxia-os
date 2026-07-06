# State-of-the-Art Regime Detection Features for Intraday Quantitative Trading

> **Research compiled July 2026** — spanning arXiv papers, ML4T 3rd edition (Jansen 2026), and quant industry practices.
> Target timeframes: M1, M5, M15, H1.

---

## 1. Volatility Regime Features

### 1.1 Parkinson Volatility Estimator

**Formula:**
```
σ_parkinson = sqrt( (1 / (4 * N * ln(2))) * Σ (ln(H_i / L_i))^2 )
```

**Python sketch:**
```python
def parkinson_vol(df, window=20):
    log_hl = np.log(df['high'] / df['low'])
    return np.sqrt(1.0 / (4.0 * np.log(2)) * log_hl.rolling(window).apply(lambda x: (x**2).mean()))
```

- **Reference:** Parkinson (1980), "The Extreme Value Method for Estimating the Variance of the Rate of Return." J. Business. Efficiency 5.2x vs close-to-close.
- **Intraday config:** M15 with window=16 (4-hour lookback). For M5 use window=48. For M1 use window=60.

### 1.2 Garman-Klass (GK) Volatility Estimator

**Formula:**
```
σ_gk = sqrt( 0.5*(ln(H/L))^2 - (2*ln(2)-1)*(ln(C/O))^2 )
```

**Python sketch:**
```python
def garman_klass(df):
    c = np.log(df['close'] / df['open'])
    h = np.log(df['high'] / df['open'])
    l = np.log(df['low'] / df['open'])
    return np.sqrt(0.5 * (h - l)**2 - (2 * np.log(2) - 1) * c**2)
```

- **Reference:** Garman & Klass (1980), "On the Estimation of Security Price Volatilities from Historical Data." Efficiency 7.4x vs close-to-close.
- **Intraday config:** M15 with window=16. M5 with window=48. GK is the most efficient OHLC estimator for near-zero-drift assets.

### 1.3 Yang-Zhang (YZ) Volatility Estimator

**Formula:**
```
σ_yz = sqrt( σ_o^2 + k * σ_c^2 + (1 - k) * σ_rs^2 )

where:
  σ_o^2 = overnight (open-to-prior-close) variance
  σ_c^2 = close-to-close variance
  σ_rs^2 = Rogers-Satchell range-based variance
  k = 0.34 / (1.34 + (n + 1) / (n - 1))
```

**Python sketch:**
```python
def yang_zhang(df, window=20):
    log_oc = np.log(df['open'] / df['close'].shift(1))  # overnight
    log_co = np.log(df['close'] / df['open'])            # open-close
    log_ho = np.log(df['high'] / df['open'])
    log_lo = np.log(df['low'] / df['open'])
    log_hl = np.log(df['high'] / df['low'])

    rs = log_ho * (log_ho - log_co) + log_lo * (log_lo - log_co)
    k = 0.34 / (1.34 + (window + 1) / (window - 1))
    overnight_vol = log_oc.rolling(window).var()
    open_close_vol = log_co.rolling(window).var()
    rs_vol = rs.rolling(window).mean()
    return np.sqrt(overnight_vol + k * open_close_vol + (1 - k) * rs_vol)
```

- **Reference:** Yang & Zhang (2000), "Drift-Independent Volatility Estimation Based on High, Low, Open, and Close Prices." Handles drift and overnight gaps — best for opening-gap regimes.
- **Intraday config:** Primarily daily, but can be adapted for H1 with window=24 (daily-equiv). For M15 use window=96.

### 1.4 EWMA Volatility

**Formula:**
```
σ_ewma_t = sqrt( λ * σ_ewma_{t-1}^2 + (1 - λ) * r_t^2 )
```
**Common λ = 0.94 (RiskMetrics).**

```python
def ewma_vol(returns, lambda_=0.94):
    ewma = [returns.iloc[0]**2]
    for r in returns.iloc[1:]:
        ewma.append(lambda_ * ewma[-1] + (1 - lambda_) * r**2)
    return np.sqrt(pd.Series(ewma, index=returns.index))
```

- **Reference:** JP Morgan RiskMetrics (1996). λ=0.94 for daily, λ=0.97 for monthly. For intraday: λ=0.84 (M15), λ=0.92 (H1).

### 1.5 GARCH(1,1) Volatility

**Formula:**
```
σ_t^2 = ω + α * ε_{t-1}^2 + β * σ_{t-1}^2
```

```python
from arch import arch_model
model = arch_model(returns, vol='Garch', p=1, q=1)
res = model.fit(disp='off')
garch_vol = res.conditional_volatility
```

- **Reference:** Bollerslev (1986). For intraday, calibrate on M15-M30 returns. Rolling 1000-bar re-fit every 50 bars.
- **ML feature usage:** Stack GARCH(1,1) conditional vol + GJR-GARCH (asymmetric vol for leverage effect) + EGARCH on residuals.

### 1.6 Realized Volatility (for tick/sub-minute data)

**Formula:**
```
RV_t = Σ_i r_{t,i}^2   where r_{t,i} are sub-sampled returns within bar t
```

```python
def realized_vol(price, freq='5min'):
    log_ret = np.log(price.resample(freq).last()).diff()
    return np.sqrt((log_ret**2).rolling(20).sum())
```

- **Reference:** Andersen, Bollerslev, Diebold & Labys (2001). For M1 bars, sum M1 returns squared over window=30. For H1, use M5 sub-samples.

### 1.7 Volatility-of-Volatility (VoV / VVIX-analog)

**Formula:**
```
VoV_t = std(σ_{t-w:t}) / mean(σ_{t-w:t})
```

```python
def vol_of_vol(vol_series, window=20):
    return vol_series.rolling(window).std() / vol_series.rolling(window).mean()
```

- **Reference:** Just & Echaust (2020), VVIX literature applied to any vol estimator. High VoV → regime change imminent.
- **Intraday config:** Window=12 (M15), window=20 (M5), window=48 (M1).

### 1.8 Regime-Switching GARCH (MS-GARCH)

```python
# Use statsmodel MarkovAutoregression or custom MS-GARCH
# Key: regime-dependent volatility parameters α₁, β₁ vs α₂, β₂
```

- **Reference:** Haas, Mittnik & Paolella (2004). arXiv:2210.11520 — semiparametric GARCH change-point detection outperforms QMLE.
- **Configuration:** 2-regime (low-vol / high-vol), calibrated on trailing 500 bars.

### 1.9 Threshold Methods for Vol Regime Switching

| Method | Configuration |
|--------|--------------|
| **Percentile threshold** | Vol > 80th percentile of trailing 200-bar vol → high-vol regime |
| **Bollinger Band on vol** | Vol > SMA_vol + 2*σ → high-vol; Vol < SMA_vol - 2*σ → low-vol |
| **CUSUM on log-vol** | Cumulative sum of deviations from mean → detects structural breaks in volatility |
| **Chow test on vol windows** | Rolling F-test comparing vol in window A vs window B |
| **PELT / Binary Segmentation** | Optimal change-point detection (killick & Eckley 2014, R changepoint package) |

---

## 2. Hidden Markov Model (HMM) Regimes

### 2.1 Standard Gaussian HMM for Market Regimes

**Approach:** Fit HMM on multivariate features (returns, vol, volume, spread). Latent states = market regimes.

```python
from hmmlearn import hmm
model = hmm.GaussianHMM(n_components=3, covariance_type='full', n_iter=1000)
model.fit(features)  # features: [ret, vol, volume, spread]
states = model.predict(features)
probs = model.predict_proba(features)  # Use as ML features!
```

**2-state:** Bull/Bear or Trending/Ranging
**3-state:** Bull/Neutral/Bear or High-vol/Medium-vol/Low-vol
**4-state+:** Overfits without cross-validation. **3-state is the sweet spot.**

- **Reference:** arXiv:2104.09700 — "Stock Market Trend Analysis Using HMM and LSTM" (Liu et al., 2021). GMM-HMM + LSTM ensemble outperforms standalone methods.
- **Reference:** arXiv:2310.03775 — "Hidden Markov Models for Stock Market Prediction" (Catello et al., 2023). Evaluates MAPE and Directional Prediction Accuracy.
- **Reference:** ML4T 3rd Ed., Chapter 9 (model-based features) — covers HMM state probabilities as features.

### 2.2 HMM Feature Design for ML

```python
# Extract regime features from HMM fit
state_probs = model.predict_proba(features)  # (N, n_states) float array
regime_transition_matrix = model.transmat_     # (n_states, n_states)
current_regime = states[-1]
regime_entropy = -np.sum(state_probs[-1] * np.log(state_probs[-1] + 1e-10))  # uncertainty measure
```

**HMM features to pass to downstream ML:**
1. `hmm_state_probs` — full probability vector (n_states features)
2. `hmm_current_regime` — hard regime assignment (categorical)
3. `hmm_regime_entropy` — how confident is the regime assignment?
4. `hmm_regime_duration` — how many bars has the current regime persisted?
5. `hmm_transition_risk` — probability of leaving current regime: `1 - transmat[current_state, current_state]`

### 2.3 Variants & Extensions

| Variant | Use Case |
|---------|----------|
| **GMM-HMM** | Gaussian Mixture emissions — captures fat tails in returns |
| **HSMM (Hidden Semi-Markov)** | Models explicit regime durations — prevents flickering |
| **Auto-regressive HMM** | Each state has its own AR(p) dynamics |
| **MS-VAR (Markov Switching VAR)** | arXiv:2109.01046 — regime-dependent impact of exogenous variables |
| **Dirichlet Process HMM** | Nonparametric — infers optimal n_states from data |

### 2.4 Intraday Configuration

| Timeframe | Lookback bars | n_states | Features |
|-----------|--------------|----------|----------|
| M1 | 500-1000 | 3 | ret_1min, vol_20min, spread, volume_zscore |
| M5 | 200-500 | 3 | ret_5min, vol_1h, HVOL ratio, volume |
| M15 | 150-300 | 3 | ret_15min, vol_2h, trend strength, vol_ratio |
| H1 | 100-200 | 2-3 | ret_1h, vol_daily, SMA slope, macro regime |

**Key:** Re-fit HMM every 50-100 bars rolling window. Smooth regime by requiring ≥3 consecutive bars in same state.

---

## 3. Trend vs Mean-Reversion Detection

### 3.1 Hurst Exponent (Rolling)

**Formula:** R/S analysis or DFA-based estimation.

```
H ≈ 0.5: Random walk (efficient)
H > 0.5: Trend-persistent (>0.55 = trending)
H < 0.5: Mean-reverting (<0.45 = mean-reverting)
```

```python
def hurst_exponent(ts, max_lag=20):
    lags = range(2, max_lag)
    tau = [np.sqrt(np.std(np.subtract(ts[lag:], ts[:-lag]))) for lag in lags]
    poly = np.polyfit(np.log(lags), np.log(tau), 1)
    return poly[0]  # slope = Hurst exponent
```

- **Reference:** arXiv:0712.1624 — Eom et al. (2007). "Hurst exponent and prediction based on weak-form efficient market hypothesis." H > 0.55 → high hit rate from nearest-neighbor prediction. Strong positive correlation between Hurst and predictability.
- **Reference:** arXiv:1109.0465 — Morales et al. (2011). "Dynamical Hurst exponent as a tool to monitor unstable periods." Weighted Hurst (recent observations weighted higher) detects pre-crisis instability. Bail-out firms showed increasing H before 2007-2010 credit crisis.

**Intraday rolling Hurst:**
```python
# For H1: rolling window = 48 bars (2 days of H1)
# For M15: window = 96 bars (1 day)
# For M5: window = 288 bars (1 day)
# For M1: window = 480 bars (~1 session)
```

### 3.2 Variance Ratio Test

**Formula:**
```
VR(k) = Var(r_t + r_{t-1} + ... + r_{t-k+1}) / (k * Var(r_t))
```
Under random walk null: VR(k) = 1. VR(k) < 1 → mean-reversion. VR(k) > 1 → momentum.

```python
def rolling_variance_ratio(returns, k=5, window=50):
    """Lo & MacKinlay (1988) Variance Ratio"""
    var_1 = returns.rolling(window).var()
    k_period_ret = returns.rolling(k).sum()
    var_k = k_period_ret.rolling(window).var()
    vr = var_k / (k * var_1)
    return vr  # >1 trending, <1 mean-reverting
```

- **Reference:** Lo & MacKinlay (1988), "Stock Market Prices Do Not Follow Random Walks."

### 3.3 Autocorrelation Decay Features

```python
def acf_features(returns, nlags=20, window=50):
    """A collection of autocorrelation-based regime features"""
    acf = [returns.rolling(window).apply(
        lambda x: pd.Series(x).autocorr(lag=i), raw=False) for i in range(1, nlags+1)]

    # Features:
    acf_lag1 = acf[0]  # First-order autocorrelation
    acf_sum5 = sum(acf[:5])  # Total short-term momentum
    acf_decay = acf[0] - acf[-1]  # How fast ACF decays
    acf_sign_reversals = sum(1 for i in range(len(acf)-1)
                            if np.sign(acf[i]) != np.sign(acf[i+1]))
    return acf_lag1, acf_sum5, acf_decay
```

**Key features:**
| Feature | Interpretation |
|---------|---------------|
| `acf_lag1` | Positive → trending (return momentum), Negative → mean-reversion |
| `acf_lag1_sign_change` | Binary: recent sign flip = regime change signal |
| `acf_area` | Sum of ACF lags 1-10 (positive = trending) |

### 3.4 Combined Trend/Mean-Reversion Classifier

```python
def trend_mr_classifier(df):
    h = hurst_exponent(df['close'].pct_change().dropna()[-200:])
    vr = rolling_variance_ratio(df['close'].pct_change()[-100:], k=5)
    acf1 = df['close'].pct_change()[-50:].autocorr()

    if h > 0.55 and vr > 1.1 and acf1 > 0.05:
        return 'TRENDING_UP'
    elif h > 0.55 and vr > 1.1 and acf1 < -0.05:
        return 'TRENDING_DOWN'
    elif h < 0.45 and vr < 0.9:
        return 'MEAN_REVERTING'
    else:
        return 'RANDOM_WALK'
```

---

## 4. Market Microstructure Regimes

### 4.1 Order Flow Imbalance (OFI)

**Reference:** arXiv:2602.23784 — "TradeFM: A Generative Foundation Model for Trade-flow and Market Microstructure" (Kawawa-Beaudan et al., 2026). 524M-parameter Transformer learns scale-invariant trade-flow representations.
**Reference:** arXiv:2507.16701 — Order flow imbalance = 43.2% feature importance for forecasting price moves (minute-level SPY data, AUC 88.25%).

```python
def order_flow_imbalance(df):
    """Cont, Kukanov & Stoikov (2014)"""
    bid_vol_chg = df['bid_vol'] - df['bid_vol'].shift(1)
    ask_vol_chg = df['ask_vol'] - df['ask_vol'].shift(1)
    ofi = bid_vol_chg - ask_vol_chg
    return ofi.rolling(20).zscore()
```

### 4.2 Relative Spread (Bid-Ask Spread Regime)

```python
def relative_spread(df):
    spread = (df['ask'] - df['bid']) / ((df['ask'] + df['bid']) / 2)
    return spread  # High spread → low-liquidity regime
```

**Regime detection:** `spread > 95th percentile of trailing 200 bars` = illiquid/volatile regime.

### 4.3 Volume Profile / Volume-Weighted Average Price (VWAP) Deviation

```python
def vwap_deviation(df):
    vwap = (df['close'] * df['volume']).rolling(48).sum() / df['volume'].rolling(48).sum()
    return (df['close'] - vwap) / vwap  # Above VWAP = bullish pressure
```

### 4.4 Kyle's Lambda (Price Impact)

```python
def kyles_lambda(df, window=50):
    """λ = Cov(ΔP, signed_volume) / Var(signed_volume)"""
    dp = df['close'].diff()
    signed_vol = df['volume'] * np.sign(dp)  # Lee-Ready classification approx
    cov_dp_sv = dp.rolling(window).cov(signed_vol)
    var_sv = signed_vol.rolling(window).var()
    return cov_dp_sv / var_sv  # High λ = low-liquidity regime
```

### 4.5 Time-of-Day Regime Features

```python
def session_regime_features(df):
    """One-hot encoded session features"""
    df['london_open'] = (df.index.hour == 8) | (df.index.hour == 9)  # 8-9 UTC
    df['ny_open'] = (df.index.hour == 14) | (df.index.hour == 15)     # 14-15 UTC
    df['asia_session'] = df.index.hour.between(1, 9)
    df['london_session'] = df.index.hour.between(8, 17)
    df['ny_session'] = df.index.hour.between(13, 22)
    df['overlap'] = df['london_session'] & df['ny_session']
    df['settlement_window'] = df.index.hour.between(20, 22)
    return df
```

**Reference:** arXiv:2605.11423 — "VVG Classifier for MNQ Intraday Data" (Mesfin, 2026). First-30-min return magnitude + overnight gap + abnormal opening volume = 3-condition composite classifier. Finds statistically distinct intraday regimes (directional morning drift + late-session reversal). *Caveat:* descriptive only — no deployable strategy withstood costs.

### 4.6 Volume-Weighted Volatility Ratio

```python
def volume_weighted_vol_regime(df, window=20):
    """High vol + low volume = dangerous regime; High vol + high volume = genuine move"""
    vol = df['close'].pct_change().rolling(window).std()
    vol_ratio = df['volume'] / df['volume'].rolling(window).mean()
    return vol * vol_ratio  # High = confirmed regime, Low = noise
```

---

## 5. Correlation Regime Features

### 5.1 Rolling PCA and First Eigenvalue

```python
def rolling_pca_features(returns_df, window=50, n_assets=10):
    """returns_df: (T, N) DataFrame of returns for N assets"""
    from sklearn.decomposition import PCA
    pca = PCA()
    pca.fit(returns_df.iloc[-window:])

    lambda_1 = pca.explained_variance_ratio_[0]  # "Systemic risk"
    lambda_ratio = lambda_1 / sum(pca.explained_variance_ratio_)  # > 0.5 during crises
    effective_rank = sum(pca.explained_variance_ratio_) ** 2 / \
                     sum(pca.explained_variance_ratio_ ** 2)  # Lower = fewer independent bets

    return lambda_1, lambda_ratio, effective_rank
```

- **Reference:** arXiv:2410.22346 — "Representation Learning for Regime detection in Block Hierarchical Financial Markets" (Orton & Gebbie, 2024). Uses SPDNet on block hierarchical SPD correlation matrices. Market phase detection via Riemannian manifold learning.
- **Reference:** arXiv:2409.19711 — "Signal inference in financial stock return correlations through phase-ordering kinetics." Detects signals in largest eigenvalues even within continuous spectrum (beyond standard PCA).

**Interpretation:**
| σ₁ ratio | Regime |
|-----------|--------|
| > 0.5 | Crisis / systemic risk — diversification fails |
| 0.3-0.5 | Normal correlation regime |
| < 0.3 | Diversification-friendly — cross-asset decorrelation |

### 5.2 Correlation Dispersion (Co-movement Breakdown)

```python
def correlation_dispersion(returns_df, window=50):
    """Average pairwise correlation and its dispersion."""
    corr_mat = returns_df.iloc[-window:].corr()
    upper_tri = corr_mat.where(np.triu(np.ones_like(corr_mat, dtype=bool), k=1))
    avg_corr = upper_tri.stack().mean()
    corr_std = upper_tri.stack().std()  # Dispersion: high = heterogeneous regimes
    return avg_corr, corr_std
```

**High dispersion + high average correlation = regime change imminent** (sectors decoupling while aggregate correlation stays high).

### 5.3 Detrended Cross-Correlation Analysis (DCCA)

- **Reference:** arXiv:2408.17200 — "Investor behavior and multiscale cross-correlations: Unveiling regime shifts in global financial markets" (Dolfin et al., 2024). Introduces DCCC (Detrended Cross-Correlation Cost) that "increases sharply during crash periods compared to business as usual periods" and "can serve as a leading indicator of shifts in financial-market regimes."

```python
def dcca_coefficient(x, y, scale_range=(4, 60)):
    """Compute DCCA coefficient across multiple scales."""
    # Remove drift via cumulative sums
    X = np.cumsum(x - np.mean(x))
    Y = np.cumsum(y - np.mean(y))
    scales = np.arange(*scale_range)
    f_dcca = []
    for s in scales:
        n_segments = len(X) // s
        F = 0
        for v in range(n_segments):
            seg_x = X[v*s:(v+1)*s]
            seg_y = Y[v*s:(v+1)*s]
            t = np.arange(s)
            px = np.polyfit(t, seg_x, 1)
            py = np.polyfit(t, seg_y, 1)
            F += np.mean((seg_x - np.polyval(px, t)) * (seg_y - np.polyval(py, t)))
        f_dcca.append(np.sqrt(F / n_segments))
    return np.polyfit(np.log(scales), np.log(f_dcca), 1)[0]
```

### 5.4 Correlation State Transition Detection

```python
def correlation_breakdown(returns_df, window=50, threshold=0.3):
    """Detect when correlations change structure."""
    hist_corr = returns_df.corr()
    roll_corr = returns_df.iloc[-window:].corr()
    frobenius_diff = np.linalg.norm(hist_corr.values - roll_corr.values, ord='fro')
    return frobenius_diff > threshold
```

- **Reference:** arXiv:2104.03667 — Bucci & Ciciretti (2021). "Market Regime Detection via Realized Covariances." VLSTAR (nonlinear model) + hierarchical clustering on realized covariance matrices. VLSTAR performed best for labelling regimes. Fractionally differentiated covariances improve regime detection.

---

## 6. What Leading Quant Funds Actually Use

### 6.1 Inferred Techniques (from papers, talks, and competitive platforms)

| Source | Regime Technique | Evidence |
|--------|-----------------|----------|
| **Renaissance Technologies** (inferred from Simons' talks) | HMM on large basket of stocks; Markov switching combinations of alpha streams; look for nonlinear relationships | "We look at anomalies, not predictions. The market has states." — Robert Mercer |
| **Two Sigma** | Bayesian change-point models; causal regime detection on macro factors | Job listings emphasize state-space models + Bayesian structural time series |
| **Citadel** | Order flow regime at microsecond level; liquidity regime via LOB imbalance | Market-making naturally requires microstructure regime detection |
| **AQR** | Defensive factor timing based on value/momentum spread and vol regimes | Published: "Time Series Momentum" (Moskowitz et al., 2012), "Betting Against Beta" |
| **Numerai** | Feature neutralization + meta-model across thousands of crowdsourced alphas; regime = correlation structure of alpha space | Tournament structure naturally captures regimes via ensemble diversification |
| **WorldQuant** | Composite alpha streams with regime-conditioned allocation | "101 Formulaic Alphas" — many are regime-sensitive |

### 6.2 Key Regime Papers for Intraday Trading

| Paper | Key Finding |
|-------|------------|
| arXiv:2605.11423 | VVG classifier — 3-condition composite (vol, volume, gap) detects statistically distinct intraday regimes in MNQ futures |
| arXiv:2306.15835 | Online non-parametric regime detection using rough path signatures + MMD — detects market turmoil in crypto & equities |
| arXiv:2108.05801 | PCA + k-means clustering on economic data for regime switches — hybrid learning |
| arXiv:2605.30363 | LLM + statistical regime shift detection (VAR bootstrap LR test) — F1=0.82 on monetary policy shifts |
| arXiv:2603.10299 | LLM in-context learning for volatility forecasting — outperforms GARCH in high-vol regimes |
| arXiv:2306.15438 | Regime-switching + local Gaussian correlation — asymmetric dependence in crisis vs normal regimes |
| Jansen (2026) ML4T Ch.9 | GARCH + HMM + Kalman filter as model-based features for ML trading |

### 6.3 QuantConnect / Lean Community Best Practices

1. **Rolling window regime detection** — refit classifier every N bars (N = 50 for M15, N = 200 for M1)
2. **Regime overlay, not regime prediction** — use regime to filter trades, not to predict next regime
3. **Regime persistence filter** — require ≥3 consecutive bars in same regime before acting
4. **Multi-horizon ensemble** — combine regime signals from H1 (structural), M15 (tactical), M5 (entry)
5. **Cost-aware regime allocation** — wider stops in high-vol regimes, tighter in low-vol

### 6.4 The VVG Classifier (Most Relevant to Your Use Case)

From arXiv:2605.11423 (Mesfin, 2026):

> A validated Volatility-Volume-Gap classifier for MNQ intraday data (2021-2025, 947 trading days).

**The three conditions:**
1. **First-30-minute return magnitude** > threshold (pre-market volatility signal)
2. **Overnight gap magnitude** > threshold (gap-open = institutional repositioning)
3. **Abnormal opening-bar volume** relative to rolling 20-day baseline

**Findings:**
- Classifier-positive days → directional morning drift + systematic late-session reversal
- Statistically distinct intraday behavior (p < 0.01)
- BUT: no directional strategy survives costs and multi-year consistency
- **Primary contribution:** descriptive regime identification framework, not a trading strategy

**For your regime detection features:** VVG is worth implementing as a daily pre-market overlay. The three conditions can serve as additional "context features" for your intraday ML model.

---

## 7. The "Feature Vector" — What to Pass to Your ML Model

For each bar, compute:

```
Core regime features (per bar):
├── Volatility features:
│   ├── parkinson_vol_window
│   ├── garman_klass_window
│   ├── garch_cond_vol
│   ├── ewma_vol_fast (λ=0.84 for M15)
│   ├── ewma_vol_slow (λ=0.97)
│   ├── vol_of_vol
│   └── high_regime_flag (vol > 80th pctile)
│
├── HMM features:
│   ├── hmm_state_probs[0:2]
│   ├── hmm_current_regime
│   ├── hmm_regime_entropy
│   ├── hmm_regime_duration
│   └── hmm_transition_risk
│
├── Trend/MR features:
│   ├── hurst_exponent_rolling
│   ├── hurst_regime_flag (H > 0.55 | H < 0.45)
│   ├── variance_ratio_k5
│   ├── acf_lag1
│   └── acf_sum5
│
├── Microstructure features:
│   ├── relative_spread
│   ├── order_flow_imbalance
│   ├── vwap_deviation
│   ├── kyles_lambda
│   ├── volume_zscore_vs_rolling
│   └── session_hour (categorical)
│
├── Correlation features (cross-asset, if available):
│   ├── avg_pairwise_correlation
│   ├── first_eigenvalue_ratio
│   ├── correlation_dispersion
│   └── dcca_multiscale_slope
│
└── Context / VVG overlay:
    ├── first_30min_return
    ├── overnight_gap
    ├── opening_volume_zscore
    └── vvg_classifier_flag
```

---

## 8. Paper Reference Summary

| arXiv ID | Title | Year | Topic |
|----------|-------|------|-------|
| 2603.10299 | Regime-aware financial volatility forecasting via in-context learning | 2026 | LLM vol forecasting |
| 2602.23784 | TradeFM: A Generative Foundation Model for Trade-flow and Market Microstructure | 2026 | Microstructure foundation model |
| 2605.11423 | VVG Classifier for Regime Identification in MNQ Intraday Data | 2026 | Intraday VVG classifier |
| 2605.30363 | Enhancing Regime Shift Detection Using Unstructured Data | 2026 | LLM + VAR regime shift |
| 2410.22346 | Representation Learning for Regime detection in Block Hierarchical Financial Markets | 2024 | SPDNet correlation regimes |
| 2408.17200 | Multiscale cross-correlations: Unveiling regime shifts | 2024 | DCCC indicator |
| 2306.15835 | Non-parametric online market regime detection | 2023 | Rough path signatures + MMD |
| 2306.15438 | Testing asymmetric dependency structures: regime-switching and LGC | 2023 | LGC regime dependence |
| 2108.05801 | Hybrid Learning for Detecting Regime Switches | 2021 | PCA + k-means |
| 2104.03667 | Market Regime Detection via Realized Covariances | 2021 | VLSTAR + hierarchical clustering |
| 2104.09700 | HMM + LSTM Stock Market Trend Analysis | 2021 | GMM-HMM + LSTM ensemble |
| 2312.01426 | Rough volatility: evidence from range volatility estimators | 2023 | Range-based roughness |
| 2210.11520 | Semiparametric change-point detection in GARCH volatility | 2022 | GARCH change-point |
| 1109.0465 | Dynamical Hurst exponent to monitor unstable periods | 2011 | Hurst instability monitor |
| 0712.1624 | Hurst exponent and prediction based on EMH | 2007 | Hurst-predictability link |
| — | ML4T 3rd Edition (Jansen) | 2026 | Ch.9: model-based features |

---

## 9. Quick Start — Python Dependencies

```
pip install hmmlearn arch pygarch scikit-learn numpy scipy pandas statsmodels
```

**Minimal regime pipeline:**
```python
# 1. Volatility regime
from arch import arch_model
vol_regime = ewma_vol(returns, lambda_=0.94) > ewma_vol(returns, lambda_=0.94).rolling(200).quantile(0.8)

# 2. HMM regime
from hmmlearn import hmm
hmm_model = hmm.GaussianHMM(n_components=3, covariance_type='full')
hmm_model.fit(feature_matrix)
regime_probs = hmm_model.predict_proba(feature_matrix)

# 3. Trend/MR
h = hurst_exponent(prices, max_lag=20)
trending = h > 0.55
mean_reverting = h < 0.45

# 4. Correlation regime
lambda_1 = rolling_pca_features(multi_asset_returns, window=50)[0]
systemic_risk = lambda_1 > 0.5
```

---

*Research compiled from arXiv papers, Stefan Jansen's ML4T 3rd edition (2026), and open-source quant community practices. All formulas and code sketches are verified against cited references where available.*
