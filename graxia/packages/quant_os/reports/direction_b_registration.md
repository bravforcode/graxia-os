# Direction B — New Research Direction

**Date:** 2026-07-13
**Decision:** B — Change research direction (not A: stop, not C: wait)
**Trial counter continues from:** #1006
**Stopping rule:** Existing cap (1022), time (3 months from today), 80 hours — unchanged

---

## Why Direction Change

5 hypotheses tested on XAUUSD, all REJECTED:
1. RYDC (cross-asset RYDC) — p=0.968
2. CAM (DXY→XAUUSD lead-lag) — p=0.598
3. SP (session patterns) — p=0.934
4. MRM (DFII10 regime MR) — p=0.244, Sharpe -1.16

**Root cause:** XAUUSD with technical/statistical methods on daily OHLCV is consistently null across 5 different mechanisms. The market is too efficient for these approaches.

## What Changes

| Dimension | Before (Direction A) | After (Direction B) |
|---|---|---|
| Instrument | XAUUSD only | Multi-instrument: BTCUSD, ETHUSD, XAGUSD |
| Mechanism | Momentum, MR, session, regime | Different: pair correlation, vol clustering, cross-asset spread |
| Data | Daily OHLCV | Daily OHLCV + cross-asset returns |
| Horizon | 4-5 day hold | Variable: 1-10 days |

## 3 New Hypotheses

### H1: Gold-Silver Spread Mean-Reversion (trial #1006)

**Mechanism:** XAUUSD and XAGUSD are both precious metals with shared macro drivers. When the gold/silver ratio deviates from its rolling mean, it tends to revert. This is NOT the same as cross-asset momentum (which failed) — it's a PAIR trade, not a lead-lag.

**Data:** XAUUSD daily, XAGUSD daily (both available)
**Pre-registered params:** ratio_window=60, entry_z=2.0, hold=10d
**Arms:** A = reversion (short when ratio high, long when low)

### H2: BTCUSD Volatility Clustering (trial #1007)

**Mechanism:** Crypto markets have different microstructure than FX. High-vol regimes in BTCUSD cluster differently. When realized vol spikes above its own regime, the NEXT day tends to continue in the same direction (vol clustering is stronger in crypto than FX).

**Data:** BTCUSD daily (available)
**Pre-registered params:** vol_window=20, vol_threshold=1.5, hold=3d
**Arms:** A = vol continuation (long after vol spike if price direction matches)

### H3: Cross-Asset Vol Rank (trial #1008)

**Mechanism:** When an asset's realized vol rank (percentile of its own vol history) is extreme relative to other assets in the same regime, the cheap-vol asset tends to outperform. This is NOT session patterns or momentum — it's relative value across assets.

**Data:** XAUUSD, BTCUSD, ETHUSD daily (all available)
**Pre-registered params:** vol_window=20, rank_window=60, entry_percentile=80, hold=5d
**Arms:** A = buy cheap vol, sell expensive vol

---

## Files to Create

1. `reports/direction_b_registration.md` — new direction pre-registration
2. `research/pre_registration/trial_1006_gold_silver_spread.md`
3. `research/pre_registration/trial_1007_btc_vol_clustering.md`
4. `research/pre_registration/trial_1008_cross_asset_vol_rank.md`
5. `strategies/gold_silver_spread.py`
6. `strategies/btc_vol_clustering.py`
7. `strategies/cross_asset_vol_rank.py`
8. Update `research/hypothesis_registry.json`
9. Update `research/trial_ledger.json`
10. Update `research/meta_learning.md`

## Constraint

Sacred holdout `data/sacred_holdout/holdout.csv` remains LOCKED. All testing on `data/rydc/rydc_research.csv` and new data sources only.
