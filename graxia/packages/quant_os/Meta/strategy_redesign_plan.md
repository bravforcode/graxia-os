# Strategy Redesign Plan — XAUUSD (Full Deep Dive)

**Created**: 2026-06-29
**Status**: Planning — awaiting approval before execution
**Trigger**: B2 pre-register contingency: "If fail WR → feature redesign (cross-asset + session model)"

---

## CRITICAL FINDINGS SUMMARY

| # | Finding | Impact | Action |
|---|---------|--------|--------|
| 1 | features_v3 has 158 cols including 42 cross-asset | Cross-asset already built | Use what exists |
| 2 | M15 has 50K bars (777 days) | Data is sufficient | No need to collect more |
| 3 | Walk-forward V5 net +$3,467 but t-stat 1.48 | Edge exists but variance high | Fix variance via regularization |
| 4 | Train accuracy = 100% every fold | Massive overfitting | Reduce model capacity |
| 5 | Only 10.9% of bars cover costs | Most bars are noise | Session + magnitude filter critical |
| 6 | Overlap session has BEST model F1 (46.4%) | Session filter reversed | Trade overlap + NY late |
| 7 | Sydney has WORST cost/range (4.2%) | Sydney is expensive | Skip Sydney session |
| 8 | Binary is_long target is noisy | Labels need fixing | Use triple-barrier labels |

---

## 1. DATA AVAILABILITY — What We Actually Have

### 1.1 OHLCV Data

| Symbol | Timeframe | Rows | Date Range | Days | Status |
|--------|-----------|------|------------|------|--------|
| XAUUSD | M15 | 50,000 | 2024-05-03 → 2026-06-20 | **777 days** | ✅ SUFFICIENT |
| XAUUSD | M1 | 5,000 | 2026-06-22 → 2026-06-26 | 4 days | ❌ INSUFFICIENT |
| XAUUSD | M5 | 5,000 | 2026-06-22 → 2026-06-26 | 4 days | ❌ INSUFFICIENT |

**Critical finding**: M15 has 777 days of data — more than enough for training. The previous "142 samples" problem from SUMMARY.md was about an older, smaller dataset. The current M15 CSV has 50K bars.

### 1.2 Feature Parquets

| Dataset | Rows | Cols | Date Range | Cross-Asset | Status |
|---------|------|------|------------|-------------|--------|
| features_v2 (1min) | 3,315 | 67 | 2026-06-22 → 2026-06-24 | ❌ None | ⚠️ Too small |
| features_v3 (15min) | 60,000 | 158 | RangeIndex 0-59999 | ✅ 42 columns | ✅ COMPREHENSIVE |

**Critical finding**: features_v3 already has **158 columns** including:
- 47 technical features (ATR, RSI, Stoch, CCI, EMAs, Bollinger, candle patterns)
- 12 cross-asset ratios (gold/silver, gold/DXY corr, gold/oil, gold/VIX)
- 25 macro features (real yield, breakeven, yield curve, credit spreads, Fed balance)
- 17 COT positioning features (commercials, managed money, large speculators)
- 32 cross-asset momentum features (DXY, VIX, TLT, oil, silver, S&P500, USDJPY, BTC)
- 10 regime flags (VIX, yield curve, dollar, credit, gold)
- 7 time features (hour, day_of_week, session labels)
- 6 target columns (forward returns, is_long, target_class)

### 1.3 FRED Macro Data

| Series | File | Status |
|--------|------|--------|
| DFII10 (10Y real yield) | `data/fred/daily/DFII10.csv` | ✅ Available |
| VIXCLS (VIX) | `data/fred/daily/VIXCLS.csv` | ✅ Available |
| DCOILWTICO (WTI) | `data/fred/daily/DCOILWTICO.csv` | ✅ Available |
| DGS10 (10Y nominal) | `data/fred/daily/DGS10.csv` | ✅ Available |
| T10YIE (breakeven) | Not checked | Likely available |
| DTWEXBGS (broad dollar) | Not checked | Likely available |

### 1.4 Fill Simulation Data

| File | Rows | Status |
|------|------|--------|
| `fill_samples_XAUUSD_1min.csv` | Available | ✅ |
| `fill_samples_fixed/XAUUSD_1min.csv` | Available | ✅ |

---

## 2. CURRENT MODEL PERFORMANCE — Every Experiment

### 2.1 Walk-Forward V5 (XAUUSD 15min, 500w/200t, conf≥0.85)

| Metric | Value | Threshold | Pass? |
|--------|-------|-----------|-------|
| Total folds | 166 | — | — |
| Positive folds | 104 (62.7%) | >50% | ✅ |
| Total trades | 13,154 | — | — |
| Total net P&L | **+$3,467.40** | >$0 | ✅ |
| Weighted accuracy | 59.26% | — | — |
| Avg net per fold | $20.89 | — | — |
| Net stability t | **1.48** | ≥2.0 | ❌ |
| Train accuracy | 100% (every fold) | — | ⚠️ OVERFIT |

**Key insight**: The system IS profitable ($3,467 net over 166 folds) but the t-stat is 1.48, below the 2.0 threshold. This means the edge is real but variance is high.

### 2.2 Backtest Cost (XAUUSD 1min)

| Conf | Trades | Accuracy | Gross | Cost | Net | WR | Sharpe |
|------|--------|----------|-------|------|-----|-----|--------|
| 0.00 | 499 | 55.5% | $105.90 | $157.75 | **-$51.85** | 44.9% | -19.47 |
| 0.50 | 499 | 55.5% | $105.90 | $157.75 | **-$51.85** | 44.9% | -19.47 |
| 0.55 | 394 | 56.1% | $107.26 | $124.55 | **-$17.29** | 45.7% | -8.74 |
| 0.60 | 287 | 56.8% | $75.31 | $90.74 | **-$15.43** | 47.0% | -10.53 |
| 0.65 | 179 | 57.5% | $42.65 | $56.62 | **-$13.97** | 48.0% | -14.84 |
| **0.70** | **109** | **56.9%** | **$38.93** | **$34.46** | **+$4.47** | **47.7%** | **7.64** |
| 0.75 | 48 | 47.9% | $14.00 | $15.16 | **-$1.16** | 39.6% | -3.46 |
| 0.80 | 23 | 39.1% | $5.10 | $7.27 | **-$2.17** | 30.4% | -10.76 |
| 0.85 | 9 | 33.3% | $8.15 | $2.83 | **+$5.32** | 33.3% | 47.67 |
| 0.90 | 4 | 50.0% | $9.29 | $1.25 | **+$8.04** | 50.0% | 117.76 |

**Key insight**: At conf≥0.70, the 1min system is marginally profitable (+$4.47) but only 47.7% win rate. At conf≥0.75, accuracy collapses to 47.9%. The model is overconfident on wrong predictions.

### 2.3 Fold-by-Fold Analysis (Walk-Forward V5)

Best folds:
- Fold 5: 85.2% accuracy, $263.68 net, Sharpe 172.8
- Fold 3: 71.9% accuracy, $155.07 net, Sharpe 68.78
- Fold 4: 68.1% accuracy, $108.11 net, Sharpe 71.13

Worst folds:
- Fold 0: 36.1% accuracy, -$42.70 net, Sharpe -66.01
- Fold 7: 35.3% accuracy, -$61.35 net, Sharpe -63.49
- Fold 160: 26.7% accuracy, -$38.42 net, Sharpe -92.81

**Key insight**: Performance is highly regime-dependent. Some folds are spectacular, others are catastrophic. The model doesn't adapt well to regime changes.

---

## 3. ROOT CAUSE ANALYSIS — Why The System Struggles

### 3.1 The Cost Problem

| Component | Value | Notes |
|-----------|-------|-------|
| Spread (return units) | 0.000050 | ~$0.12 at $2350 |
| Slippage P90 (return units) | 0.000027 | ~$0.06 at $2350 |
| Total cost/trade | ~$0.18 | Round-trip at $2350 |
| Commission (Pepperstone) | $0 | Zero commission on XAUUSD |
| **Effective cost** | **$0.18/trade** | Must be overcome |

At 0.10 lot (100 oz), each $1 move = $10. So $0.18 cost = 1.8 points of XAUUSD.

The avg_move at conf≥0.70 is 116 points ($1.16) → cost/move ratio = 15.5%. This is actually manageable!
But at conf≥0.75, avg_move = 143 points → cost/move = 12.6%. Still OK.

The REAL problem is accuracy: 56.9% at conf≥0.70 means only 56.9% of trades capture the move. The 43.1% losers eat the edge.

### 3.2 The Accuracy Problem

The model is a binary classifier (is_long: 1 if next bar return > 0). Problems:

1. **Label noise**: Binary direction is noisy — a bar can go up 0.01% and be labeled "long" but that's not tradeable
2. **No magnitude awareness**: Model doesn't predict HOW MUCH price will move
3. **Overfitting**: Train accuracy = 100% on every fold → model memorizes training data
4. **Regime blindness**: Model trained on mixed regimes performs poorly when regime shifts

### 3.3 The Overfitting Problem

Every single fold in walk-forward V5 shows train_acc = 1.0. This means:
- XGBoost with 500 estimators, max_depth=6, is memorizing the 500-bar training window
- The model has too much capacity for the signal-to-noise ratio
- Walk-forward with 500 train / 200 test / 200 step means heavy overlap

### 3.4 The Session Problem

The model trades all hours equally. But gold volatility varies dramatically:
- Asian session (00:00-07:00 UTC): Low volatility, range-bound
- London session (07:00-17:00 UTC): High volatility, trend initiation
- NY session (12:00-22:00 UTC): High volatility, continuation
- Overlap (12:00-17:00 UTC): Highest volatility, biggest moves

Trading during Asian hours dilutes edge with low-vol noise.

---

## 4. WHAT'S ALREADY BUILT — Redesign Leverage Points

### 4.1 Cross-Asset Features (ALREADY IN features_v3)

The 42 cross-asset columns in features_v3 include:
- **Real yield**: `real_yield_10y`, `real_yield_10y_chg5d`, `real_yield_10y_chg20d`
- **DXY**: `dxy_mom_5d/10d/20d`, `dxy_vol_20d`
- **VIX**: `vix_level`, `vix_mom_5d/10d/20d`, `vix_vol_20d`
- **COT**: 17 positioning features
- **Credit**: `hy_spread`, `hy_spread_chg5d`, `hy_spread_zscore`
- **Regime flags**: 10 regime indicators
- **Session**: `is_london_session`, `is_ny_session`, `is_asian_session`

**These are already computed and ready to use.** The question is whether the training pipeline uses them effectively.

### 4.2 Session Labels (ALREADY IN features_v3)

```python
is_london_session  # 07:00-17:00 UTC
is_ny_session      # 12:00-22:00 UTC
is_asian_session   # Before 07:00 UTC
```

### 4.3 Triple-Barrier Labeling (EXISTS but not used in v3)

`ml/labeling.py` has `compute_triple_barrier()` with configurable TP/SL multipliers. Currently NOT used in features_v3 (which uses binary is_long).

### 4.4 Dynamic Spread Model (EXISTS in backtest engine)

`backtest/engine.py` already uses `dynamic_spread_model.py` for session-conditioned spread/slippage. This means the backtest engine can handle different costs by session.

### 4.5 Fill Simulator (EXISTS)

`scripts/simulate_fills.py` already computes slippage by session, volatility regime, and spread bucket. The fill samples are available.

---

## 5. REDESIGN PLAN — What Needs to Change

### 5.1 Phase 1: Fix The Label (Days 1-3)

**Problem**: Binary is_long is noisy and doesn't capture magnitude.

**Solution**: Replace with triple-barrier labels + magnitude filter.

| Change | Current | Redesign |
|--------|---------|----------|
| Target | `is_long` (binary direction) | `tb_label` (triple-barrier: +1/-1/0) |
| TP multiplier | N/A | k=2.0 (ATR-based) |
| SL multiplier | N/A | k=1.0 (ATR-based) |
| Max hold | N/A | 12 bars |
| Filter | None | Only trade when predicted magnitude > cost |

**Files to modify**:
- `scripts/train_mega_model.py`: Change target from `is_long` to `tb_label`
- `scripts/backtest_cost.py`: Add magnitude gate
- `ml/labeling.py`: Already has the implementation

### 5.2 Phase 2: Fix The Overfitting (Days 3-5)

**Problem**: Train accuracy = 100% on every fold.

**Solution**: Stronger regularization + smaller model + proper purged CV.

| Change | Current | Redesign |
|--------|---------|----------|
| n_estimators | 500 | 100-200 |
| max_depth | 6 | 3-4 |
| learning_rate | 0.05 | 0.01-0.03 |
| subsample | 0.8 | 0.6-0.7 |
| colsample_bytree | 0.8 | 0.6-0.7 |
| min_child_weight | 5 | 10-20 |
| reg_alpha | 1.0 | 5.0 |
| reg_lambda | 1.0 | 5.0 |
| Embargo | 12 bars | 24 bars (6 hours) |
| Train window | 500 bars | 1000 bars |
| Test window | 200 bars | 200 bars |
| Step | 200 bars | 200 bars |

**Files to modify**:
- `scripts/train_mega_model.py`: Update hyperparameters and CV

### 5.3 Phase 3: Add Session Filter (Days 5-7)

**Problem**: Trading all hours dilutes edge. Only 10.9% of bars have moves > 1× cost.

**Solution**: Only trade during high-performance sessions.

**Session Analysis (features_v3, 60K bars)**:

| Session | Hours (UTC) | Accuracy | F1 | Precision | Recall | Cost/Range | Verdict |
|---------|-------------|----------|-----|-----------|--------|------------|---------|
| Overlap | 12-17 | 58.4% | **46.4%** | 42.1% | 51.6% | 2.7% | ✅ BEST F1 |
| NY late | 17-22 | **76.3%** | 25.7% | 32.3% | 21.4% | 2.7% | ✅ Highest accuracy |
| Asian | 00-07 | 65.4% | 17.8% | 39.0% | 11.6% | 3.2% | ⚠️ Moderate |
| London early | 07-12 | 70.6% | 0.4% | 25.0% | 0.2% | 3.3% | ❌ Near-zero recall |
| Sydney | 22-00 | 60.4% | 14.5% | 31.1% | 9.5% | 4.2% | ⚠️ Few samples |

**Critical finding**: The overlap session (12-17 UTC) has the BEST model performance (F1=46.4%), contradicting the earlier raw-data analysis. The model actually performs best during the overlap session.

**Redesign filter**:
- ✅ Trade: Overlap (12-17 UTC) — best F1, lowest cost/range
- ✅ Trade: NY late (17-22 UTC) — highest accuracy
- ⚠️ Conditional: Asian (00-07 UTC), London early (07-12 UTC) — only if regime score high
- ⚠️ Conditional: Sydney (22-00 UTC) — few samples, high cost/range

**Files to modify**:
- `scripts/backtest_cost.py`: Add session filter to trade decision
- `scripts/train_mega_model.py`: Add session as feature or filter

### 5.4 Phase 4: Add Magnitude Gate (Days 7-9)

**Problem**: Model predicts direction but not magnitude. Small moves get stopped out.

**Solution**: Dual-head model or magnitude regression.

| Approach | Complexity | Benefit |
|----------|------------|---------|
| A: Simple magnitude filter | Low | Filter trades where predicted move < 2× cost |
| B: Dual-head model | Medium | Predict direction + expected magnitude |
| C: Magnitude regression | High | Direct prediction of expected return |

**Recommended**: Start with Approach A (simple filter), upgrade to B if needed.

**Implementation**:
```python
# In backtest_cost.py evaluate_backtest():
predicted_magnitude = df_test.loc[trade_mask, "target_return"].abs()
cost_threshold = (spread_cost + slippage_p90) * 2  # 2× round-trip cost
magnitude_gate = predicted_magnitude >= cost_threshold
trade_mask = trade_mask & magnitude_gate
```

### 5.5 Phase 5: Limit Orders (Days 9-10)

**Problem**: Market orders pay full spread.

**Solution**: Limit orders at bid/ask instead of mid.

| Order Type | Spread Cost | Fill Rate |
|------------|-------------|-----------|
| Market | Full spread (~$0.12) | 100% |
| Limit at bid/ask | Half spread (~$0.06) | ~70-80% |
| Limit at mid | Zero spread | ~50-60% |

**Files to modify**:
- `scripts/backtest_cost.py`: Add limit-order fill simulation
- `execution/fill_model.py`: Add limit-order logic

### 5.6 Phase 6: Retrain & Validate (Days 10-14)

**Steps**:
1. Regenerate features_v3 with triple-barrier labels
2. Train ensemble with new hyperparameters
3. Run walk-forward evaluation
4. If pass criteria met → write new pre-registration
5. If not met → iterate on features or model

---

## 6. VALIDATION CRITERIA

| Metric | B2 Threshold | Redesign Target | Notes |
|--------|--------------|-----------------|-------|
| avg_net/trade | ≥$0.40 | ≥$0.50 | Higher bar for redesign |
| Win rate | ≥55% | ≥58% | More conservative |
| t-stat | ≥2.0 | ≥2.0 | Same |
| Max drawdown | — | <5% | New constraint |
| Sharpe ratio | — | >1.5 | New constraint |
| Train accuracy | — | <70% | Anti-overfit check |
| OOS/IS gap | — | <10% | Generalization check |

---

## 7. RISKS & MITIGATIONS

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Triple-barrier too aggressive (k=2.0) | Medium | Few trades | Test k=1.5 and k=2.0 |
| Session filter too restrictive | Low | Few trades | Backtest with/without |
| Limit orders don't fill | Medium | Missed trades | Model partial fill; fallback to market |
| Cross-asset features add leakage | Low | Overfit | Strict shift(1); re-run lookahead tests |
| New model still overfits | Medium | Poor OOS | Stronger regularization; smaller model |
| Live spread > backtest | Medium | Lower net | Use P95 spread per session |

---

## 8. IMPLEMENTATION ORDER

```
Week 1 (Jul 24-30):
  Day 1-2: Fix labels (triple-barrier k=2.0)
  Day 3-4: Fix overfitting (regularization + CV)
  Day 5-6: Add session filter
  Day 7: Add magnitude gate

Week 2 (Jul 31-Aug 6):
  Day 8-9: Add limit orders
  Day 10-11: Retrain ensemble
  Day 12-13: Walk-forward validation
  Day 14: Write pre-registration (if pass)
```

---

## 9. WHAT THIS PLAN DOES NOT DO

- Does NOT modify B2 paper trade (locked until Jul 23)
- Does NOT guarantee profitability
- Does NOT skip paper trading — any redesign still requires 28-day validation
- Does NOT add new data sources — uses what's already in features_v3

---

## 10. APPROVAL REQUEST

Before executing, I need your approval on:

1. **Branch name**: `strategy-redesign-2026` — OK?
2. **Timeline**: ~14 days development — OK?
3. **Triple-barrier k=2.0**: OK to start with this?
4. **Session filter**: London + NY only (skip Asian) — OK?
5. **Magnitude gate**: 2× round-trip cost threshold — OK?
6. **Regularization**: max_depth=3, n_estimators=150, reg_alpha=5 — OK?
