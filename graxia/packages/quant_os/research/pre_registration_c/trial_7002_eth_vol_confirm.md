# Hypothesis Pre-Registration — ETH Volume Confirmation

**Status:** LOCKED — 2026-07-13
**Trial number:** #7002 (Direction C) — renumbered from #3002 2026-07-31, see TRIAL_ID_RANGES.md

## 1. Economic Rationale

When ETH price and volume both confirm (new extreme + high volume), the move has conviction. continuation is more likely than reversal. This is the flip side of BTCVD — instead of fading weak moves, we follow strong ones.

## 2. Arm Selection

**Registered choice: Arm A (confirmation = continuation).**
New high + high volume → long.
New low + high volume → short.

## 3. Data

ETHUSD daily, 2021-2025 (1283 bars with volume).

## 4. Features

```
price_high_10 = rolling max(high, 10).shift(1)
price_low_10 = rolling min(low, 10).shift(1)
vol_pct = rolling percentile(volume, 10).shift(1)
vol_confirm = vol_pct > 80
```

## 5. Rules

- **Long:** new_high AND vol_confirm
- **Short:** new_low AND vol_confirm
- **Hold:** 3 days
- **Stop:** 2.0 × ATR(14)

## 6-8. Same gates as trial #2001.
