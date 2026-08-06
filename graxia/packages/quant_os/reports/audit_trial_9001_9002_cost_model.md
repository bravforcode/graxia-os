# AUDIT — Cost-Model Unit Error: `commission_bps` mis-scaled 8-29x for FX/crypto

**Date:** 2026-08-06
**Auditor:** builder-agent (user-requested deep audit of REJECT verdicts)
**Status:** CONFIRMED — root cause identified, impact scoped, fix + rerun pending approval

---

## 1. TL;DR

`config/cost_calibration.json` stores the field `commission_bps` with values
that are actually **USD per round-trip lot** (Pepperstone Razor: $7/rt on FX,
$10/rt on BTCUSD) — not basis points. Any consumer that treats the field as
bps and computes `round_trip_bps = spread*2 + commission*2` inflates the true
round-trip cost **8-29x** for FX pairs and ~4x for BTCUSD. This is a REAL
system-calculation defect, exactly what the user suspected.

**Affected verdicts:** Trial 9001 (REJECT at 22x-inflated costs) and the
TSM-series / original 2026-07-12 forex batch that ran on
`run_multi_instrument_wf.py` / `tsm_*` runners. **NOT affected:** 9002, 8001,
8002, 1034/1035, 4001-4003 (they run through the BacktestEngine
`commission_per_lot` = $/lot path, which is correct).

---

## 2. Evidence chain

### 2.1 The true broker cost

`FOREX_EDGE_INVESTIGATION.md:33`:
> **Pepperstone Razor charges $7/round-trip commission on all FX pairs.**

`reports/broker_comparison_pepperstone_vs_icmarkets_thai.md:29`:
> Pepperstone Razor charges $3.50/side only on margin FX (forex pairs).

So: $7 round trip per standard lot (100,000 units) — the field should be
named `commission_usd_per_rt_lot`, and its bps equivalent is notional-dependent.

### 2.2 What the calibration actually stores

`config/cost_calibration.json` (from `scripts/complete_cost_calibration_entries.py`, commit 595d070d):

```python
"EURUSD": {"commission_bps": 7.0, "contract_size": 100000.0, ...}
"BTCUSD": {"commission_bps": 10.0, "contract_size": 1.0, ...}
...
"round_trip_bps_measured": float(sbps_f.median()) * 2 + float(str(meta["commission_bps"])) * 2,
```

The 7.0 / 10.0 are the $/lot values, but the formula adds them as bps.

### 2.3 Correct vs reported round-trip cost

| Symbol | spread (bps) | comm field | rt REPORTED | comm TRUE (bps) | rt TRUE | **overstated** |
|---|---|---|---|---|---|---|
| USDCAD | 0.071 | 7.0 | 14.14 | 0.500 | 0.64 | **22x** |
| EURUSD | 0.087 | 7.0 | 14.17 | 0.606 | 0.78 | 18x |
| USDCHF | 0.124 | 7.0 | 14.25 | 0.864 | 1.11 | 13x |
| AUDUSD | 0.142 | 7.0 | 14.28 | 0.986 | 1.27 | 11x |
| NZDUSD | 0.341 | 7.0 | 14.68 | 1.186 | 1.87 | 8x |
| USDJPY | 0.124 | 7.0 | 7.25 | 0.045 | 0.25 | 29x |
| GBPUSD | 0.076 | 7.0 | 7.15 | 0.520 | 0.67 | 11x |
| BTCUSD | 2.376 | 10.0 | 24.75 | 1.546 | 6.30 | 4x |
| XAUUSD | 0.324 | 0.0 | 0.65 | 0.000 | 0.65 | 1x ✓ |
| NAS100/OIL/US30 | — | 0.0 | — | 0.000 | — | 1x ✓ |

True commission bps = `comm_field * 10000 / (price * contract_size)`.

---

## 3. Impact scope (which trials are affected)

### 🔴 AFFECTED — verdicts unreliable (cost overstated 4-29x)

| Trial | Runner path | Verdict | Note |
|---|---|---|---|
| **9001** forex4 retest | `run_multi_instrument_wf.py` (rt_bps) | REJECT t=-8..-17 | cost 22x high → REJECT may flip to INCONCLUSIVE or better |
| Original 2026-07-12 batch | `run_multi_instrument_wf.py` | GBPUSD/USDJPY REJECT, 4 INCONCLUSIVE | all on inflated costs |
| TSM series (2001, 2009-2011, 8003) | `tsm_backtest_real_costs.py`, `tsm_ensemble_backtest*.py` | various | uses rt_bps → overstated |
| `walk_forward.py` | rt_bps path | — | same bug |
| `select_tradeable_instruments.py` | rt_bps | universe selection | may have excluded cheap symbols wrongly |

### 🟢 NOT AFFECTED — verdicts stand

| Trial | Runner | Why correct |
|---|---|---|
| **9002** RSI-MR | BacktestEngine `commission_per_lot=7.0` | $/lot path — empirically verified (trace: 0.25 lots × $7 = $1.75 ✓) |
| **8001/8002** (Direction G) | `run_direction_g_trials.py:142` `commission_per_lot=profile.commission_bps` | value 7.0 passed as $/lot — correct by coincidence |
| **1034/1035** M15 scalpers | `edge_search_m15_scalper.py` `COMMISSION_PER_LOT` | $/lot hardcoded correctly |
| **4001-4003** funding arb | dedicated path | spot/perp, not affected |
| **8003** BTC TSMOM+YZ | 3 trades, structural | verdict driven by inactivity, not costs |

---

## 4. Why the engine path was right (verification)

Empirical trace through `BacktestEngine` (USDCAD, SHORT, 0.25 lots @ 1.381):

```
ACTUAL fees   = $1.75        (0.25 lots × $7/rt lot) ✓
EXPECTED comm = $48.33       (would be if 7 bps: 34525 × 7bps × 2)  ← WRONG interpretation
TRUE comm     = $1.75        ✓ matches engine
```

The engine's `commission_per_lot` semantics ($ per lot) is correct. The defect
is purely in the **calibration field naming + bps-formula consumers**.

---

## 5. Root cause & systemic risk

1. `complete_cost_calibration_entries.py` (595d070d, 2026-08-05) hardcoded
   `commission_bps: 7.0/10.0` with the value being $/lot — **mislabeled field**.
2. `run_multi_instrument_wf.py:117` + `tsm_*` runners consume
   `round_trip_bps_measured` which baked in the mislabel → **all forex
   walk-forward/TSM verdicts since 2026-07-12 are unreliable**.
3. No unit test asserted that `commission_bps` converts to a sane bps range
   for FX (7 bps on FX is ~14x the true cost — should have been caught).

---

## 6. Fix plan (proposed, pending approval)

1. **Rename/clarify calibration field**: add `commission_usd_per_rt_lot`
   (7.0/10.0) and compute `commission_bps_true` per symbol from price ×
   contract size; keep `round_trip_bps_measured` consistent with the TRUE
   value. Preserve backward-compat fields where tests rely on them.
2. **Fix consumers**: `run_multi_instrument_wf.py`, `tsm_*`, `walk_forward.py`,
   `select_tradeable_instruments.py`, `edge_search_*` gross-reconstruct paths —
   use true bps; add a unit test asserting FX rt_bps ∈ [0.5, 2.5] sanity range.
3. **Rerun affected trials** with corrected costs (pre-registration unchanged;
   same frozen params): 9001 (forex4 retest), original batch verdicts, TSM series.
4. **Re-stamp verdicts** + update ledgers/registries + consecutive-fail counts.
5. Optional: re-run universe selection to confirm no symbol was wrongly excluded.

## 7. Honest note

The direction-i session (parallel) is doing a C0.x/C1.x re-audit and holds the
writer lock. This audit is read-only; the fix + rerun needs the lock (or
coordination with that session) before touching calibration/registries.
