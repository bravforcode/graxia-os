# Stopping Rule — Direction G (Trend/Breakout on now-calibrated symbols) — Pre-Registration

**Status:** LOCKED — 2026-08-05
**Supersedes for future trials:** nothing (new direction, parallel to D/E/F)
**SHA-256 of this file:** recorded in `research/trial_ledger_g.json` → `lock_doc_sha256` at lock time (same self-reference-avoidance convention as the 07-30 document)
**Cumulative trial count at lock:** 0 (separate ledger per Path-B precedent — `trial_ledger_b.json`/`trial_ledger_c.json` each have their own counter)

---

## 0. This document opens a NEW direction — stated plainly

Direction D (`stopping_rule_2026_07_30.md`) locked the research program to
**XAUUSD, USOIL, USDJPY only**, explicitly excluding the other 18 symbols with
this reason:

> The other 18 symbols (EURUSD, GBPUSD, SILVER, NAS100, +14 more) are
> **excluded — no cost data at all.** A trial against any of them would not be
> testing an edge net of real costs; it would be testing an edge net of an
> assumption.

That exclusion is now **resolved for BTCUSD and EURUSD**: real tick-derived
cost calibration exists as of 2026-08-05 (see `config/cost_calibration.json`,
both `FROM_TICKS`, measured from ~1.29M BTCUSD ticks / ~290K EURUSD ticks via
`mt5.copy_ticks_range`, broker source recorded). This document therefore opens
Direction G for **BTCUSD and EURUSD** — the two symbols whose cost-data blocker
has been lifted — using **structural mechanisms not yet exhausted**: H1 trend
following (BTCUSD) and session-window breakout (EURUSD).

Trials 1034/1035 (M15 scalpers on XAUUSD/FX) were REJECTED at measured costs
and their post-mortem (`reports/postmortem_1034_1035_m15_scalpers.md`) closes
the *M15 scalper on gold/FX without filter* hypothesis space. Direction G does
not retest that space.

---

## 1. Scope — instruments & mechanisms

| Trial (pre-registered) | Instrument | Mechanism |
|---|---|---|
| 8001 | BTCUSD H1 | Donchian 20-bar breakout, volume filter, ATR trailing exit |
| 8002 | EURUSD M15 | London-session (07:00 UTC) breakout of Asian range, volatility-expansion filter |

**Cost basis (measured, FROM_TICKS, 2026-08-05):**

| Symbol | spread_bps (median) | commission_bps | round_trip_bps | slippage source |
|---|---|---|---|---|
| BTCUSD | 2.376 | 10.0 | 24.75 | `fill_samples_BTCUSD_1min.csv` P90 = 32 pts |
| EURUSD | 0.087 | 7.0 | 14.17 | `fill_samples_EURUSD_1min.csv` P90 = 1 pt |

Slippage comes from the fill simulator (`scripts/simulate_fills.py`, real
ticks, `artifacts/fill_samples_fixed/`) — **never** a fabricated 0.0. Registry
entries MUST use `research/registry_schema.stamp_trial_entry()` so provenance
is written at registration time (per Phase 1, commit baa0f395).

## 2. Scope — methodology

Gate stack carries over unchanged from Direction D (p-value, WFA-OOS, WFE,
DSR, PBO-CSCV, bootstrap CI, min-independent-trades). Regime conditioning
remains OUT OF SCOPE (same reasoning as 07-30 §2 — don't stack methodology
changes).

## 3. Trial budget

- **New hypothesis budget:** 25 (same size as Path-B allowance — not enlarged)
- **Trial range:** 8000–8999 (free block per `TRIAL_ID_RANGES.md`)
- **Separate ledger:** `research/trial_ledger_g.json` + `research/hypothesis_registry_g.json` (Path-B precedent; Direction D's use of the main ledger is acknowledged as an anomaly, not copied here)

## 4. Stopping conditions (carried over from 07-30 §3)

Research under this direction stops when **any** of:
- **4.1** New hypothesis count reaches 25.
- **4.2** 3 months elapse from this lock date (deadline: 2026-11-05).
- **4.3** 80 research-hours are logged against this direction.
- **4.4** 3 consecutive hypotheses fail at the same gate — stop and re-examine calibration, data quality, or framing.

---

## 7. STOPPING RULE TRIGGERED — 2026-08-06 (§4.4)

**3 consecutive REJECT verdicts:**
| Trial | Mechanism | n_trades | Sharpe | PF | Verdict |
|---|---|---|---|---|---|
| 8001 | BTCUSD H1 Donchian breakout | 1,391 | 0.24 | 1.14 | REJECT |
| 8002 | EURUSD M15 London session breakout | 20 (UNDERPOWERED) | -0.07 | 1.04 | REJECT |
| 8003 | BTCUSD D1 TSMOM + Yang-Zhang vol targeting | 3 | 0.18 | 0.32 | REJECT |

**Action per §4.4:** research under Direction G STOPS. No new hypothesis
(8004+) may be registered under this direction without a new stopping-rule
document (Direction H or reopening with stated justification).

**Frozen findings:**
- M15 scalper space closed (1034/1035 post-mortem).
- Fast H1 breakout on BTCUSD: no edge at measured costs (8001).
- EURUSD session-breakout: inconclusive (underpowered, 20 trades) — NOT
  counted as mechanism-death, but direction stands REJECT.
- Slow TSMOM + vol targeting on BTCUSD: 3 trades in 10 years (SL/TP too wide
  for the slow signal; strategy effectively never traded) — mechanism not
  validated, REJECT for insufficient activity (8003).

**Cost + provenance were real for all three** (FROM_TICKS, fill-simulator
slippage, stamped at verdict time per Phase 1) — the failures are structural,
not cost artifacts. Broker-switch thesis remains falsified.

## 5. Preconditions

1. Trials 8001/8002 may be PRE-REGISTERED now (this document + registries).
2. Verdicts MUST be stamped with provenance (`registry_schema.stamp_trial_entry`).
3. Slippage MUST come from fill-simulator P90 — `slippage_source: "none"` is
   only acceptable if the runner explicitly does not model slippage (recorded
   honestly, never as 0.0).
4. Sacred holdout (`data/sacred_holdout/`) stays LOCKED — unlock Phase 4.5 only.

## 6. Acknowledgment

By locking this document:
1. This opens a new direction whose two instruments were previously excluded
   for lack of cost data; that blocker is now resolved with real tick-derived
   measurements.
2. Budget is 25 hypotheses in a separate ledger — it does NOT touch the main
   ledger cap or Direction D's budget.
3. The M15-scalper space (1034/1035) is closed by post-mortem; Direction G
   mechanisms (trend/session breakout) are structurally different.
4. Regime conditioning is deliberately excluded to avoid compounding
   methodology changes.
