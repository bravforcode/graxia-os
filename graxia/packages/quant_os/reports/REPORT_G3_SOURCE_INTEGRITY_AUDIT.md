# REPORT_G3_SOURCE_INTEGRITY_AUDIT

Verdict: `BLOCKED`

## Scope

Source-integrity audit only.

Not run:

- `order_send`
- demo order
- MT5 order API submission
- `scripts/g3_execute_demo_canary.py`
- `scripts/g3_close_demo_canary.py`
- any merge / cherry-pick / rebase of Quality lane

## Freeze Record

- Current branch at audit start: `g0a-security-truth-closure-20260623`
- Current HEAD SHA at audit start: `50fec7631aa3e05f8c4afb8fea183033484d98eb`
- Exact G3.2.2 SHA: `42b773aa3f5b72a710927f48fb68e4db1a5654fe`
- Current HEAD commit subject: `fix(quant_os): G3.2.3 quote coherence gate`

## Current Workspace State Before Audit

`git status --short --branch`

```text
## g0a-security-truth-closure-20260623
 M ../../../CLAUDE.md
 m ../../../repos/hftbacktest
?? artifacts/g3_execute/
?? artifacts/preflight/g2_mt5_snapshot.json
?? execution/demo_canary/margin_guard.py
?? execution/demo_canary/market_data_guard.py
?? execution/demo_canary/order_geometry_guard.py
?? reports/REPORT_QUALITY_CI_Q7_FINAL.md
?? reports/quality_ci/
?? scripts/__init__.py
?? scripts/g2_mt5_snapshot.py
?? setup.py
```

`git diff --name-status`

```text
M	CLAUDE.md
M	repos/hftbacktest
```

`git diff --cached --name-status`

```text
(empty)
```

## Required Path Audit

Audit rule used:

- `TRACKED_IN_HEAD`
- `TRACKED_IN_OTHER_COMMIT`
- `UNTRACKED`
- `MISSING`
- `GENERATED_ARTIFACT`
- `NOT_REQUIRED_FOR_G3`

### Main workspace classification

| Path | Status | Evidence |
|---|---|---|
| `execution/demo_canary/margin_guard.py` | `UNTRACKED` | present in filesystem, absent from `git ls-files` |
| `execution/demo_canary/market_data_guard.py` | `UNTRACKED` | present in filesystem, absent from `git ls-files` |
| `execution/demo_canary/order_geometry_guard.py` | `UNTRACKED` | present in filesystem, absent from `git ls-files` |
| `scripts/__init__.py` | `UNTRACKED` | present in filesystem, absent from `git ls-files` |
| `scripts/g2_mt5_snapshot.py` | `UNTRACKED` | present in filesystem, absent from `git ls-files` |
| `scripts/g2_1_calibrate.py` | `TRACKED_IN_HEAD` | returned by `git ls-files` |
| `scripts/g3_execute_demo_canary.py` | `TRACKED_IN_HEAD` | returned by `git ls-files` |
| `scripts/g3_close_demo_canary.py` | `TRACKED_IN_HEAD` | returned by `git ls-files` |
| `shadow/canonical_tick_authority.py` | `TRACKED_IN_HEAD` | returned by `git ls-files` |

### Fresh detached worktree classification

Detached worktree created from explicit HEAD SHA:

- `C:\tmp\quant_os_g3_source_audit_50fec763`
- detached HEAD: `50fec7631aa3e05f8c4afb8fea183033484d98eb`

| Path | Status | Evidence |
|---|---|---|
| `execution/demo_canary/margin_guard.py` | `MISSING` | absent from clean committed snapshot |
| `execution/demo_canary/market_data_guard.py` | `MISSING` | absent from clean committed snapshot |
| `execution/demo_canary/order_geometry_guard.py` | `MISSING` | absent from clean committed snapshot |
| `scripts/__init__.py` | `MISSING` | absent from clean committed snapshot |
| `scripts/g2_mt5_snapshot.py` | `MISSING` | absent from clean committed snapshot |
| `scripts/g2_1_calibrate.py` | `TRACKED_IN_HEAD` | present in committed snapshot |
| `scripts/g3_execute_demo_canary.py` | `TRACKED_IN_HEAD` | present in committed snapshot |
| `scripts/g3_close_demo_canary.py` | `TRACKED_IN_HEAD` | present in committed snapshot |
| `shadow/canonical_tick_authority.py` | `TRACKED_IN_HEAD` | present in committed snapshot |

## Source Closure Analysis

### Reproduced fail path

1. `tests/test_g2_preflight.py` imports:
   - `execution.demo_canary.order_geometry_guard`
   - `execution.demo_canary.market_data_guard`
   - `execution.demo_canary.margin_guard`
2. In clean detached worktree, all three files are `MISSING`.
3. Result: import collection fails before test execution.

4. `tests/test_stop_geometry.py` imports:
   - `from scripts.g2_1_calibrate import normalize_price, compute_required_distance`
5. `scripts/g2_1_calibrate.py` is `TRACKED_IN_HEAD`.
6. But `scripts/__init__.py` is `MISSING` in clean detached worktree.
7. Result: `scripts.g2_1_calibrate` is not importable as a package path; collection fails.

### Implication

Execution lane source snapshot is not closed.

The main workspace contains execution-relevant files that are untracked.
The committed execution snapshot used for release proof does not contain all load-bearing imports referenced by G2 preflight and stop-geometry tests.

Per source-closure rule, this blocks G3 progression.

## Fresh Immutable Verification Checkout

Command used:

```text
git worktree add --detach C:\tmp\quant_os_g3_source_audit_50fec763 50fec7631aa3e05f8c4afb8fea183033484d98eb
```

Stage records:

```text
cd /d C:\tmp\quant_os_g3_source_audit_50fec763
git rev-parse --show-toplevel -> C:/tmp/quant_os_g3_source_audit_50fec763
git rev-parse HEAD -> 50fec7631aa3e05f8c4afb8fea183033484d98eb
git status --short --branch -> ## HEAD (no branch)
```

Clean-at-birth result:

- PASS
- Detached verification worktree was clean before verification.

Post-check status:

```text
## HEAD (no branch)
```

Clean-after-checks result:

- PASS
- Verification commands did not dirty the detached worktree.

## Required No-Order Checks

### 1. Static `order_send` allowlist test

Command:

```text
python -m pytest tests\test_execution_import_isolation.py -q -p no:cacheprovider --basetemp C:\tmp\g3_source_audit_pytest_import_iso
```

Result:

- `3 passed, 2 warnings in 0.61s`

### 2. G3.2.1 time-authority test

Command:

```text
python -m pytest tests\test_time_authority.py -q -p no:cacheprovider --basetemp C:\tmp\g3_source_audit_pytest_time
```

Result:

- `18 passed, 2 warnings in 0.38s`

### 3. G3.2.2 canonical UTC tick authority test

Command:

```text
python -m pytest tests\test_canonical_tick_authority.py -q -p no:cacheprovider --basetemp C:\tmp\g3_source_audit_pytest_canonical
```

Result:

- `26 passed, 2 warnings in 0.31s`

### 4. G2 preflight import smoke

Command:

```text
python -m pytest tests\test_g2_preflight.py --collect-only -q -p no:cacheprovider --basetemp C:\tmp\g3_source_audit_pytest_g2_collect
```

Result:

- `BLOCKED`
- collection error:

```text
ImportError: cannot import name 'order_geometry_guard' from 'execution.demo_canary'
```

### 5. Stop-geometry import smoke

Command:

```text
python -m pytest tests\test_stop_geometry.py --collect-only -q -p no:cacheprovider --basetemp C:\tmp\g3_source_audit_pytest_stop_collect
```

Result:

- `BLOCKED`
- collection error:

```text
ModuleNotFoundError: No module named 'scripts.g2_1_calibrate'
```

## Quality/CI Separation Check

Detached execution worktree had no execution diff and no quality-branch patch mixed into tracked changes:

```text
git status --short --branch
## HEAD (no branch)
```

However the main workspace still contains untracked Quality outputs:

- `reports/REPORT_QUALITY_CI_Q7_FINAL.md`
- `reports/quality_ci/`

These were not used as release proof.

## Findings

1. `P0` — execution source snapshot is not closed.
   - Three guard modules required by `tests/test_g2_preflight.py` are not in committed HEAD.
   - Status in main workspace: `UNTRACKED`
   - Status in clean detached HEAD snapshot: `MISSING`

2. `P0` — `scripts.g2_1_calibrate` import path is broken in committed snapshot.
   - `scripts/g2_1_calibrate.py` is tracked.
   - `scripts/__init__.py` is missing.
   - `tests/test_stop_geometry.py` fails import at collection time.

3. `P1` — current working branch is not an execution-lane branch.
   - Audit started on `g0a-security-truth-closure-20260623`, not a dedicated G3 execution branch.
   - Even though HEAD commit is G3.2.3, workspace source integrity is mixed with non-execution lane state.

4. `P1` — main workspace contains untracked execution-relevant files that must not be treated as release source.
   - `execution/demo_canary/margin_guard.py`
   - `execution/demo_canary/market_data_guard.py`
   - `execution/demo_canary/order_geometry_guard.py`
   - `scripts/__init__.py`
   - `scripts/g2_mt5_snapshot.py`

## Truthful Conclusion

Good news:

- Fresh detached worktree from explicit HEAD SHA is clean and reproducible.
- G3.2.1 time-authority tests pass in that clean snapshot.
- G3.2.2 canonical UTC tick authority tests pass in that clean snapshot.
- Static `order_send` allowlist test passes in that clean snapshot.

Blocking truth:

- Committed execution HEAD does not contain all load-bearing source files required by G2 preflight and stop-geometry import paths.
- Main workspace has untracked execution files, so local filesystem cannot be treated as release source.
- Therefore G3.2.3 Quote Coherence work must not proceed as release proof from this state.

## Required Verdict

`BLOCKED`
