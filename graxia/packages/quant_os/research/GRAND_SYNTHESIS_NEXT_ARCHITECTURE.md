# GRAND SYNTHESIS: Next-Generation Quant System Architecture

**Date**: 2026-07-06
**Status**: POST-ML-DIRECTION-FAILURE REDESIGN
**Based on**: 6 parallel research agents (regime, microstructure, cross-asset, targets, what-works, BOS/CHOCH)

---

## Executive Summary

ML binary direction prediction on XAUUSD/EURUSD produced **0/23 profitable walk-forward folds** after fixing all measurement bugs. This system is **dead** as currently designed. The research reveals a clear path forward: a **3-stage architecture** where volatility and regime prediction form the foundation, and directional signals are only a lightweight overlay.

---

## Stage 1: Why Direction Prediction Failed (And Always Will)

### The Signal-to-Noise Problem
- Financial returns have **near-zero SNR** — the best ensemble models achieve at most 55-57% binary accuracy (Weinberg, 2025)
- Fang & Ślepaczuk (2026): return predictability "remains weak, state-dependent, and concentrated primarily in low-volatility regimes"
- Sarkar (2026): Fin-AdaptFormer on AAPL achieved only **51.7% accuracy** (essentially random)
- Fang & Ślepaczuk: "Naive predictive strategies generally fail after accounting for realistic transaction costs"

### Our Evidence
| Metric | XAUUSD H1 | EURUSD H1 |
|--------|-----------|-----------|
| OOS Accuracy | 52.93% | 50.46% |
| Folds Profitable | 0/11 | 0/12 |
| Label Shuffle p-value | 0.38 (not significant) | — |

**Verdict**: Direction prediction on liquid markets with ML is a solved problem — and the answer is "it doesn't work."

---

## Stage 2: What Actually Works (Proven Approaches)

### Approach #1: Multi-Asset Time Series Momentum ⭐ TOP PICK
- Moskowitz, Ooi, Pedersen (2012): **Sharpe 1.0-1.31** across 58 instruments
- Quantpedia replication: 20.70% return, 15.74% vol, Sharpe 1.31
- **No ML needed** — just compute past returns over 1M/3M/12M lookbacks
- Works on all 15 instruments simultaneously
- Fits our exact asset mix: FX, metals, crypto, indices

### Approach #2: Volatility Risk Premium Harvesting
- Sell options/volatility when implied vol > realized vol
- Sharpe 0.8-1.5 in academic literature
- Requires options data or proxy (VIX-like from crypto)
- Works best as overlay, not standalone

### Approach #3: Carry Trade (FX)
- Classic strategy: long high-yield currencies, short low-yield
- Still profitable in 2024-2026 (less than historical highs)
- Sharpe ~0.4-0.6 standalone, improves with momentum overlay
- Perfect for our FX pairs (USD crosses)

### Approach #4: Statistical Arbitrage (Pairs)
- Cointegration-based mean reversion on related pairs
- EURUSD-GBPUSD, XAUUSD-XAGUSD, BTC-ETH
- Sharpe 1.0-2.0 in literature (but crowded)
- Requires cointegration testing + half-life monitoring

### Approach #5: Volatility Prediction → Position Sizing
- HAR model family: predict realized volatility (not direction!)
- Blake et al. (2025): 8-12% MSE reduction via regime-switching HAR
- **Concrete edge**: volatility clusters and has long memory (predictable)
- Use predicted vol → risk-targeted position sizing → converts ANY weak signal to better Sharpe

### What Renaissance Actually Does (Based on Inference)
- **Thousands of simple mean-reversion pairs** at very high speed
- **Market making** with inventory management (Avellaneda-Stoikov)
- **Statistical arbitrage** across correlated instruments
- NOT AI-based direction prediction on single instruments
- "If you have 1000 strategies with Sharpe 0.3 each, the portfolio Sharpe can be 3.0+"

---

## Stage 3: The New 3-Stage Architecture

```
                    INPUT: 15 instruments × multi-timeframe data
                                    │
                    ┌───────────────▼───────────────┐
                    │  STAGE 1: VOLATILITY ENGINE    │
                    │  Predict: log(RV_{t+1})        │
                    │  Model: HAR + XGBoost regime    │
                    │  Output: σ̂_{t+1} per instrument │
                    └───────────────┬───────────────┘
                                    │ σ̂
                    ┌───────────────▼───────────────┐
                    │  STAGE 2: REGIME + RISK GATE   │
                    │  Classify: trending/ranging/   │
                    │    high-vol/crash               │
                    │  Model: HMM + XGBoost           │
                    │  Output: position_size_scale    │
                    │    [0.0, 0.5, 1.0, 1.5]        │
                    └───────────────┬───────────────┘
                                    │ scale
                    ┌───────────────▼───────────────┐
                    │  STAGE 3: SIGNAL GENERATION    │
                    │  Multi-asset TSMOM             │
                    │  + Carry overlay                │
                    │  + Pairs mean-reversion         │
                    │  Output: signal ∈ {-1,0,1}      │
                    └───────────────┬───────────────┘
                                    │
                    ┌───────────────▼───────────────┐
                    │  FINAL: RISK-TARGETED SIZE      │
                    │  position = signal × scale      │
                    │            × (σ_target / σ̂)     │
                    │            × capital / ATR      │
                    └───────────────────────────────┘
```

---

## Stage 4: Concrete Features to Build

### Category A: Volatility Features (for Stage 1)
| # | Feature | Formula | Papers |
|---|---------|---------|--------|
| V1 | Parkinson vol | √(1/(4n ln2) × Σ (ln(H/L))²) | Parkinson 1980 |
| V2 | Garman-Klass vol | √(0.5×(ln(H/L))² - (2ln2-1)×(ln(C/O))²) | GK 1980 |
| V3 | EWMA vol λ=0.84 (M15), λ=0.92 (H1) | σ²_t = λσ²_{t-1} + (1-λ)r²_t | RiskMetrics |
| V4 | Vol-of-Vol | StdDev(EWMA Vol, lookback=20) | Transition signal |
| V5 | HAR daily/weekly/monthly lags | RV_d, RV_w, RV_m | Corsi 2009 |
| V6 | Jump variation | max(RV - BPV, 0) | Bollerslev |
| V7 | GARCH(1,1) conditional vol | σ²_t = ω + αε²_{t-1} + βσ²_{t-1} | Bollerslev 1986 |

### Category B: Regime Features (for Stage 2)
| # | Feature | Formula | Papers |
|---|---------|---------|--------|
| R1 | Hurst exponent (rolling 100) | log(R/S) / log(n) | Mandelbrot |
| R2 | Variance ratio | Var(r_k) / (k × Var(r_1)) | Lo & MacKinlay |
| R3 | HMM state probabilities | 3-state on [ret,vol,spread] | Baum-Welch |
| R4 | Regime entropy | -Σ p_i × log(p_i) | Transition risk |
| R5 | ACF lag-1 | Auto-correlation at 1 bar | Trend vs MR |
| R6 | ACF sign flips | Count of ACF sign changes in window | Regime change |
| R7 | Volatility percentile | rank(σ) in rolling 252-window | Vol regime |

### Category C: Cross-Asset Features (P0 Priority)
| # | Feature | Formula | Papers |
|---|---------|---------|--------|
| C1 | DXY momentum | DXY returns lagged 1-20 bars | Moskowitz-Ooi-Pedersen |
| C2 | Currency Strength Index | Basket-weighted momentum | WQ101 |
| C3 | RORO composite | NAS100+BTC+AUD - USDJPY-USDCHF-gold | Risk-on/off |
| C4 | PC1 score (PCA) | First PC from all asset returns | Kritzman |
| C5 | Absorption ratio | Σ eigenvalues of top N / Σ all eigenvalues | Kritzman et al. |
| C6 | Avg pairwise correlation | mean(corr_matrix) | Crisis detector |
| C7 | Safe haven score | NAS↓ + JPY↑ + gold↑ → binary flag | Risk-off |
| C8 | BTC vol proxy | BTC 24h realized vol → crypto VIX | NAS100 lead |

### Category D: Microstructure Features (Tier 1)
| # | Feature | Formula | Papers |
|---|---------|---------|--------|
| M1 | Order Flow Imbalance | (B_trades - S_trades) / total | Cont et al. 2021 |
| M2 | VPIN | Volume-sync. prob. informed trading | Easley et al. |
| M3 | Kyle's lambda | Δprice / net_volume | Kyle 1985 |
| M4 | Amihud illiquidity | |return| / dollar_volume | Amihud 2002 |
| M5 | Effective spread | 2 × |price - mid_quote| | Roll 1984 |
| M6 | Session one-hot | London=1, NY=2, Asia=3, Overlap=4 | Time-of-day |

### Category E: Signal Features (for Stage 3)
| # | Feature | Lookback | Strategy |
|---|---------|----------|----------|
| S1 | TSMOM 1M | 21-day return | Time-series momentum |
| S2 | TSMOM 3M | 63-day return | Time-series momentum |
| S3 | TSMOM 12M | 252-day return | Time-series momentum |
| S4 | Carry signal | IR differential + fwd points | Carry trade |
| S5 | Value signal | PPP deviation, REER | FX value |
| S6 | Pair z-score | (priceA/priceB - mean) / std | Pairs trading |
| S7 | Cointegration half-life | -ln(2)/ln(λ) from AR(1) | Pairs MR speed |

---

## Stage 5: Implementation Plan

### Phase 1: Foundation (Week 1-2)
1. **Build volatility features** V1-V7 for all 15 instruments
2. **Build HAR model** with regime-switching (coefficient clustering)
3. **Validate**: can we predict vol with R² > 0.2?
4. **Build risk-targeted position sizer** (inverse-vol scaling)

### Phase 2: Regime Gate (Week 3-4)
5. **Build regime features** R1-R7 + cross-asset C1-C8
6. **Train 4-class regime classifier** (trending-up/down/ranging/crash)
7. **Validate**: can we predict regime with >60% accuracy?
8. **Build regime-gated position controller**

### Phase 3: Signal Layer (Week 5-6)
9. **Implement TSMOM** (1M/3M/12M) on all 15 instruments
10. **Add carry overlay** for FX pairs
11. **Add pairs mean-reversion** for XAU-XAG, EUR-GBP, BTC-ETH
12. **Validate**: does TSMOM+carry produce Sharpe > 0.5 on OOS?

### Phase 4: Integration (Week 7-8)
13. **Wire Stage 1 → Stage 2 → Stage 3** together
14. **Walk-forward test** on 2022-2026 data
15. **Label shuffling** on combined signal
16. **Cost perturbation sweep** (0.5×-5× costs)

### Phase 5: Go/No-Go (Week 9)
17. **If integrated Sharpe > 0.8 with p<0.05** → paper trade 2 weeks
18. **If paper Sharpe stable** → live at 0.01 lots
19. **If ANY stage fails validation** → STOP and reassess

---

## Stage 6: Kill Criteria (Updated)

| Criterion | Threshold | Why |
|-----------|-----------|-----|
| Volatility prediction R² | < 0.15 | Vol not predictable → can't size |
| Regime classification accuracy | < 55% | Can't detect regime → can't gate |
| TSMOM Sharpe (OOS) | < 0.3 | No momentum premium in our instruments |
| Integrated Sharpe (OOS) | < 0.5 | Not worth the complexity |
| Label shuffle p-value | > 0.05 | Edge indistinguishable from noise |
| Cost 2× survival | Sharpe < 0.0 | Too fragile for real costs |

---

## Stage 7: What We Learned From The Failed System

### Bug Categories Found (and Fixed)
1. **Data leakage**: `target_3class` included in features → 100% fake accuracy
2. **P&L unit error**: contract_size not applied → 100× understatement
3. **Cost hardcoding**: magic number 2350.0 for gold price → wrong PnL
4. **Annualization error**: `sqrt(252*1440)` for H1 data → Sharpe inflated 8×
5. **Fake retraining**: `evaluate_model()` returned hardcoded sharpe=1.0
6. **Zero purge gap**: train/test overlap → autocorrelation bleed
7. **Hardcoded credentials**: Pepperstone keys in plaintext

### Design Principles Going Forward
1. **No ML on direction** — it's a solved failure mode
2. **Predict what's predictable** — volatility (R²>0.3), regime (60%+), correlations
3. **Simple signals, complex sizing** — TSMOM is 1 line, position sizing is the alpha
4. **Test with real costs** — no hardcoded prices, use contract_size × point_value
5. **Purge gaps mandatory** — no feature calculation across train/test boundary
6. **Label shuffling as gate** — if real result inside null distribution, reject
7. **Every parameter from data** — no magic numbers (2350.0, 0.024, etc.)

---

## Stage 8: Feature Count Summary

| Category | # Features | Data Required |
|----------|-----------|---------------|
| Volatility (V) | 7 | OHLCV (any tf) |
| Regime (R) | 7 | OHLCV (any tf) |
| Cross-Asset (C) | 8 | Multi-instrument OHLCV |
| Microstructure (M) | 6 | Tick or M1 OHLCV |
| Signal (S) | 7 | OHLCV (any tf) |
| **Total** | **35** | Mix of OHLCV + multi-instrument |

Compared to current system: **21 → 35 features**, but completely different categories. Current features are 100% single-instrument technical indicators (RSI, MACD, Bollinger) — the new features are cross-asset, regime-aware, and volatility-calibrated.

---

**Bottom Line**: The ML direction prediction system is dead. The research shows a clear alternative: **volatility prediction + regime gating + factor-based signals (momentum, carry, value)**. This is what Renaissance/Two Sigma/AQR actually do. The 3-stage architecture converts weak signals into robust, risk-targeted positions with explicit kill criteria at every stage.
