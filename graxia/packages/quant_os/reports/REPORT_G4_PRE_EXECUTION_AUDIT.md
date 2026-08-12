# REPORT_G4_PRE_EXECUTION_AUDIT

Verdict: `BLOCKED`

## Scope

Pre-execution audit only.

Not run:

- `order_send`
- demo order
- broker mutation
- `scripts/g3_execute_demo_canary.py`
- `scripts/g3_close_demo_canary.py`
- strategy, signal, automation, or campaign expansion

## Candidate SHAs

| Candidate | Role | Clean worktree | Result |
|---|---|---:|---|
| `e83403141a190ae0c5a6bd9c128d24ee398baa3d` | current main execution lineage | yes | source closure passes, retcode matrix absent |
| `c7933f9ee750e72dc88af2dee98e9048e28c0972` | `release/g3-canonical-geometry-rc` lineage | yes | retcode matrix passes, source closure fails |

## Evidence: `e834031`

Fresh detached worktree:

```text
C:\tmp\quant_os_g4_readiness_e834031
git status --short --branch -> ## HEAD (no branch)
```

Tracked required paths:

```text
execution/demo_canary/margin_guard.py
execution/demo_canary/market_data_guard.py
execution/demo_canary/order_geometry_guard.py
scripts/__init__.py
scripts/g2_1_calibrate.py
scripts/g3_close_demo_canary.py
scripts/g3_execute_demo_canary.py
shadow/canonical_tick_authority.py
tests/test_quote_role_separation.py
```

Source-closure import checks:

```text
python -m pytest tests\test_g2_preflight.py --collect-only -q
47 tests collected in 0.53s

python -m pytest tests\test_stop_geometry.py --collect-only -q
36 tests collected in 0.43s
```

No-order readiness suite:

```text
python -m pytest tests\test_g2_preflight.py tests\test_stop_geometry.py tests\test_time_authority.py tests\test_canonical_tick_authority.py tests\test_execution_import_isolation.py tests\test_quote_role_separation.py -q
159 passed, 2 warnings in 0.98s
```

Retcode matrix files:

```text
tests/test_g3_4_ordersend_failure_matrix.py
tests/test_g3_4_ordersend_integration.py
```

Status in `e834031`:

```text
not tracked
```

Conclusion for `e834031`:

- Source closure: `PASS`
- No-order readiness tests: `PASS`
- G4.4 retcode-matrix coverage: `MISSING`
- G4.0 eligibility: `BLOCKED`

## Evidence: `c7933f9`

Fresh detached worktree:

```text
C:\tmp\quant_os_g4_retcode_c793_clean
git status --short --branch -> ## HEAD (no branch)
```

Retcode matrix:

```text
python -m pytest tests\test_g3_4_ordersend_failure_matrix.py tests\test_g3_4_ordersend_integration.py -q
30 passed, 2 warnings in 0.51s
```

Source-closure check:

```text
python -m pytest tests\test_g2_preflight.py tests\test_stop_geometry.py tests\test_time_authority.py tests\test_canonical_tick_authority.py tests\test_execution_import_isolation.py tests\test_quote_role_separation.py tests\test_g3_4_ordersend_failure_matrix.py tests\test_g3_4_ordersend_integration.py -q
ERROR tests\test_g2_preflight.py
ImportError: cannot import name 'order_geometry_guard' from 'execution.demo_canary'
```

Tracked required paths in `c7933f9`:

```text
scripts/__init__.py
scripts/g2_1_calibrate.py
scripts/g3_close_demo_canary.py
scripts/g3_execute_demo_canary.py
shadow/canonical_tick_authority.py
tests/test_g3_4_ordersend_failure_matrix.py
tests/test_g3_4_ordersend_integration.py
tests/test_quote_role_separation.py
```

Missing from `c7933f9`:

```text
execution/demo_canary/margin_guard.py
execution/demo_canary/market_data_guard.py
execution/demo_canary/order_geometry_guard.py
```

Conclusion for `c7933f9`:

- Retcode matrix: `PASS`
- Source closure: `FAIL`
- G4.0 eligibility: `BLOCKED`

## Finding

There is no single clean release candidate that currently proves both:

1. execution source closure, and
2. G3.4 retcode-matrix fail-closed coverage.

`e834031` is the safer base for G4 because it closes source provenance and import graph. The retcode-matrix tests from `c7933f9` must be brought forward into a new clean candidate before any real `order_send` is approved.

## Required Next Action

Create one clean, hook-verified G4 pre-execution candidate from `e834031` that adds only:

- `tests/test_g3_4_ordersend_failure_matrix.py`
- `tests/test_g3_4_ordersend_integration.py`
- any minimal non-execution support code required by those tests
- a report documenting exact verification

Then verify in a fresh detached worktree:

```text
git status --short --branch
python -m pytest tests\test_g2_preflight.py tests\test_stop_geometry.py tests\test_time_authority.py tests\test_canonical_tick_authority.py tests\test_execution_import_isolation.py tests\test_quote_role_separation.py tests\test_g3_4_ordersend_failure_matrix.py tests\test_g3_4_ordersend_integration.py -q -p no:cacheprovider
git status --short --branch
```

Only after that candidate passes should G4.0 one-shot demo `order_send` be considered for separate explicit approval.

## Final Verdict

`BLOCKED`
