# WS-A Pre-Registration — TSMOM on 6-Symbol Breadth Universe (Trial 1033)

- **Trial:** 1033
- **Track:** WS-A (replicate-published-edge) — same track as trials 1028 (TSMOM) / 1032 (52w-high)
- **Registered:** 2026-08-04
- **Status:** PRE-REGISTERED (NOT yet backtested formally)
- **Sacred holdout:** LOCKED — `data/sacred_holdout/holdout.csv` NOT touched
- **Cumulative trial count entering:** 1050+ (per `validation/n_trials` reconciliation)
- **Post-cap note:** Trial 1033 is post-cap (cap=1022 consumed; extended per stopping_rule_2026_07_30). Recorded for audit trail — same precedent as 1028/1031/1032.

---

## 1. Why this trial exists (honest lineage — NOT a re-run of 1028)

Trial **1028 (WS-A TSMOM, 7-symbol universe)** was REJECTED: DK t=0.464 << 2.0,
DSR (unit-correct) p=0.9277 FAIL. The universe included XAGUSD/NAS100 which were
**NOT cost-calibrated at the time** (they ran on a frozen pepperstone_razor table
with `require_cost_calibration=False` — a caveat recorded in the 1028 pre-reg).

**SP3 (2026-08-03) changed the cost-calibration infrastructure**: 4 new symbols
(BTCUSD, EURUSD, GBPUSD, US30) were calibrated FROM_TICKS from real tick parquet
data, and BTCUSD passed the provenance floor (added 2009-01-03). An **EXPLORATORY**
run (NOT a verdict — recorded as `reports/exploratory_breadth_6sym_20260803.json`)
of TSMOM on the 6-symbol universe (XAUUSD, EURUSD, GBPUSD, USDJPY, BTCUSD, US30)
showed Sharpe 0.905, DSR p=0.0083 PASS, WFA 0.943 PASS — vs 1028's Sharpe 0.365.

**This trial formalizes that exploratory result** with full pre-registration:
frozen parameters, full gate stack, and honest recording. It is a NEW hypothesis
because the **universe changed** (breadth expansion is a material parameter
change) — NOT a re-run of 1028, and NOT a tuning of 1028's rejection.

**Transparency:** the exploratory result was seen before this pre-registration
exists (dated 2026-08-03). We register it anyway as an explicit *confirmation
trial* — with the acknowledgment that the exploratory run informed the universe
selection. This is recorded here so the multiple-testing correction can be
debated honestly: the DSR uses N=1050 (reconciled), which already includes the
exploratory look.

## 2. Strategy specification (FROZEN)

```
TSMOM (Moskowitz-Ooi-Pedersen 2012), single 12M lookback — same as trial 1028:
    mom[t] = close[t] / close[t-252] - 1
    signal[t] = +1 if mom[t] > 0 else -1 if mom[t] < 0 else 0
```

- **Lookback:** 252 (12M) — single, canonical MOP (identical to 1028)
- **Rebalance:** every 21 trading days (monthly, D1 bars)
- **Vol-targeting:** vol_target=0.10, clip [0.01, 2.0], 21d realized vol
- **Universe (FROZEN — the SP3 breadth set):**
  `XAUUSD, EURUSD, GBPUSD, USDJPY, BTCUSD, US30` (6 symbols)
- **Costs:** SP3 calibrated FROM_TICKS table:
  XAUUSD 0.324/0, EURUSD 0.088/7, GBPUSD 0.076/7, USDJPY 0.124/7,
  BTCUSD 2.511/10, US30 0.231/0 (spread_bps/commission_bps)
- **Data:** `provenance.load_provenance_checked` — all 6 pass the provenance
  floor + cost gate as of 2026-08-03 (verified). `require_cost_calibration=True`
  (SP3 made this possible — no caveat needed).

## 3. FROZEN parameters

| Param | Value | Rationale |
|---|---|---|
| lookback | 252 (12M) | MOP canonical |
| rebalance_freq | 21 (1M) | monthly, D1 |
| vol_target | 0.10 | clip [0.01, 2.0] |
| universe | 6 symbols (SP3 set) | breadth expansion — all FROM_TICKS |
| cost model | SP3 calibrated (per-symbol) | real ticks, no frozen table |

Frozen. If the backtest fails → REJECT and stop. No threshold tuning.

## 4. Success criteria (pre-registered — identical gates to 1028/1032 + SP2)

Primary:
- **DK-test t > 2.0** (`edge_search_all.run_dk_test`, verified Newey-West HAC)
- **DSR p < 0.05** with N=1050 (`dsr_from_annualized`, unit-correct — SP1)

Secondary (SP2 institutional gates — must hold for GO):
- **WFA (purged-CV 5f):** mean OOS Sharpe > 0
- **Bootstrap CI:** lower bound > 0
- **MinBTL:** sufficient = True
- **Jackknife:** per-symbol drop delta < 0.5 Sharpe
- **Cost-stress:** Sharpe > 0 at 1.5x and 2.0x
- **Label-shuffle:** p <= 0.05 (signal inconsistent with shuffled labels)
- **PBO:** N/A — single frozen config (no search space) — same rationale as SP2

## 5. Stopping rule

- ONE hypothesis. Run once. Primary fails → REJECT, stop. No tuning.
- Sacred holdout remains LOCKED until Phase 4.5.
- Result recorded in `research/trial_ledger.json` (trial 1033) + `research/hypothesis_registry.json`.

## 6. What happens next if PASS

If all primary + secondary gates pass: next step is Phase 4 (paper trading
readiness) — requires the measurement daemon two-pass bar for the 6 symbols
(daemon started 2026-08-04, coverage accumulating). NOT an immediate live
promotion.
