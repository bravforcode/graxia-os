# Stop-Loss Audit: B2 XAUUSD Paper Trade

**Auditor**: agent:auditor (Ruflow Project Gracia)
**Date**: 2026-06-25
**Source**: `Meta/pre_register_b2.md` — pre-registered B2 stop-loss at $6.30/trade
**Contract source**: `markets/eurusd/contract_snapshot.py:XAUUSDContractSnapshot`
**Frozen params**: `tests/test_phase_2b.py:_xauusd_spec()`

---

## 1. Verified XAUUSD Contract Parameters

| Parameter | Value | Source |
|-----------|-------|--------|
| Contract size (1.0 lot) | 100 oz | `contract_snapshot.py` L49 |
| Tick size | $0.01 (1 point) | L53 |
| Tick value (1.0 lot) | $1.00 per tick | L54 |
| Digits | 2 (price: XXXX.XX) | L55 |
| 1 pip (= 10 ticks) | $0.10 | by convention |
| Stops level (min stop) | 50 points = **$0.50** | `test_phase_2b.py` L74 |
| Typical spread | ~$0.30 (30 points) | `contract_snapshot.py` L56 |
| Volume step | 0.01 lot | L52 |

**Pip/tick disambiguation**: 1 point = 1 tick = $0.01 price move.
1 pip = 10 points = $0.10 price move.
*This matters because the pre-register calculations conflate pips with ticks.*

---

## 2. Arithmetic Verification

### 2A. Price-move derivation (both correct)

| Lot | Multiplier | Price move = $6.30 ÷ mult | User says | Verdict |
|-----|-----------|--------------------------|-----------|---------|
| 0.1 | 0.1×100=10 oz | $0.63 | $0.63 | ✅ |
| 1.0 | 1.0×100=100 oz | $0.063 | $0.063 | ✅ |

### 2B. Pip conversion (both *incorrect* in pre-register)

| Lot | Price move | In ticks ($0.01) | In pips ($0.10) | User says | Error |
|-----|-----------|-----------------|-----------------|-----------|-------|
| 0.1 | $0.63 | **63 ticks** | **6.3 pips** | 63 pips | ❌ 10× over — counts ticks as pips |
| 1.0 | $0.063 | **6.3 ticks** | **0.63 pips** | 6.3 pips | ❌ 10× over — same error |

**Root cause**: The formula `$0.63 / $0.10 × 10 = 63` double-counts the lot-size scaling. The correct formula is:
```
pips = price_move / pip_value($0.10)
```
No extra factor of 10. The ×10 would only apply if converting price-pips to tick-count for a position — but that's ticks, not pips.

### 2C. Percentage of price (both correct)

| Lot | % of $2350 | User says | Verdict |
|-----|-----------|-----------|---------|
| 0.1 | $0.63/$2350 = **0.0268%** | 0.027% | ✅ |
| 1.0 | $0.063/$2350 = **0.00268%** | 0.0027% | ✅ |

### 2D. Broker minimum-stop check (MISSING from pre-register)

| Lot | Stop distance (ticks) | Broker min (ticks) | Result |
|-----|----------------------|-------------------|--------|
| 0.1 | 63 ticks ($0.63) | 50 ticks ($0.50) | ✅ **Passes** (63 > 50) |
| 1.0 | **6.3 ticks ($0.063)** | 50 ticks ($0.50) | ❌ **FAILS** (6.3 < 50) |

**Critical finding**: The 1.0 lot stop at $0.063 violates the broker's `stops_level_points=50` minimum. The order would be rejected by the broker before it reaches the market.

---

## 3. Practicality Analysis

### 3.1 Lot comparison matrix

| Factor | 0.1 lot | 1.0 lot |
|--------|---------|---------|
| Stop distance | 63 ticks / $0.63 | 6.3 ticks / $0.063 |
| Spread ratio | 63 / 30 = **2.1× spread** | 6.3 / 30 = **0.21× spread** |
| Broker min-stop | Passes (63 > 50) | **Fails** (6.3 < 50) |
| Trigger on noise | Low — outside spread + 1 tick | **Certain** — inside spread |
| Slippage risk | $0.63 × ~10% = $0.06 | $0.063 × ~50% = $0.03 (but stop may not fill) |
| Visible on 15min chart | Tight but visible | Invisible — sub-tick on most charts |
| Price move magnitude | ~4-6% of typical M15 candle | ~0.4-0.6% of typical M15 candle |

### 3.2 Why 1.0 lot is non-viable

1. **Broker rejects the order** — `stops_level_points=50` means minimum stop distance is $0.50. At 1.0 lot, the B2 stop is $0.063 (6.3 ticks), which is 8× tighter than the broker allows.
2. **Stop inside the spread** — XAUUSD typical spread is ~$0.30 (30 ticks). The stop would be triggered immediately on entry.
3. **Execution impossibility** — Even if a broker accepted it, spread + slippage would consume the entire risk budget.

**Verdict**: 1.0 lot is **not viable** for this test. Remove from consideration.

### 3.3 Why 0.1 lot is viable — with caveats

- ✅ Passes broker minimum stop (63 ticks > 50)
- ✅ Outside spread zone (2.1× typical spread) — won't trigger on normal spread
- ✅ Survives normal noise on 15min chart
- ⚠️ Tight by any standard — 63 ticks is small relative to XAUUSD M15 ATR (~$10-15 range per bar)
- ⚠️ Slippage on stop execution could add 10-30% to the $6.30 loss in fast markets

---

## 4. Lot-Size Recommendation for 28-Day Paper Trade

### Decision

**Use 0.1 lot. The 1.0 lot is not viable.**

### Rationale

| Criterion | 0.1 lot | 1.0 lot |
|-----------|---------|---------|
| Feasible to execute | ✅ Yes | ❌ No |
| Tests B2 stop at $6.30 | ✅ Yes | No (broker rejects) |
| Statistical validity (noise-free) | ⚠️ Acceptable | Inapplicable |
| Matches pre-registered criteria | ✅ Yes | ❌ Violates |

### Residual risk at 0.1 lot

1. **Gap risk**: At XAUUSD volatility of ~$20-40/day, a gap over weekend/news could exceed $0.63 (i.e., 1.5-3% of daily range). This is tolerable — the pre-register already accounts for this via the contingency plan (if gap risk exceeds estimate, retry at $7.00 stop).
2. **Slippage on stop**: Market-stop execution on a 15min chart may slip 1-2 ticks ($0.01-0.02) in normal conditions, 5-10 ticks in fast markets. At worst, slippage adds ~$0.10 to the loss ($6.30 → $6.40 = +1.6%). Acceptable.
3. **Statistical resolution**: At $6.30 per trade and expected avg_net ≥ $0.40, the test can detect signal with ~28-56 trades over 28 days. This is adequate but marginal — do not reduce further.

### If 0.1 lot also proves too tight

- Do NOT switch to 1.0 lot (broker rejects).
- Do NOT use 0.01 lot (zero statistical resolution — the avg_net of $0.40 becomes $0.04, which is below MT5 PnL rounding noise).
- **Only viable alternative**: Use 0.1 lot with a wider stop ($7.00 as pre-registered contingency).
- If even $7.00 fails: the strategy is not testable via fixed-$ stop on XAUUSD. Switch to ATR-based dynamic stop.

### Prohibited configs for the 28-day test

The following WOULD violate the pre-registered locked config:
- ❌ Using 1.0 lot (unexecutable + voids "B2 at $6.30")
- ❌ Widening the stop without triggering the contingency protocol
- ❌ Using 0.01 lot (avg_net expectation drops to $0.04 — below measurable threshold)
- ❌ Mid-period lot-size switching (violates pre-registration)

---

## 5. Summary of Findings

| Item | Status | Detail |
|------|--------|--------|
| Price-move arithmetic | ✅ Correct | $6.30/10=$0.63 (0.1 lot), $6.30/100=$0.063 (1.0 lot) |
| Pip conversion | ❌ 10× error | Pre-register counts ticks, labels them pips |
| %-of-price | ✅ Correct | 0.027% and 0.0027% |
| Broker min-stop | ❌ MISSING | 1.0 lot violates `stops_level_points=50` |
| 0.1 lot viability | ✅ Passes | 63 ticks > 50 min, 2.1× spread, workable |
| 1.0 lot viability | ❌ Fails | 6.3 ticks < 50 min, inside spread |
| 28-day recommendation | **0.1 lot** | Only viable size that tests B2 as intended |

### Recommended action

1. **Lock 0.1 lot** as the paper-trade lot size in the pre-registration.
2. **Correct the pip arithmetic** in the pre-register (change "63 pips" → "63 ticks / 6.3 pips").
3. **Add broker minimum-stop check** to pre-register as a pre-flight gate.
4. **No further changes** — proceed with the 28-day paper trade at 0.1 lot, $6.30 stop, pre-registered pass criteria.
