# Pending Work Audit — 2026-07-20

Full sweep of outstanding work in `quant_os`, reconciling the stale 2026-07-12
`LIVE_TRADING_READINESS_MASTER.md` against everything on disk as of today.
Read-only findings first, then what was actually fixed this session.

---

## 1. RESOLVED — Sacred Holdout: ledger was pointing at a dead, already-retired file; corrected to the real active one

Initial read of `research/trial_ledger_b.json` showed `sacred_holdout.use_count: 0`,
status LOCKED, path `data/sacred_holdout/holdout.csv` — treated as the live
Phase 4.5 gate. Two things turned out to be wrong with that, discovered in
sequence:

**(a) That lineage was already peeked at, 2026-07-15.**
`scripts/comprehensive_edge_search.py::prong_holdout()` (line 116) opened and
backtested against `data/sacred_holdout/holdout.csv` on **2026-07-15T20:03:46**,
running *six* strategies against it in one pass (tsm_ensemble,
tsm_dxy_divergence, real_yield_regime, donchian_20, donchian_vol_filter,
vrp_holdout) — a full sweep, not a single pre-committed test. Per the ledger's
own policy: *"Opening this file and running any backtest against it counts as
1 trial. Cannot be reopened."* This also explains finding #2 below (the fake
`tsm_dxy_divergence` GO result inherits its params from this peek).

**(b) The file was gone from disk — and it turned out to already be retired.**
Hash-checking `holdout.csv` against the locked hash in
`program_closure_2026_07.md` (`5a15961c...`) to confirm the Jul-15 run hit the
real file, `data/sacred_holdout/` turned out to contain no `holdout.csv` at
all — only `holdout_btc.csv`, `holdout_btc_h1.csv`, `holdout_fresh_20260717.csv`.
Not knowing better yet, I regenerated it via `scripts/split_sacred_holdout.py`
from the unchanged `rydc_daily.csv` source. The result hashed to
`5a15961c15b1f4be50022b6c997418b267557beaf221c4b5769a0f9ebc9a9eed` — an exact
match to the old locked hash, proving the regeneration was a byte-for-byte
restore of the same (already-peeked) data, not fresh material — the source
CSV hasn't grown past 2026-07-01, and the split script is fully deterministic.
This also serves as hard confirmation the Jul-15 peek hit the genuine file.

**Then `reports/holdout_retirement_20260717.md` turned up** (missed on the
first pass) and explained why `holdout.csv` was gone: it was formally retired
**2026-07-17**, for an independent, earlier-discovered reason — the validation
pipeline had been running `donchian_20` against it through a toy-simulation
stand-in instead of the real `BacktestEngine`. The retirement doc renamed the
old file to `holdout_BURNED_toy_sim_20260716.csv` (on paper; it had actually
just vanished from disk, matching the "gone" state found above) and designated
`data/sacred_holdout/holdout_fresh_20260717.csv` — 7 assets (XAUUSD, XAGUSD,
EURUSD, GBPUSD, USDJPY, NAS100, US30), 1,799 rows, 2025-07-01 to 2026-06-29 —
as the new active holdout. `reports/EDGE_SEARCH_FINAL_20260718.md` confirms it
was still **LOCKED — do not burn** as of 2026-07-18, and a repo-wide grep for
`holdout_fresh_20260717` across all `.py` files today (2026-07-20) turns up
**zero** references — nothing has ever opened it. It is intact and unused.

**So the real state of the world, as of this audit:**
- The file `research/trial_ledger_b.json` (authored 2026-07-19, two days
  *after* the retirement) pointed at was already dead and already replaced —
  the ledger's authors apparently didn't know about, or didn't propagate,
  the Jul-17 retirement.
- `research/trial_ledger.json` (the main ledger, locked 2026-07-12, predates
  everything above) had the same stale path and had never been touched since.
- `research/trial_ledger_c.json`'s `direction_a_b_holdout` cross-reference
  note pointed at the same dead path.

**Fixed, mechanically (reconciling ledgers with an already-made decision, not
making a new one):**
- `research/trial_ledger_b.json`: `sacred_holdout.path` → `holdout_fresh_20260717.csv`,
  full `burn_history` added (Jul-15 peek → Jul-17 retirement → Jul-20
  regeneration/rename), `use_count` reset to 0 to reflect that *this* file
  has never been opened.
- `research/trial_ledger.json`: same path fix, with a note pointing at the
  Path B ledger's full history rather than duplicating it.
- `research/trial_ledger_c.json`: `direction_a_b_holdout.path` corrected the
  same way.
- The resurrected `data/sacred_holdout/holdout.csv` (the byte-identical
  restore of the retired file) renamed on disk to
  `holdout_BURNED_toy_sim_20260716.csv`, matching the name the retirement doc
  already claimed it had — so the dead path can't be mistaken for active
  again by a future session (as it was by this one, for a few steps).

**Net: no outstanding decision here.** The retirement and replacement were
already decided by an earlier session; this was a reconciliation of stale
records against that decision, not a new governance call. Phase 4.5 has a
real, intact, never-opened gate file at
`data/sacred_holdout/holdout_fresh_20260717.csv`.

## 2. The Path B "GO" result you have not seen yet is not real — but explains why someone tried it

`reports/pooled_tsmdxydivergence_results.json` (2026-07-19T05:31, roughly 3.5
days after the Jul-15 holdout peek, same lineage) shows a composite
`tsm_dxy_divergence` strategy — combining the TSM-momentum and DXY-divergence
signals — scoring **GO**: `dk_t=4.95`, holds up under 50% cost stress. On
paper this looks like the best result in the entire Path B / A+B+C program.

It isn't usable evidence, on three independent grounds, any one of which is
sufficient:

1. **175 total trades**, against the project's own pre-registered floor of
   1,000 (`reports/pooled_tsmom_preregistration.md:49`: *"If excluding an asset
   drops total trades below 1,000, flag as INSUFFICIENT_SAMPLE"*).
2. **Non-frozen, ad-hoc parameters** (`lookbacks=[20,40,60,120]`,
   `atr_sl_mult=4.0`) that match none of the 7 registered Path B hypotheses,
   and are not the frozen TSMOM params (`lookback=252`) from the actual
   pre-registration doc.
3. **Traced lineage to the burned holdout**: the exact same lookback set
   `[20,40,60,120]` appears in `comprehensive_edge_search.py:134`'s
   `prong_holdout()` TSM ensemble test from Jul 15 — the parameters were
   almost certainly carried over from peeking at holdout results, then
   re-tried pooled across a live-data universe. Per-asset profit factors of
   50.5 (EURUSD/GBPUSD, on 40/35 trades) and 9.6 (XAGUSD) are textbook
   small-sample overfit signatures, not edge.

Later the same day (17:10–17:30), the two components were tested standalone
under their actual frozen, registered params — `DXYDiv_default` (trial 3004)
and `TSMOM_default` (trial 3005) — and **both REJECT** (`dk_t=-1.31` and
`dk_t=-1.21` respectively). That's the correct, disciplined result. The
composite GO is noise from an undisciplined probe, not a resurrected edge.

**Net: no live edge here. The "no edge found" conclusion from
`program_closure_2026_07.md` and `PROVENANCE_INDEX.md` still stands** —
this doesn't change it, it just needed tracing down before I could say that
with confidence.

## 3. Path B ledger — RESOLVED this session (trial 3007 / COT)

Good news: `research/trial_ledger_b.json` and `hypothesis_registry_b.json`
already reflect 3004 (DXYDiv) and 3005 (TSMOM) as REJECTED
(`consecutive_fail_count: 2`) — this was already committed to git before this
session, so no action was needed there.

The suspicion in the original draft of this section was correct — the old
`reports/cot_positioning_edge_verification.txt` (0 trades, Sharpe/Sortino/CAGR
exactly `0.0000`) was not a clean REJECT, it was broken. Root-caused this
session:

1. `scripts/deep_dive_cot_positioning_validation.py` was previously a stub
   that never called `compute_cot_positioning_signals()` with real CFTC COT
   data — rewired to load real COT parquet data via `load_cot_data()` and do a
   point-in-time as-of lookup per bar.
2. Re-running still produced "0/5 gates, NO EDGE." Instrumented the real
   `StrategyValidator.run()` pipeline directly (real `ValidationConfig`:
   `risk_per_trade_bps=100`, `initial_capital=$10,000`) and found the true
   cause: of 484 signal calls, 24 lost their stop-loss to insufficient local
   ATR warmup history at the start of each WFA-fold/PBO-period slice (a minor,
   separate bug), and of the 358 that reached position sizing, **348 (97%)
   rounded down to 0.00 lots** — XAUUSD's current ($3400+) price/volatility
   regime produces 2×ATR stop distances of $27-$810 (median $83), which need
   $2,700-$81,000+ of one-lot risk against a $100 (1% of $10k) risk budget.
   Only 10 of 484 calls ever produced a trade. This is a harness
   capital-scale limitation, not a real test of the COT mechanism — the same
   category of issue that got 3006 (FOMC) marked UNTESTED rather than
   REJECTED.
3. Asked the user how to classify it given this evidence. **Decision:
   UNTESTED**, same treatment as 3006, does not count toward the stopping
   rule. Recorded in `research/trial_ledger_b.json` (`consecutive_fail_count`
   stays at 2/3, `is_stopped: false`); `cot_positioning_edge_verification.txt`
   now carries a superseded-header explaining why the raw "0/5 gates" numbers
   in that file are not trustworthy.

Trials 3001 (Carry), 3002 (VRP), 3003 (CAM), and 3006 (FOMC) remain open —
not blocked, since the stopping rule never tripped.

## 4. Fixed this session (safe, reversible, in-scope)

- **MT5 direct-connection guard on the three scripts implicated in the
  2026-07-17 incident** (`reports/incident_unvalidated_scripts_20260717.md`).
  `scripts/mega_paper_v4.py`, `scripts/live_donchian.py` (real-order path
  only), and `scripts/tsm_paper_trade.py --live` now hard-stop before calling
  `mt5.initialize()`/`mt5.order_send()` unless
  `QUANT_OS_ALLOW_UNVALIDATED_LIVE=1` is set, with a message pointing at the
  incident report. `tsm_paper_trade.py --dry-run` and `live_donchian.py
  --dry-run` are both explicitly unaffected — `live_donchian.py`'s guard was
  originally unconditional (would have blocked its own advertised
  signal-logging-only mode), caught and fixed to gate on `not args.dry_run`
  before finalizing this report. `scripts/run_paper_trading.bat` launches
  `tsm_paper_trade.py --live`, so the scheduled-task path is covered by the
  same guard. This does **not** fix the underlying architectural gap (any
  script can still call `mt5.initialize()` directly — a repo-wide guard would
  need to live in `broker/mt5_gateway.py` plus a lint/CI rule banning direct
  `mt5.` calls outside it); it closes the specific reopening vector for the
  three scripts named in the incident.
- **`.env.example` default Postgres credentials** (`postgres:postgres`)
  replaced with `CHANGE_ME:CHANGE_ME` so a copy-pasted `.env` doesn't silently
  run with a known-default DB password.

All four edits above (`mega_paper_v4.py`, `live_donchian.py`,
`tsm_paper_trade.py`, `.env.example`) are **staged in the working tree only —
not committed.** `mega_paper_v4.py` and `live_donchian.py` are untracked
(never committed even before this session); `tsm_paper_trade.py` and
`.env.example` are tracked and now show as modified. Nothing has been
committed or pushed; say the word if you want these committed.

## 5. Everything else — reconciling the stale master doc

Verified in a prior session (Explore agent), still holding as of this audit
unless noted:

**Already fixed, master doc is stale on these:**
- B4 `evaluate_model()` dummy metrics — fixed by 2026-07-13.
- B2 StateCoordinator 5-store sync — fixed by 2026-07-13.
- B3 AlertManager routing — fixed (partially) by 2026-07-13.
- B2 Telegram `pass` blocks — false alarm, best-effort exception swallowing by
  design, not broken handlers.
- B1/E1 `position_sizer_v2.py` margin placeholder — not a bug, real check is
  in `risk/pre_trade_risk.py:97-99`.

**Confirmed still open:**
- B3: heartbeat_monitor (1hr) vs DeadMansSwitch (5min) threshold mismatch.
- B1: `position_reconciler.py` not wired to run in real-time.
- D2: (now fixed — see §4).
- G2: `core/news_blackout.py` not wired to any economic-calendar feed.
- Category A (Proven Edge) — still fully blocking, and the situation is
  *worse* than the 2026-07-12 doc assumed: not only is Category A unmet, the
  entire A+B+C research program formally closed 11/11 REJECT
  (2026-07-13), and Path B is now at 3/3 consecutive REJECT pending the
  ledger write in §3. **There is no proven edge on any tested hypothesis as
  of this audit.**
- All of Category C (0/60 days paper trading, integration/stress testing),
  D1 (manual secret rotation), Category F (deployment/DR untested) — untouched,
  unstartable by code changes alone.

## 6. What still needs a decision from you

1. ~~Sacred holdout~~ — **resolved, no decision needed.** Turned out to
   already be handled by an earlier session (retired 2026-07-17, replacement
   `holdout_fresh_20260717.csv` already created and still untouched). This
   session's job was just reconciling three ledgers' stale pointers to that
   decision — done, see §1.
2. ~~Path B stopping rule / trial 3007~~ — **resolved.** Rewired the COT
   validator to use real CFTC data, root-caused the "0/5 gates" result to a
   confirmed harness capital-scale bug (97% of signals silently size to 0
   lots), and per user decision recorded 3007 as UNTESTED rather than
   REJECT — stopping rule stays at 2/3, nothing blocked. See §3.
3. Whether to invest in the architectural fix (CI/lint rule banning direct
   `mt5.` calls outside `broker/mt5_gateway.py`) beyond the three-script guard
   added today — that's a larger, higher-effort item the incident report
   recommended but scoped as future work. Still open, no action taken this
   session.
