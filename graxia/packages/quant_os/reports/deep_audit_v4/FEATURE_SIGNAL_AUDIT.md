# FEATURE & SIGNAL AUDIT — Phase 5
**Date:** 2026-07-05 | **Auditor:** Strategist Agent | **Protocol:** QUANT_BOT_DEEP_AUDIT_PROMPT_v4.md

---

## 5.1 — Complete Feature Inventory

### A. build_features.py — Standard Technical Features (~36 features)
`scripts/build_features.py:126-204`

| # | Feature | Formula | Line | Window | Stationary? |
|---|---------|---------|------|--------|-------------|
| 1 | return_1 | close.pct_change(1) | 132 | 1 | ~Yes |
| 2 | return_5 | close.pct_change(5) | 133 | 5 | ~Yes |
| 3 | return_10 | close.pct_change(10) | 134 | 10 | ~Yes |
| 4 | return_20 | close.pct_change(20) | 135 | 20 | ~Yes |
| 5 | log_return | log(close/shift(1)) | 138 | 1 | ~Yes |
| 6-9 | sma_5,10,20,50 | close.rolling(window).mean() | 142-143 | 5,10,20,50 | NO — raw MA |
| 10-13 | ema_5,10,20,50 | close.ewm(span).mean() | 144 | 5,10,20,50 | NO — raw MA |
| 14 | macd | ema_12 - ema_26 | 147-148 | 12/26 | ~Yes |
| 15 | macd_signal | macd.ewm(9).mean() | 149 | 9 | ~Yes |
| 16 | macd_hist | macd - signal | 150 | — | ~Yes |
| 17-19 | rsi_7,14,21 | RSI formula | 154-155 | 7,14,21 | YES (0-100) |
| 20 | stoch_k | %K(14,3) | 160 | 14 | YES (0-100) |
| 21 | stoch_d | stoch_k.rolling(3).mean() | 161 | 3 | YES (0-100) |
| 22 | roc_10 | pct_change(10)*100 | 164 | 10 | ~Yes |
| 23 | roc_20 | pct_change(20)*100 | 165 | 20 | ~Yes |
| 24 | bb_upper | SMA20 + 2*std | 169 | 20 | NO — price-level |
| 25 | bb_middle | SMA20 | 170 | 20 | NO — price-level |
| 26 | bb_lower | SMA20 - 2*std | 171 | 20 | NO — price-level |
| 27 | bb_width | (upper-lower)/mid | 173 | 20 | ~Yes |
| 28 | bb_pct | (close-lower)/(upper-lower) | 174 | 20 | YES (0-1) |
| 29 | atr_14 | ATR(14) | 177 | 14 | NO — scale-dependent |
| 30 | volatility_10 | rolling(10).std()*√252 | 180 | 10 | ~Yes |
| 31 | volatility_20 | rolling(20).std()*√252 | 181 | 20 | ~Yes |
| 32 | volume_sma_20 | volume.rolling(20).mean() | 185 | 20 | NO — scale |
| 33 | volume_ratio | volume/volume_sma_20 | 186 | 20 | ~Yes |
| 34 | obv | cumulative volume*sign(diff) | 187 | — | NO — cumulative |
| 35 | body | close - open | 191 | 1 | ~Yes (raw diff) |
| 36 | body_pct | body/open | 192 | 1 | ~Yes |
| 37 | upper_shadow | high - max(open,close) | 193 | 1 | ~Yes |
| 38 | lower_shadow | min(open,close) - low | 194 | 1 | ~Yes |
| 39 | hour | index.hour | 198 | — | NO — cyclical |
| 40 | day_of_week | index.dayofweek | 199 | — | NO — cyclical |
| 41 | is_london | hour 7-16 bool | 200 | — | NO — categorical |
| 42 | is_ny | hour 12-21 bool | 201 | — | NO — categorical |
| 43 | is_overlap | hour 12-16 bool | 202 | — | NO — categorical |

### B. build_mega_features.py — Microstructure (~52 features)
`scripts/build_mega_features.py:164-295`

| # | Feature Group | Count | Examples | Window |
|---|--------------|-------|----------|--------|
| 44-49 | Returns (multi-bar) | 6 | ret_1bar, ret_5bar...ret_60bar | 1-60 |
| 50-52 | ATR ratios | 3 | atr_7,14,21 | 7-21 |
| 53-55 | Rolling volatility | 3 | rvol_10,20,60 | 10-60 |
| 56-58 | RSI | 3 | rsi_7,14,21 | 7-21 |
| 59-60 | Stochastic | 2 | stoch_k, stoch_d | 14 |
| 61 | CCI | 1 | cci_20 | 20 |
| 62 | Williams %R | 1 | willr_14 | 14 |
| 63-68 | EMA distances | 6 | ema_5_dist...ema_200_dist | 5-200 |
| 69-70 | SMA crosses | 2 | sma_20_50_cross, sma_50_200_cross | 20-200 |
| 71 | ADX | 1 | adx_14 | 14 |
| 72-74 | BB width/pctb/squeeze | 3 | bb_width, bb_pctb, bb_squeeze | 20-120 |
| 75 | OBV slope | 1 | obv_slope_20 | 20 |
| 76 | VWAP distance | 1 | vwap_dist | 96 |
| 77 | Vol ratio | 1 | vol_ratio_20 | 20 |
| 78 | Body ratio | 1 | body_ratio | 1 |
| 79-80 | Shadows | 2 | upper_shadow, lower_shadow | 1 |
| 81-84 | Candlestick | 4 | is_doji, is_hammer, is_bull_engulf, is_bear_engulf | 1-2 |

### C. build_mega_features.py — Cross-Asset + Macro (~90 features)
`scripts/build_mega_features.py:298-550`

| # | Source | Count | Examples |
|---|--------|-------|----------|
| 85-140 | yfinance (28 tickers × 5 cols) | ~56 | gold_futures_close, dxy_close, vix_close, sp500_close... |
| 141-176 | FRED daily (29 series) | ~29 | fred_dfii10, fred_dgs10, fred_vixcls, fred_dcoilwtico... |
| 177-182 | FRED monthly (6 series) | ~6 | fred_unrate, fred_cpiaucsl, fred_fedfunds... |
| 183-185 | COT (3 cols) | ~3 | cot_gold_commercials_net_pct, managed_money_net_pct, open_interest |

### D. build_features_v3_multi_asset.py — SMC Features (~30 features)
`scripts/build_features_v3_multi_asset.py:121-166`

| # | Detector | Features | Location in smc_detectors.py |
|---|----------|----------|------------------------------|
| 186-187 | Fractals | swing_high, swing_low | :94-160 |
| 188-191 | Liquidity Sweeps | sweep_bearish_flag, sweep_bullish_flag, sweep_magnitude, bars_since_sweep | :166-257 |
| 192-194 | Order Blocks | ob_distance_atr, ob_age_bars, ob_strength | :262-380 |
| 195-197 | Fair Value Gaps | fvg_nearest_distance_atr, fvg_nearest_size_atr, fvg_inside_flag | :394-492 |
| 198-200 | Structure (BOS/CHoCH) | structure_state, bars_since_bos_choch, structure_event_flag | :498-621 |
| 201-203 | Liquidity Pools (EQH/EQL) | pool_nearest_distance_atr, pool_age_bars, pool_strength | :627-721 |
| 204-207 | Killzones | is_london_open, is_ny_open, is_overlap, is_crypto_funding | :756-823 |
| 208-209 | OTE | ote_in_band, ote_retracement_pct | :829-878 |
| 210-212 | Liquidity Voids | liquidity_void_flag, liquidity_void_size_atr, liquidity_void_age_bars | :883-932 |
| 213-214 | Mitigation + Inversion | ob_mitigation_depth, inversion_fvg_flag | :938-1007 |
| 215-216 | Judas Swing | judas_swing_flag, judas_direction | :1013-1072 |
| 217-219 | Wyckoff Events | wyckoff_range_bound, wyckoff_spring_flag, wyckoff_upthrust_flag | :1059-1114 |
| 220-222 | Volume Profile | vp_poc_distance_atr, vp_inside_value_area, vp_hvn_proximity | :1120-1215 |

### E. FRED + COT from build_features_v3 (~11 features)
`scripts/build_features_v3_multi_asset.py:169-252`

| # | Source | Features | Line |
|---|--------|----------|------|
| 223-228 | FRED Core (6 series) | fred_dfii10_daily...fred_dtwexbgs_daily | :200-211 |
| 229-231 | COT Gold (3 cols) | cot_gold_commercials_net_pct, etc. | :243-252 |

**TOTAL FEATURE ESTIMATE: ~220-250 columns** when all feature builders run (with significant overlap where v1/v2/v3 share standard indicators).

---

## 5.2 — IC / Correlation Figures Verification

### What Is Claimed
- `reports/FULL_REPOSITORY_AUDIT.md:140`: "max |r| ≈ 0.06 on 1-min features" — marked as **UNVERIFIED**, from "likely external analysis, not in codebase"
- `SUMMARY.md:6`: "58.2% accuracy OOS at conf≥0.75" — claimed in summary
- `reports/deep_audit_v4/HONEST_SCORECARD.md:13`: "Is there a statistically significant OOS edge after costs? → INSUFFICIENT EVIDENCE"

### What Is Actually Implemented
- `scripts/diagnose_features.py:62-169`: Computes **both Pearson and Spearman** correlation, mutual information, with **Bonferroni correction** applied (α = 0.05/N_features at line 132).
- Default noise floor: |r| > 0.02 (`scripts/diagnose_features.py:65`)
- Walk-forward stability check: splits data, checks sign consistency between train/test halves (`:137-145`)
- **No results in codebase** — the script exists but generated output files (under `artifacts/diagnostics/`) are not in the repo.
- `scripts/audit_full.py:166-216`: Computes feature correlation matrix, flags |ρ| > 0.95 pairs only (redundancy), does NOT compute IC.

### Verdict
- **IC peak value**: UNVERIFIED — |r| ≈ 0.06 is a reported number with no code trace
- **IC type (Pearson/Spearman)**: Both implemented in `diagnose_features.py`, actual output unknown
- **IC decay curve**: NOT IMPLEMENTED — no code computes IC as a function of horizon
- **ICIR (Information Coefficient IR)**: NOT COMPUTED — no aggregate ICIR calculation found
- **Walk-forward IC stability**: IMPLEMENTED in `diagnose_features.py:137-145` but no results
- **All IC figures**: `[UNVERIFIED — diagnostic tools exist but no output preserved]`

---

## 5.3 — Multiple Testing Problem

| Parameter | Value | Source |
|-----------|-------|--------|
| Total features tested | ~50-250 (depends on pipeline) | build_features.py + mega + v3 |
| Independent hypotheses | NOT ESTIMATED — high multicollinearity (EMAs of different periods are ~identical) | — |
| Significance level α | 0.05 default | `diagnose_features.py:132` |
| E[FP] = α × N | 0.05 × 50 = 2.5 to 0.05 × 250 = 12.5 expected false positives | — |
| Bonferroni correction | IMPLEMENTED in `diagnose_features.py:132` (`bonf_alpha = 0.05 / n_features_tested`) | Fair |
| BH-FDR correction | NOT FOUND — `FULL_REPOSITORY_AUDIT.md:147-148` confirms absent | — |
| In practice | `[UNCORRECTED FOR MULTIPLE TESTING]` in all strategy selection and walk-forward aggregation | `FULL_REPOSITORY_AUDIT.md:149` |

**Key gap**: `diagnose_features.py` applies Bonferroni internally but its results are not used by any strategy selection or parameter optimization code. `scripts/walk_forward.py` evaluates multiple confidence thresholds (`:386`) without correcting for the threshold sweep itself. `ParamSweep` (`core/param_sweep.py`) tests all grid combinations and picks the best without any multiple-testing adjustment.

---

## 5.4 — Feature Stationarity

### ADF/KPSS Tests
- **NOT FOUND** — no ADF (Augmented Dickey-Fuller) or KPSS test implemented anywhere in the codebase
- The word "stationarity" appears nowhere in `build_features.py`, `build_features_v3_multi_asset.py`, or `build_mega_features.py`

### Raw Price as Feature
- **YES — multiple raw price-level features used directly:**
  - `sma_5/10/20/50` (line-average of raw price) — `build_features.py:143`
  - `ema_5/10/20/50` — `build_features.py:144`
  - `bb_upper/middle/lower` — `build_features.py:169-171`
  - `atr_14` (scale-dependent, not normalized to price) — `build_features.py:177`
  - `ema_5_dist`...`ema_200_dist` use `(close-ema)/ema` (normalized) — `build_mega_features.py:219`

### Verdict
- `[FAIL]` — Raw price-level features (SMA, EMA, BB levels, ATR) fed into XGBoost will lose stationarity. Tree-based models are partially robust to trends, but break in out-of-sample regimes (e.g., XAUUSD at $3,000 vs training at $1,800). StandardScaler (`core/ml_pipeline.py:152`) will center but spreads will be regime-dependent.
- **Normalized alternatives exist** (`ema_dist`, `bb_pctb`) but are mixed with raw-level features in the same dataset.

---

## 5.5 — Feature Interdependence

| Check | Status | Source |
|-------|--------|--------|
| Correlation matrix computed | YES, but only for |ρ| > 0.95 pairs | `scripts/audit_full.py:181-197` |
| |ρ| > 0.7 flagging threshold | NOT USED — threshold is 0.95 | `:189` |
| Identifiable multicollinear groups | Multiple: EMA 5/10/20/50/100/200 — near-perfect cross-correlations | `build_features.py:142-144`, `build_mega_features.py:217-219` |
| SMA 20_50 and 50_200 crosses | Partially redundant with EMA distances | — |

**Severity**: EMA_5 through EMA_200 are all highly collinear (correlations likely > 0.9). The feature deletion/quarantine list (`data/feature_deletion_list.json`, referenced at `build_features_v3_multi_asset.py:62`) exists but content is not in-repo. Use of unnecessary redundant features inflates N_tests and worsens the multiple-testing problem.

---

## 5.6 — Feature Stability Across Regimes

- **IC broken down by regime**: NOT COMPUTED — no code divides feature IC by high/low volatility or trending/ranging
- `core/regime_filter.py` and `regime/detector.py` exist and classify regimes, but never joined with feature IC analysis
- `scripts/diagnose_regime_accuracy.py` exists (referenced path) but only checks model accuracy, not feature IC

**Verdict**: `[NOT TESTED]` — No regime-conditional feature IC decomposition.

---

## 5.7 — Hypothesis Log

- `RESEARCH_LOG.md`: Exists and follows format — but contains only **3 experiments**, 2 of which are marked "NOT STARTED"
  - EXP-001: XGBoost on XAUUSD H1 → **FAIL** (net -$1,225, Sharpe 0.3)
  - EXP-002: Session filter → NOT STARTED
  - EXP-003: Limit order simulation → NOT STARTED
- `Meta/` directory: Contains `Meta/research/DEEP_DIVE_SYNTHESIS.md` and other research docs
- **No centralized hypothesis log tracking feature-level hypotheses** — the log records strategies, not feature significance claims

**Verdict**: `[SPARSE]` — RESEARCH_LOG.md is 31 lines. No feature-level hypothesis tracking.

---

## 5.8 — Feature Importance Stability Across Folds

- `scripts/walk_forward.py` trains XGBoost per fold but does NOT extract or store feature importance per fold
- `validation/walk_forward.py` has no feature importance tracking
- XGBoost's `feature_importances_` attribute is computed per model but never collected (`scripts/walk_forward.py:186` — `model.fit()` but no `.feature_importances_`)
- No SHAP values computed

**Verdict**: `[NOT TESTED]` — Feature importance across folds cannot be assessed.

---

## 5.9 — Theoretical Capacity / Crowding

- **No argument provided** for why public-price-data features (EMA crosses, RSI, MACD) should persist
- No capacity analysis (spread capture vs cost)
- No crowding analysis (open interest changes reflecting strategy adoption)
- `reports/edge_detection_research.md:69-101` discusses edge decay theory but never maps it to this system's specific features

**Verdict**: `[NO DEFENSE STATED]` — The feature set is standard TA. No theoretical basis for expecting persistence against efficient-market pressures.

---

## 5.10 — SMC Detector Audit

### Detector-by-Detector Analysis

All detectors in `core/smc_detectors.py` — module-level docstring at `:9-17` claims "Every detector is lookahead-safe."

| # | Detector | Requires Bars AFTER t? | Repaint Risk? | Analysis |
|---|----------|----------------------|---------------|----------|
| 1 | Swing Points (Fractals) | YES — k=2 bars after. Event timestamp shifted to confirmation bar i+k (`:127-129`). | Controlled — explicit lag. Feature columns placed at confirmation bar. | `:94-160` |
| 2 | Liquidity Sweeps | YES — requires close[i] to have reclaimed level. Checks in same-bar loop but triggers on close confirm. | Low — uses current bar close (operates at close of sweep bar). | `:166-257` |
| 3 | Order Blocks | Partially — detects OB at close of structure-break bar (bar i). Mitigation tracked over future bars. Features USE only OBs with bar_idx < current. | Controlled — OB identified at bar j, features available from bar j+1 forward (only if end_bar_idx check passes). | `:262-380` |
| 4 | Fair Value Gaps | **YES — 1-bar lookahead in detection** — `high[i-1] < low[i+1]` at line 420. FVG classified at bar i using bar i+1 data. Features compensate: only use FVGs where `end_bar_idx < current` (line 462). | **Detection repaints but feature usage is safe.** `[PARTIALLY MITIGATED]` | `:394-492` |
| 5 | Structure (BOS/CHoCH) | Partially — uses swing points which are already lagged by k bars. New swing at bar i confirms structure event immediately. | Low — since swings have k-bar lag, the structure event is effectively lag-adjusted. | `:498-621` |
| 6 | EQH/EQL (Liquidity Pools) | NO — pool clustering uses swing points (already lagged). Features use pools with `newest_bar_idx < current`. | Safe — swings are lagged, pools are based on confirmed swings. | `:627-721` |

### Repainting Assessment

**The FVG detector is the only one with a 1-bar lookahead in pattern classification** (`:420` — uses `low[i+1]`). The feature-usage pattern (`:462` — `f.end_bar_idx >= i: continue`) mitigates this for features but **not for event consumers**.

- If any code path uses `fvg.timestamp` as the signal time (which is set to bar i at `:425`), it would be using information from bar i+1 to make a decision at bar i.
- The module docstring (`:13-14`) claims: "fractal highs/lows are only marked once the confirming future bar has closed." This is true for fractals but **false for FVG timestamps** which are set to the middle bar (i), not the confirmation bar (i+1).

### IC Values for SMC Detectors

- **NOT reported separately** — no file extracts per-detector IC for SMC features
- The feature columns are all numerical and fed into XGBoost, which may learn any signal, but there is no per-detector validation

---

## 5. — FINAL VERDICT (Phase 5)

| Criterion | Status |
|-----------|--------|
| Complete feature inventory | PARTIAL — features exist in 3 separate scripts; inventory requires manual reconciliation |
| IC/correlation verification | INSUFFICIENT EVIDENCE — tools exist, output missing |
| Multiple testing correction | FAIL — Bonferroni tool exists but unused in strategy selection |
| Stationarity | FAIL — raw price-level features, no ADF/KPSS |
| Interdependence | WEAK — only |ρ|>0.95 flagged, not 0.7 |
| Regime stability | NOT TESTED |
| Hypothesis log | SPARSE — 31-line RESEARCH_LOG.md |
| Feature importance stability | NOT TESTED |
| Crowding/capacity | NO DEFENSE |
| SMC repainting | PARTIAL — FVG has 1-bar lookahead in detection, feature path compensated |

**Overall**: `[INSUFFICIENT EVIDENCE]` — The feature infrastructure is extensive but evidence of predictive power is missing or unreported.
