# Trial ID Ranges

Disjoint trial-number ranges per direction/registry. **Trial numbers MUST be
unique across ALL ledgers/registries combined** — see
`scripts/check_trial_uniqueness.py`, which globs every `trial_ledger*.json` and
`hypothesis_registry*.json` and fails on any cross-file trial-number reuse.

| Direction / Registry        | Documented range | Actual on-disk range (verified 2026-07-31) | Files                                                      |
|-----------------------------|-------------------|------------------------------------------------|------------------------------------------------------------|
| Main                        | 1000–1999         | 1001–1031                               | `hypothesis_registry.json`, `trial_ledger.json`            |
| Direction B                 | 2000–2999         | **3001–3008** (never actually used 2000–2999)   | `hypothesis_registry_b.json`, `trial_ledger_b.json`        |
| Direction C                 | 7000–7999         | **7001–7003** (renumbered 2026-07-31 off collision with Direction B; see below) | `hypothesis_registry_c.json`, `trial_ledger_c.json`        |
| Direction D                 | 4001+             | 4001–4003 (funding-rate arb)             | `hypothesis_registry_d.json` (ledger: uses MAIN — anomaly, see below) |
| Direction E                 | 5001+             | 5001–5002 (cointegration pairs)          | `hypothesis_registry_e.json` (no separate ledger)          |
| Direction F                 | 6001+             | 6001 (crypto basis/carry)                | `hypothesis_registry_f.json` (no separate ledger)          |
| Direction G                 | 8000–8999         | 8001–8002 (pre-registered 2026-08-05)    | `hypothesis_registry_g.json`, `trial_ledger_g.json`        |
| Direction H                 | 9000–9999         | 9001 (REJECTED 2026-08-06), 9002 (FROZEN) | `trial_ledger_h.json`, `hypothesis_registry_h.json`        |
| Direction I                 | 10000–10999       | (pre-registration starts 2026-08-06)     | `trial_ledger_i.json`, `hypothesis_registry_i.json`, `screening_log_i.json` |
| Reserved (future directions)| 4000+            | — | allocate the next free 1000-block and record it here      |

The "Documented range" column is what this table asserted before 2026-07-31;
it does not match what is actually on disk for Main, Direction B, or
Direction C. Treat the "Actual on-disk range" column as the current source of
truth until the collisions below are resolved and this table is corrected to
match a real fix (not just re-asserted).

## Rules
- Never reuse a trial number across different directions/registries.
- When adding a new direction, allocate the next free 1000-block and record it in
  this table.
- Ranges follow DIRECTION CREATION ORDER, not alphabetical order (e.g., C=7xxx
  predates D=4xxx). Derive the next block from the highest allocated block,
  never from the letter.
- Run `python scripts/check_trial_uniqueness.py` after any ledger/registry edit.
- This file is referenced from `CONTRIBUTING.md`.

## Current collisions to resolve (re-verified 2026-07-31, supersedes the prior note below)

**1. Direction C's internal self-disagreement is FIXED (2026-07-31).** Its
ledger had logged "BTC vol divergence" as trial #3004 while its own registry,
registry's `pre_registration_doc` path, and the actual filename
`research/pre_registration_c/trial_3001_btc_vol_divergence.md` all agreed on
#3001 — a data-entry typo in `trial_ledger_c.json`, not two commits that
needed merging (both files are untracked working-tree JSON, never committed;
there was nothing to merge). Corrected `trial_ledger_c.json`'s entry and its
`next_available_trial_number` (3005 → 3004) to match the registry.

**2. Direction B vs Direction C, trial numbers 3001–3004 — RESOLVED (2026-07-31)
by renumbering Direction C, not Direction B:**

| Number | Direction B (`trial_ledger_b.json` / `hypothesis_registry_b.json`) | Direction C (`hypothesis_registry_c.json` / `trial_ledger_c.json`) |
|--------|---|---|
| 3001 | PATHB-CARRY-XAUUSD | *(now 7001, was BTCVD-BTC-VOL-DIVERGENCE)* |
| 3002 | PATHB-VRP-XAUUSD | *(now 7002, was ETHVC-ETH-VOL-CONFIRM)* |
| 3003 | PATHB-CAM-XAUUSD | *(now 7003, was BEVS-BTC-ETH-VOL-SPREAD)* |
| 3004 | PATHB-DXY-DIV-XAUUSD | *(was already free within C)* |

Direction B occupies the entire 3001–3008 block; Direction C independently
claimed 3001–3003 a week earlier (registered 2026-07-13, before Direction B's
2026-07-19/20). Whoever set up Direction B's numbering didn't check that
range was already taken. Decision (2026-07-31): move Direction C to the
7000–7999 block (both directions' ledger/registry files, and the
`pre_registration_c/trial_NNNN_*.md` doc filenames, renumbered 3001→7001,
3002→7002, 3003→7003; `next_available_trial_number` 3004→7004). Direction B
is untouched and is now the sole owner of 3001–3008. This table's previous
"Direction B = 2000–2999" claim was never true in practice; Direction B's
ledger/registry started numbering at 3001 from creation and this was not
caught until 2026-07-31.

**3. Main registry has a stray Trial #2002** (`hypothesis_registry.json`,
`cumulative_trial_count_at_creation: 2002`, the LLM news-sentiment
pre-registration) sitting inside Main's 1000–1999 block. **FIXED (2026-07-31):**
renumbered to #1031 (next available in Main's range, after discovering #1030
was already occupied by DTSMOM `trial_1030_diversified_tsmom.md`).

**Superseded (2026-07-31): the note this replaced described Direction C
reusing 2002/2003/2004 against Main, described as already addressed by a
2001→2004 renumber. That specific issue is not reproducible against the
current files and is not what `check_trial_uniqueness.py` currently reports —
the live conflict is the B/C one documented above.**
