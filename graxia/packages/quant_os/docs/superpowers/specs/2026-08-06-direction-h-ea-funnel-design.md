# Design Spec — Direction H: EA Deep-Mine Funnel (2026-08-06)

**Status:** APPROVED (design review 2026-08-06, sections 1-6 + amendments A1-A7)
**Next step:** writing-plans → implementation plan
**Owner:** direction-h-funnel-design (writer lock acquired 2026-08-06)

---

## 1. Context & Prior Evidence

Everything below is verified from committed repo state (2026-08-06). No claims without evidence.

### 1.1 Direction G STOPPED (2026-08-06, §4.4)
3 consecutive REJECT verdicts at real measured costs:

| Trial | Mechanism | n_trades | Sharpe | PF | Verdict |
|---|---|---|---|---|---|
| 8001 | BTCUSD H1 Donchian(20) breakout + vol filter | 1,391 | 0.24 | 1.14 | REJECT |
| 8002 | EURUSD M15 London session breakout | 20 | -0.07 | 1.04 | REJECT (UNDERPOWERED) |
| 8003 | BTCUSD D1 TSMOM + Yang-Zhang vol targeting | 3 | 0.18 | 0.32 | REJECT (insufficient activity) |

Per `reports/stopping_rule_2026_08_05.md` §4.4: research under Direction G STOPS. New direction (H) requires its own stopping-rule document. Cost + provenance were real for all three (FROM_TICKS, fill-simulator slippage) — failures are structural, not cost artifacts.

### 1.2 Closed hypothesis spaces (must not retest)
- **M15 scalper on gold/FX without filter:** CLOSED — post-mortem 1034/1035 (PF 0.68-0.95)
- **Fast H1 breakout on BTCUSD:** no edge at measured costs (8001)
- **Slow TSMOM + vol targeting on BTCUSD:** never traded (8003)
- **TSM Portfolio (Sharpe 1.17, Sortino 1.58):** REJECTED — jackknife `reports/tsm_portfolio_jackknife_20260728.json`: `concerning_single_asset_dependence: ["BTC_YF"]`, mislabeled 2-asset artifact (`reports/decisions_20260729.md:25`). The "DSR significant" claim was a false pass from `n_trials=4` instead of N=1050 (`reports/validation_stack_false_pass_20260729.md:25` — trial #2012)
- **donchian_vol_filter:** REJECTED — jackknife +3.318 → -0.136 (single-asset artifact, F27)
- **Funding-rate arb (Path B #3005-class):** FAIL_RIGOR; **Crypto basis/carry #6001:** REJECTED (p=0.50-0.96 across 8 combos)
- **Dual Thrust:** rejected on literature (SPY Sharpe -0.37, QuantConnect tutorial)

### 1.3 Closed governance items (verified 2026-08-06)
- **Lookahead-gap 8001/8002:** annotated LOOKAHEAD-GAP STATUS in `research/hypothesis_registry_g.json` (commit f69a0f43). REJECT stands: lookahead-cheating only inflates, cannot explain REJECT. 8002 additionally marked inconclusive-not-dead (UNDERPOWERED)
- **Incident 4002:** CLOSED NO-ACTION-REQUIRED (f69a0f43) — record never committed, parallel session reverted its own edit; registry_d intact; ratchet 63/0

### 1.4 Known gaps that Direction H must respect
- `scan_for_data_leaks()` does NOT exist in code (only referenced in registry notes). Engine has `LookaheadGuard(strict=True)` + `get_slice` (`backtest/engine.py:521-597`) but `guard.violations` is never asserted post-run
- `reports/lookahead_guard_reachability_audit_2026_07_30.md:28-34`: cross-sectional/khubiev/funding-rate families were NEVER inside BacktestEngine guard scope — their correctness relies on un-audited manual lag/shift discipline
- `ws_b_paper_bot_revalidation_20260729.md:63-65`: TSM jackknife re-run from regenerated D1 data recommended but no record of completion; jackknife JSON shows suspicious identical OIL/SILVER rows (possible placeholders)

### 1.5 Existing data & cost infrastructure
- **Data:** 15 symbols × 9 timeframes (M1,M5,M15,M30,H1,H4,D1,W1,MN1): XAUUSD, XAGUSD, XPDUSD, XPTUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, US30, NAS100, BTCUSD, ETHUSD
- **Cost calibration (FROM_TICKS, verified 2026-08-06):** 10 symbols — XAUUSD, USDJPY, BTCUSD, EURUSD, GBPUSD, US30, USDCAD, USDCHF, AUDUSD, NZDUSD (USDCAD/USDCHF/AUDUSD/NZDUSD added 2026-08-06 by parallel session commit a88ddc22 via `scripts/calibrate_forex4_from_ticks.py`; slippage P90 for forex4 recorded null honestly — pending fill simulator). OIL = single-snapshot, NAS100 = UNVERIFIED_NO_DATA. 13 symbols pending
- **N baseline:** 1050 (reconciled, `validation/n_trials.py` → `trial_count_reconciliation_20260720.json`)
- **Trial ranges:** Main 1000-1999, B 3001-3008, C 7000-7999, D 4001+, E 5001+, F 6001+, G 8000-8999 → **H = 9000-9999** (next free 1000-block per `TRIAL_ID_RANGES.md`; NOT yet registered by the parallel session — P0 must add the row)
- **Uncommitted prior research in working tree (absorb, do not redo):** `reports/research_retail_forex_eas_20260804.md`, `reports/deep_research_institutional_gates_20260803.md`, `Meta/states/researcher-{eatested-ea-ranking,forex-ea-verification,forexroasted}.md`, `data/backfill/` — attributed as prior work (A7)

### 1.6 Committed prior Direction H work (ABSORB — do not duplicate)
Parallel session committed 2026-08-06 05:20 (+0700), commit a88ddc22 (author bravforcode):
- **Trial 9001 DRAFT** — `research/pre_registration/trial_9001_forex4_retest.md` — H1 trend-continuity retest on USDCAD/USDCHF/AUDUSD/NZDUSD (4 INCONCLUSIVE-underpowered pairs from original 6-pair batch; root cause: unmeasured costs + underpowered folds). Status: DRAFT — NOT frozen, NOT ledger-registered
- **Cost calibration** — USDCAD/USDCHF/AUDUSD/NZDUSD FROM_TICKS (344k/243k/285k/231k quote ticks, ask>bid filtered) → `config/cost_calibration.json`
- **Script** — `scripts/calibrate_forex4_from_ticks.py` (135 lines)
- **Missing governance (confirmed 2026-08-06):** no `reports/stopping_rule_2026_08_06_direction_h.md` (File Not Found), no `trial_ledger_h.json`/`hypothesis_registry_h.json`, no TRIAL_ID_RANGES.md row — P0 must close all three (draft's own open items 3/4/5)
- **Trial-counting rule:** trial 9001 = **1 trial** (one mechanism family; 4 pairs = internal diagnostics, not 4 trials). §4.4 counts trial-level fails. The draft's proposed "4 consecutive pair-REJECTs = direction stop" is SUPERSEDED by the funnel's §4.4 (3 trial-level fails) — reconciled in the stopping-rule doc at creation
- **Freeze prerequisites from draft (open items 1/2):** exact rule parameters from `run_multi_instrument_wf.py` baseline (no selection), min-confidence/bar-cap change frozen at a number (target 40+ trades/fold), slippage P90 from fill simulator or null recorded honestly

---

## 2. Governance — Direction H

| Parameter | Value |
|---|---|
| Direction | H (range 9000-9999, registered in TRIAL_ID_RANGES.md) |
| Ledgers | `research/trial_ledger_h.json` + `research/hypothesis_registry_h.json` + NEW `research/screening_log_h.json` |
| Max Total Trials (H) | **40 — hard cap across ALL cycles (C1/C2/C3) AND all sub-programs (A2)** |
| Deadline | REMOVED (user override 2026-08-06 — no time limit) |
| Research-hours | 400 (§4.3) |
| Consecutive fails | 3 (§4.4 — quality gate, kept) |
| Writer lock | `acquire_writer_lock.py --owner "direction-h-funnel-design"` — enforced before any write |
| Uniqueness | `check_trial_uniqueness.py` after every ledger/registry edit |

Stopping-rule doc: `reports/stopping_rule_2026_08_06_h.md` (new, SHA-256 locked, same self-reference convention as prior directions).

### 2.1 §4.4 Decision Tree (A5)
3 consecutive fails → **stop C1 immediately** → joint-cause analysis (e.g., "all killed by cost" vs "all structural fail") → human decision among:
1. Pivot to P5 (data infrastructure) then restart C1
2. Amend funnel parameters (documented amendment, pre-registered)
3. Terminate Direction H
No automatic default.

### 2.2 Trial budget allocation (A2/A3)
- Single central pool of 40. Every trial (any cycle, any sub-program) pre-registers and **deducts from the pool**
- **Trial 9001 (forex4 retest, DRAFT a88ddc22) = first pre-registered trial — consumes 1 of 40** → 39 remaining (A8)
- **Exempt (0 trials):** replication benchmarks (calibration only — Faber/Moreira-Muir/Baltas-Kosowski on our data+costs), H.4 HFT latency analysis (metadata analysis)
- Sub-programs H.1 (regime), H.2 (cross-exchange arb), H.3 (tick-level), H.5 (factor library) request from the 40 with pre-registration

---

## 3. N Accounting

```
N_H = 1050 (reconciled baseline)
    + |distinct configs in screening_log_h|
    + |trials in trial_ledger_h (including the one being judged)|
```

### 3.1 Counts as +1 N (all registered BEFORE run)
- Every executed screening config — hash of `(mechanism, symbol, timeframe, params, data_range)`; identical hash = same config = NOT double-counted
- **VOID runs (guard violation): still count** (they were tried) + mandatory audit before continue
- Every full-gate trial (including current — precedent: trial 1003 cumulative count includes itself)
- Grid amendment configs (all new configs added by the amendment)

### 3.2 Does NOT count (0 N — rationale written in doc)
- Taxonomy classification (no returns evaluated)
- Cost-viability math (arithmetic, not a test)
- Risk-of-ruin Monte Carlo (constraint check, not an edge test — recorded as screening_log metadata)
- Jackknife leave-one-out runs (diagnostics of a single hypothesis — precedent F27/#2010)
- Confirmatory retests with fresh data (validation, not selection)
- TSM jackknife closure re-run (Phase 0 closure verification)

### 3.3 Hash definition (A6 — written into `validation/n_trials_h.py`)
- `data_range` (start/end) change = **distinct config** (+1 N)
- Confirmatory retest on new data (validation purpose) = **not counted** (only screening configs + trials count)
- Mechanism: `validation/n_trials_h.py` (pattern of `validation/n_trials.py`), built in Phase 0

---

## 4. Martingale/Grid Hard Gate

**Path:** martingale/grid EA → Phase 2 flag → MUST pass this gate BEFORE Phase 4 screening. Fail = eliminated (no screening budget spent).

**Gate (all frozen before running):**
1. **Risk-of-ruin Monte Carlo** — `core/risk/monte_carlo.py`: P(ruin) < 1% at 10-year horizon under fixed max exposure cap, using worst-case-observed costs (precedent: XAUUSD rollover spike 2026-06-26 — 325 ticks >5bps, real recorded data)
2. **Bounded sizing** — max gross exposure ≤ 20% equity, frozen at pre-registration, no tuning after results
3. **Max DD** — projected max DD > 30% = disqualify at screening

**Triple-freeze rule:** order sequence (multiplier, grid spacing, scale-in/out) + exposure cap + sizing rule — all frozen in writing before run. Post-hoc tuning = disqualify + re-pre-register.

**Trial level:** full gate stack + risk-of-ruin MC re-run at calibrated costs; **risk-of-ruin reported as mandatory verdict metric** (not just Sharpe) — lesson from Happy Gold Scalper (narrow TP / wide SL hides tail risk).

---

## 5. Funnel Architecture (8 phases)

### P0 — Governance + Closure
- Writer lock, ledgers creation (3 files), TRIAL_ID_RANGES.md update (add Direction H 9000-9999 row — NOT yet registered by parallel session), `check_trial_uniqueness.py` pass
- Stopping-rule doc H (`reports/stopping_rule_2026_08_06_direction_h.md` — draft's open item #3) written + SHA-256 locked; reconcile trial-9001 pair-stop proposal into funnel §4.4 (trial-level counting)
- **Absorb committed Direction H work (A8):** freeze trial 9001 DRAFT per its open items (exact params from `run_multi_instrument_wf.py` baseline, min-confidence/bar-cap number, slippage P90 or null) → register into `trial_ledger_h.json` + `hypothesis_registry_h.json` + confirm trial number via `scripts/auto_increment_trial.py`
- **Closure checklist (all must close before first screening):**
  1. TSM jackknife re-run from current data (verify REJECT holds; close ws_b residual)
  2. Engine attr-scan gap: add `scan_for_data_leaks()`-equivalent (post-run attr scan) + mandatory `assert guard.violations == 0`
  3. Verify 8001/8002 annotations present in registry (verified ✅ 2026-08-06)
  4. Trial 9001 freeze + governance scaffolding (ledgers, stopping-rule doc, ranges table)

### P1 — Massive Mining (subagent swarm)
10-12 research subagents in parallel, one per source:
| Agent | Source | Target |
|---|---|---|
| S1 | MQL5 Code Base (categories split ×2) | 500+ EAs |
| S2 | GitHub (EarnForex, freqtrade, forex-stuff, backtrader collections ×2) | 300+ repos |
| S3 | MyFxBook verified (FX ×2: FX + crypto/metals) | 100+ verified systems |
| S4 | Forex Factory + TradingView Pine | 200+ community strategies |
| S5 | Academic (SSRN/JF/NBER/AQR/Man/Alpha Architect/Quantpedia ×2: quant-finance + crypto) | 100+ mechanisms |
| S6 | Institutional/obscure (QuantConnect Alphas, cTrader cBots, StrategyQuant, Numerai, RU/TH/CN forums ×2) | 150+ entries |

**Rules:** every entry must have source URL + metadata (mechanism, params, claimed perf, evidence tier). No fabrication. Blocked source = record + workaround (browser tools / archive.org / RU-TH-CN mirrors), never guess.
**Target: 2,500+ raw entries** → `research/catalog_h/raw_*.json`
**A7:** absorb existing uncommitted EA research artifacts (§1.5) into catalog with attribution — do not redo.

### P2 — Taxonomy + Dedup Fingerprint (**0 N**)
- Classify by mechanism from description/code → 60+ canonical mechanisms (incl. ICT/SMC, Wyckoff, VSA, harmonics, orderflow/Auction Market Theory, microstructure, seasonality/calendar, carry/rollover)
- Martingale/grid → flag into hard-gate path
- Output: `research/catalog_h/canonical_mechanisms.json` — mechanism × representative EAs × structural variants × evidence tier

### P3 — Evidence Triage (0 N)
- 3 tiers: literature-verified numbers / MyFxBook verified live / practitioner lore
- **Cost-viability math before backtest** — kills structurally impossible candidates (e.g., M1 scalper on BTCUSD 24.75bps RT) without spending screening budget
- Output: shortlist 10-20 mechanisms → Phase 4

### P4 — Screening Backtests (every config registered BEFORE run)
- **Every config = +1 N** (screening_log_h.json + hash, written BEFORE execute)
- Runner: **`BacktestEngine.run()` ONLY** + `assert guard.violations == 0` post-run (violation = VOID + audit; still counts N)
- Grids pre-registered in full — no post-hoc expansion without written amendment (which itself adds N)
- **Cost rule (A1):** screening uses conservative cost proxies (asset-class worst-case ×1.5) — makes screening HARDER, not easier
- Low bar (kill losers, not crown winners): raw Sharpe > 0 after proxy costs + min trades
- Output: survivors (target 5-15) → Phase 5

### P5 — Data Infrastructure + Full Calibration
- **Mandatory re-filter (A1):** every P4 survivor is re-screened at REAL costs (FROM_TICKS) in P5 before entering P6. Fail at real costs = back to screening pool (same hash, no extra N)
- Acquire 8 missing symbols' data (per universe config) + TF coverage audit (precedent: DATA_PIPELINE_FORENSICS)
- Full 23-symbol cost calibration: `mt5.copy_ticks_range` backfill (proven: BTCUSD 1.29M ticks / EURUSD 290K) + fill simulator; provenance FROM_TICKS stamped
- Symbol whose calibration fails = excluded from trials (precedent Direction D — "edge net of an assumption" forbidden)
- Output: `config/cost_calibration.json` extended (23 symbols)

### P6 — Pre-Registered Trials (full gate stack, tiered)
- Each survivor → `research/pre_registration_h/trial_9XXX_*.md` (mechanism, params frozen, N_H at registration)
- Gates per tier (A4):
  - **G1 (ALL trials):** p-value (HAC/Newey-West) · WFA-OOS · WFE · DSR(N_H) · cost-stress (incl. multi-broker ±30%)
  - **G2 (top 5 of G1):** PBO-CSCV · purged/embargoed CV · bootstrap CI · sub-period stability (5 windows: 2006-10/2011-15/2016-20/2021-23/2024-26)
  - **G3 (final 1-2):** jackknife leave-one-symbol-out · label-shuffle · parameter sensitivity · trade-level forensics (MFE/MAE, win/loss distribution, time-of-day)
- Martingale/grid survivors: + risk-of-ruin MC re-run at calibrated costs (mandatory verdict metric)
- Verdicts stamped `registry_schema.stamp_trial_entry`; stopping rules live (§4.1-4.4)
- Output: verdicts + evidence-tiered catalog (final deliverable)

### P7 — Confirmation (final survivors only)
- Shadow/paper validation on broker demo (existing infra: `shadow/`, pepperstone campaign) — confirmatory, not exploratory
- **Engine cross-validation:** survivor re-run on independent engine (vectorbt — `docs/vectorbt_patterns.md`) — results must agree
- **Sacred holdout unlock** (`data/sacred_holdout/` — locked per governance, unlock ONLY at this stage): final confirmation
- Stress scenarios mandatory for finalists: 2008 / COVID-2020 / 2022 rate-shock / 2024 yen-carry unwind

---

## 6. Research Cycles (iterative deepening, N accumulates across cycles)

- **C1 — Broad Sweep:** 2,500+ entries → taxonomy → triage → screening → first trial batch
- **C2 — Variant Deep-Dive:** near-miss families (borderline REJECT) → structurally distinct variants (must differ from tested — no "same test re-run") → screening + trials
- **C3 — Ensemble & Regime:** surviving mechanisms → correlation-adjusted portfolio construction (institutional edge) + H.1 regime conditioning (separate sub-program) → final trials
- Every cycle: N accumulates (no reset) — C3 survivors must win against TOTAL N

---

## 7. Sub-Programs (same ledger, own pre-registration, draw from pool of 40)

| ID | Sub-program | Trials | Notes |
|---|---|---|---|
| H.1 | Regime conditioning | From 40 | Separate pre-registration — avoids stacking methodology changes mid-direction |
| H.2 | Cross-exchange crypto arb | From 40 | Model ALL frictions: transfer time, withdrawal fees, counterparty risk — or it's fake numbers |
| H.3 | Tick-level microstructure | From 40 | Spread dynamics, order-flow imbalance, bid-ask bounce → feed cost models + alpha hunt |
| H.4 | HFT latency analysis | **0 (metadata)** | Measure VPS→MT5→broker latency, alpha-decay curves per family — goal: kill latency-sensitive ideas with proof (retail 10-100ms vs institutional μs) + optimize survivor execution |
| H.5 | Multi-asset factor library | From 40 | Momentum 12-1, carry, low-vol, term-structure, basis across 23 symbols → correlation matrix → portfolio phase |
| REP | Replication benchmarks | **0 (calibration)** | Faber / Moreira-Muir / Baltas-Kosowski replicated exactly on our data+costs — sets the bar (what a known-good published strategy achieves here) |
| EVT | Event/calendar studies | From 40 | FOMC/CPI/NFP drift (`fomc_drift.py`), COT (`cot_positioning.py`), funding-rate positioning proxy |
| KEL | Kelly sizing science | n/a (overlay) | Fractional Kelly + estimation-error haircut + vol targeting — for portfolio phase, not standalone trials |

---

## 8. Validation Stack (tiered — compute-efficient)

Tiered per A4 (see P6). Full stack = 15 layers:
p-value (HAC/NW) · WFA-OOS · WFE · DSR(N_H) · cost-stress+multi-broker · PBO-CSCV · purged/embargoed CV · bootstrap CI · sub-period stability · jackknife LOO · label-shuffle · parameter sensitivity · trade-level forensics · risk-of-ruin MC (martingale/grid) · stress scenarios (P7)

---

## 9. Risk Register

| Risk | Mitigation |
|---|---|
| False-positive survivor at 500+ config scale | guard assertion + N accounting + conservative screening costs + full tiered gate |
| Blocked sources → mining shortfall | browser tools / archive.org / RU-TH-CN mirrors; record blocked, never guess |
| Subagent fabrication/drift | structured JSON contract + source URL mandatory + reviewer pass before catalog |
| MT5 data gaps (8 symbols) | quality gate; symbol excluded from trials if calibration unavailable |
| Martingale/grid tail risk slips through | triple-freeze + trial-level MC re-run + risk-of-ruin as verdict metric |
| §4.4 hit (3 consecutive fails) | decision tree §2.1 — human decision, no auto-continue |
| Data-mining bias from grid expansion | full pre-registration of grids + amendment-only expansion (which adds N) |

---

## 10. Deliverables

1. **Evidence-tiered catalog** — canonical mechanisms × source citations × evidence tiers (`research/catalog_h/`) — delivered regardless of win/loss
2. **Funnel artifacts** — raw catalogs (10-12 sources), screening_log_h.json (every config + N), screening results
3. **23-symbol cost calibration** — FROM_TICKS + fill simulator, provenance stamped
4. **Trials 9001+** — pre-registration docs + verdicts with provenance
5. **≥1 trial surviving full gate at measured costs** = proven edge (DoD)
6. **Direction H closure report** — phases, final N_H, lessons

---

## 11. Success Criteria (measurable)

- [ ] ≥1 trial survives full gate stack at measured costs (23 symbols × all TFs)
- [ ] Evidence-tiered catalog delivered with zero uncited claims (source URL per entry)
- [ ] `check_trial_uniqueness.py` passes at every ledger/registry edit
- [ ] Every verdict stamped with provenance (`registry_schema.stamp_trial_entry`)
- [ ] All Phase 0 closure items closed before first screening run

---

## 12. Amendment Log

| ID | Date | Change | Source |
|---|---|---|---|
| A1 | 2026-08-06 | P4 uses cost proxy; P5 mandatory re-filter at real costs before P6 | Review round 2 |
| A2 | 2026-08-06 | Max Total Trials (H) = 40 hard cap, all cycles + sub-programs, single pool | Review round 2 |
| A3 | 2026-08-06 | Exempt 0-trial: replication benchmarks + H.4 HFT latency | Review round 2 |
| A4 | 2026-08-06 | Validation gates tiered G1/G2/G3 for compute efficiency | Review round 2 |
| A5 | 2026-08-06 | §4.4 decision tree — human decision, no auto-continue | Review round 2 |
| A6 | 2026-08-06 | N hash definition: data_range change = distinct config; confirmatory retests = 0 N | Review round 2 |
| A7 | 2026-08-06 | P1 absorbs uncommitted prior EA research artifacts with attribution | Lock investigation |
| A8 | 2026-08-06 | Absorb committed prior Direction H work (a88ddc22): trial 9001 DRAFT = first trial (1 of 40); cost calibration corrected to 10 FROM_TICKS; P0 scaffolding incl. stopping-rule doc, ranges table, ledgers, freeze | Commit investigation |

---

## 13. Open Items (explicit, not hidden)

- Exact 23-symbol universe list to pin from `config/tradeable_universe.json` at plan time
- Writer lock was stale (dead PID 21672) — cleared by human-approved force 2026-08-06; released after spec commit
- TSM jackknife re-run result unknown until Phase 0 executes (closure item 1)
- MQL5/MyFxBook access friction unknown until P1 probes (Cloudflare risk recorded in project memory)
- Trial 9001 freeze prerequisites (params, min-confidence, slippage P90) — closed in P0 per draft's open items
- 13 symbols still need FROM_TICKS calibration (10 done; OIL single-snapshot, NAS100 unverified)
