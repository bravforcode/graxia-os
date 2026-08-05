# Direction B Pre-Registration — True FX Carry (Trial 3008)

- **Trial:** 3008
- **Track:** Direction B — PATHB-CARRY-FX (true cross-currency carry)
- **Registered:** 2026-07-20 (ledger entry) / this doc locked 2026-08-03 before running
- **Status:** PRE-REGISTERED (NOT yet backtested — data blocked until 2026-08-03)
- **Sacred holdout:** LOCKED — not touched
- **Cumulative trial count entering:** 1022 (Direction B ledger; trial numbering 3008 in Direction B range per TRIAL_ID_RANGES.md)

---

## 0. Why this is a NEW trial, not a re-run

Trial **3001 (PATHB-CARRY-XAUUSD)** was INVALIDATED on audit (2026-07-20): it used
`DGS10-DGS2` — the US yield-curve slope — as if it were currency carry. It is not.
True currency carry = **cross-currency interest-rate differential** (foreign rate − USD rate).
This trial (3008) was pre-registered in `research/trial_ledger_b.json` on 2026-07-20 as
UNTESTED with the explicit data requirement: *"EUR interest rate (ECB main rate or German
Bund yield) + JPY interest rate (BOJ rate or JGB yield)"*. That data was missing from
`data/fred/` at the time. On 2026-08-03 the missing series were fetched (see §3), unlocking
this trial. The mechanism tested is the one described in the original pre-registration —
nothing about the mechanism changed.

## 1. Economic Rationale

**Mechanism (named, falsifiable):** uncovered interest parity (UIP) fails persistently:
high-interest-rate currencies do not depreciate enough to offset the rate differential
(forward-premium puzzle / carry trade premium). A portfolio long high-yield FX and short
low-yield FX collects the rate differential as positive expected return. This is one of the
most robust cross-sectional FX anomalies (Lustig, Roussanov & Verdelhan 2011; Menkhoff et al.
2012) and a distinct *risk-premium* mechanism — NOT the behavioral/technical families
exhausted under Directions A/C.

**Why persistent:** funding constraints + crash risk premium + central-bank reaction
functions keep the premium in place; it is a priced risk factor, not a pure arbitrage.

**Testable prediction:** sign of (foreign 3M interbank rate − USD 3M interbank rate) predicts
positive expected excess return of that FX pair over the following month, net of realistic costs.

## 2. Arm Selection — ONE Arm, Picked Before Testing

| Arm | Prediction | Mechanism |
|---|---|---|
| **A — Long-high/short-low carry** | Long FX pairs whose foreign rate > USD rate, short pairs whose foreign rate < USD rate | UIP failure / carry premium |
| B — Momentum-filtered carry | Only enter when carry sign AND trailing 12M return agree | Interaction effect |

**Registered choice: Arm A.** Pure sign-of-carry, matching the published cross-sectional
carry anomaly. Arm B requires an extra free parameter and is out of scope.

## 3. Data Requirements

| Series | Source | Frequency | Range | Status |
|---|---|---|---|---|
| EURUSD D1 | `data/EURUSD_D1.csv` via provenance loader | D1 | 2005→2026 | available (provenance-checked, cost caveat below) |
| GBPUSD D1 | `data/GBPUSD_D1.csv` | D1 | 2005→2026 | available |
| USDJPY D1 | `data/USDJPY_D1.csv` | D1 | 2005→2026 | available, **cost-calibrated FROM_TICKS** |
| EUR 3M interbank | FRED `IR3TIB01EEM156N` | monthly | 2004→2026 | fetched 2026-08-03 |
| JPY 3M interbank | FRED `IR3TIB01JPM156N` | monthly | 2004→2026 | fetched 2026-08-03 |
| GBP 3M interbank | FRED `IR3TIB01GBM156N` | monthly | 2004→2026 | fetched 2026-08-03 |
| USD 3M | FRED `DGS3MO` (existing) | daily | 2005→2026 | available |

**Cost-calibration caveat (recorded, not hidden):** `config/cost_calibration.json`
(2026-07-26 fix) lists only XAUUSD/USDJPY/OIL/NAS100 as measured; EURUSD/GBPUSD were moved to
`removed_assets`. `load_provenance_checked` therefore refuses EURUSD/GBPUSD with
`require_cost_calibration=True`. Following the precedent of trial 1028 (WS-A TSMOM, which
ran all 7 symbols with the same pepperstone-razor cost table), this trial uses the **frozen
pepperstone_razor cost table** embedded in the harness (identical to the 1028 harness:
EURUSD spread 0.10bps + 7bps commission; GBPUSD 0.12bps + 7bps; USDJPY 0.12bps + 7bps) and
loads EURUSD/GBPUSD with `require_cost_calibration=False`, explicitly recorded here. USDJPY
uses the same table for consistency. Cost stress at 1.5×/2.0× multiplies the same table.

## 4. Feature Construction (exact, no discretion)

```
On each rebalance date t (every 21 trading days, matching WS-A cadence):
    foreign_rate[t] = monthly interbank rate, forward-filled to daily, as-of t (no lookahead)
    usd_rate[t]     = DGS3MO (daily), as-of t
    carry[t]        = foreign_rate[t] − usd_rate[t]
    signal[t]       = sign(carry[t])          # +1 long pair, −1 short pair, 0 flat
```

- Rate series are monthly → **forward-filled** to daily and aligned to the D1 calendar.
  Only rates observed **on or before** t are used (shift(1) applied to the merged rate
  series before signal construction to guarantee no same-day lookahead).
- Carry is re-evaluated monthly (every 21 trading days), positions held flat between
  rebalances.
- Universe: EURUSD, GBPUSD, USDJPY (3 FX pairs with both price + rate data).

## 5. Signal & Trade Rule (fixed — cannot be tuned after seeing results)

- **Entry long:** carry[t] > 0 → long the pair (foreign currency is high-yield vs USD).
- **Entry short:** carry[t] < 0 → short the pair (foreign currency is low-yield vs USD).
- **Exit:** position reverses when sign(carry) flips, or monthly rebalance sets signal=0.
- **Stop-loss:** none (carry is a slow risk-premium harvest; stops are not in the published mechanism).
- **Sizing:** equal risk across the 3 pairs, vol-scaled per asset identical to WS-A
  (vol_target=0.10, clip [0.01, 2.0], 21d realized vol) — keeps comparability with trial 1028.
- **Filters:** none.

## 6. Validation Gates — Identical to Existing Pipeline, No Relaxation

| Gate | Threshold | Note |
|---|---|---|
| Pooled DK-test t-stat (Newey-West HAC) | > 2.0 | `edge_search_all.run_dk_test` (verified impl) |
| Deflated Sharpe Ratio | p < 0.05 | N = 1050 (reconciled cumulative count via `validation/n_trials.get_reconciled_n_trials`) |
| Cost stress | Sharpe > 0 at 1.5× and 2.0× | pepperstone_razor table × multiplier |
| Jackknife (drop-one-pair) | Sharpe delta < 0.5 | per-symbol drop |
| Min independent trades | ≥ 50 per pair | position changes at monthly rebalance (WS-A PINNED definition) |
| Label shuffle | p > 0.05 → FAIL | shuffle-sign null on pooled returns |
| Sacred holdout | NOT burned | remains LOCKED |

## 7. Sample Size Check

~21 years × 12 rebalances/yr = ~252 rebalance dates per pair; carry sign is sticky
(monthly rate differentials change slowly), so expected independent position changes ≈
50–150 per pair — meets the ≥50 PINNED definition. Expected pooled trades ≈ 150–450.

## 8. Pre-Registration Lock Checklist

- [x] Arm chosen in §2 (Arm A)
- [x] IS/OOS split fixed (none — single full-sample run + DSR multiple-testing correction, per 1028 precedent)
- [x] Parameters frozen (§4–§5)
- [x] DSR uses cumulative trial count (N=1050)
- [x] Go/no-go criteria match pipeline (§6)
- [x] Sample-size decision made (§7)
- [x] Trial number allocated (3008, Direction B range)
- [x] Document hashed at lock

---

## 9. Validation Results — [PASSED/REJECTED] (fill after running)

**Date:**
**Verdict:**
**Trial count after:**

| Gate | Value | Threshold | Status |
|---|---|---|---|
| DK t-stat | | > 2.0 | |
| DSR | | p < 0.05 | |
| Cost stress 1.5× | | Sharpe > 0 | |
| Cost stress 2.0× | | Sharpe > 0 | |
| Jackknife | | delta < 0.5 | |
| Min trades | | ≥ 50/pair | |
| Label shuffle | | p > 0.05 | |
