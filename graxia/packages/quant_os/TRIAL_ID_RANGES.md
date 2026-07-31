# Trial ID Ranges

Disjoint trial-number ranges per direction/registry. **Trial numbers MUST be
unique across ALL ledgers/registries combined** — see
`scripts/check_trial_uniqueness.py`, which globs every `trial_ledger*.json` and
`hypothesis_registry*.json` and fails on any cross-file trial-number reuse.

| Direction / Registry        | Documented range | Actual on-disk range (verified 2026-07-31) | Files                                                      |
|-----------------------------|-------------------|------------------------------------------------|------------------------------------------------------------|
| Main                        | 1000–1999         | 1001–1029, **plus a stray 2002** (see below)   | `hypothesis_registry.json`, `trial_ledger.json`            |
| Direction B                 | 2000–2999         | **3001–3008** (never actually used 2000–2999)   | `hypothesis_registry_b.json`, `trial_ledger_b.json`        |
| Direction C                 | 3000–3999         | 3001–3003 (registry) / 3002–3004 (ledger) — internally inconsistent, see below | `hypothesis_registry_c.json`, `trial_ledger_c.json`        |
| Reserved (future directions)| 4000+            | Direction D (funding-rate arb) correctly uses 4001+ | allocate the next free 1000-block and record it here      |

The "Documented range" column is what this table asserted before 2026-07-31;
it does not match what is actually on disk for Main, Direction B, or
Direction C. Treat the "Actual on-disk range" column as the current source of
truth until the collisions below are resolved and this table is corrected to
match a real fix (not just re-asserted).

## Rules
- Never reuse a trial number across different directions/registries.
- When adding a new direction, allocate the next free 1000-block and record it in
  this table.
- Run `python scripts/check_trial_uniqueness.py` after any ledger/registry edit.
- This file is referenced from `CONTRIBUTING.md`.

## Current collisions to resolve (re-verified 2026-07-31, supersedes the prior note below)

**1. Direction B vs Direction C, trial numbers 3001–3004 — real, different trials sharing numbers, not a casing issue:**

| Number | Direction B (`trial_ledger_b.json` / `hypothesis_registry_b.json`) | Direction C (`hypothesis_registry_c.json`) | Direction C (`trial_ledger_c.json`) |
|--------|---|---|---|
| 3001 | PATHB-CARRY-XAUUSD | BTCVD-BTC-VOL-DIVERGENCE | *(absent)* |
| 3002 | PATHB-VRP-XAUUSD | ETHVC-ETH-VOL-CONFIRM | ETHVC-ETH-VOL-CONFIRM |
| 3003 | PATHB-CAM-XAUUSD | BEVS-BTC-ETH-VOL-SPREAD | BEVS-BTC-ETH-VOL-SPREAD |
| 3004 | PATHB-DXY-DIV-XAUUSD | *(absent)* | btc_vol_divergence |

Direction B occupies the entire 3001–3008 block; Direction C's own two files
disagree with each other about whether "BTC vol divergence" is #3001 (per its
registry) or #3004 (per its ledger) — a second, separate problem internal to
Direction C, on top of the B/C cross-direction collision. This table's
previous "Direction B = 2000–2999" claim was never true in practice; Direction
B's ledger/registry started numbering at 3001 from creation (2026-07-19) and
this was not caught until 2026-07-31.

**2. Main registry has a stray Trial #2002** (`hypothesis_registry.json`,
`cumulative_trial_count_at_creation: 2002`, the LLM news-sentiment
pre-registration) sitting inside Main's 1000–1999 block. This is on hold —
do not renumber or relocate it until the Direction B/C collision above is
resolved, since any target range for #2002 depends on knowing which ranges
are actually free.

**Superseded (2026-07-31): the note this replaced described Direction C
reusing 2002/2003/2004 against Main, described as already addressed by a
2001→2004 renumber. That specific issue is not reproducible against the
current files and is not what `check_trial_uniqueness.py` currently reports —
the live conflict is the B/C one documented above.**
