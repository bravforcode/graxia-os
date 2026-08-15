# Trial #1028 (Breakout XAUUSD H1) — Unrunnable As Frozen

**Date:** 2026-07-25 | **Trial:** `Meta/pre_register_breakout_xauusd_h1.json`
**Finding:** The pre-registered GO gate cannot be evaluated for this trial. Do not implement/run until a human corrects and re-freezes the spec.

## The gate is arithmetically unreachable

GO requires `positive_sharpe_count >= 5`. This metric — as computed by the only DK-test harness that exists (`scripts/edge_search_all.py`) — counts how many symbols in a tested universe had positive Sharpe. Trial #1028 pre-registers a **single symbol** (XAUUSD only). `total_assets = 1` → the count can never exceed 1 → `>= 5` can never be true. The gate cannot return GO no matter what the strategy does. This is not an ambiguity to resolve by picking an interpretation — either the trial was meant to run pooled across a multi-symbol universe (and "XAUUSD/H1" in the JSON undersells the actual scope) or the GO criteria were copied from the pooled-test template without adapting them for a single-instrument trial. Only whoever owns this protocol can say which, and that has to happen before any run — not after, since choosing after seeing related data is itself a form of post-hoc researcher discretion.

Separately: no H1 DK-test harness exists at all (`edge_search_all.py` hardcodes `_D1.csv`), so even the "single symbol" framing has no infrastructure to evaluate it on the pre-registered timeframe.

## Relevant prior evidence (not a substitute — informational)

The mechanism family this trial proposes (channel breakout + volume/momentum filter) was already pooled-DK-tested on D1 data across a 6-8 symbol universe on 2026-07-17 (`reports/edge_search_all_results.json`) — never logged under a trial ID in any ledger, which is itself a small process gap worth closing separately. Every variant REJECTED: `Donchian_10/20/55`, `DonchianADX_10_25`, `VolumeBreakout_2.0/1.5` — all negative dk_t (-0.49 to -0.77), all negative pooled Sharpe, positive_sharpe_count 0-2 of 6. This does not answer whether the specific combined-filter, single-symbol, H1 version in #1028 would pass or fail — that's exactly what makes it dangerous to lean on now: any decision made after seeing this is contaminated by it. It is cited here only so whoever corrects the spec has the context.

## Recommendation

Do not implement `strategies/breakout.py` or attempt any run under the current pre-registration. Either:
1. A human re-scopes and re-freezes #1028 with a gate that's actually satisfiable for a single-symbol trial (e.g. a walk-forward-fold-based positive-Sharpe count instead of a cross-symbol one), or
2. A human explicitly reframes it as a pooled multi-symbol test and re-freezes with the real universe, or
3. The trial is abandoned.

Any of these is a legitimate protocol decision. Reconstructing one myself, holding the 2026-07-17 evidence, is not.
