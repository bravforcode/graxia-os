# FEATURE_SIGNAL_AUDIT.md — Phase 5

## 5.1 — Complete Feature Inventory

The ML pipeline generates ~35 features in `ml/pipeline.py:88-210`:

| Feature | Formula | Code Location | Window | Stationary? | Tested? |
|---------|---------|---------------|--------|-------------|---------|
| return_1 | pct_change(1) | pipeline.py:95 | 1 | Yes | Yes |
| return_5 | pct_change(5) | pipeline.py:96 | 5 | Yes | Yes |
| return_10 | pct_change(10) | pipeline.py:97 | 10 | Yes | Yes |
| return_20 | pct_change(20) | pipeline.py:98 | 20 | Yes | Yes |
| log_return_1 | log(close/close.shift(1)) | pipeline.py:100 | 1 | Yes | Yes |
| price_position_20 | (close - rolling_min) / (rolling_max - rolling_min) | pipeline.py:105 | 20 | Yes | Yes |
| ema_9_dist | (close - EMA9) / EMA9 | pipeline.py:112 | 9 | Yes | Yes |
| ema_20_dist | (close - EMA20) / EMA20 | pipeline.py:112 | 20 | Yes | Yes |
| ema_50_dist | (close - EMA50) / EMA50 | pipeline.py:112 | 50 | Yes | Yes |
| ema_200_dist | (close - EMA200) / EMA200 | pipeline.py:112 | 200 | Yes | Yes |
| ema_cross_9_20 | (EMA9 - EMA20) / EMA20 | pipeline.py:118 | 9/20 | Yes | Yes |
| rsi_14 | RSI(14) | pipeline.py:122 | 14 | Yes | Yes |
| rsi_14_normalized | (RSI - 50) / 50 | pipeline.py:123 | 14 | Yes | Yes |
| macd | MACD line | pipeline.py:127 | 12/26/9 | Yes | Yes |
| macd_signal | MACD signal | pipeline.py:128 | 12/26/9 | Yes | Yes |
| macd_hist | MACD histogram | pipeline.py:129 | 12/26/9 | Yes | Yes |
| bb_width | (upper - lower) / mid | pipeline.py:133 | 20 | Yes | Yes |
| bb_position | (close - lower) / (upper - lower) | pipeline.py:134 | 20 | Yes | Yes |
| atr_14 | ATR(14) | pipeline.py:140 | 14 | Yes | Yes |
| atr_ratio | ATR / close | pipeline.py:141 | 14 | Yes | Yes |
| adx | ADX(14) | pipeline.py:145 | 14 | Yes | Yes |
| volume_ratio | volume / SMA(volume, 20) | pipeline.py:155 | 20 | Yes | Yes |
| volume_change | pct_change(1) of volume | pipeline.py:157 | 1 | Yes | Yes |
| obv_trend | (OBV - SMA(OBV,20)) / SMA(OBV,20) | pipeline.py:163 | 20 | Yes | Yes |
| realized_vol_20 | std(pct_change, 20) * sqrt(252) | pipeline.py:166 | 20 | Yes | Yes |
| realized_vol_5 | std(pct_change, 5) * sqrt(252) | pipeline.py:167 | 5 | Yes | Yes |
| vol_ratio | rvol_5 / rvol_20 | pipeline.py:168 | 5/20 | Yes | Yes |
| gk_vol_14 | Garman-Klass(14).shift(1) * sqrt(252*23) | pipeline.py:178 | 14 | Yes | Yes |
| gk_vol_20 | Garman-Klass(20).shift(1) * sqrt(252*23) | pipeline.py:179 | 20 | Yes | Yes |
| parkinson_vol_14 | Parkinson(14).shift(1) * sqrt(252*23) | pipeline.py:183 | 14 | Yes | Yes |
| candle_body_ratio | body / range | pipeline.py:186 | 1 | Yes | Yes |
| upper_shadow | upper_shadow / range | pipeline.py:187 | 1 | Yes | Yes |
| lower_shadow | lower_shadow / range | pipeline.py:188 | 1 | Yes | Yes |
| momentum_10 | close - close.shift(10) | pipeline.py:195 | 10 | No (price) | Yes |
| momentum_20 | close - close.shift(20) | pipeline.py:196 | 20 | No (price) | Yes |
| stoch_k | Stochastic %K | pipeline.py:200 | 14 | Yes | Yes |
| stoch_d | Stochastic %D | pipeline.py:201 | 14 | Yes | Yes |

**SMC detectors** (in `strategies/mlb.py:328-329`):
- `swing_high`: rolling(5, center=True).max() == high — **LOOKAHEAD BIAS** (P1)
- `swing_low`: rolling(5, center=True).min() == low — **LOOKAHEAD BIAS** (P1)

## 5.2 — IC / Correlation Figures

- No IC/IR figures are reported in the current codebase for the 35 ML features
- `validation/signal_validator.py` has IC analysis capability but no stored results found
- **[IC ANALYSIS NOT PERFORMED OR NOT REPORTED]**

## 5.3 — Multiple Testing Problem

- **Features tested**: ~35 in ML pipeline + ~6 SMC detectors = ~41 total
- **Significance level**: Not explicitly set (no Bonferroni/BH-FDR correction found in feature selection)
- **Expected false positives**: At α=0.05, E[FP] = 0.05 × 41 = ~2 features could be spurious
- **Correction**: NONE APPLIED — **[UNCORRECTED FOR MULTIPLE TESTING — may be spurious]**

## 5.4 — Feature Stationarity

- Return-based features (return_N, pct_change) are stationary by construction — **PASS**
- `momentum_10`, `momentum_20` are non-stationary (price differences) — **P3 FINDING**: these should be converted to returns for stationarity
- No ADF/KPSS tests found in the codebase — **[UNVERIFIED]**

## 5.5 — Feature Interdependence

- No correlation matrix computed for features — **[UNVERIFIED]**
- EMA features (9, 20, 50, 200) are highly correlated by construction — flagging

## 5.8 — Feature Importance Stability

- XGBoost feature importances available via `model.feature_importances_` in `ml/pipeline.py:296`
- No fold-by-fold stability analysis found — **[NEVER CHECKED]**

## 5.10 — SMC Detector Audit

- `swing_high` and `swing_low` in `strategies/mlb.py:328-329` use `center=True` — **CONFIRMED LOOKAHEAD/REPAINT**
- Running these detectors live bar-by-bar would produce different labels than running vectorized on full data
- **P1 FINDING**: Equivalent severity to Phase 1 lookahead findings

---

**P0 Findings**: 0
**P1 Findings**: 2 (SMC center=True repaint, no IC analysis)
**P2 Findings**: 1 (multiple testing uncorrected)
**P3 Findings**: 2 (non-stationary momentum features, no correlation matrix)
