# Features V3 — Full Feature List

Generated: 2026-07-02
Source: `scripts/build_features_v3_multi_asset.py`

## Feature Blocks

### 1. SMC Features (Smart Money Concepts)
| Feature | Source | Lag-safe |
|---------|--------|----------|
| swing_high / swing_low | detect_fractals | Yes |
| sweep_bearish_flag / sweep_bullish_flag | detect_sweeps | Yes |
| sweep_magnitude / bars_since_sweep | detect_sweeps | Yes |
| ob_distance_atr / ob_age_bars / ob_strength | detect_order_blocks | Yes |
| fvg_nearest_distance_atr / fvg_nearest_size_atr / fvg_inside_flag | detect_fvg | Yes |
| structure_state / bars_since_bos_choch / structure_event_flag | detect_structure | Yes |
| pool_nearest_distance_atr / pool_age_bars / pool_strength | detect_liquidity_pools | Yes |
| is_london_open / is_ny_open / is_overlap / is_crypto_funding | classify_killzone | Yes |
| ote_in_band / ote_retracement_pct | detect_ote | Yes |
| liquidity_void_flag / size_atr / age_bars | detect_liquidity_voids | Yes |
| ob_mitigation_depth / inversion_fvg_flag | detect_mitigation_and_inversion | Yes |
| judas_swing_flag / judas_direction | detect_judas_swings | Yes |
| wyckoff_range_bound / spring_flag / upthrust_flag | detect_wyckoff_events | Yes |
| vp_poc_distance_atr / vp_inside_value_area / vp_hvn_proximity | volume_profile_features | Yes |

### 2. Technical Features (NEW in Wave 5)
| Feature | Parameters | Description |
|---------|-----------|-------------|
| rsi_14 | period=14 | Relative Strength Index |
| macd | fast=12, slow=26 | MACD line (EMA12 - EMA26) |
| macd_signal | signal=9 | MACD signal line (EMA9 of MACD) |
| macd_hist | — | MACD histogram (MACD - signal) |
| bb_width | length=20, std=2 | Bollinger Band width / mid |
| atr_ratio | period=14 | ATR14 / close |
| adx_14 | period=14 | Average Directional Index |
| dist_ma_20 | period=20 | (close - MA20) / MA20 |
| dist_ma_50 | period=50 | (close - MA50) / MA50 |
| dist_ma_200 | period=200 | (close - MA200) / MA200 |

### 3. FRED Macro Features (forward-filled daily)
| Feature | Series ID | Description |
|---------|-----------|-------------|
| fred_dfii10_daily | DFII10 | 10Y real yield |
| fred_dgs10_daily | DGS10 | 10Y nominal yield |
| fred_vixcls_daily | VIXCLS | Equity vol (VIX) |
| fred_gvzcls_daily | GVZCLS | Gold vol (GVZ) |
| fred_dcoilwtico_daily | DCOILWTICO | Oil price |
| fred_dtwexbgs_daily | DTWEXBGS | Broad dollar index |

### 4. COT Positioning Features (forward-filled weekly)
| Feature | Description |
|---------|-------------|
| cot_gold_commercials_net_pct | Commercial hedger net positioning |
| cot_gold_managed_money_net_pct | Managed money net positioning |
| cot_gold_open_interest | Total open interest |

### 5. Categorical Encoding
All object/string columns are encoded to numeric codes via pandas category encoding.

## Lookahead Safety
- All SMC detectors are lag-safe by design
- Technical features use only past/current bar data (rolling windows, EWM)
- FRED features forward-fill daily — no future data
- COT features forward-fill weekly — no future data
- MA distance uses current close vs historical MA — no future data

## Total Feature Count
- SMC block: ~35 features
- Technical block: 10 features
- FRED block: 6 features
- COT block: 3 features
- **Total: ~54 features**
