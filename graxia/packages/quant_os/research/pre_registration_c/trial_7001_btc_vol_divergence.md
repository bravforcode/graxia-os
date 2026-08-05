# Hypothesis Pre-Registration — BTC Volume-Price Divergence

**Status:** LOCKED — 2026-07-13
**Trial number:** #7001 (Direction C, fresh family) — renumbered from #3001 2026-07-31, see TRIAL_ID_RANGES.md (also corrects a pre-existing stale "#2001" typo)
**Direction:** C — Volume-Price Divergence in Crypto

---

## 1. Economic Rationale

Volume measures conviction. When BTC makes new price extreme on low volume, the move is likely noise (few participants). Institutional flow checks volume; retail follows price. Information asymmetry between volume-checking and price-following participants creates exploitable edge.

## 2. Arm Selection

**Registered choice: Arm A (divergence = reversal).**
New high + low volume → short (weak rally, likely reversal).
New low + low volume → long (weak selloff, likely reversal).

## 3. Data Requirements

| Series | Source | History |
|---|---|---|
| BTCUSD daily OHLCV | data/BTCUSD_D1.csv | 2022-2025 (1280 bars with volume) |

## 4. Feature Construction

```
price_high_20 = rolling max(high, 20).shift(1)
price_low_20 = rolling min(low, 20).shift(1)
vol_avg_20 = rolling mean(volume, 20).shift(1)
vol_ratio = volume / vol_avg_20
new_high = high >= price_high_20
new_low = low <= price_low_20
vol_weak = vol_ratio < 0.8
```

## 5. Signal & Trade Rule

- **Entry long:** new_low AND vol_weak → buy at close
- **Entry short:** new_high AND vol_weak → sell at close
- **Exit:** 5-day fixed hold
- **Stop-loss:** 2.0 × ATR(14)

## 6. Validation Gates

| Gate | Threshold |
|---|---|
| p-value | < 0.05 |
| WFA OOS | ≥ 70% |
| WFE | ≥ 0.5 & < 1.5 |
| DSR | > 95% (trial count = 1) |
| Bootstrap CI | excludes 0 |
| Min trades | ≥ 100 |

## 7. Sample Size Check

1280 bars, ~25% trigger rate = ~320 potential signals. After hold-period spacing: ~60-100 non-overlapping trades. Borderline for 100 target.

## 8. Lock Checklist

- [x] Arm A chosen
- [x] Parameters frozen
- [x] DSR trial count = 1
- [x] Sacred holdout = holdout_btc.csv (LOCKED)
