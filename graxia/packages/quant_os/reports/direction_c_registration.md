# Direction C — Volume-Price Divergence in Crypto

**Date:** 2026-07-13
**Status:** LOCKED — new research program (separate from Direction A+B)
**Trial counter:** Starts at #2001 (fresh, not continuing from 1008)

---

## 1. Why Direction C Is Structurally Different

Previous research (Direction A+B) tested 8 hypotheses on XAUUSD/technical methods. All REJECTED. Direction C meets all 3 required conditions:

| Condition | How Direction C Meets It |
|---|---|
| **Less efficient market** | BTC/ETH = retail-heavy, different microstructure than FX/gold. Crypto markets have wider spreads, more noise, different participant mix. |
| **New data type** | Volume (not just OHLC price). Previous hypotheses used only price-based features. Volume is a new dimension. |
| **Different mechanism** | Volume-price divergence = information-flow-based. NOT momentum (follow trend), NOT mean-reversion (fade extremes), NOT vol-clustering. Volume reveals conviction, price reveals direction — when they diverge, one is wrong. |

---

## 2. Economic Rationale

Volume is a measure of conviction. When price moves on high volume, the move is likely genuine (many participants agree). When price moves on low volume, the move is likely noise (few participants, easily reversed).

**Candidate edge:** When BTC/ETH makes new price extreme (20-day high/low) but volume doesn't confirm (below average), the move is likely to reverse. This is information-flow-based: the volume tells you the price move is weak.

**Why it might persist:** Crypto markets are dominated by retail participants who follow price without checking volume. Institutional flow (which checks volume) is still a smaller fraction of crypto than FX/gold. This information asymmetry could create a exploitable edge.

---

## 3. Three Hypotheses

### H1: BTC Volume-Price Divergence (trial #2001)

When BTC makes new 20-day high but volume < 80% of 20-day average → short (weak move, likely reversal).
When BTC makes new 20-day low but volume < 80% of 20-day average → long.

**Config (frozen):**
- price_window = 20
- vol_window = 20
- vol_threshold = 0.8
- hold_days = 5
- atr_period = 14
- stop_atr = 2.0

### H2: ETH Volume Confirmation (trial #2002)

When ETH price and volume both confirm (new 10-day high + volume > 80th percentile) → long (strong move continues).
When new 10-day low + high volume → short.

**Config (frozen):**
- price_window = 10
- vol_window = 10
- vol_confirm_pct = 80
- hold_days = 3
- atr_period = 14
- stop_atr = 2.0

### H3: BTC-ETH Volume Divergence Spread (trial #2003)

When BTC volume diverges from ETH volume (BTC high + ETH low) → long BTC, short ETH.
When opposite → short BTC, long ETH.

**Config (frozen):**
- vol_window = 15
- divergence_threshold = 0.3
- hold_days = 5
- atr_period = 14
- stop_atr = 2.0

---

## 4. Data

| Series | Source | Research | Sacred Holdout |
|---|---|---|---|
| BTCUSD daily (vol>0) | data/BTCUSD_D1.csv | 1280 rows (2022-2025) | 364 rows (2025-07 to 2026-06) |
| ETHUSD daily (vol>0) | data/ETHUSD_D1.csv | 1283 rows (2021-2025) | 364 rows (2025-07 to 2026-06) |

**Sacred holdout:** `data/sacred_holdout/holdout_btc.csv` — READ-ONLY until Phase 4.5
**Research data:** `data/direction_c/btc_research.csv`, `data/direction_c/eth_research.csv`

---

## 5. Stopping Rule (Direction C — Separate)

| Trigger | Limit |
|---|---|
| Max hypotheses | 10 (trials #2001-2010) |
| Time | 2 months from Direction C start |
| Research hours | 40 hours max |
| 3-in-a-row same-gate failure | STOP |

---

## 6. Validation Gates (Same as Direction A+B, No Relaxation)

| Gate | Threshold |
|---|---|
| p-value | < 0.05 |
| WFA OOS positive | ≥ 70% |
| WFE | ≥ 0.5 & < 1.5 |
| Deflated Sharpe | > 95% |
| Bootstrap CI | excludes 0 |
| Min trades | ≥ 100 |

**DSR trial count:** Starts at 1 (fresh family, separate from Direction A+B's 1008 trials)

---

## 7. Sacred Holdout Rules

- One-time use only
- No reset on failure
- Read-only until Phase 4.5
- 364 rows covering 2025-07-01 to 2026-06-29
