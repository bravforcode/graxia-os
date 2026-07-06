# State-of-the-Art Market Microstructure Features
## For M1–H1 Intraday Quant Trading

> **Compiled:** July 2026
> **Sources:** arXiv (q-fin.TR), GitHub (high-star microstructure repos), seminal papers (Cont, Bouchaud, Easley, Kyle, Amihud, etc.)

---

## 1. ORDER FLOW FEATURES

### 1.1 Order Flow Imbalance (OFI) — Standard

**Formula (level-k bid/ask):**

```
OFI_t^(k) = I(b_t^(k) > b_{t-1}^(k)) * q_t^{b,k}   # new bid orders
          - I(b_t^(k) < b_{t-1}^(k)) * q_{t-1}^{b,k} # cancelled bid orders
          - I(a_t^(k) > a_{t-1}^(k)) * q_t^{a,k}     # new ask orders (price up = less buying interest)
          + I(a_t^(k) < a_{t-1}^(k)) * q_{t-1}^{a,k} # cancelled ask orders
```

Where `I()` is indicator, `b_t^(k)` is bid price at level k at time t, `q_t^{b,k}` is bid volume at level k.

**Python sketch:**
```python
def ofi_level(prev_bid_price, cur_bid_price, prev_bid_vol, cur_bid_vol,
              prev_ask_price, cur_ask_price, prev_ask_vol, cur_ask_vol):
    ofi = 0
    if cur_bid_price > prev_bid_price:    ofi += cur_bid_vol   # new bid queue at higher price
    elif cur_bid_price < prev_bid_price:  ofi -= prev_bid_vol  # bid queue removed (price moved down)
    if cur_ask_volume > prev_ask_volume:  ofi -= cur_ask_vol   # new ask queue
    elif cur_ask_volume < prev_ask_volume: ofi += 0            # (depends on sign convention)
    return ofi
```

**Reference:** Cont, Cucuringu, Zhang (2021) "Cross-Impact of Order Flow Imbalance in Equity Markets" [arXiv:2112.13213]
**Timeframe:** M1 optimal for L1–L5, M5 with aggregated OFI. H1 loses microstructure signal.
**Data req:** L2 order book snapshots or order-by-order (MBO) data.

---

### 1.2 Multi-Level Order Flow Imbalance (MLOFI)

**Formula (vectorized):**

```
MLOFI_t = [OFI_t^(1), OFI_t^(2), ..., OFI_t^(K)]
ΔP_mid = β₀ + β₁ OFI_t^(1) + β₂ OFI_t^(2) + ... + β_K OFI_t^(K) + ε
```

Each additional level improves out-of-sample R² monotonically for Nasdaq stocks.

**Python sketch:**
```python
import numpy as np
from sklearn.linear_model import LinearRegression

def mlofi_features(snapshots, n_levels=5):
    """snapshots: list of (bids, asks) where bids/asks are [(price, vol), ...]"""
    mlofi = np.zeros((len(snapshots)-1, n_levels))
    for t in range(1, len(snapshots)):
        prev_b, prev_a = snapshots[t-1]
        cur_b, cur_a = snapshots[t]
        for k in range(min(n_levels, len(prev_b), len(cur_b))):
            mlofi[t-1, k] = ofi_level(
                prev_b[k][0], cur_b[k][0], prev_b[k][1], cur_b[k][1],
                prev_a[k][0], cur_a[k][0], prev_a[k][1], cur_a[k][1])
    return mlofi
```

**Reference:** Xu, Gould, Howison (2019) "Multi-Level Order-Flow Imbalance in a Limit Order Book" [arXiv:1907.06230]
**Timeframe:** M1–M5. R² improves ~5–8% vs single-level at M1, ~3–5% at M5.
**Data req:** L2 order book (top 5 levels minimum).

---

### 1.3 Generalized Stationarized Order Flow Imbalance (log-GOFI)

**Formula:**

```
GOFI_t = Σ_k w_k * OFI_t^(k)          # integrated OFI with level weights
log_GOFI_t = sign(GOFI_t) * log(1 + |GOFI_t|)  # stationarized
```

Using non-minimum tick unit normalization, log-GOFI achieves **R² = 83.57% (30s) / 85.37% (1m) / 86.01% (5m)** vs 32–42% for raw OFI.

**Python sketch:**
```python
def log_gofi(ofis, weights=None, epsilon=1.0):
    if weights is None:
        weights = 1.0 / np.arange(1, len(ofis)+1)  # decay by level
    gofi = np.dot(ofis, weights)
    return np.sign(gofi) * np.log(1 + np.abs(gofi))

def tick_normalized_ofi(price_diff, tick_size, volume):
    """Normalize price changes by tick units"""
    tick_units = int(price_diff / tick_size)
    return tick_units * volume if tick_units != 0 else 0
```

**Reference:** Su, Sun, Li, Yuan (2021) "The Price Impact of Generalized Order Flow Imbalance" [arXiv:2112.02947]
**Timeframe:** 30s–5m (exceptional across all sub-H1 horizons).
**Data req:** L2 snapshots with tick-size-aware normalization.

---

### 1.4 Trade-Side Classification (Bulk Volume / Aggressor Ratio)

**Formula (BVC — Bulk Volume Classification):**

For each time bar with volume `V_t` and price change `ΔP_t`:
```
V_buy,t  = V_t * Z(ΔP_t / (σ_ΔP * √Δt))
V_sell,t = V_t - V_buy,t
trade_imbalance_t = (V_buy,t - V_sell,t) / V_t
aggressor_ratio_t = V_buy,t / (V_buy,t + V_sell,t)
```

Where `Z(·)` is the CDF of standard normal — trade volume is probabilistically assigned to buy/sell based on price movement.

**Python sketch:**
```python
from scipy.stats import norm

def bulk_volume_classification(volume, close, window=20, bar_dt=1.0):
    price_changes = np.diff(close)
    sigma = np.sqrt(np.mean(price_changes[-window:]**2))
    z = price_changes / (sigma * np.sqrt(bar_dt) + 1e-10)
    vol_buy = volume[1:] * norm.cdf(z)
    vol_sell = volume[1:] * (1 - norm.cdf(z))
    aggressor_ratio = vol_buy / (vol_buy + vol_sell + 1e-10)
    return vol_buy, vol_sell, aggressor_ratio

def tick_rule(price, last_trade_price):
    """Classify at tick level"""
    if price > last_trade_price: return 1   # buy-initiated (uptick)
    elif price < last_trade_price: return -1 # sell-initiated (downtick)
    else: return 0  # same price -- use prior tick
```

**Reference:** Easley, López de Prado, O'Hara (2012) "Flow Toxicity and Liquidity in a High-Frequency World"; BVC method in Easley et al.
**Timeframe:** Tick → M1 → M5 (aggregated). Aggressor ratio loses signal at H1.
**Data req:** Tick-level trade data (price + volume per trade).

---

### 1.5 Cumulative Delta (CVD)

**Formula:**

```
CVD_t = Σ_{i=1}^{t} (V_buy,i - V_sell,i)
normalized_CVD_t = CVD_t / Σ_{i=1}^{t} V_i
```

CVD divergence from price = absorption signals (smart money accumulating against price).

**Python sketch:**
```python
def cumulative_delta(vol_buy, vol_sell):
    delta = vol_buy - vol_sell
    cvd = np.cumsum(delta)
    # Normalized CVD
    ncvd = np.cumsum(delta) / np.cumsum(vol_buy + vol_sell + 1e-10)
    # CVD slope (acceleration)
    cvd_ma5 = np.convolve(delta, np.ones(5)/5, mode='same')
    # CVD divergence from price
    return cvd, ncvd, cvd_ma5

def absorption_signal(cvd_1min, price_1min, window=20):
    """Divergence: CVD going up, price flat = buy absorption"""
    price_roc = np.diff(price_1min) / price_1min[:-1]
    cvd_roc = np.diff(cvd_1min) / (np.abs(cvd_1min[:-1]) + 1)
    # Correlation rolling
    rank_corr = pd.Series(cvd_roc).rolling(window).corr(pd.Series(price_roc))
    return np.where(rank_corr < -0.3, 1, 0)  # divergence signal
```

**Reference:** Cont, Kukanov, Stoikov (2014) "The Price Impact of Order Book Events"; Steenbarger (2003) on absorption.
**Timeframe:** Tick → M1. At M5, use CVD slope/divergence.
**Data req:** Tick-level trades OR 1-min OHLCV with BVC.

---

### 1.6 VPIN — Volume-Synchronized Probability of Informed Trading

**Formula:**

1. Group sequential trades into buckets of constant volume `V`
2. Within each bucket, estimate buy/sell volumes via tick rule or BVC
3. Compute bucket imbalance: `OI_τ = |V_buy,τ - V_sell,τ|`
4. VPIN (rolling window of `n` buckets):
```
VPIN_t = (1/n) * Σ_{τ=t-n+1}^{t} OI_τ / V
```
5. CDF(VPIN) ≈ CDF of the CDF of standard normal. Toxic flow threshold: VPIN > 0.70 (or CDF > 0.90).

**Python sketch:**
```python
def vpin(trade_prices, trade_volumes, bucket_size=50, n_buckets=50):
    """Easley et al. (2012) VPIN implementation"""
    buy_sell = []
    for i in range(1, len(trade_prices)):
        if trade_prices[i] > trade_prices[i-1]:
            buy_sell.append((1, trade_volumes[i]))
        elif trade_prices[i] < trade_prices[i-1]:
            buy_sell.append((-1, trade_volumes[i]))
        else:
            buy_sell.append((buy_sell[-1][0] if buy_sell else 0, trade_volumes[i]))

    buckets = []
    current_v = 0; current_imb = 0
    for sign, vol in buy_sell:
        remaining = vol
        while remaining > 0:
            fill = min(remaining, bucket_size - current_v)
            current_v += fill
            current_imb += sign * fill
            remaining -= fill
            if current_v >= bucket_size:
                excess = current_v - bucket_size
                current_imb -= sign * excess
                buckets.append(abs(current_imb) / bucket_size)
                current_v = excess
                current_imb = sign * excess

    vpin_series = pd.Series(buckets).rolling(n_buckets).mean()
    # CDF-based toxicity
    vpin_cdf = vpin_series.rank(pct=True)
    return vpin_series, vpin_cdf
```

**Reference:** Easley, López de Prado, O'Hara (2012) "Flow Toxicity and Liquidity in a High-Frequency World"; `PINstimation` R package by monty-se.
**Timeframe:** Adaptive (volume-based bars). Typically produces 50–200 buckets per day.
**Data req:** Tick-level trade data (price + volume). VPIN bucket_size ~ 50× average trade volume.

---

## 2. VWAP AND EXECUTION FEATURES

### 2.1 VWAP Deviation

**Formula:**
```
VWAP_t = Σ_i (P_i * V_i) / Σ_i V_i              # over window or day
VWAP_deviation_t = (P_t - VWAP_t) / VWAP_t      # signed deviation
VWAP_zscore_t = VWAP_deviation_t / rolling_std(VWAP_deviation, 60)
```

**Python sketch:**
```python
def vwap_features(high, low, close, volume, window_day_start=0):
    typical = (high + low + close) / 3
    cum_pv = (typical * volume).cumsum()
    cum_vol = volume.cumsum()
    vwap = cum_pv / cum_vol
    # Deviation from session VWAP
    if window_day_start:
        session_vwap = (typical[window_day_start:] * volume[window_day_start:]).cumsum() / \
                       volume[window_day_start:].cumsum()
    deviation = (close - vwap) / vwap
    zscore = deviation / deviation.rolling(60).std()
    return vwap, deviation, zscore
```

**Timeframe:** Session-level → M5/H1 signals. VWAP bounce/reversion at M1.
**Data req:** 1-min OHLCV bar data.

---

### 2.2 Anchored VWAP (AVWAP)

Anchor VWAP to significant events (open, news, recent high/low, session start):
```
AVWAP_{event}(t) = Σ_{i=event}^{t} (P_i * V_i) / Σ_{i=event}^{t} V_i
```

Multiple anchors produce a multi-timeframe feature set.

**Python sketch:**
```python
def anchored_vwap(df, anchor_indices):
    """df with columns: typical_price, volume"""
    avwaps = {}
    for name, idx in anchor_indices.items():
        slice_df = df.iloc[idx:]
        cum_pv = (slice_df['typical'] * slice_df['volume']).cumsum()
        cum_vol = slice_df['volume'].cumsum()
        avwaps[f'avwap_{name}'] = cum_pv / cum_vol
    return avwaps
```

**Timeframe:** M5–H1. Anchors at session open, overnight, pre-market high/low.
**Data req:** 1-min OHLCV.

---

### 2.3 TWAP Deviation

```
TWAP_t = (1/t) * Σ_{i=1}^{t} (High_i + Low_i + Close_i)/3
twap_spread_t = (P_t - TWAP_t) / TWAP_t
```

**Timeframe:** M1–M5 for execution monitoring. Low alpha for prediction.

---

### 2.4 Market-on-Close (MOC) Imbalance

**Data:** Exchange-published MOC order imbalances (if available) or inferred from closing auction.

```
MOC_imbalance_t = (Buy_MOC_volume - Sell_MOC_volume) / (Buy_MOC_volume + Sell_MOC_volume)
```

**Timeframe:** Last 10–15 min of session. **Extremely predictive** for closing price.

---

## 3. VOLUME PROFILE AND AUCTION FEATURES

### 3.1 Volume-at-Price (VAP)

Bin volume by price level over a rolling window:
```
VAP(p, [t-W, t]) = Σ_{i=t-W}^{t} V_i * I(P_i ∈ [p, p+Δp])
```

**Python sketch:**
```python
def volume_at_price(df, num_bins=50, window=390):
    """window in bars (e.g., 390 = full day at 1-min)"""
    price_bins = np.linspace(df['low'].min(), df['high'].max(), num_bins)
    vap = np.zeros(num_bins)
    for i in range(len(df)):
        idx = np.searchsorted(price_bins, df.iloc[i]['close']) - 1
        if 0 <= idx < num_bins:
            vap[idx] += df.iloc[i]['volume']
    return price_bins, vap
```

**Timeframe:** Day-level VAP, M5–H1 for rolling VAP zones.
**Data req:** 1-min OHLCV (better: tick data for precise binning).

---

### 3.2 POC (Point of Control) Features

```
POC_t = argmax_p VAP(p, [t-W, t])
poc_rank_t = percentile_of_price(P_t, VAP_distribution)
poc_migration_t = POC_t - POC_{t-W}
poc_migration_acceleration_t = poc_migration_t - poc_migration_{t-W}
```

**Python sketch:**
```python
def poc_features(vap_bins, vap_values, current_price, prev_poc=None):
    poc_idx = np.argmax(vap_values)
    poc_price = vap_bins[poc_idx]
    # Price relative to POC
    price_to_poc = (current_price - poc_price) / poc_price
    # Price quantile in volume profile
    rank = (np.searchsorted(np.cumsum(vap_values) / vap_values.sum(), 0.5)
            / len(vap_values))
    # POC migration (trend detection)
    poc_migration = poc_price - prev_poc if prev_poc else 0
    return poc_price, price_to_poc, poc_migration
```

**Timeframe:** M5–H1 for POC support/resistance. M1 POC too noisy.
**Data req:** 1-min OHLCV (rolling 1–5 day window).

---

### 3.3 Value Area Features (70% Rule)

```
Volume_pct_at_price = sort(VAP) / Σ VAP
VA_high = min price where cumulative volume ≥ 85%
VA_low  = max price where cumulative volume ≤ 15%
VA_ratio = (VA_high - VA_low) / POC
balance_indicator = |(P - center_of_VA) / VA_width|
```

**Python sketch:**
```python
def value_area(vap_bins, vap_values, high_pct=0.85, low_pct=0.15):
    cumsum = np.cumsum(vap_values) / vap_values.sum()
    va_high = vap_bins[np.searchsorted(cumsum, high_pct)]
    va_low = vap_bins[np.searchsorted(cumsum, low_pct)]
    poc_price = vap_bins[np.argmax(vap_values)]
    va_width = va_high - va_low
    va_ratio = va_width / poc_price
    mid_va = (va_high + va_low) / 2
    balance = (poc_price - mid_va) / va_width if va_width > 0 else 0
    return va_high, va_low, va_ratio, balance
```

**Timeframe:** Session-level. Balance indicator at M5.
**Data req:** 1-min OHLCV.

---

### 3.4 Volume Distribution Moments

```
μ_vol = Σ p_i * (V(p_i) / ΣV(p_j))           # volume-weighted mean price
σ²_vol = Σ (p_i - μ_vol)² * (V(p_i) / ΣV(p_j)) # variance
skew_vol = Σ (p_i - μ_vol)³ / σ³              # skewness
kurt_vol = Σ (p_i - μ_vol)⁴ / σ⁴              # kurtosis
```

Positive volume skew = buying interest concentrated above POC (bullish).

**Python sketch:**
```python
from scipy.stats import skew, kurtosis
def volume_distribution_moments(vap_bins, vap_values):
    probs = vap_values / vap_values.sum()
    mean = np.average(vap_bins, weights=vap_values)
    var = np.average((vap_bins - mean)**2, weights=vap_values)
    std = np.sqrt(var)
    skewness = np.average(((vap_bins - mean)/std)**3, weights=vap_values)
    kurto = np.average(((vap_bins - mean)/std)**4, weights=vap_values)
    return mean, var, skewness, kurto
```

**Timeframe:** M5–H1. Skewness/kurtosis are persistent microstructure regime indicators.
**Data req:** 1-min OHLCV with at least 100 bars for stable moments.

---

## 4. SPREAD AND LIQUIDITY FEATURES

### 4.1 Effective Spread vs Quoted Spread

**Formula:**
```
Quoted_Spread = Ask - Bid
Effective_Spread = 2 * |P_trade - Midpoint_trade|
Relative_Effective_Spread = 2 * |P_trade - Midpoint| / Midpoint
Realized_Spread = 2 * D_t * (P_trade - Midpoint_{t+Δ})  # D_t = +1 buy, -1 sell
```

Effective spread captures actual trading costs better than quoted spread (trades often occur inside the spread).

**Python sketch:**
```python
def spread_features(trades, quotes, delta=5):
    """trades: [(price, time)], quotes: [(bid, ask, time)]"""
    effective_spreads = []
    for trade_price, trade_time in trades:
        quote = nearest_quote(trade_time, quotes)
        midpoint = (quote[0] + quote[1]) / 2
        eff_spread = 2 * abs(trade_price - midpoint)
        rel_eff_spread = eff_spread / midpoint
        effective_spreads.append((eff_spread, rel_eff_spread))
    return effective_spreads
```

**Reference:** Bessembinder (2003) "Issues in assessing trade execution costs"; Hendershott, Jones, Menkveld (2011).
**Timeframe:** Tick → M1 aggregated. H1 uses average effective spread over the hour.
**Data req:** Tick trades + quote timestamps.

---

### 4.2 Kyle's Lambda (Price Impact)

**Formula (linear Kyle model):**

```
ΔP_t = λ_t * Q_t + ε_t
λ_t = |ΔP_t| / |Q_t|  (simplified per-trade)
λ_rolling_t = Cov(ΔP, Q_sign * √V) / Var(Q_sign * √V)  # over rolling window
```

Where `Q_t = sign(trade) * volume` (signed order flow). Larger λ = less liquidity.

**Python sketch:**
```python
def kyles_lambda(trade_prices, trade_volumes, trade_signs, window=100):
    """Kyle's lambda estimation over rolling window"""
    rets = np.diff(np.log(trade_prices))
    signed_flow = np.array(trade_signs[1:]) * np.sqrt(trade_volumes[1:])
    lambdas = np.zeros(len(rets))
    for i in range(window, len(rets)):
        y = rets[i-window:i]
        x = signed_flow[i-window:i]
        # simple OLS λ
        cov = np.cov(y, x)[0, 1]
        var = np.var(x)
        lambdas[i] = cov / var if var > 0 else 0
    return lambdas

def kyle_lambda_simple(price_changes, signed_volumes):
    """Simplified: λ = |ΔP| / |V_signed|"""
    return np.abs(price_changes) / (np.abs(signed_volumes) + 1e-10)
```

**Reference:** Kyle (1985) "Continuous Auctions and Insider Trading"; Cont, Kukanov, Stoikov (2014).
**Timeframe:** Tick → M5 (rolling window of 50–200 trades). H1 monthly λ.
**Data req:** Tick trades + trade sign classification.

---

### 4.3 Amihud Illiquidity Ratio (Intraday Version)

**Formula:**
```
ILLIQ_t = |R_t| / (P_t * V_t)            # per-bar
ILLIQ_daily = avg(|R_i| / (P_i * V_i))   # aggregated
```

Intraday: use 5-min or 1-min bars with rolling median.

**Python sketch:**
```python
def amihud_illiquidity(returns, prices, volumes, window=78):
    """window=78 → 390 min day / 5-min bars"""
    illiq = np.abs(returns) / (prices * volumes + 1e-10)
    amihud_roll = pd.Series(illiq).rolling(window).median()
    return amihud_roll

def amihud_zscores(amihud_series):
    """Detect liquidity crises: z-score > 2"""
    mean = amihud_series.rolling(390).mean()
    std = amihud_series.rolling(390).std()
    return (amihud_series - mean) / std
```

**Reference:** Amihud (2002) "Illiquidity and stock returns"; Goyenko, Holden, Trzcinka (2009).
**Timeframe:** M5 optimal. M1 noisy. H1 monthly is standard.
**Data req:** 1-min or 5-min OHLCV.

---

### 4.4 Depth-Weighted Spread

**Formula:**
```
Weighted_Bid = Σ_k w_k * BidPrice_k * BidVolume_k / Σ_k w_k * BidVolume_k
Weighted_Ask = Σ_k w_k * AskPrice_k * AskVolume_k / Σ_k w_k * AskVolume_k
Depth_Weighted_Spread = Weighted_Ask - Weighted_Bid
w_k = 1/k  (or exponential decay)
```

**Python sketch:**
```python
def depth_weighted_spread(bids, asks, levels=10):
    """bids/asks: list of (price, volume) sorted by depth"""
    w = 1.0 / np.arange(1, levels+1)
    bid_p = np.array([b[0] for b in bids[:levels]])
    bid_v = np.array([b[1] for b in bids[:levels]])
    ask_p = np.array([a[0] for a in asks[:levels]])
    ask_v = np.array([a[1] for a in asks[:levels]])
    w_bid = np.average(bid_p, weights=w * bid_v) if bid_v.sum() > 0 else bid_p[0]
    w_ask = np.average(ask_p, weights=w * ask_v) if ask_v.sum() > 0 else ask_p[0]
    return w_ask - w_bid
```

**Timeframe:** Tick → M1.
**Data req:** L2 order book.

---

### 4.5 Order Book Imbalance at Top N Levels

**Formula:**

```
Volume_Imbalance_N = (Σ_k BidVolume_k - Σ_k AskVolume_k) / (Σ_k BidVolume_k + Σ_k AskVolume_k)
```

This is the most commonly used LOB feature. Top 5 levels for equities, top 10 for crypto.

**Python sketch:**
```python
def order_book_imbalance(bids, asks, levels=5):
    bid_vol = sum(b[1] for b in bids[:levels])
    ask_vol = sum(a[1] for a in asks[:levels])
    total = bid_vol + ask_vol
    return (bid_vol - ask_vol) / total if total > 0 else 0

def weighted_obi(bids, asks, levels=5, decay=0.5):
    """Exponential decay weight by level"""
    w_bid = sum(b[1] * (decay ** i) for i, b in enumerate(bids[:levels]))
    w_ask = sum(a[1] * (decay ** i) for i, a in enumerate(asks[:levels]))
    total = w_bid + w_ask
    return (w_bid - w_ask) / total if total > 0 else 0
```

**Reference:** Cao, Hansch, Wang (2009) "The information content of an open limit-order book"; Bouchaud et al. (2004).
**Timeframe:** Tick → M1. At M5/H1, use aggregated imbalance.
**Data req:** L2 order book.

---

### 4.6 Liquidity Timing Features

```
Liquidity_Clock = avg_spread_by_hour / global_avg_spread
Spread_Risk = rolling_std(spread) / rolling_mean(spread)  # spread volatility
Depth_Durability = avg_time_between_depth_changes  # how stable is the book
```

---

## 5. TICK DATA FEATURES

### 5.1 Tick Arrival Rate / Tick Velocity

**Formula:**
```
Tick_Rate_t = count(trades in [t, t+Δt]) / Δt
Tick_Acceleration = Tick_Rate_t - Tick_Rate_{t-1}
High_Frequency_Regime = Tick_Rate_t > μ_TickRate + 2 * σ_TickRate
```

**Python sketch:**
```python
def tick_arrival_features(trade_timestamps, bar_dt=60):
    """bar_dt in seconds"""
    bar_start = trade_timestamps[0]
    tick_counts = []
    bar_starts = []
    for ts in trade_timestamps:
        while ts >= bar_start + bar_dt:
            bar_start += bar_dt
            tick_counts.append(0)
            bar_starts.append(bar_start)
        tick_counts[-1] = tick_counts[-1] + 1 if tick_counts else 1
    return np.array(tick_counts)
```

**Timeframe:** M1. Tick cluster detection is highly predictive of imminent volatility.
**Data req:** Tick-level trade timestamps.

---

### 5.2 Trade Size Distribution Moments

```
avg_trade_size_t = mean(V_i for trades in [t, t+Δt])
abnormal_size_flag = 1 if V_i > μ_V + 3 * σ_V
large_trade_ratio = V_large / V_total
whale_index = count(trades > 99th_pctile_avg_size) / total_trades
```

**Python sketch:**
```python
def trade_size_features(trade_volumes, trade_times, bar_dt=60):
    df = pd.DataFrame({'vol': trade_volumes, 'time': pd.to_datetime(trade_times)})
    grouped = df.set_index('time').resample(f'{bar_dt}s')
    avg_size = grouped['vol'].mean()
    max_size = grouped['vol'].max()
    # Abnormal trade detection
    rolling_mean = avg_size.rolling(100).mean()
    rolling_std = avg_size.rolling(100).std()
    whale_idx = (max_size > rolling_mean + 3 * rolling_std).astype(int)
    return avg_size, whale_idx
```

**Timeframe:** M1–M5. Whale detection across all timeframes.
**Data req:** Tick-level trade volumes.

---

### 5.3 Cancel-to-Trade Ratio (Inferred)

Cannot directly observe cancels from trade data, but for LOB data:

```
CTR_t = ΔBookVolume_t / ΔTradeVolume_t
Cancel_Intensity_t = c * exp(β * |queue_age|)  # Hawkes intensity
```

For trade-only data, infer from volume auto-correlation decay.

**Python sketch:**
```python
def cancel_to_trade_ratio(order_book_snapshots, trades, window=60):
    """Requires L2 snapshots. Inferred from book depth changes."""
    depth_changes = []
    for i in range(1, len(order_book_snapshots)):
        prev_depth = sum(b[1] for b in order_book_snapshots[i-1][0]) + \
                     sum(a[1] for a in order_book_snapshots[i-1][1])
        cur_depth = sum(b[1] for b in order_book_snapshots[i][0]) + \
                   sum(a[1] for a in order_book_snapshots[i][1])
        depth_changes.append(abs(prev_depth - cur_depth))
    trade_vol_agg = pd.Series([t[1] for t in trades]).rolling(window).sum()
    depth_change_agg = pd.Series(depth_changes).rolling(window).sum()
    ctr = (depth_change_agg - trade_vol_agg) / trade_vol_agg.replace(0, np.nan)
    return ctr
```

**Timeframe:** Tick → M1. High CTR = spoofing/liquidity ghosting.
**Data req:** L2 order book snapshots + trade data.

---

### 5.4 Trade Size Imbalance (TSI)

```
TSI_t = Σ_{i∈[t,t+Δt]} sign(trade_i) * V_i / Σ V_i
```

A tick-level analog to OFI using executed trades rather than quote changes.

---

## 6. HAWKES PROCESS FEATURES

### 6.1 Multivariate Hawkes for Order Flow

Model the mutually exciting nature of order book events:

```
λ_buy(t)  = μ_buy  + Σ_{τ_i < t} α_buy,buy * exp(-β * (t-τ_i)) + α_buy,sell * exp(-β * (t-τ_i))
λ_sell(t) = μ_sell + Σ_{τ_i < t} α_sell,buy * exp(-β * (t-τ_i)) + α_sell,sell * exp(-β * (t-τ_i))
λ_cancel(t) = μ_cancel + ...
```

The branching ratio `Γ = α_self / β` measures endogeneity (reflexivity). Γ close to 1 = unstable regime.

**Python sketch:**
```python
def hawkes_endogeneity(intensities, kernels, decay):
    """Estimate branching ratio from fitted Hawkes"""
    # α matrix sum over events, divided by β
    alpha_sum = sum(k['alpha'] for k in kernels)  # simplified
    branching_ratio = alpha_sum / decay
    return branching_ratio

def hawkes_kernel_sum_of_exponentials(t, alphas, betas):
    """ϕ(t) = Σ α_i * exp(-β_i * t)"""
    return sum(a * np.exp(-b * t) for a, b in zip(alphas, betas))
```

**Reference:** Bacry, Mastromatteo, Muzy (2015) "Hawkes processes in finance"; Anantha & Jain (2024) [arXiv:2408.03594]; Wu et al. (2019) [arXiv:1901.08938].
**Timeframe:** Tick → M1 (Hawkes intensity forecasts OFI).
**Data req:** Tick-level event timestamps from LOB.

---

## 7. WHAT ACTUALLY WORKS — EMPIRICAL RANKINGS

Based on published results (Cont/Cucuringu 2021, Xu/Gould/Howison 2019, Su et al. 2021, Bieganowski & Ślepaczuk 2026), ranked by predictive power:

### Tier 1: Highest Alpha (consistently verified)

| Rank | Feature | R² / Sharpe | Horizon | Data Needed |
|------|---------|------------|---------|-------------|
| 1 | **log-GOFI** (Generalized Stationarized OFI) | R²=83-86% | 30s–5m | L2 snapshots |
| 2 | **MLOFI** (Multi-level OFI) | R²~70% | 1m | L2 snapshots |
| 3 | **Order Book Imbalance (top N)** | Sharpe 1.5–2.5 | 1–10s | L2 snapshots |
| 4 | **VPIN** (CDF > 0.9 threshold) | Crisis predictor | Adaptive | Tick trades |
| 5 | **CVD Divergence** (absorption detection) | Sharpe 1.0–2.0 | 1–60m | Tick/BVC |
| 6 | **OFI + Cross-impact** (lagged) | R²~15-20% | 5m–1H | L2 snapshots |
| 7 | **Hawkes Branching Ratio** | Regime classifier | Tick | LOB events |

### Tier 2: Supplementary (improves combined models)

| Feature | Use Case | Horizon |
|---------|----------|---------|
| Volume profile skewness | Regime detection | M5–H1 |
| POC migration | Trend confirmation | M5–H1 |
| Amihud illiquidity | Crisis avoidance | M5 |
| Kyle's λ | Slippage estimation | M5 |
| Depth-weighted spread | Execution quality | Tick–M1 |
| Tick arrival acceleration | Volatility spike predictor | M1 |
| Whale index | Institutional flow detection | M1–M5 |
| Value Area ratio | Range-bound vs trending | M5–H1 |

### Tier 3: Context-dependent

| Feature | When it Works | When it Doesn't |
|---------|--------------|-----------------|
| VWAP deviation | Trending sessions | Choppy/ranging |
| TWAP deviation | Execution monitoring | Alpha generation |
| Trade size moments | Stocks with institutional flow | Retail-dominated assets |
| Cancel-to-trade ratio | LOB data available | Trade-only data |
| Aggressor ratio | High-liquidity assets | Illiquid assets (BVC bias) |

### Cross-Asset Stability (Bieganowski & Ślepaczuk 2026)

Key finding: OFI, spread, and adverse selection features show **remarkably similar SHAP dependence shapes** across BTC, LTC, ETC, ENJ, ROSE (order-of-magnitude mcap range). Universal feature libraries are possible for crypto. Taker strategies get killed in flash crashes (adverse selection), maker strategies capture spread.

---

## 8. FEATURE IMPORTANCE FROM MODEL STUDIES

From Bieganowski & Ślepaczuk (2026), CatBoost + GMADL objective on 1-second crypto data:

| Rank | Feature Group | SHAP Importance |
|------|--------------|-----------------|
| 1 | Order flow imbalance (OFI) | ★★★★★ |
| 2 | Spread (bid-ask, depth-weighted) | ★★★★★ |
| 3 | Adverse selection indicators | ★★★★☆ |
| 4 | Volume-at-price (VAP) | ★★★★☆ |
| 5 | Tick arrival rate | ★★★☆☆ |
| 6 | Return autocorrelation | ★★★☆☆ |

From Su et al. (2021), OFI tree model for CSI 500 stocks:
- Order flow imbalance: **43.2%** feature importance
- log-GOFI > OFI by 2.5× R²

---

## 9. COMPLETE FEATURE PIPELINE (Example)

```python
import numpy as np
import pandas as pd
from scipy.stats import norm, skew, kurtosis

class MicrostructureFeatures:
    """
    Compute SOTA microstructure features.
    Input: L2 snapshots + trades (or just 1-min OHLCV for tiers 2-3)
    """
    def __init__(self, n_levels=5, tick_size=0.01):
        self.n_levels = n_levels
        self.tick_size = tick_size

    def ofi_vector(self, prev_snap, cur_snap):
        """Multi-level OFI vector"""
        ofis = np.zeros(self.n_levels)
        for k in range(self.n_levels):
            ofis[k] = self._ofi_level(
                prev_snap['bid_price'][k], cur_snap['bid_price'][k],
                prev_snap['bid_vol'][k],   cur_snap['bid_vol'][k],
                prev_snap['ask_price'][k], cur_snap['ask_price'][k],
                prev_snap['ask_vol'][k],   cur_snap['ask_vol'][k])
        return ofis

    def _ofi_level(self, pb0, pb1, vb0, vb1, pa0, pa1, va0, va1):
        ofi = 0.0
        if pb1 > pb0: ofi += vb1
        elif pb1 < pb0: ofi -= vb0
        if pa1 > pa0: ofi -= va1
        elif pa1 < pa0: ofi += 0
        return ofi

    def log_gofi(self, ofis, weights=None):
        if weights is None:
            weights = 1.0 / np.arange(1, len(ofis)+1)
        gofi = np.dot(ofis, weights)
        return np.sign(gofi) * np.log(1 + np.abs(gofi))

    def volume_imbalance(self, bids, asks):
        bid_v = sum(b[1] for b in bids[:self.n_levels])
        ask_v = sum(a[1] for a in asks[:self.n_levels])
        total = bid_v + ask_v
        return (bid_v - ask_v) / total if total > 0 else 0.0

    def depth_weighted_spread(self, bids, asks):
        weights = 1.0 / np.arange(1, self.n_levels+1)
        w_bid = np.average([b[0] for b in bids[:self.n_levels]],
                           weights=weights * [b[1] for b in bids[:self.n_levels]])
        w_ask = np.average([a[0] for a in asks[:self.n_levels]],
                           weights=weights * [a[1] for a in asks[:self.n_levels]])
        return w_ask - w_bid

    @staticmethod
    def bvc(volume, close, window=20):
        rets = np.diff(close)
        sigma = np.std(rets[-window:])
        z = rets / (sigma * np.sqrt(1) + 1e-10)
        vol_buy = volume[1:] * norm.cdf(z)
        vol_sell = volume[1:] * (1 - norm.cdf(z))
        return vol_buy, vol_sell

    @staticmethod
    def cumulative_delta(vol_buy, vol_sell):
        delta = vol_buy - vol_sell
        cvd = np.cumsum(delta)
        cvd_normalized = np.cumsum(delta) / (np.cumsum(vol_buy + vol_sell) + 1e-10)
        return cvd, cvd_normalized

    @staticmethod
    def poc_migration(vap_bins, vap_values, prev_poc):
        poc = vap_bins[np.argmax(vap_values)]
        return poc - prev_poc if prev_poc else 0.0

    @staticmethod
    def kyles_lambda_rolling(rets, signed_flow, window=100):
        lambdas = np.full(len(rets), np.nan)
        for i in range(window, len(rets)):
            cov = np.cov(rets[i-window:i], signed_flow[i-window:i])[0,1]
            var = np.var(signed_flow[i-window:i])
            lambdas[i] = cov / var if var > 0 else 0.0
        return lambdas

    @staticmethod
    def amihud(returns, prices, volumes):
        return np.abs(returns) / (prices * volumes + 1e-10)

    @staticmethod
    def volume_profile_moments(price_bins, vap):
        probs = vap / (vap.sum() + 1e-10)
        mu = np.sum(price_bins * probs)
        sigma = np.sqrt(np.sum((price_bins - mu)**2 * probs))
        skewness = np.sum(((price_bins - mu) / sigma)**3 * probs) if sigma > 0 else 0
        kurt = np.sum(((price_bins - mu) / sigma)**4 * probs) if sigma > 0 else 0
        return mu, sigma, skewness, kurt

    @staticmethod
    def tick_rate(trade_times, bar_seconds=60):
        if len(trade_times) < 2:
            return np.array([0])
        edges = np.arange(trade_times[0], trade_times[-1] + bar_seconds, bar_seconds)
        counts, _ = np.histogram(trade_times, bins=edges)
        return counts
```

---

## 10. DATA REQUIREMENTS SUMMARY

| Feature Category | Minimum Data | Optimal Data | Notes |
|-----------------|--------------|--------------|-------|
| OFI / MLOFI / log-GOFI | L2 top 5 | Full LOB | L1 only loses significant signal |
| OBI (volume imbalance) | L2 top 3 | L2 top 10 | Most robust feature |
| VPIN | Tick trades | Tick trades + quotes | Volume bucket size critical |
| CVD / Aggressor ratio | Tick trades | Tick trades + LOB | BVC needed if no trade direction |
| VWAP / AVWAP / TWAP | 1-min OHLCV | Tick trades for precision | Standard bar data works |
| Volume Profile (POC, VA, moments) | 1-min OHLCV | Tick data | 1-min adequate for M5+ features |
| Spread / Kyle λ / Amihud | Tick quotes | L2 snapshots | Quotes needed for effective spread |
| Depth-weighted spread | L2 top 10 | Full LOB | Crypto: use top 20 |
| Trade size / Tick rate | Tick trades | Tick trades + LOB | timestamps + volume |
| Hawkes processes | LOB event stream | MBO (market-by-order) | Computationally expensive |
| Cancel-to-trade ratio | L2 snapshots + trades | MBO | Requires depth tracking |

---

## 11. KEY REFERENCES

| Paper | Authors | Year | Key Contribution |
|-------|---------|------|-----------------|
| Multi-Level OFI in LOB | Xu, Gould, Howison | 2019 | MLOFI: each level adds explanatory power |
| Cross-Impact of OFI | Cont, Cucuringu, Zhang | 2021 | Integrated OFI > single-level; lagged cross-asset |
| Price Impact of Generalized OFI | Su, Sun, Li, Yuan | 2021 | log-GOFI: R² 83-86% (3x raw OFI) |
| Flow Toxicity and Liquidity | Easley, López de Prado, O'Hara | 2012 | VPIN metric, bulk volume classification |
| Forecasting HF Order Flow Imbalance | Anantha, Jain | 2024 | Hawkes + sum-of-exponentials for OFI forecast |
| Queue-Reactive Hawkes | Wu, Rambaldi, Muzy, Bacry | 2019 | State-dependent Hawkes for LOB |
| Explainable Crypto Microstructure | Bieganowski, Ślepaczuk | 2026 | Stable cross-asset feature importance (SHAP) |
| ClusterLOB | Zhang, Cucuringu, Shestopaloff, Zohren | 2025 | Clustering MBO events → directional/opportunistic/mm |
| Universal Scaling of Aggregate Impact | Patzelt, Bouchaud | 2017 | Square-root impact law universality |
| Polymarket VPIN Benchmark | Qin, Yang | 2026 | Ground-truth VPIN beats inferred; classification errors propagate |
| PINstimation (R package) | monty-se | 2023 | Full VPIN/PIN/MPIN/AdjPIN implementations |
| Continuous Auctions and Insider Trading | Kyle | 1985 | Kyle's lambda (seminal) |
| Illiquidity and Stock Returns | Amihud | 2002 | Amihud illiquidity ratio |

---

## 12. PRACTICAL RECOMMENDATIONS

1. **Start with the Tier 1 features** (log-GOFI, OBI, CVD). These work cross-asset and cross-timeframe.
2. **For M1 models**: L2 snapshots are essential. Tick data adds 10–20% edge.
3. **For M5–H1 models**: 1-min OHLCV + VPIN + volume profile features are sufficient.
4. **VPIN uses adaptive volume bars**, not clock bars. This is critical — don't use 5-min VPIN.
5. **log-GOFI > raw OFI** by a factor of 2.5× in R². Always stationarize with log transform.
6. **Cross-asset OFI is real**: Cont/Cucuringu/Zhang show lagged cross-impact exists at short horizons.
7. **CVD divergence** is a practical re-implementation of Kyle's model without needing trade classification.
8. **Hawkes branching ratio** is the best single metric for detecting fragile/reflexive market conditions.
9. **Cancel-to-trade ratio** (from LOB data) detects spoofing and phantom liquidity — important for risk.
10. **Feature universality holds for crypto** (Bieganowski & Ślepaczuk 2026): same features rank similarly across assets of vastly different mcap.
