# F27 — Contract-Spec Bug Verification for donchian_p1 / tsm_dxy_divergence

Date: 2026-07-28

## ⚠️ Data-preservation note (read first)

Re-running `scripts/run_p1_pooled_tests.py` to verify F27 **overwrote** the
original 2026-07-19 result files at the same path (`reports/pooled_donchianp1_results.json`,
`reports/pooled_tsmdxydivergence_results.json`) — neither was git-tracked
(`git status` confirms both `??`, `git log` confirms zero history), so the
original raw JSON (full per-asset table, trade list, correlation matrix) is
**not recoverable**. This should have been copied aside before re-running.
The key numbers from the original are not fully lost — they were already
quoted in `reports/warehouse_dedup_exposure_audit_20260728.md` and in
MEGA_PLAN v2's F27 entry (dk_t=+7.93 / +4.95, GO verdict, EURUSD/GBPUSD-driven,
profit_factor 23-32, XAUUSD flat) — but the full artifact is gone. Logging
this as a mistake, not glossing over it.

## Question

Do `strategies/donchian_p1.py` and `strategies/tsm_dxy_divergence.py`'s
2026-07-19 GO verdicts (dk_t=+7.93, dk_t=+4.95) survive on the current,
bug-fixed `BacktestEngine`, or were they an artifact of the symbol-threading
bug (commit `59a15bd0`, same day, 2026-07-19 14:48:22 +0700)?

## Evidence trail (concrete, not pattern-match)

1. `backtest/engine.py:887` calls `InlineContractSpec.for_symbol(signal.symbol)`.
   Confirmed via direct read: EURUSD/GBPUSD have correct real FX specs
   registered (`contract_size=100000, tick_size=0.0001, tick_value=10.0`,
   engine.py:108-117) — **if** `signal.symbol` resolves correctly. The
   fallback for an unmapped symbol is `specs.get(symbol, cls())` — the
   class defaults (`contract_size=100, tick_size=0.01, tick_value=1.0`,
   i.e. XAUUSD-shaped values) — engine.py:147.

2. Commit `59a15bd0` (2026-07-19 14:48:22 +0700), message verified verbatim:
   > Bug #1: engine.py hardcoded symbol=BACKTEST in generate_signal().
   > Non-XAUUSD symbols got wrong contract sizing (~1000x under).
   > Fix: add engine._symbol attr, set in all 10 caller scripts.

   Confirmed via `git show 59a15bd0 -- scripts/pooled_donchian_test.py`: the
   fix is a 1-line addition, `engine._symbol = symbol  # Fix Bug #1: ...`,
   inserted immediately before `engine.set_strategy(strategy)` — this exact
   line is present at `scripts/pooled_strategy_test.py:138` today.

3. `scripts/pooled_strategy_test.py` (the harness `run_p1_pooled_tests.py`
   uses) was authored as a brand-new file inside commit `59a15bd0` — no
   git-tracked prior version exists, so no direct before/after diff is
   possible for this specific file via git.

4. Filesystem timestamps (not git, since untracked):
   - `scripts/pooled_strategy_test.py`: **ctime 05:21:19**, **mtime 14:46:16** (same day) — created early, edited again ~9.5h later, right before the 14:48:22 commit.
   - `reports/pooled_donchianp1_results.json` (original, now overwritten): mtime **05:29:15**
   - `reports/pooled_tsmdxydivergence_results.json` (original, now overwritten): mtime **05:31:30**

   Both original GO results were generated **between** the file's creation
   (05:21) and its last edit (14:46) — i.e., before whatever change was made
   at 14:46, which is also when the commit (14:48) bundling the Bug #1 fix
   across "10 caller scripts" happened. This is circumstantial (no direct
   diff available for this specific file) but consistent with the original
   runs predating the fix.

## Direct empirical test (decisive)

Reran `scripts/run_p1_pooled_tests.py` today against the **current, fixed**
engine (same strategy code, same data, same universe):

| Strategy variant | Original (2026-07-19, pre-fix) | Rerun today (post-fix) | Verdict shift |
|---|---|---|---|
| donchian_p1 (best variant) | dk_t = **+7.93**, GO | donchian_20: dk_t = **3.679**; donchian_vol_filter: dk_t = **3.318** | GO → **MARGINAL** |
| tsm_dxy_divergence | dk_t = **+4.95**, GO | dk_t = **2.901** | GO → **MARGINAL** |

Per-asset detail from the rerun (donchian_vol_filter): EURUSD Sharpe 0.12
(nw_t 0.61), GBPUSD Sharpe -0.19 (nw_t -0.88) — **no longer** the extreme
profit-factor/high-drawdown signature (PF 23-32) documented in the original.
XAUUSD is now the negative leg (nw_t -1.45) rather than flat. 4/8 assets
Sharpe > 0 in both reruns (script's own GO rule requires `dk_t > 2.0 AND
positive_sharpe_count >= 5`; MARGINAL rule is `dk_t > 1.5 OR
positive_sharpe_count >= 3` — both reruns hit MARGINAL via the asset-breadth
shortfall, not because dk_t collapsed to noise).

## Verdict

**Partially confirmed, more nuanced than "bug explains everything."** The
symbol-threading bug was real, was fixed same-day, and the fix — combined
with whatever else changed in that edit window — cut dk_t roughly in half
(7.93→3.3-3.7, 4.95→2.9) and flipped the verdict from GO to MARGINAL under
the script's own rule. But dk_t did **not** collapse to noise level (both
reruns remain > 2.0, well above the label-shuffle-typical noise band ~0.3-0.9
seen elsewhere in this codebase's REJECTED trials). The extreme EURUSD/GBPUSD
profit-factor signature is gone, consistent with the tick-size artifact
explanation — but a real, weaker, positive dk_t remains.

**This is not a clean bug-explains-it-all close, and not a clean surviving-edge
open either.** Per MEGA_PLAN v2 F27's own instructions: since the result is
NOT confirmed dead (dk_t remains > 2.0), it must go through the full Task 0A
gate battery — label-shuffle, Deflated Sharpe Ratio (N=1050 reconciled),
PBO/CSCV, cost-stress, jackknife — before any GO/REJECT call, not registered
as-is and not dismissed as pure artifact. Neither strategy is cleared for the
alpha engine on the strength of this rerun alone.

## Update 2026-07-28 (same day) — jackknife closes this decisively

Per-asset breakdown of the post-fix rerun showed XAGUSD as an outlier
unlike anything else in the panel: `nw_t_stat=5.76-5.88`, `profit_factor=
29-34`, in **both** donchian variants and in tsm_dxy_divergence. Checked
`InlineContractSpec.for_symbol()` (`backtest/engine.py:104-146`) directly:
**XAGUSD is not in the symbol map at all** (neither is NAS100, US30, or
`BTCUSD` — only `BTCUSDT` is mapped). All four silently fall back to
`specs.get(symbol, cls())` — the class defaults, which are XAUUSD-shaped
(`contract_size=100, tick_size=0.01, tick_value=1.0`), not correct for
silver. A second, independent contract-spec table exists in
`risk/position_sizer.py` (`_SYMBOL_CONTRACT_SIZES`) that **does** have
`XAGUSD: 5000` (correct, 5000oz/lot) and `BTCUSD: 1` — i.e. two
disagreeing, duplicated contract-spec sources in this codebase, and the
backtest engine uses the incomplete one.

Rather than patch `InlineContractSpec` (would require inventing/sourcing
exact tick_size/tick_value for XAGUSD/NAS100/US30, not something to be
guessed at) and re-running, ran the mechanism-agnostic test instead:
leave-one-asset-out on the existing `donchian_vol_filter` result, reusing
`pooled_strategy_test.py::run_one_variant()`'s existing `universe=` param
(no engine change needed):

| Universe | dk_t | Verdict | Pos. Sharpe |
|---|---|---|---|
| Full (8 assets) | **+3.318** | MARGINAL | 4/8 |
| Exclude XAGUSD only (7) | **−0.136** | MARGINAL (only via pos_sharpe rule) | 3/7 |
| Exclude BTCUSD only (7) | **+3.369** | MARGINAL | 3/7 |
| Exclude both (6) | **−1.014** | REJECT | 2/6 |

Removing XAGUSD alone flips the pooled result from clearly positive
(+3.32) to flat/negative (−0.14). Removing BTCUSD barely moves it
(+3.32→+3.37), confirming BTCUSD isn't a material driver despite its own
elevated PF (9.5). **The entire "surviving" post-symbol-fix signal is
carried by a single asset (XAGUSD) whose contract spec is independently
confirmed missing/wrong** — this is not inferred from a similarity to a
known bug pattern, it's demonstrated directly by removing that one asset
and watching the pooled statistic invert.

**Revised verdict: F27 → REJECT**, for both `donchian_p1` variants (tested
directly) and inferred for `tsm_dxy_divergence` (same universe, same
engine, same missing-XAGUSD defect, XAGUSD showed the identical nw_t≈5.8/
PF≈9.65 outlier signature in that strategy's own per-asset table — not
independently jackknifed, flag as inferred-not-directly-tested if this
matters later). No genuine multi-asset edge survives. Full Task 0A battery
(label-shuffle/DSR/PBO) is not needed — this fails at the jackknife stage,
which is a lower bar than any of those.

## Action items

- [x] ~~Run full battery~~ — superseded: jackknife alone is decisive REJECT.
- [ ] Register both donchian_p1 variants and tsm_dxy_divergence in
      `research/hypothesis_registry_b.json` / `trial_ledger_b.json` as
      **REJECTED**, citing the jackknife result above, not the stale
      +7.93/+4.95.
- [ ] Separate, non-blocking hygiene ticket: `InlineContractSpec.for_symbol()`
      is missing XAGUSD, NAS100, US30, and `BTCUSD` (vs `BTCUSDT`) — should
      be reconciled against `risk/position_sizer.py`'s separate table
      (which has correct XAGUSD=5000, BTCUSD=1) so there is one source of
      truth, not two disagreeing ones. Low priority: only matters for
      future backtests including these symbols; does not change any
      REJECTED trial's direction (already-negative results don't flip sign
      from a sizing bug alone at this asset weight).
- [ ] Going forward: **copy any result JSON to a `_original` suffix before
      re-running a script that writes to the same output path** — this
      session's mistake, don't repeat it. (Done for this rerun: see
      `reports/pooled_donchianp1_results_20260728_postfix.json` and
      `reports/pooled_tsmdxydivergence_results_20260728_postfix.json`.)
