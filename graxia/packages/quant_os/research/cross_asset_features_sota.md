# State-of-the-Art Cross-Asset Features for Quant Trading

> Target assets: XAUUSD, EURUSD, GBPUSD, USDCAD, USDJPY, USDCHF, NZDUSD, AUDUSD, BTCUSD, ETHUSD, NAS100, US30, XAGUSD
> Research compiled 2026 — academic literature + sell-side research + practitioner knowledge

---

## 1. Cross-Asset Momentum / Spillover

### 1.1 Dollar Index (DXY) Momentum → FX Returns

**Formula:**
```
DXY_ret[t] = log(DXY[t]) - log(DXY[t-1])
DXY_roll_N[t] = prod(1 + DXY_ret[t-i]) - 1,   i=0..N-1
feature = DXY_roll_N[t]  # e.g. N=5, 20, 50 bars
```
**Assets:** DXY → EURUSD (strongest, DXY is ~57% EUR), GBPUSD, all USD pairs.
**Implementation:**
```python
# DXY is ~57.6% EUR — the anti-EURUSD proxy
# DXY returns negatively predict EURUSD, GBPUSD, AUDUSD
dxy_ret = np.log(dxy).diff()
for window in [5, 10, 20, 50]:
    df[f"dxy_mom_{window}h"] = dxy_ret.rolling(window).sum()
```
**Timeframe:** H1, H4, D1. H1 best for intraday regime detection.
**Predictive power:** HIGH for all USD pairs. DXY is THE dominant feature for EURUSD, GBPUSD, AUDUSD. DXY momentum often leads FX moves by 1-3 bars.

### 1.2 Gold (XAUUSD) → FX Risk-Off Proxy

**Formula:**
```
gold_ret[t] = log(XAUUSD[t]) - log(XAUUSD[t-1])
feature_gold_mom = gold_ret rolling N
feature_gold_diff = XAUUSD - XAUUSD.rolling(N).mean()
```
**Assets:** XAUUSD → EURUSD (positive correlation in risk-on), USDJPY (negative — gold up means risk-off, yen safe haven).
**Implementation:**
```python
gold_ret = np.log(gold_bid).diff()
df["gold_mom_5h"] = gold_ret.rolling(5).sum()
df["gold_mom_20h"] = gold_ret.rolling(20).sum()
df["gold_rel_str"] = (np.log(gold_bid) - np.log(gold_bid.rolling(50).mean()))
```
**Timeframe:** H1, H4. Gold is slower — H4/D1 better signal.
**Predictive power:** MODERATE-HIGH. Gold leads USDJPY and commodity currencies (AUD, NZD, CAD). Gold spikes often precede broad USD weakness.

### 1.3 Bitcoin → Risk-On/Risk-Off Leading Indicator

**Formula:**
```
btc_ret[t] = log(BTCUSD[t]) - log(BTCUSD[t-1])
btc_shock[t] = btc_ret[t] / btc_vol.rolling(20)[t]  # volatility-normalized
```
**Assets:** BTCUSD → NAS100 (strong positive), AUDUSD (risk proxy), USDJPY (risk-off proxy).
**Implementation:**
```python
btc_ret = np.log(btc_usd).diff()
btc_vol = btc_ret.rolling(20).std()
df["btc_shock"] = btc_ret / btc_vol  # z-score style
df["btc_mom_12h"] = btc_ret.rolling(12).sum()
df["btc_drawdown_5h"] = btc_ret.rolling(5).min()  # max pain in 5h
```
**Timeframe:** H1 works because crypto trades 24/7. BTC often moves first, then NAS100 follows.
**Predictive power:** MODERATE-HIGH for NAS100 and AUDUSD. BTC's 24/7 nature means it prices in weekend news before FX opens Monday — "crypto Monday gap fill" is a real effect.

### 1.4 Commodity → Currency Channel

**Formula:**
```
aud_gold_corr[t] = rolling_corr(AUDUSD_ret, XAUUSD_ret, N=60)
cad_oil_corr[t] = rolling_corr(USDCAD_ret, -WTI_ret, N=60)  # inverted because USDCAD
nzd_dairy_corr[t] = rolling_corr(NZDUSD_ret, XAUUSD_ret, N=60)  # NZD proxy
```
**Assets:** AUDUSD ↔ XAUUSD (+), USDCAD ↔ WTI oil (-), NZDUSD ↔ soft commodities.
**Implementation:**
```python
# AUDUSD = commodity currency — gold + iron ore + copper proxy
df["aud_gold_spread"] = np.log(audusd) - 0.5 * np.log(gold)
df["aud_gold_spread_z"] = (df["aud_gold_spread"] - df["aud_gold_spread"].rolling(50).mean()) / df["aud_gold_spread"].rolling(50).std()

# USDCAD = anti-oil proxy (Canada exports oil)
# Without oil data: use XAUUSD as commodity proxy
df["cad_commodity_spread"] = np.log(usdcad_bid) + 0.3 * np.log(gold)  # gold up → CAD up → USDCAD down
```
**Timeframe:** H4 to D1. Commodity-currency relationships work on slower timeframes.
**Predictive power:** MODERATE for AUDUSD (gold proxy), USDCAD. Slow signal, better for regime than tick-level.

### 1.5 Risk-On/Risk-Off (RORO) Index

**Formula:**
```
# Risk-on assets get +1 weight (rise = risk-on)
# Risk-off assets get -1 weight (rise = risk-off)
roro[t] = w1*NAS100_ret[t] + w2*BTCUSD_ret[t] + w3*AUDUSD_ret[t] + w4*EURUSD_ret[t]
        - w5*USDJPY_ret[t] - w6*USDCHF_ret[t] - w7*XAUUSD_ret[t]
# Weights from inverse-vol parity: w_i = 1/σ_i
```
**Assets:** Every target asset. The RORO index captures market-wide risk appetite.
**Implementation:**
```python
def roro_index(returns_dict, lookback=20):
    """
    returns_dict: {"NAS100": series, "BTCUSD": series, ...}
    Risk-on: NAS100, BTCUSD, AUDUSD, NZDUSD, EURUSD (carry receivers)
    Risk-off: USDJPY, USDCHF, XAUUSD (safe havens)
    """
    risk_on = ["NAS100", "BTCUSD", "AUDUSD", "NZDUSD", "EURUSD"]
    risk_off = ["USDJPY", "USDCHF", "XAUUSD"]

    vols = {k: v.rolling(lookback).std() for k, v in returns_dict.items()}
    w_on = {k: 1.0 / vols[k] for k in risk_on if k in vols}
    w_off = {k: 1.0 / vols[k] for k in risk_off if k in vols}

    roro = sum(w_on[k] * returns_dict[k] for k in w_on) - sum(w_off[k] * returns_dict[k] for k in w_off)
    roro /= len(w_on) + len(w_off)  # normalize
    return roro

df["roro"] = roro_index(rets)
df["roro_mom_5h"] = df["roro"].rolling(5).sum()
df["roro_regime"] = (df["roro_mom_5h"] > 0).astype(int)  # 1=risk-on, 0=risk-off
```
**Timeframe:** H1, recalculated every bar. Stable signal.
**Predictive power:** HIGH for regime classification. During risk-on: long AUD, NZD, NAS100; short USDJPY, USDCHF. During risk-off: reverse.

### 1.6 Crypto Volatility → VIX Proxy

**Formula:**
```
crypto_vix[t] = 10 * std(log(ETHUSD[t-i]/ETHUSD[t-i-1]), i=0..23)  # 24h rolling on H1
btc_eth_spread_vol[t] = std(log(BTCUSD)/log(ETHUSD) ratio, 20h)
```
**Assets:** Crypto vol → NAS100, FX vol. Crypto vol spikes often precede equity vol spikes.
**Implementation:**
```python
# Crypto volatility as fear/greed proxy
df["crypto_vol_24h"] = btc_ret.rolling(24).std() * np.sqrt(24)  # annualized proxy
df["crypto_vol_shock"] = df["crypto_vol_24h"] / df["crypto_vol_24h"].rolling(120).mean()  # vol-of-vol

# BTC/ETH ratio — risk-on when BTC underperforms (alt season)
btc_eth_ratio = np.log(btc_usd) / np.log(eth_usd)
df["btc_eth_ratio_z"] = (btc_eth_ratio - btc_eth_ratio.rolling(100).mean()) / btc_eth_ratio.rolling(100).std()
```
**Timeframe:** H1. Crypto vol regimes switch fast.
**Predictive power:** MODERATE for NAS100 and risk-sensitive FX. Crypto vol > 2x normal = risk-off regime ahead.

### 1.7 Cross-Asset Rotational Momentum (WorldQuant-style)

**Formula:**
```
# For each target asset, compute "how many other assets are trending in the same direction?"
rotation_score[t] = sign(ret_target[t]) * sum(sign(ret_other[t])),  for all other assets
```
**Assets:** All → each individually.
**Implementation:**
```python
def rotational_alignment(rets_df, lookback=20):
    """How aligned is this asset's trend with the rest of the basket?"""
    moms = rets_df.rolling(lookback).sum()
    sign_moms = np.sign(moms)
    # For each asset, fraction of others trending same direction
    n = len(sign_moms.columns)
    alignment = {}
    for col in sign_moms.columns:
        same_dir = (sign_moms[col].values[:, None] * sign_moms.drop(columns=col).values).sum(axis=1)
        alignment[f"{col}_align"] = same_dir / (n - 1)
    return pd.DataFrame(alignment)
```
**Timeframe:** H1, H4.
**Predictive power:** MODERATE. Broad asset alignment = stronger trends. Divergence = reversal likely.

---

## 2. Correlation Structure Features

### 2.1 Rolling Pairwise Correlations

**Formula:**
```
corr_ij[t] = rolling_corr(ret_i, ret_j, window=60)  # on H1 = ~2.5 days
feature_corr_avg[t] = mean(corr_ij[t] for all i != j)  # average pairwise
feature_corr_max[t] = max(abs(corr_ij[t]))  # strongest pairwise
```
**Assets:** Every pair within the basket. Most predictive: EURUSD-XAUUSD, AUDUSD-XAUUSD, NAS100-BTCUSD.
**Implementation:**
```python
from numpy.lib.stride_tricks import sliding_window_view

def rolling_pairwise_features(rets, window=60):
    """Returns: avg_corr, max_corr, corr_dispersion for each time step"""
    n_assets = rets.shape[1]
    n = len(rets)
    avg_corr = np.full(n, np.nan)
    max_corr = np.full(n, np.nan)
    # Efficient rolling corr via sliding window
    for i in range(window, n):
        win = rets.iloc[i-window:i].values
        C = np.corrcoef(win.T)
        upper = C[np.triu_indices(n_assets, k=1)]
        avg_corr[i] = np.mean(upper)
        max_corr[i] = np.max(np.abs(upper))
    return avg_corr, max_corr

df["avg_pairwise_corr_60h"] = avg_corr
df["max_pairwise_corr_60h"] = max_corr
df["corr_dispersion"] = max_corr - avg_corr  # high dispersion = idiosyncratic moves
```
**Timeframe:** H1 with window 60-120 (2.5-5 days). Shorter windows are noisy.
**Predictive power:** MODERATE. Average correlation spike → systemic event / risk-off. Correlation breakdown (sudden drop) → regime shift.

### 2.2 PCA on Multiple Assets → Top PCs

**Formula:**
```
returns_matrix[N_assets x T] → eigendecomposition
PC1[t] = sum(w_i * ret_i[t])   # "market" component
PC2[t] = sum(v_i * ret_i[t])   # "FX vs crypto" or "risk vs safety"
explained_variance_ratio_N[t] = sum(lambda_i, i=1..N) / sum(all lambdas)
```
**Assets:** All 13 assets. PC1 = "global risk factor." PC2 = "dollar factor."
**Implementation:**
```python
from sklearn.decomposition import PCA

def pca_features(rets, lookback=100, n_components=3):
    pca = PCA(n_components=n_components)
    features = {}

    for t in range(lookback, len(rets)):
        window = rets.iloc[t-lookback:t]
        pca.fit(window)
        # Project current return onto PCs
        scores = pca.transform(rets.iloc[t:t+1].values)[0]
        for j in range(n_components):
            features.setdefault(f"pc{j+1}_score", [np.nan]*len(rets))
            features[f"pc{j+1}_score"].append(scores[j])
        features.setdefault("pc1_var_ratio", [np.nan]*len(rets))
        features["pc1_var_ratio"].append(pca.explained_variance_ratio_[0])

    # Derived features
    df["pc1"] = features["pc1_score"]  # global risk factor loading
    df["pc2"] = features["pc2_score"]  # dollar/fx factor
    df["pc1_var_ratio"] = features["pc1_var_ratio"]  # concentration of risk
    df["pc_residual"] = rets - pca.inverse_transform(scores)  # idiosyncratic
    return df
```
**Timeframe:** H1 with 100-bar window (~4 days of hourly data).
**Predictive power:** HIGH. PC1 predicts all assets (absorbing common risk). PC1 variance ratio > 0.5 = high systemic risk → trend following works. PC residual = mean-reverting alpha.

### 2.3 Dynamic Conditional Correlation (DCC-Beta)

**Formula (simplified GARCH-DCC):**
```
# Simplified DCC using EWMA
sigma_ij[t] = lambda * sigma_ij[t-1] + (1-lambda) * ret_i[t-1] * ret_j[t-1]
rho_ij[t] = sigma_ij[t] / sqrt(sigma_ii[t] * sigma_jj[t])
dcc_diff[t] = rho_ij[t] - rho_ij[t-1]  # correlation change
```
**Assets:** All pairs. Most useful: DCC of DXY↔XAUUSD, NAS100↔BTCUSD, EURUSD↔USDJPY.
**Implementation:**
```python
def ewma_dcc(rets, lambda_=0.94):
    """Exponential-weighted moving average DCC (RiskMetrics style)"""
    n_assets = rets.shape[1]
    T = len(rets)
    # Initialize
    cov_matrices = np.zeros((T, n_assets, n_assets))
    corr_matrices = np.zeros((T, n_assets, n_assets))
    # Run EWMA
    cov = np.outer(rets.iloc[0], rets.iloc[0])
    for t in range(1, T):
        r = rets.iloc[t].values
        cov = lambda_ * cov + (1 - lambda_) * np.outer(r, r)
        cov_matrices[t] = cov
        D = np.sqrt(np.diag(cov))
        corr_matrices[t] = cov / np.outer(D, D)

    # Extract features
    # DCC beta: avg correlation of asset i with all others
    dcc_betas = corr_matrices.mean(axis=2)  # T x n_assets
    # Correlation change (acceleration)
    dcc_delta = np.diff(corr_matrices, axis=0).mean(axis=2).mean(axis=2)  # avg corr change
    return dcc_betas, dcc_delta

df["dcc_beta_eurusd"] = dcc_betas[:, asset_idx["EURUSD"]]
df["dcc_delta"] = dcc_delta  # positive = correlations rising (systemic), negative = decorrelation
```
**Timeframe:** H1, D1. Lambda=0.94 (RiskMetrics standard) gives ~14 day half-life. H1 recalc ~100 bars instead.
**Predictive power:** HIGH for regime detection. Rising DCC = risk-off / systemic. Falling DCC = dispersion / alpha opportunity. DCC beta > 0.8 = asset moves with the herd.

### 2.4 Correlation Breakdown Detection (Crisis Indicator)

**Formula:**
```
# Mahalanobis distance of current correlation matrix from history
corr_vec[t] = upper_triangle(corr_matrix[t])  # flatten upper triangle
corr_mean[t] = rolling_mean(corr_vec, 500h)
corr_cov[t] = rolling_cov(corr_vec, 500h)
maha_dist[t] = sqrt((corr_vec[t] - corr_mean[t])' * inv(corr_cov[t]) * (corr_vec[t] - corr_mean[t]))
crisis_signal[t] = maha_dist[t] > 3.0  # 3-sigma deviation
```
**Assets:** All. Crisis = everything correlates to 1.
**Implementation:**
```python
def correlation_breakdown(rets, window=500, threshold=3.0):
    """Detect when correlation structure breaks from history"""
    n_assets = rets.shape[1]
    tri_idx = np.triu_indices(n_assets, k=1)
    n_pairs = len(tri_idx[0])
    T = len(rets)

    corr_vecs = np.zeros((T, n_pairs))
    for t in range(60, T):  # need min window for corr
        win = rets.iloc[max(0, t-60):t+1].values
        C = np.corrcoef(win.T)
        corr_vecs[t] = C[tri_idx]

    # Rolling Mahalanobis (expensive — use EWMA for mean/cov)
    maha = np.full(T, np.nan)
    for t in range(window, T):
        hist = corr_vecs[t-window:t]
        mu = hist.mean(axis=0)
        Sig = np.cov(hist.T) + 1e-6 * np.eye(n_pairs)
        try:
            maha[t] = np.sqrt((corr_vecs[t] - mu) @ np.linalg.solve(Sig, corr_vecs[t] - mu))
        except:
            pass
    return maha

df["corr_breakdown"] = maha
df["crisis_mode"] = (df["corr_breakdown"] > 3.0).astype(int)
```
**Timeframe:** H1 with 500 bar history (~21 days of hourly data).
**Predictive power:** HIGH-LOW asymmetry. In crisis mode: trend-following works, mean-reversion fails, diversification disappears. In normal mode: mean-reversion works, carry trades work.

### 2.5 Eigenvalue Ratios (Absorption Ratio)

**Formula:**
```
# Absorption Ratio (Kritzman, Li, Page, Turkington 2011)
# Fraction of total variance explained by top K PCs
AR[t] = sum(lambda_i, i=1..K) / sum(lambda_i, i=1..N)
# K = floor(N/5) typically. For 13 assets: K=2 or 3
# high AR = markets are tightly coupled (risk rises)
```
**Assets:** All 13 assets.
**Implementation:**
```python
def absorption_ratio(rets, window=100, k=None):
    """Kritzman et al. (2011) Absorption Ratio"""
    n_assets = rets.shape[1]
    if k is None:
        k = max(1, n_assets // 5)
    T = len(rets)
    ar = np.full(T, np.nan)
    for t in range(window, T):
        win = rets.iloc[t-window:t].values
        eigenvalues = np.linalg.eigvalsh(np.cov(win.T))
        eigenvalues = eigenvalues[::-1]  # descending
        ar[t] = eigenvalues[:k].sum() / eigenvalues.sum()
    return ar

# Also: max eigenvalue / sum (market concentration)
df["absorption_ratio"] = ar
df["max_eigen_ratio"] = max_eigenvalue / total  # single-factor dominance

# Eigenvalue entropy (dispersion of risk)
def eigen_entropy(rets, window=100):
    ...
    p = eigenvalues / eigenvalues.sum()
    entropy = -np.sum(p * np.log(p + 1e-10)) / np.log(n_assets)  # normalized
    return entropy  # 1 = all equal, 0 = one dominates
```
**Timeframe:** H1, 100-bar. Also compute on D1 for slower signal.
**Predictive power:** HIGH for risk regime. AR spiking = unity correlation → hedge, reduce exposure. AR falling = diversifying markets → take risk.

---

## 3. Relative Value / Pairs Features

### 3.1 Cointegration-Based Spread

**Formula:**
```
# Johansen or Engle-Granger cointegration
# Example: XAUUSD and AUDUSD are cointegrated (gold producer currency)
spread[t] = log(AUDUSD[t]) - beta * log(XAUUSD[t]) - alpha
zscore[t] = (spread[t] - mean(spread[t-lookback:t])) / std(spread[t-lookback:t])
```
**Assets:** XAUUSD-AUDUSD (gold miner), EURUSD-GBPUSD (European cluster), BTCUSD-ETHUSD (crypto pair), XAUUSD-XAGUSD (gold-silver ratio).
**Implementation:**
```python
from statsmodels.tsa.stattools import coint
from sklearn.linear_model import LinearRegression

def cointegration_spread(y, x, lookback=500, hedge_ratio_lookback=500):
    """Rolling cointegration z-score"""
    # Fit hedge ratio on expanding/lookback window
    y_log = np.log(y)
    x_log = np.log(x)

    lr = LinearRegression()
    T = len(y)
    zscore = np.full(T, np.nan)

    for t in range(hedge_ratio_lookback, T):
        x_win = x_log.iloc[t-hedge_ratio_lookback:t].values.reshape(-1, 1)
        y_win = y_log.iloc[t-hedge_ratio_lookback:t].values
        lr.fit(x_win, y_win)
        beta = lr.coef_[0]
        alpha = lr.intercept_
        spread = y_log.iloc[t-hedge_ratio_lookback:t] - beta * x_log.iloc[t-hedge_ratio_lookback:t] - alpha
        zscore[t] = (spread.iloc[-1] - spread.mean()) / spread.std()

    return zscore

# Key pairs to monitor
df["aud_gold_z"] = cointegration_spread(audusd, xauusd)
df["eur_gbp_z"] = cointegration_spread(eurusd, gbpusd)
df["btc_eth_z"] = cointegration_spread(btcusd, ethusd)
df["gold_silver_z"] = cointegration_spread(xauusd, xagusd)
```
**Timeframe:** H1 with 500-bar hedge ratio estimation (~21 days). Signal valid for 1-5 days after estimation.
**Predictive power:** MODERATE. Mean-reversion of spreads. Best for AUDUSD-XAUUSD and BTC-ETH. Z > 2 → short spread, Z < -2 → long spread. Works better in range-bound regimes.

### 3.2 Gold-Silver Ratio (Macro Regime)

**Formula:**
```
xau_xag_ratio[t] = XAUUSD[t] / XAGUSD[t]
ratio_z[t] = (ratio[t] - SMA(ratio, 100)) / std(ratio, 100)
```
**Assets:** XAGUSD → XAUUSD (and vice versa). Ratio spike = risk-off / deflation fear.
**Implementation:**
```python
df["xau_xag_ratio"] = xauusd / xagusd
df["xau_xag_z"] = (df["xau_xag_ratio"] - df["xau_xag_ratio"].rolling(100).mean()) / df["xau_xag_ratio"].rolling(100).std()
df["xau_xag_mom"] = np.log(df["xau_xag_ratio"]).diff(20)  # 20-bar trend
```
**Timeframe:** D1 preferred (macro signal), H4 works. H1 is noisy.
**Predictive power:** MODERATE for gold/silver individually. High ratio (>90) = silver undervalued → buy XAGUSD. Rising ratio = risk-off.

### 3.3 Currency Strength Index

**Formula:**
```
# For each currency, average its performance against all others
# USD_strength[t] = mean(ret of all XXXUSD inverted, USDXXX direct)
# EUR_strength[t] from EURUSD (+), EURGBP (derived), EURJPY (derived)
csi[t] = (1/N) * sum(ret_i[t] for i in the currency's pairs)
csi_mom[t] = csi[t] rolling_N
csi_diff[t] = csi[t] - csi_avg[t]  # deviation from fair value
```
**Assets:** All FX pairs. Each pair gets both currencies' strength as features.
**Implementation:**
```python
def currency_strength_index(pairs_returns, base_map):
    """
    base_map: {"EURUSD": ("EUR", "USD"), "GBPUSD": ("GBP", "USD"), ...}
    Returns: DataFrame with columns: USD, EUR, GBP, JPY, CHF, CAD, AUD, NZD
    """
    currencies = ["USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"]
    csi = {c: pd.Series(0.0, index=pairs_returns.index) for c in currencies}
    counts = {c: 0 for c in currencies}

    for pair, ret in pairs_returns.items():
        base, quote = base_map[pair]
        csi[base] += ret
        csi[quote] -= ret
        counts[base] += 1
        counts[quote] += 1

    for c in currencies:
        csi[c] /= counts[c]

    csi_df = pd.DataFrame(csi)
    return csi_df

# Features from CSI
csi = currency_strength_index(pairs_rets, base_map)
df["usd_strength_5h"] = csi["USD"].rolling(5).sum()
df["eur_strength_5h"] = csi["EUR"].rolling(5).sum()
df["csi_dispersion"] = csi.std(axis=1)  # how spread out are currencies?
```
**Timeframe:** H1, recalulated each bar.
**Predictive power:** HIGH for FX. USD strength is THE most important FX feature. CSI dispersion high = trending FX market = trend-following. Low = mean-reverting.

### 3.4 Composite Precious Metals Index

**Formula:**
```
# Combine gold + silver into composite PM index
pm_index[t] = w1 * log(XAUUSD[t]) + w2 * log(XAGUSD[t])  # w1+w2=1
pm_mom[t] = pm_index[t] - pm_index[t-N]
pm_vs_fx[t] = pm_mom[t] / dxy_mom[t]  # relative strength of PM vs dollar
```
**Assets:** XAUUSD, XAGUSD → all FX pairs (as commodity/risk signal).
**Implementation:**
```python
df["pm_index"] = 0.7 * np.log(xauusd) + 0.3 * np.log(xagusd)
df["pm_mom_20h"] = df["pm_index"].diff(20)
df["pm_vs_dxy"] = df["pm_mom_20h"] - np.log(dxy).diff(20)  # PM leading or lagging dollar?
```
**Timeframe:** H4, D1. PM index is slower-moving.
**Predictive power:** MODERATE. PM index up + DXY down = classic risk-on for commodity currencies.

### 3.5 Relative Value Z-Score

**Formula:**
```
# "Is this asset cheap or expensive relative to its history and basket?"
rv[t] = log(price[t]) - log(SMA_N(price[t]))
rv_norm[t] = rv[t] / std(rv, N)
# Also: relative to its typical correlation-weighted basket
basket[t] = sum(w_i * log(price_i[t]))
rv_vs_basket[t] = log(price[t]) - basket[t]
```
**Assets:** Every asset individually.
**Implementation:**
```python
def relative_value_z(price, lookback=100):
    log_p = np.log(price)
    z = (log_p - log_p.rolling(lookback).mean()) / log_p.rolling(lookback).std()
    return z

for asset in all_assets:
    df[f"{asset}_rv_z"] = relative_value_z(df[asset])
    df[f"{asset}_rv_20h"] = np.log(df[asset]).diff(20)  # 20-bar momentum = trend strength
```
**Timeframe:** H1, works at all timeframes.
**Predictive power:** LOW-MODERATE alone. Z-score mean-reversion works in range-bound but fails in trends. Combine with regime filter.

---

## 4. Macro Surprise / Sentiment Features

### 4.1 Extracting Macro Surprise from Asset Moves

**Formula:**
```
# "What did the bond market just tell us about the economy?"
# Without bond data: use inter-currency relationships

# USDJPY = risk-off barometer (JPY = safe haven)
# Rule: USDJPY down = risk-off = bad for equities, good for gold
yen_riskoff[t] = -USDJPY_ret[t]  # positive = risk-off

# Extract "implied rate differential" from FX moves
# EURUSD - 2yr EU-US spread ≈ "risk premium" residual
usd_risk_premium[t] = -EURUSD_ret[t] - DXY_ret[t]  # residual dollar bid

# "What did gold tell us about inflation expectations?"
gold_infl_signal[t] = XAUUSD_ret[t] - (-DXY_ret[t])  # gold move NOT explained by dollar
```
**Assets:** USDJPY, USDCHF (safe havens), NAS100, BTCUSD (risk assets).
**Implementation:**
```python
# Decompose gold move into "dollar component" and "residual"
df["gold_dollar_component"] = -0.5 * dxy_ret  # beta ~0.5
df["gold_residual"] = gold_ret - df["gold_dollar_component"]  # "pure gold" signal

# Safe haven flow detection
# When NAS100 down + USDJPY down + XAUUSD up = safe haven rotation
df["safe_haven_score"] = -nas_ret + (-usdjpy_ret) + 0.5 * gold_ret
df["safe_haven_z"] = (df["safe_haven_score"] - df["safe_haven_score"].rolling(50).mean()) / df["safe_haven_score"].rolling(50).std()

# Risk appetite decomposition
# When risky assets rise together AND safe havens fall together = genuine risk-on
df["pure_risk_on"] = (nas_ret > 0) & (audusd_ret > 0) & (usdjpy_ret > 0) & (gold_ret < 0)
df["risk_on_score_5h"] = df["pure_risk_on"].rolling(5).sum()

# Divergence signals: risk assets UP but safe haven NOT falling = fragile rally
df["fragile_rally"] = (nas_ret > 0) & (gold_ret > 0)  # gold should not rally in risk-on
```
**Timeframe:** H1 for detection. H4 for confirmation.
**Predictive power:** MODERATE-HIGH. Safe haven score > 2σ = genuine risk-off, gold and yen outperforming. Fragile rallies (gold + stocks both up) often reverse.

### 4.2 Carry Trade Barometer

**Formula:**
```
# Carry = long high-yielding currency, short low-yielding
# Without direct rate data: use momentum of interest-rate-sensitive pairs
# AUDJPY, NZDJPY = classic carry proxies
# When carry unwinds: AUDJPY down, NZDJPY down, USDJPY down
carry_barometer[t] = AUDJPY_ret[t] + NZDJPY_ret[t]  # derived from available pairs
# Or: basket of commodity currencies vs funding currencies
carry[t] = (AUDUSD_ret[t] + NZDUSD_ret[t]) - 0.5*(USDJPY_ret[t] + USDCHF_ret[t])
```
**Assets:** All FX. Carry barometer captures global risk appetite.
**Implementation:**
```python
# Derive cross-rates from USD pairs
df["audjpy_ret"] = audusd_ret + usdjpy_ret  # AUDUSD + USDJPY = cross AUDJPY
df["nzdjpy_ret"] = nzdusd_ret + usdjpy_ret
df["eurjpy_ret"] = eurusd_ret + usdjpy_ret
df["gbpjpy_ret"] = gbpusd_ret + usdjpy_ret

# Carry barometer = average of all JPY crosses (positive = carry works)
df["carry_barometer"] = (df["audjpy_ret"] + df["nzdjpy_ret"] + df["eurjpy_ret"] + df["gbpjpy_ret"]) / 4
df["carry_unwind_signal"] = (df["carry_barometer"].rolling(5).sum() < -0.005).astype(int)

# Funding currency strength: JPY + CHF strengthening = carry unwind
df["funding_strength"] = usdjpy_ret + usdchf_ret  # positive = USD up, i.e. funding currencies weakening = risk-on
```
**Timeframe:** H1, H4.
**Predictive power:** HIGH for FX. Carry unwind = all yen crosses fall simultaneously = risk-off. In carry unwind: sell AUD, NZD, EUR; buy JPY, CHF.

### 4.3 Inflation Expectations Proxy

**Formula:**
```
# From gold: breakeven inflation ≈ gold momentum over long windows
infl_exp_3m[t] = log(XAUUSD[t]) - log(XAUUSD[t-1440])  # ~3 months on H1

# Gold vs silver ratio rising = deflation fear = inflation expectations falling
infl_exp[t] = -log(XAUUSD[t]/XAGUSD[t])  # silver outperforms = inflation expectations rising

# "Commodity currency" basket as inflation proxy
commod_fx[t] = (AUDUSD_ret[t] + NZDUSD_ret[t] + 0.5*USDCAD_ret[t]) / 3  # CAD inverted
```
**Assets:** XAUUSD, XAGUSD → all.
**Implementation:**
```python
df["gold_trend_3m"] = np.log(xauusd).diff(1440)  # proxy for long-term inflation view
df["silver_gold_ratio"] = xagusd / xauusd  # silver outperforms = industrial demand = growth
df["silver_gold_mom"] = np.log(df["silver_gold_ratio"]).diff(20)  # 20-bar trend

# Real yield proxy (gold + dollar combined)
# Gold up + USD down = real yields falling = dovish Fed = risk-on for equities
df["real_yield_proxy"] = gold_ret - 0.5 * dxy_ret  # higher = real yields falling
```
**Timeframe:** D1 for long-term signal, H4 for tactical.
**Predictive power:** MODERATE. Inflation proxy affects gold and commodity currencies. Slow-moving but persistent.

### 4.4 Risk Parity Decomposition Features

**Formula:**
```
# Decompose each asset's return into:
# 1. Carry component (differential with funding)
# 2. Trend component (trailing momentum)
# 3. Value component (deviation from long-term mean)

rp_trend[t] = ret[t-N:t].sum() / sigma[t-N:t]  # Sharpe-style trend
rp_value[t] = (log(price[t]) - log(price[t-M])) / sigma_value[t]  # normalized value
rp_carry[t] = diff_of_interest_rates[t]  # if available, else proxy

rp_composite[t] = w_trend * rp_trend[t] + w_value * rp_value[t] + w_carry * rp_carry[t]
```
**Assets:** Each asset individually. Composite feature feeds into prediction.
**Implementation:**
```python
def risk_parity_decomposition(rets, price, lookback_trend=60, lookback_value=500):
    vol = rets.rolling(lookback_trend).std()
    trend = rets.rolling(lookback_trend).sum() / (vol + 1e-8)  # risk-adjusted momentum

    log_p = np.log(price)
    value = (log_p - log_p.rolling(lookback_value).mean()) / log_p.rolling(lookback_value).std()

    # Combine: trend wins in trending markets, value wins at extremes
    composite = 0.5 * trend + 0.5 * value
    return trend, value, composite

for asset in all_assets:
    trend, value, comp = risk_parity_decomposition(df[f"{asset}_ret"], df[asset])
    df[f"{asset}_rp_trend"] = trend
    df[f"{asset}_rp_value"] = value
    df[f"{asset}_rp_composite"] = comp
```
**Timeframe:** H1 for trend, H4/D1 for value component.
**Predictive power:** MODERATE. Trend component predicts continuation. Value component predicts reversals at extremes. Composite works for regime-adaptive strategies.

---

## 5. Intermarket Lead-Lag

### 5.1 Granger Causality Features

**Formula:**
```
# Test: does asset X's past return help predict asset Y's current return?
# For each pair (i,j), compute F-statistic of:
# ret_Y[t] = alpha + sum(beta_k * ret_Y[t-k]) + sum(gamma_k * ret_X[t-k]) + eps[t]
# Feature: granger_fstat_ij[t] (rolling), granger_significant_ij[t] (boolean)
# Feature: direction_ij[t] = sign(sum(gamma_k))  # does X lead Y up or down?
```
**Assets:** All pairs. Key: DXY→EURUSD, XAUUSD→AUDUSD, BTC→NAS100, DXY→XAUUSD.
**Implementation:**
```python
from statsmodels.tsa.stattools import grangercausalitytests

def rolling_granger_features(x_ret, y_ret, window=200, max_lag=5):
    """Rolling Granger causality: does X lead Y?"""
    T = len(x_ret)
    f_stats = np.full(T, np.nan)
    p_values = np.full(T, np.nan)
    direction = np.full(T, np.nan)  # positive = X leads Y up

    for t in range(window, T):
        data = pd.DataFrame({
            "Y": y_ret.iloc[t-window:t].values,
            "X": x_ret.iloc[t-window:t].values
        })
        try:
            # Test X → Y
            result = grangercausalitytests(data[["Y", "X"]], max_lag=max_lag, verbose=False)
            # Use lag-1 F-stat
            f_stats[t] = result[1][0]["ssr_ftest"][0]
            p_values[t] = result[1][0]["ssr_ftest"][1]
            # Direction: sum of X's coefficients
            model = sm.OLS(data["Y"].iloc[1:], sm.add_constant(data[["Y", "X"]].shift(1).iloc[1:])).fit()
            direction[t] = np.sign(model.params["X"])
        except:
            pass
    return f_stats, p_values, direction

# Key pairs (most studied in literature)
df["dxy_granger_eur"] = f_stat["DXY→EURUSD"]
df["dxy_granger_eur_p"] = p_val["DXY→EURUSD"]
df["gold_granger_aud"] = f_stat["XAU→AUDUSD"]
df["btc_granger_nas"] = f_stat["BTC→NAS100"]
```
**Timeframe:** H1, 200-bar rolling window (~8 days). Lag=1-5.
**Predictive power:** MODERATE. Granger causality is inconsistent — works in some regimes, breaks in others. Better as regime indicator (when significant: trend-following; when not: mean-reversion).

### 5.2 Cross-Correlation at Specific Lags

**Formula:**
```
# Exactly: correlation(ret_Y[t], ret_X[t-k]) for multiple lags k
xcorr_ij_lag_k[t] = rolling_corr(Y_ret[t-window:t], X_ret[t-k-window:t-k], window=N)
lead_lag_optimal[t] = argmax_k(abs(xcorr_ij_lag_k[t]))  # which lag gives strongest correlation?
```
**Assets:** All pairs. Known leads: DXY leads everything by 1-2 bars. Gold leads AUDUSD by 2-5 bars.
**Implementation:**
```python
def lead_lag_features(rets_i, rets_j, max_lag=10, window=100):
    """Find optimal lead-lag between two assets"""
    T = len(rets_i)
    optimal_lag = np.full(T, np.nan)
    max_corr = np.full(T, np.nan)

    for t in range(window + max_lag, T):
        best_corr = -1
        best_lag = 0
        for k in range(1, max_lag + 1):
            # Does I lead J? (I[t-k] drives J[t])
            win_i = rets_i.iloc[t-k-window:t-k].values
            win_j = rets_j.iloc[t-window:t].values
            corr = np.corrcoef(win_i, win_j)[0, 1]
            if abs(corr) > abs(best_corr):
                best_corr = corr
                best_lag = k
        optimal_lag[t] = best_lag
        max_corr[t] = best_corr
    return optimal_lag, max_corr
```
**Timeframe:** H1, max_lag=10 (10 hours). For slower effects, H4 with max_lag=20.
**Predictive power:** MODERATE. Optimal lag changes through time — need rolling estimation. DXY→EURUSD optimal lag typically 1-2 hours on H1.

### 5.3 Lead-Lag Heatmap (Static Analysis)

**Known lead-lag relationships from academic literature and practitioner research:**

| Leader | Lagger | Lag (H1) | Direction | Strength | Why |
|--------|--------|----------|-----------|----------|-----|
| DXY | EURUSD | 1-2 bars | Negative | Very Strong | DXY is 57% EUR |
| DXY | GBPUSD | 1-3 bars | Negative | Strong | Dollar dominance |
| DXY | AUDUSD | 2-5 bars | Negative | Strong | Commodity-USD link |
| DXY | XAUUSD | 2-5 bars | Negative | Strong | Dollar-gold inverse |
| XAUUSD | AUDUSD | 2-5 bars | Positive | Moderate | Gold producer |
| BTCUSD | NAS100 | 1-5 bars | Positive | Strong | 24/7 leading |
| NAS100 | AUDUSD | 1-3 bars | Positive | Moderate | Risk appetite |
| USDJPY | EURJPY | 1-2 bars | Positive | Strong | Yen crosses |
| EURUSD | GBPUSD | 1-2 bars | Positive | Moderate | European cluster |
| XAUUSD | XAGUSD | 1-3 bars | Positive | Strong | Same asset class |

### 5.4 Lead-Lag Ratio Feature

**Formula:**
```
# For each pair (i, j) where i is known to LEAD j:
# signal = normalized ratio of i's recent return to j's recent return
lead_lag_signal[t] = (ret_i[t-1] / ret_j[t]) - 1  # if i leads, this should capture divergence
```
**Assets:** All leader-follower pairs from the heatmap above.
**Implementation:**
```python
# "If DXY just moved but EURUSD hasn't caught up yet → EURUSD will follow"
df["dxy_eur_divergence"] = dxy_ret.shift(2) - eurusd_ret  # DXY lag 2, should predict EURUSD direction
df["gold_aud_divergence"] = gold_ret.shift(3) / audusd_ret - 1  # gold leads AUD

# "BTC already moved, NAS100 still sleeping" (during Asian/European hours)
df["btc_nas_divergence"] = btc_ret.shift(5) - 0.3 * nas_ret  # BTC overnight move
```
**Timeframe:** H1, with lags 1-5.
**Predictive power:** MODERATE. Works best in trending regimes. In choppy markets, lead-lag breaks down.

### 5.5 Transfer Entropy (Information Flow)

**Formula:**
```
# Measures: how much does knowing X's past reduce uncertainty about Y's future?
# TE_{X→Y} = sum p(y_{t+1}, y_t, x_t) * log( p(y_{t+1}|y_t, x_t) / p(y_{t+1}|y_t) )
# Higher TE = more information flowing from X to Y
```
**Assets:** All pairs. Most informative: DXY → EURUSD, XAUUSD → AUDUSD, BTC → NAS100.
**Implementation:**
```python
def transfer_entropy(x, y, bins=5, lag=1):
    """Discretized transfer entropy from X to Y at specified lag"""
    from collections import Counter

    # Discretize into bins
    x_disc = pd.cut(x, bins=bins, labels=False)
    y_disc = pd.cut(y, bins=bins, labels=False)

    # Compute joint and conditional distributions
    # TE = H(Y_{t+1}|Y_t) - H(Y_{t+1}|Y_t, X_t)
    # Using histograms for speed
    te = 0.0
    for yt in range(bins):
        for xt in range(bins):
            for yt1 in range(bins):
                p_yt1_yt_xt = np.mean((y_disc.iloc[lag:] == yt1) & (y_disc.shift(lag).iloc[lag:] == yt) & (x_disc.shift(lag).iloc[lag:] == xt))
                p_yt1_yt = np.mean((y_disc.iloc[lag:] == yt1) & (y_disc.shift(lag).iloc[lag:] == yt))
                p_yt_xt = np.mean((y_disc.shift(lag).iloc[lag:] == yt) & (x_disc.shift(lag).iloc[lag:] == xt))
                p_yt = np.mean(y_disc.shift(lag).iloc[lag:] == yt)

                if p_yt1_yt_xt > 0 and p_yt_xt > 0 and p_yt1_yt > 0 and p_yt > 0:
                    te += p_yt1_yt_xt * np.log2(p_yt1_yt_xt * p_yt / (p_yt_xt * p_yt1_yt))
    return max(te, 0)

# Roll transfer entropy
te_dxy_eur = rolling_transfer_entropy(dxy_ret, eurusd_ret, window=200, bins=5, lag=2)
```
**Timeframe:** H1, 200-bar window. Computationally expensive — pre-compute and cache.
**Predictive power:** MODERATE. TE is more robust than Granger causality (captures non-linear dependencies). High TE → strong lead relationship. TE rising = regime where lead-lag works.

---

## 6. What Top Funds Actually Do

Based on published research from AQR, Two Sigma, WorldQuant, Man AHL, CFM, and academic quant finance:

### 6.1 Time-Series Momentum with Cross-Asset Filtering (Moskowitz, Ooi, Pedersen 2012)

Funds extend single-asset trend to cross-asset trend signals.
```python
def cross_asset_trend(rets_df, lookback=60):
    """TSMOM with cross-asset risk filtering"""
    # Traditional TSMOM
    signal = np.sign(rets_df.rolling(lookback).sum())
    # But scale by inverse vol AND condition on cross-asset alignment
    vol = rets_df.rolling(lookback).std()
    scale = 0.20 / vol  # target 20% annualized vol

    # Cross-asset filter: only take signals when RORO regime agrees
    roro = roro_index(rets_df)
    roro_signal = np.sign(roro.rolling(lookback).sum())

    # For risk-on assets (AUDUSD etc): only go long in risk-on
    # For risk-off assets (USDJPY etc): only go long in risk-off
    return signal * scale
```

### 6.2 Adaptive Risk Budgeting via Absorption Ratio

```python
def adaptive_risk_budget(ar_ratio, base_exposure=1.0):
    """When AR > threshold, reduce exposure"""
    if ar_ratio > 0.7:
        return 0.3 * base_exposure  # crisis — cut risk massively
    elif ar_ratio > 0.5:
        return 0.7 * base_exposure  # elevated correlations
    else:
        return base_exposure  # normal
```

### 6.3 Momentum Spillover (WorldQuant 101-style Alpha)

```python
# Alpha #: momentum of correlated assets → predict this asset
# "If gold and silver have strong positive momentum, AUD will follow"
def momentum_spillover(target_ret, related_rets, window=20):
    """Average momentum of related assets as predictor"""
    related_mom = related_rets.rolling(window).sum().mean(axis=1)
    return related_mom  # use as feature for target prediction
```

### 6.4 Regime-Switching via Hidden Markov Model on Cross-Asset Features

```python
from hmmlearn import hmm

def regime_features(rets_df, n_regimes=3):
    """HMM on cross-asset correlation and vol structure"""
    # Features: avg correlation, PC1 variance ratio, crypto vol, DXY mom
    features = pd.DataFrame({
        "avg_corr": avg_pairwise_corr(rets_df, 60),
        "pc1_var": absorption_ratio(rets_df, 100, k=1),
        "dxy_mom": dxy_ret.rolling(20).sum(),
        "crypto_vol": btc_ret.rolling(24).std(),
    }).dropna()

    model = hmm.GaussianHMM(n_components=n_regimes, covariance_type="full")
    model.fit(features.values)
    regimes = model.predict(features.values)
    regime_probs = model.predict_proba(features.values)

    # Regime 0 typically = low vol, low corr (normal)
    # Regime 1 = trending, rising corr (risk-off)
    # Regime 2 = high vol, high corr (crisis)
    return regimes, regime_probs
```

---

## Summary: Feature Priority Matrix

| Priority | Feature | Source Assets | Target Assets | Timeframe | Expected Power |
|----------|---------|---------------|---------------|-----------|----------------|
| **P0** | DXY momentum | DXY | All USD pairs | H1 | VERY HIGH |
| **P0** | CSI USD/EUR strength | All FX pairs | All FX pairs | H1 | VERY HIGH |
| **P0** | RORO index | 8+ assets | All 13 | H1 | HIGH |
| **P0** | PC1 score | All 13 | All 13 | H1, 100-bar | HIGH |
| **P1** | PC1 variance ratio | All 13 | All 13 | H1 | HIGH |
| **P1** | Average pairwise correlation | All 13 | All 13 | H1, 60-bar | HIGH |
| **P1** | Absorption ratio | All 13 | All 13 | H1, 100-bar | HIGH |
| **P1** | Gold-AUD spread z-score | XAUUSD, AUDUSD | XAUUSD, AUDUSD | H1, 500-bar | MODERATE |
| **P1** | Carry barometer | JPY crosses | All FX | H1 | HIGH |
| **P2** | Crypto volatility proxy | BTCUSD, ETHUSD | NAS100, FX | H1, 24-bar | MODERATE |
| **P2** | BTC-ETH ratio z-score | BTCUSD, ETHUSD | BTCUSD, ETHUSD | H1 | MODERATE |
| **P2** | Safe haven score | NAS100, USDJPY, XAUUSD | All | H1 | MODERATE-HIGH |
| **P2** | Correlation breakdown (Mahalanobis) | All 13 | All 13 | H1, 500-bar | MODERATE |
| **P2** | DCC delta | All 13 | All 13 | H1 | MODERATE |
| **P3** | Granger causality F-stat | Key pairs | Key pairs | H1, 200-bar | MODERATE |
| **P3** | Lead-lag divergence | Leader-follower pairs | Followers | H1 | MODERATE |
| **P3** | Transfer entropy | Key pairs | Key pairs | H1, 200-bar | MODERATE |
| **P3** | Risk parity decomposition | Each asset | Same asset | H1/H4 | MODERATE |
| **P3** | HMM regime | All 13 | All 13 | H1 | MODERATE |
| **P4** | Gold-silver ratio | XAUUSD, XAGUSD | XAUUSD, XAGUSD | H4/D1 | MODERATE |
| **P4** | Fragile rally flag | NAS100, XAUUSD | NAS100 | H1 | LOW-MODERATE |
| **P4** | Inflation expectations proxy | XAUUSD, XAGUSD | Commodity FX | D1 | LOW-MODERATE |
| **P5** | Rotational alignment | All 13 | All 13 | H1 | LOW-MODERATE |
| **P5** | Eigenvalue entropy | All 13 | All 13 | H1 | LOW-MODERATE |

---

## Implementation Notes

1. **Lookahead bias:** All rolling features must use `shift(1)` to ensure no future information leaks into predictions.

2. **Computational budget:** PCA, DCC, and Granger causality are expensive (O(N^3) or O(T*N^2)). Pre-compute on D1 frequency and interpolate to H1 for speed.

3. **Missing data:** BTCUSD has gaps on some brokers. Interpolate only within trading hours. Cross-asset features require aligned timestamps.

4. **Stationarity:** All return-based features are naturally stationary. Price-based features (spreads, ratios) should be z-scored before use.

5. **Feature count:** ~60-80 cross-asset features. With 13 assets × ~5 individual features each = ~65 more, total ~130 features. Use feature selection (SHAP, permutation importance) to prune to top 30-50.

6. **Out-of-sample decay:** Leading indicators (BTC, DXY, gold) work best when the lead is short (1-5 bars). Longer leads (>20 bars) have no predictive power at H1.

---

## References (Key Papers)

- Moskowitz, Ooi, Pedersen (2012) — "Time Series Momentum" — Journal of Financial Economics
- Kritzman, Li, Page, Turkington (2011) — "Principal Components as a Measure of Systemic Risk" — Journal of Portfolio Management
- Avdulaj & Barunik (2015) — "Are Benefits from Oil–Stocks Correlations Gone?" — DCC methodology
- Bekaert & Harvey (2000) — "Foreign Speculators and Emerging Equity Markets" — FX carry factor
- Menkhoff et al. (2012) — "Currency Momentum Strategies" — cross-sectional FX momentum
- Brunnermeier, Nagel, Pedersen (2008) — "Carry Trades and Currency Crashes" — carry unwind dynamics
- Engle (2002) — "Dynamic Conditional Correlation" — Journal of Business & Economic Statistics
- Schreiber (2000) — "Measuring Information Transfer" — Transfer entropy in time series
- WorldQuant (2015) — "101 Formulaic Alphas" — cross-asset rotational features
