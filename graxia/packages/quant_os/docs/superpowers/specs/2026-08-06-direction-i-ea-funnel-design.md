# Design Spec — Direction I: EA Deep-Mine Funnel (2026-08-06)

**Status:** APPROVED (design review 2026-08-06, sections 1-6 + amendments A1-A18; renamed H→I per Option C+)
**Next step:** writing-plans → implementation plan
**Owner:** direction-i-funnel-design (writer lock acquired 2026-08-06)

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

Per `reports/stopping_rule_2026_08_05.md` §4.4: research under Direction G STOPS. Cost + provenance were real for all three (FROM_TICKS, fill-simulator slippage) — failures are structural, not cost artifacts.

### 1.2 Closed hypothesis spaces (must not retest)
- **M15 scalper on gold/FX without filter:** CLOSED — post-mortem 1034/1035 (PF 0.68-0.95)
- **Fast H1 breakout on BTCUSD:** no edge at measured costs (8001)
- **Slow TSMOM + vol targeting on BTCUSD:** never traded (8003)
- **TSM Portfolio (Sharpe 1.17, Sortino 1.58):** REJECTED — jackknife `reports/tsm_portfolio_jackknife_20260728.json`: `concerning_single_asset_dependence: ["BTC_YF"]`, mislabeled 2-asset artifact (`reports/decisions_20260729.md:25`). The "DSR significant" claim was a false pass from `n_trials=4` instead of N=1050 (`reports/validation_stack_false_pass_20260729.md:25` — trial #2012)
- **donchian_vol_filter:** REJECTED — jackknife +3.318 → -0.136 (single-asset artifact, F27)
- **Funding-rate arb (Path B #3005-class):** FAIL_RIGOR; **Crypto basis/carry #6001:** REJECTED (p=0.50-0.96 across 8 combos)
- **Dual Thrust:** rejected on literature (SPY Sharpe -0.37, QuantConnect tutorial)
- **Forex4 H1 trend-continuity (USDCAD/USDCHF/AUDUSD/NZDUSD):** CLOSED — absorbed from **Direction H trial 9001** (verdict t=-8.2 to -17.4 at measured costs, commit 7fbe921a) — resolves the 2026-07-12 INCONCLUSIVE verdicts to conclusive REJECT (A17)

### 1.3 Closed governance items (verified 2026-08-06)
- **Lookahead-gap 8001/8002:** annotated LOOKAHEAD-GAP STATUS in `research/hypothesis_registry_g.json` (commit f69a0f43). REJECT stands: lookahead-cheating only inflates, cannot explain REJECT. 8002 additionally marked inconclusive-not-dead (UNDERPOWERED)
- **Incident 4002:** CLOSED NO-ACTION-REQUIRED (f69a0f43) — record never committed, parallel session reverted its own edit; registry_d intact; ratchet 63/0

### 1.4 Known gaps that Direction I must respect
- `scan_for_data_leaks()` does NOT exist in code (only referenced in registry notes). Engine has `LookaheadGuard(strict=True)` + `get_slice` (`backtest/engine.py:521-597`) but `guard.violations` is never asserted post-run
- `reports/lookahead_guard_reachability_audit_2026_07_30.md:28-34`: cross-sectional/khubiev/funding-rate families were NEVER inside BacktestEngine guard scope — their correctness relies on un-audited manual lag/shift discipline
- `ws_b_paper_bot_revalidation_20260729.md:63-65`: TSM jackknife re-run from regenerated D1 data recommended but no record of completion; jackknife JSON shows suspicious identical OIL/SILVER rows (possible placeholders)
- **Writer lock is ADVISORY (A18, verified 2026-08-06):** `.writer.lock` is enforced ONLY by `run_release_gate.py` and voluntary acquisition. `.pre-commit-config.yaml` contains zero lock/claim/writer references. Commits are NOT blocked by the lock (pre-commit checks git:mutate claims — a different, pass-through system). A parallel session committed Direction H trials (ba467f93, 7fbe921a) without any hard enforcement. **Direction I P0 must harden enforcement before funnel writes begin** (see §5 P0 item 0)

### 1.5 Existing data & cost infrastructure
- **Data:** 15 symbols × 9 timeframes (M1,M5,M15,M30,H1,H4,D1,W1,MN1): XAUUSD, XAGUSD, XPDUSD, XPTUSD, EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, US30, NAS100, BTCUSD, ETHUSD
- **Cost calibration (FROM_TICKS, verified 2026-08-06):** 10 symbols — XAUUSD, USDJPY, BTCUSD, EURUSD, GBPUSD, US30, USDCAD, USDCHF, AUDUSD, NZDUSD (forex4 added by parallel session commit a88ddc22 via `scripts/calibrate_forex4_from_ticks.py`; slippage P90 for forex4 recorded null honestly — pending fill simulator). OIL = single-snapshot, NAS100 = UNVERIFIED_NO_DATA. 13 symbols pending
- **N baseline:** 1050 (reconciled, `validation/n_trials.py` → `trial_count_reconciliation_20260720.json`)
- **Trial ranges:** Main 1000-1999, B 3001-3008, C 7000-7999, D 4001+, E 5001+, F 6001+, G 8000-8999, **H = 9000-9999 (parallel session's, registered 2026-08-06)** → **I = 10000-10999** (next free block per `TRIAL_ID_RANGES.md` rule — P0 must add the row; ranges follow creation order, not alphabetical — A13)
- **Uncommitted prior research in working tree (absorb, do not redo):** `reports/research_retail_forex_eas_20260804.md`, `reports/deep_research_institutional_gates_20260803.md`, `Meta/states/researcher-{eatested-ea-ranking,forex-ea-verification,forexroasted}.md`, `data/backfill/` — attributed as prior work (A7)

### 1.6 Parallel session's Direction H — CITATIONS ONLY, do not touch (A16/A17)
Direction H (block 9000-9999) is owned and executed by a parallel session (author bravforcode). State as of 2026-08-06:
- `a88ddc22` — forex4 FROM_TICKS cost calibration + trial 9001 DRAFT
- `ba467f93` — trial 9001 FROZEN + `reports/stopping_rule_2026_08_06_direction_h.md` + `research/trial_ledger_h.json` + registry (cap=25, deadline 2026-11-06, hours=80, consecutive=3)
- `7fbe921a` — **trial 9001 REJECTED** (t=-8.2..-17.4, measured costs)
- `research/pre_registration/trial_9002_forex4_rsi_mr.md` — **FROZEN** (forex4 RSI mean-reversion, in-flight)

**Direction I relationship (C+):**
- **DO NOT touch their files** — no ledger amendment, no stopping-rule edit, no registry rewrite (single-writer respect; audit trails of valid verdicts stay intact)
- **DO NOT merge trial counts/ledgers** — different governance (their 25/80h/Nov-6 vs our 40/no-deadline/400h); merging would corrupt N accounting
- **9001 REJECTED → absorbed as evidence citation** in §1.2 closed-hypothesis list (done above)
- **9002 (in-flight) → WATCH ITEM:** when it resolves (accept or reject), absorb the result as a citation — do not block Direction I waiting for it

### 1.7 EURUSD H4 candidate
`docs/superpowers/specs/2026-08-06-tier0-sweep-design.md` (committed 2b4d250b): **EURUSD H4 (TF probe gross Sharpe 3.46) is waiting for a Direction H decision** (§2.5, §11.3 — Sub-project B decision list). **Absorbed as Direction I candidate:** structurally distinct from 8002 EURUSD M15 (different timeframe; 8002 was inconclusive-not-dead). Requires pre-registration; consumes 1 of our pool of 40. **Must not pre-register before Sub-project B renders its decision (explicit dependency).**

### 1.8 Scope partition vs Direction H (A17 — prevents duplicate mining)
Mechanism families owned by Direction H — Direction I's P1/P2 must flag and NOT recommend these without structural justification:

| Family | Owner status | Direction I action |
|---|---|---|
| forex4 H1 trend-continuity (USDCAD/USDCHF/AUDUSD/NZDUSD) | H trial 9001: **REJECTED** (t=-8.2..-17.4) | CLOSED — no re-test; P2 taxonomy flags "tested elsewhere" |
| forex4 RSI mean-reversion | H trial 9002: **FROZEN, in-flight** | WATCH — P2 flags; only enter if 9002 resolves REJECT-UNDERPOWERED AND we add structural difference (documented) |
| EURUSD H4 TF-probe family | Sub-project B decision pending | WATCH — candidate (10001+), waits for decision |

P2 fingerprinting MUST check the Direction H ledger/registry before classifying any entry whose mechanism+symbol+TF matches these families.

---

## 2. Governance — Direction I

| Parameter | Value |
|---|---|
| Direction | I (range 10000-10999, registered in TRIAL_ID_RANGES.md — P0 adds row) |
| Ledgers | `research/trial_ledger_i.json` + `research/hypothesis_registry_i.json` + NEW `research/screening_log_i.json` |
| Max Total Trials (I) | **40 — hard cap across ALL cycles (C1/C2/C3) AND all sub-programs (A2)** |
| Deadline | REMOVED (user override 2026-08-06 — no time limit) |
| Research-hours | 400 (§4.3) |
| Consecutive fails | 3 (§4.4 — quality gate, kept) |
| Writer lock | `acquire_writer_lock.py --owner "direction-i-funnel-design"` — enforced before any write |
| Uniqueness | `check_trial_uniqueness.py` after every ledger/registry edit |

Stopping-rule doc: `reports/stopping_rule_2026_08_06_direction_i.md` (new, SHA-256 locked, same self-reference convention as prior directions).

### 2.1 §4.4 Decision Tree (A5)
3 consecutive fails → **stop C1 immediately** → joint-cause analysis (e.g., "all killed by cost" vs "all structural fail") → human decision among:
1. Pivot to P5 (data infrastructure) then restart C1
2. Amend funnel parameters (documented amendment, pre-registered)
3. Terminate Direction I
No automatic default.

### 2.2 Trial budget allocation (A2/A3/A15)
- Single central pool of **40 — untouched by Direction H's trials** (9001/9002 are theirs; no deduction — A17)
- **First candidate: EURUSD H4** (pending Sub-project B decision) → consumes 1 of 40 → 39 remaining
- **Priority order (A15):** C1 core sweep > C2 variant deep-dive > C3 ensemble/regime > sub-programs (I.1/I.2/I.3/I.5/EVT). Sub-programs may only draw from the pool AFTER C1's first trial batch is registered, unless user escalates otherwise
- **Escalation checkpoint (A15):** when remaining pool ≤ 10, every further allocation requires explicit user decision — recorded in ledger notes, no auto-allocation
- **Exempt (0 trials):** replication benchmarks (calibration only — Faber/Moreira-Muir/Baltas-Kosowski on our data+costs), I.4 HFT latency analysis (metadata analysis)
- Sub-programs I.1 (regime), I.2 (cross-exchange arb), I.3 (tick-level), I.5 (factor library) request from the 40 with pre-registration

### 2.3 Research-hour budget breakdown (A14 — early-warning, not hard gate)
| Phase | Hours | Phase | Hours |
|---|---|---|---|
| P0 governance+closure | 10 | P5 data+calibration | 50 |
| P1 mining | 70 | P6 trials | 120 |
| P2 taxonomy | 20 | P7 confirmation | 30 |
| P3 triage | 20 | C2/C3 cycles | 60 |
| P4 screening | 40 | Buffer | 0 |
| **Total** | | | **400** |

Exceeding a phase budget = flag + user check (early-warning for scope creep), not an automatic stop.

---

## 3. N Accounting

```
N_I = 1050 (reconciled baseline)
    + |distinct configs in screening_log_i|
    + |trials in trial_ledger_i (including the one being judged)|
```

Direction H's trials/configs do NOT enter N_I (separate ledger, separate governance — A17).

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

### 3.3 Hash definition (A6 — written into `validation/n_trials_i.py`)
- `data_range` (start/end) change = **distinct config** (+1 N)
- Confirmatory retest on new data (validation purpose) = **not counted** (only screening configs + trials count)
- Mechanism: `validation/n_trials_i.py` (pattern of `validation/n_trials.py`), built in Phase 0

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
- **Item 0 — WRITER-LOCK HARDENING (A18, FIRST):** audit + close the advisory-lock gap before any funnel write. Options: (a) pre-commit hook refuses commit while `.writer.lock` exists and is not held by the committing session, (b) make git:mutate claim mandatory for commits, or (c) orchestration-level single-writer (one funnel session only). Record the decision in the stopping-rule doc. Without this, Direction I risks the same parallel-write collision as Direction H
- Writer lock, ledgers creation (3 files: `trial_ledger_i.json`, `hypothesis_registry_i.json`, `screening_log_i.json`), TRIAL_ID_RANGES.md update (add Direction I 10000-10999 row; **document that ranges follow creation order, not alphabetical order** — A13), `check_trial_uniqueness.py` pass
- Stopping-rule doc I (`reports/stopping_rule_2026_08_06_direction_i.md`) written + SHA-256 locked
- **Scope partition enforcement (A17):** P2 taxonomy MUST check Direction H ledger/registry before classifying §1.8 families (forex4 trend-continuity = CLOSED, forex4 RSI MR = WATCH)
- **Closure checklist (all must close before first screening):**
  1. TSM jackknife re-run from current data (verify REJECT holds; close ws_b residual)
  2. **REUSE (A11):** engine guard work — take Tier0 Sweep Stream C0 output (external-state scan of `engine.run()` callers + `check_data_access` decision, spec 2b4d250b §4) as input; do NOT re-implement. Add only what C0 does not cover: mandatory post-run `assert guard.violations == 0` in the screening runner + attr-scan hook per screening run
  3. Verify 8001/8002 annotations present in registry (verified ✅ 2026-08-06)
  4. Verify Direction H state unchanged (9001 REJECTED, 9002 FROZEN — citations current)
  5. **DEPENDENCY (A9):** EURUSD H4 pre-registration waits for Sub-project B Direction H decision (tier0 spec §11.3) — do not pre-register before

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
**Target: 2,500+ raw entries** → `research/catalog_i/raw_*.json`
**A7:** absorb existing uncommitted EA research artifacts (§1.5) into catalog with attribution — do not redo.
**A17:** entries matching §1.8 partition families (forex4 trend-continuity, forex4 RSI MR) are tagged `OWNED_BY_H` at ingest — never recommended downstream without documented structural difference.

### P2 — Taxonomy + Dedup Fingerprint (**0 N**)
- Classify by mechanism from description/code → 60+ canonical mechanisms (incl. ICT/SMC, Wyckoff, VSA, harmonics, orderflow/Auction Market Theory, microstructure, seasonality/calendar, carry/rollover)
- **Partition check (A17):** every mechanism×symbol×TF classification cross-checked against Direction H ledger/registry — CLOSED/WATCH tags applied
- Martingale/grid → flag into hard-gate path
- Output: `research/catalog_i/canonical_mechanisms.json` — mechanism × representative EAs × structural variants × evidence tier

### P3 — Evidence Triage (0 N)
- 3 tiers: literature-verified numbers / MyFxBook verified live / practitioner lore
- **Cost-viability math before backtest** — kills structurally impossible candidates (e.g., M1 scalper on BTCUSD 24.75bps RT) without spending screening budget
- Output: shortlist 10-20 mechanisms → Phase 4

### P4 — Screening Backtests (every config registered BEFORE run)
- **Every config = +1 N** (`screening_log_i.json` + hash, written BEFORE execute)
- Runner: **`BacktestEngine.run()` ONLY** + `assert guard.violations == 0` post-run (violation = VOID + audit; still counts N)
- Grids pre-registered in full — no post-hoc expansion without written amendment (which itself adds N)
- **Cost rule (A1):** screening uses conservative cost proxies (asset-class worst-case ×1.5) — makes screening HARDER, not easier
- Low bar (kill losers, not crown winners): raw Sharpe > 0 after proxy costs + min trades
- Output: survivors (target 5-15) → Phase 5

### P5 — Data Infrastructure + Full Calibration
- **DEPENDENCY (A12):** universe pinning waits for Tier0 Sweep Sub-project C1 commit (tradeable_universe.json EURUSD/GBPUSD status fix — EURUSD → measuring provisional, GBPUSD → excluded with evidence note, per tier0 spec §5.2). Do NOT pin the 23-symbol list from the stale dual-membership state
- **Mandatory re-filter (A1):** every P4 survivor is re-screened at REAL costs (FROM_TICKS) in P5 before entering P6. Fail at real costs = back to screening pool (same hash, no extra N)
- Acquire 8 missing symbols' data (per universe config) + TF coverage audit (precedent: DATA_PIPELINE_FORENSICS)
- Full 23-symbol cost calibration: `mt5.copy_ticks_range` backfill (proven: BTCUSD 1.29M ticks / EURUSD 290K) + fill simulator; provenance FROM_TICKS stamped
- Symbol whose calibration fails = excluded from trials (precedent Direction D — "edge net of an assumption" forbidden)
- Output: `config/cost_calibration.json` extended (23 symbols)

### P6 — Pre-Registered Trials (full gate stack, tiered)
- Each survivor → `research/pre_registration_i/trial_10XXX_*.md` (mechanism, params frozen, N_I at registration)
- Gates per tier (A4):
  - **G1 (ALL trials):** p-value (HAC/Newey-West) · WFA-OOS · WFE · DSR(N_I) · cost-stress (incl. multi-broker ±30%)
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
- **C2 — Variant Deep-Dive:** near-miss families (borderline REJECT) → structurally distinct variants (must differ from tested — no "same test re-run"; includes re-check against §1.8 partition) → screening + trials
- **C3 — Ensemble & Regime:** surviving mechanisms → correlation-adjusted portfolio construction (institutional edge) + I.1 regime conditioning (separate sub-program) → final trials
- Every cycle: N accumulates (no reset) — C3 survivors must win against TOTAL N

---

## 7. Sub-Programs (same ledger, own pre-registration, draw from pool of 40)

| ID | Sub-program | Trials | Notes |
|---|---|---|---|
| I.1 | Regime conditioning | From 40 | Separate pre-registration — avoids stacking methodology changes mid-direction |
| I.2 | Cross-exchange crypto arb | From 40 | Model ALL frictions: transfer time, withdrawal fees, counterparty risk — or it's fake numbers |
| I.3 | Tick-level microstructure | From 40 | Spread dynamics, order-flow imbalance, bid-ask bounce → feed cost models + alpha hunt |
| I.4 | HFT latency analysis | **0 (metadata)** | Measure VPS→MT5→broker latency, alpha-decay curves per family — goal: kill latency-sensitive ideas with proof (retail 10-100ms vs institutional μs) + optimize survivor execution |
| I.5 | Multi-asset factor library | From 40 | Momentum 12-1, carry, low-vol, term-structure, basis across 23 symbols → correlation matrix → portfolio phase |
| REP | Replication benchmarks | **0 (calibration)** | Faber / Moreira-Muir / Baltas-Kosowski replicated exactly on our data+costs — sets the bar (what a known-good published strategy achieves here) |
| EVT | Event/calendar studies | From 40 | FOMC/CPI/NFP drift (`fomc_drift.py`), COT (`cot_positioning.py`), funding-rate positioning proxy |
| KEL | Kelly sizing science | n/a (overlay) | Fractional Kelly + estimation-error haircut + vol targeting — for portfolio phase, not standalone trials |

---

## 8. Validation Stack (tiered — compute-efficient)

Tiered per A4 (see P6). Full stack = 15 layers:
p-value (HAC/NW) · WFA-OOS · WFE · DSR(N_I) · cost-stress+multi-broker · PBO-CSCV · purged/embargoed CV · bootstrap CI · sub-period stability · jackknife LOO · label-shuffle · parameter sensitivity · trade-level forensics · risk-of-ruin MC (martingale/grid) · stress scenarios (P7)

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
| Trial pool exhaustion before sub-programs get a turn (A15) | priority order C1>C2>C3>sub-programs + escalation checkpoint at ≤10 remaining |
| Cross-spec dependency stalls (A9/A10/A11/A12: Sub-project B decisions, C0 output, C1 universe commit) | explicit dependencies in P0/P5; fallback manual trial-number confirmation documented |
| Duplicate guard work with Tier0 Sweep C0 (A11) | reuse C0 output — P0 adds only the post-run assertion + attr-scan hook C0 does not cover |
| **Parallel-write collision with Direction H (A17/A18)** | scope partition (§1.8) + citations-only policy + writer-lock hardening in P0 item 0 |
| Duplicate mining of H-owned mechanisms (A17) | partition tags at P1 ingest + P2 ledger cross-check |

---

## 10. Deliverables

1. **Evidence-tiered catalog** — canonical mechanisms × source citations × evidence tiers (`research/catalog_i/`) — delivered regardless of win/loss
2. **Funnel artifacts** — raw catalogs (10-12 sources), `screening_log_i.json` (every config + N), screening results
3. **23-symbol cost calibration** — FROM_TICKS + fill simulator, provenance stamped
4. **Trials 10001+** — pre-registration docs + verdicts with provenance
5. **≥1 trial surviving full gate at measured costs** = proven edge (DoD)
6. **Direction I closure report** — phases, final N_I, lessons

---

## 11. Success Criteria (measurable)

- [ ] ≥1 trial survives full gate stack at measured costs (23 symbols × all TFs)
- [ ] Evidence-tiered catalog delivered with zero uncited claims (source URL per entry)
- [ ] `check_trial_uniqueness.py` passes at every ledger/registry edit
- [ ] Every verdict stamped with provenance (`registry_schema.stamp_trial_entry`)
- [ ] All Phase 0 closure items closed before first screening run
- [ ] Direction H files untouched (git diff confirms — citations-only policy)
- [ ] Writer-lock hardening decision recorded in P0 (A18)

---

## 12. Amendment Log

| ID | Date | Change | Source |
|---|---|---|---|
| A1 | 2026-08-06 | P4 uses cost proxy; P5 mandatory re-filter at real costs before P6 | Review round 2 |
| A2 | 2026-08-06 | Max Total Trials (I) = 40 hard cap, all cycles + sub-programs, single pool | Review round 2 |
| A3 | 2026-08-06 | Exempt 0-trial: replication benchmarks + I.4 HFT latency | Review round 2 |
| A4 | 2026-08-06 | Validation gates tiered G1/G2/G3 for compute efficiency | Review round 2 |
| A5 | 2026-08-06 | §4.4 decision tree — human decision, no auto-continue | Review round 2 |
| A6 | 2026-08-06 | N hash definition: data_range change = distinct config; confirmatory retests = 0 N | Review round 2 |
| A7 | 2026-08-06 | P1 absorbs uncommitted prior EA research artifacts with attribution | Lock investigation |
| A8 | 2026-08-06 | ~~Absorb committed prior Direction H work as funnel trials~~ **SUPERSEDED BY A16/A17** — H work is citations-only, never merged | Commit investigation |
| A9 | 2026-08-06 | EURUSD H4 candidate (TF probe gross Sharpe 3.46, tier0 spec §2.5/§11.3) — Direction I candidate, waits for Sub-project B decision | Review round 3 |
| A10 | 2026-08-06 | auto_increment_trial.py cap conflict (1022 vs 1042) noted — NOT used by Direction I (per-direction ledger precedent); conflict remains Sub-project B's scope | Review round 3 |
| A11 | 2026-08-06 | P0 guard closure reuses Tier0 Sweep Stream C0 output — no re-implementation; add only post-run assertion + attr-scan hook | Review round 3 |
| A12 | 2026-08-06 | P5 universe pinning waits for Sub-project C1 commit (EURUSD/GBPUSD status fix) | Review round 3 |
| A13 | 2026-08-06 | TRIAL_ID_RANGES ordering documented as creation-order, not alphabetical | Review round 3 |
| A14 | 2026-08-06 | 400 research-hours broken down per phase as early-warning checkpoints | Review round 3 |
| A15 | 2026-08-06 | Trial allocation priority (C1>C2>C3>sub-programs) + escalation checkpoint at ≤10 remaining | Review round 3 |
| A16 | 2026-08-06 | **Rename H→I (Option C+):** parallel session owns Direction H (executed, committed); funnel opens as Direction I (10000-10999) with approved params. Rename cost scoped: ledgers, N_I, catalog_i, screening_log_i, stopping-rule doc, TRIAL_ID_RANGES row, deliverables — all updated; citations to their Direction H preserved verbatim | User decision C+ |
| A17 | 2026-08-06 | **Scope partition + absorption:** 9001 REJECTED → §1.2 closed list; 9002 → WATCH item; no ledger/trial-count merging; P1 ingest + P2 classification tagged OWNED_BY_H | User decision C+ |
| A18 | 2026-08-06 | **Writer-lock hardening action item:** verified `.writer.lock` is advisory (enforced only by release gate; pre-commit has no lock check). P0 item 0 must close enforcement gap before funnel writes | Root-cause investigation |

---

## 13. Open Items (explicit, not hidden)

- Exact 23-symbol universe list to pin from `config/tradeable_universe.json` at plan time — **AFTER Sub-project C1 commit (A12)**
- Writer lock: stale locks cleared by human-approved force twice (dead PIDs 21672, 20828); enforcement gap OPEN — P0 item 0 (A18)
- TSM jackknife re-run result unknown until Phase 0 executes (closure item 1)
- MQL5/MyFxBook access friction unknown until P1 probes (Cloudflare risk recorded in project memory)
- 13 symbols still need FROM_TICKS calibration (10 done; OIL single-snapshot, NAS100 unverified)
- Sub-project B cap decision (1022 vs 1042) unresolved — Direction H/main ledger scope, NOT ours (A10)
- Sub-project B Direction H decision (EURUSD H4) unresolved — dependency for our candidate #1 pre-registration (A9)
- Tier0 Sweep C0 output not yet delivered — P0 closure item 2 waits on it (A11)
- **Direction H watch item:** trial 9002 (forex4 RSI MR, FROZEN, in-flight) — absorb result as citation when resolved (A17); do not block on it
