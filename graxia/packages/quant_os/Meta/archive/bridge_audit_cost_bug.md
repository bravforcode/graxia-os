# Audit: Cost Multiplication Bug — $+10,789 เป็น Illusory

## Summary
walker_forward.py `compute_fold_pnl()` ขาด `* 2350` multiplier เมื่อ apply cost — ทำให้ cost/trade ถูกคิดเป็น $0.000146 แทน $0.345/trade (ต่ำกว่าความเป็นจริง 2364 เท่า) ผลลัพธ์ที่รายงานทั้งหมดเป็น invalid

## Finding #1: Cost Bug (CRITICAL)

**Location**: `scripts/walk_forward.py`, line 76-79

```python
raw_pnl_dollars = dir_mask * rets * 2350.0  # ← dollars
cost_per = spread_cost + slippage_p90        # ← return units (0.000147)
net_pnl = raw_pnl_dollars - cost_per          # ← BUG: return - dollars
```

**Fix**: `net_pnl = raw_pnl_dollars - cost_per * 2350.0`

**Proof** (XAUUSD v3 magnitude filter run, 332 folds):
| Metric | Reported (bug) | Correct | Delta |
|--------|---------------|---------|-------|
| Total cost (26,228 trades) | **$3.82** | **$9,060.46** | 2364x |
| Cost/trade | $0.000146 | $0.3454 | — |
| Net PnL | **+$10,789.25** | **+$1,732.60** | — |
| t-stat | **3.12** | **0.50** | — |
| Positive folds | **213/332 (64%)** | **201/332 (60.5%)** | — |

**Conclusion**: t=0.50 = NOT statistically significant. The edge is too small relative to noise when cost is correctly applied.

## Finding #2: Magnitude Filter — No Leakage (PASS)

- XGBRegressor trains on `X_train, y_train_reg` (train window only) ✅
- Predicts on `X_test` (test window, out-of-sample) ✅
- `expected_profit = direction * mag_pred * conf` uses only predicted values ✅
- `target_return` is signed (forward return, not absolute) — `expected_profit > 0` when classifier & regressor agree on direction. Valid consistency check. ✅
- **No data leakage found.**

## Finding #3: EURUSD Flips Negative After Cost Fix

| Metric | Reported (bug) | Correct |
|--------|---------------|---------|
| Total cost (3,310 trades) | $0.00 | $202.24 |
| Net PnL | +$103.53 | **−$98.60** |
| t-stat | 1.76 | **−1.59** |
| Positive folds | 73/129 (57%) | 57/129 (44%) |

EURUSD goes from CONDITIONAL_PASS to clearly NEGATIVE after proper cost.

## Finding #4: Old Baseline Numbers

- **−$1,304.78**: old WF net (500-window, step=100, 50k bars) with old cost_per=0.0003, buggy multiplier
- **−$646.71**: old WF gross PnL (same run)
- **−$969**: reported from console output of a DIFFERENT intermediate run (different step/window) — not comparable to above

**All three are from the old buggy cost code. None represent a valid baseline.**

## Finding #5: Fold Reduction 497→332

Not caused by magnitude filter. Old run used step=100 (497 folds on 50k bars), new used step=200 (332 folds on ~67k bars). All 332 new folds have ≥9 trades. No selection bias from filter.

## Corrected XAUUSD After Fix

With proper cost, XAUUSD net = **+$1,732.60, t=0.50** — positive gross but noise dominates. The verdict should be CONDITIONAL_PASS at best (201/332 folds positive, but t too low).

## Next Steps (after this fix)
1. Fix `* 2350` in `compute_fold_pnl`
2. Re-run XAUUSD magnitude filter WF with correct cost
3. Re-evaluate EURUSD (expect negative outright)
4. If XAUUSD still shows positive edge after correct cost → holdout validation before any paper trading
