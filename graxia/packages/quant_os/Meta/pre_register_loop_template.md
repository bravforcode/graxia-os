# Pre-Registration Template — Loop Engineering (quant_os)

> **Copy this template** to create a new `pre_register_<id>.md` + its companion
> `pre_register_<id>.json` (machine-readable source of truth, see
> `loop_engineering/pre_register.py::PreRegistration`).
>
> **Rule (Spec Part 2.1 / Part 5):** All cfg + GO/REJECT thresholds + Optuna
> parameter ranges are LOCKED here, BEFORE any prospective data is seen. They
> cannot be changed mid-run. Changing them after a backtest is p-hacking and
> voids the trial.

## 1. Identity (locked)
- **trial_id**: `<UNIQUE_ID>`  (must not collide with any id in `research/hypothesis_registry.json`)
- **direction**: `A | B | C`  (must match the ledger this trial appends to)
- **hypothesis**: `<one-line statement of the economic mechanism being tested>`

## 2. cfg (locked)
- Symbol: `<SYM>`
- Timeframe: `<TF>`
- Strategy file: `<path/to/strategy.py>`
- All other params: `<list; anything not listed is frozen at current values>`

## 3. GO / REJECT thresholds (locked — fixed, not agent-chosen)
These are the SAME fixed gates used across the research program. Do NOT relax them
to make a result pass.
- **DK-test**: `dk_t > 2.0` AND `positive_sharpe_count >= 5`  → GO candidate
- **Label-shuffle**: `p < 0.05` (>= 200 iterations)  → survives
- **Min-trades gate**: `total_trades >= 100`  → enough statistical mass
- A hypothesis is a CANDIDATE only if ALL THREE pass (Spec Part 2.5). Raw Sharpe
  alone is NEVER sufficient to call something "promising".

## 4. Optuna parameter-range lock (Spec Part 4 — ONLY if tuning)
> If you do NOT tune, set `optuna_max_trials: 0` and skip this section.
> If you DO tune, the ranges BELOW must be filled in NOW, before any backtest.

- **optuna_max_trials**: `<N>`   (also the number of multiple-testing comparisons — feed into DK/DSR correction)
- **optuna_param_ranges** (locked, [low, high] per param):
  - `param_a`: `[<lo>, <hi>]`
  - `param_b`: `[<lo>, <hi>]`
- **Rule 1**: ranges locked before results seen.
- **Rule 2**: `optuna_max_trials` counts as `n_trials` in multiple-testing correction.
- **Rule 3**: best params MUST be re-run through label-shuffle (not just "Sharpe improved once").

## 5. Human-gate checkpoints (Spec Part 3)
- **Step 7** — opening the sacred holdout REQUIRES human sign-off. The loop will
  BLOCK and return `REQUIRES_HUMAN`; it will not open the holdout on its own.
- **Step 10** — paper trading (>= 60 days) and live deployment REQUIRE human
  sign-off. The loop NEVER deploys to live capital.

## 6. Evaluation / contingency
- On REJECT at DK or verify gate: log REJECT, increment consecutive-fail count.
  At 3 consecutive fails → `is_stopped = true` → loop halts for human re-examination
  (NOT automatic class termination).
- On holdout FAIL: hypothesis REJECTED permanently; holdout cannot be reopened.
- On holdout PASS + human sign-off: enter paper trading (>= 60d) before any live.

## 7. Provenance
- **pre_registered_at**: `<YYYY-MM-DD>`
- **source_doc**: `Meta/pre_register_loop_template.md`
- Any result artifact generated BEFORE the bug-fix cutoff in
  `reports/PROVENANCE_INDEX.md` is INVALID (inflated Sharpe) and must not be cited.
