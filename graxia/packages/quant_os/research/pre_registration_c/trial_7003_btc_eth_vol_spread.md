# Hypothesis Pre-Registration — BTC-ETH Volume Divergence Spread

**Status:** LOCKED — 2026-07-13
**Trial number:** #2003 (Direction C)

## 1. Economic Rationale

BTC and ETH are correlated but have different participant mixes. When their volumes diverge (one high, one low), the one with volume confirmation is more likely to outperform. This is a relative value trade across two crypto assets using volume as the differentiator.

## 2. Arm Selection

**Registered choice: Arm A (volume divergence = relative value).**
BTC vol high + ETH vol low → long BTC (relative strength).
BTC vol low + ETH vol high → short BTC (relative weakness).

## 3. Data

BTCUSD + ETHUSD daily, aligned by date (1280+ bars).

## 4. Features

```
btc_vol_z = (volume - mean(volume, 15)) / std(volume, 15)
eth_vol_z = (volume - mean(volume, 15)) / std(volume, 15)
divergence = btc_vol_z - eth_vol_z
```

## 5. Rules

- **Long BTC:** divergence > 0.3
- **Short BTC:** divergence < -0.3
- **Hold:** 5 days
- **Stop:** 2.0 × ATR(14)

## 6-8. Same gates as trial #2001.
