# INCIDENT — Trial ID #4002 Collision in Main Ledger (2026-08-05)

## Severity
MEDIUM — data-entry/governance collision, no data loss, no fabricated numbers.

## Summary
A parallel session appended a `trial_id: "4002"` (funding_arb, EXPLORATORY)
record to `research/trial_ledger.json`'s `lineage` array. Trial number **4002 is
already owned by Direction D** (`research/hypothesis_registry_d.json` →
`FUNDING-ARB-PAPER-TRADE`, status `PAPER_TRADING_STARTED`). This violates
`TRIAL_ID_RANGES.md`: trial numbers MUST be unique across ALL ledgers/registries
combined, enforced by `scripts/check_trial_uniqueness.py`.

## Evidence

### 1. The offending record (added to main ledger lineage)
```json
{
  "trial_id": "4002",
  "strategy": "funding_arb",
  "status": "EXPLORATORY",
  "stats": {
    "n_periods": 93,
    "mean_funding_8h": 6.081806451612903e-05,
    "annualized_yield_bps": 665.9578064516129,
    "positive_share": 0.989247311827957,
    "first_ts": "2026-07-01T00:00:00Z",
    "last_ts": "2026-07-31T16:00:00Z"
  },
  "run_at": "2026-08-04T19:42:52.862389+00:00"
}
```
Source: `git diff research/trial_ledger.json` (uncommitted working-tree change,
detected 2026-08-05 ~03:00 local).

### 2. The conflicting legitimate record (Direction D registry)
```json
{
  "trial_number": 4002,
  "id": "FUNDING-ARB-PAPER-TRADE",
  "status": "PAPER_TRADING_STARTED"
}
```
Source: `research/hypothesis_registry_d.json`.

### 3. Collision rule (TRIAL_ID_RANGES.md)
> Trial numbers MUST be unique across ALL ledgers/registries combined — see
> `scripts/check_trial_uniqueness.py`, which globs every `trial_ledger*.json`
> and `hypothesis_registry*.json` and fails on any cross-file trial-number reuse.

## Root cause
The parallel session's funding-arb EXPLORATORY result was written to the **main
ledger** (`trial_ledger.json`) instead of the **Direction D ledger/registry**
(`trial_ledger_d.json` / `hypothesis_registry_d.json` — the latter of which does
not exist as a ledger; Direction D's registry is `hypothesis_registry_d.json`).
This mirrors the earlier BTCVD #3001/#3004 collision pattern (fixed 2026-07-31
by renumbering Direction C off the 3001–3008 block): a session writing a
trial-numbered record without checking the disjoint-range rule.

Secondary: the main ledger's `cumulative_trial_cap` (1022) and `lock_doc_path`
(`stopping_rule_2026_07_12.md`) are stale w.r.t. `stopping_rule_2026_07_30.md`
(cap should be 1042, doc path should point at 07_30). This incident is
independent of those stale fields but compounds the reconciliation debt.

## Impact
- `scripts/check_trial_uniqueness.py` will now fail on #4002 reuse (if run).
- The EXPLORATORY funding-arb result is misattributed: it looks like a main-ledger
  trial when it is Direction D work.
- No fabricated numbers, no data loss. The 93-period stats (annualized yield
  ~666 bps, positive share 0.989) are plausible for funding arb and are NOT in
  dispute here — only the ledger placement + numbering.

## Recommended resolution (NOT performed — requires user sign-off)
Per the project's own precedent (BTCVD renumber required sign-off), do not edit
trial numbers unilaterally. Options:
- **A.** Move the EXPLORATORY record to Direction D's registry
  (`hypothesis_registry_d.json`) under a non-colliding number (e.g. #4004), and
  remove it from main ledger lineage. Cleanest, matches "each direction owns its
  numbers" rule.
- **B.** Renumber the EXPLORATORY record to the next free main-ledger number
  (e.g. #1036) and keep it in main ledger — acceptable only if the funding-arb
  EXPLORATORY work is genuinely a main-ledger trial (it is not — funding arb is
  Direction D).
- **C.** Leave as-is, but annotate the record with a `collision_note` pointing at
  this incident doc. Weakest option — keeps `check_trial_uniqueness.py` failing.

## Recommended hardener (prevents recurrence)
- Run `scripts/check_trial_uniqueness.py` in pre-commit / CI (TRIAL_ID_RANGES.md
  says the ratchet exists — verify it actually runs).
- Add a "trial numbers are per-direction" check to the funding-arb runner
  (`scripts/run_funding_arb_4002.py`) so EXPLORATORY results can only be written
  to Direction D's registry.

## Detected by
Direction G planning session (this session), during pre-Step-1 governance
reconciliation of `trial_ledger.json` vs `hypothesis_registry*.json` files.

## Status
CLOSED — 2026-08-05 (resolved without intervention)

### Resolution note (2026-08-05)
Re-verification after user sign-off (option A: move to registry_d) found the
offending record is **GONE from the working tree and never existed in git
history** — `git log --all -p -- research/trial_ledger.json` has zero hits for
`4002`/`funding_arb`/`EXPLORATORY`, and `git diff` is clean. The parallel
session's working-tree edit was reverted/discarded on its own (unstage, stash
drop, or branch switch) before any commit.

`research/hypothesis_registry_d.json` remains correct: 4001 (PASS_FEASIBILITY),
4002 (PAPER_TRADING_STARTED), 4003 (FAIL_RIGOR). `scripts/check_trial_uniqueness.py`
passes: 63 entries, 0 collisions.

**No data was lost and no renumbering was needed.** The record that had
collided was exploratory working-tree state, never committed. The incident is
closed as NO-ACTION-REQUIRED, but the root cause (parallel session writing
trial-numbered records to the main ledger without checking direction-owned
ranges) remains a live risk — see Recommended hardener below.
