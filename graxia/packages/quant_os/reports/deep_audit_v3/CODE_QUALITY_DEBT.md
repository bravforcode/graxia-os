# Phase 18 - Code Quality and Debt Audit

Status: PARTIAL

## 18.1 Tooling

Finding: The project has Ruff, mypy, pytest, and coverage settings, but mypy is intentionally non-strict and untyped definitions are allowed.

Evidence:
- `pyproject.toml:11-19` configures Ruff lint and formatting.
- `pyproject.toml:21-31` configures mypy with `strict = false`, `disallow_untyped_defs = false`, and `check_untyped_defs = false`.
- `pyproject.toml:33-41` configures pytest test paths and markers.
- `pyproject.toml:43-48` configures coverage source and exclusions.

Verdict: PARTIAL. Tooling exists; type safety is not strict.

## 18.2 Silent Failure Risk

Finding: Several broker-facing helpers return `None` or suppress exceptions around MT5 calculations/checks. That can be acceptable at adapter boundaries only if callers fail closed; this audit did not prove every caller does.

Evidence:
- `broker/mt5_gateway.py:134-144` returns `None` from `calc_profit()` on any exception.
- `broker/mt5_gateway.py:147-154` returns `None` from `calc_margin()` on any exception.
- `broker/mt5_gateway.py:157-173` returns `None` from `check_order()` on missing result or any exception.
- `broker/mt5_gateway.py:201-207` swallows shutdown errors as best effort.

Verdict: PARTIAL. Adapter failure behavior is explicit, but downstream fail-closed proof remains required.

## 18.3 Safety Boundaries

Finding: The read-only MT5 gateway contains a self-check against order-sending functions.

Evidence:
- `broker/mt5_gateway.py:1-8` documents the module as read-only.
- `broker/mt5_gateway.py:210-221` asserts that `order_send`, `order_modify`, and `order_close` must not exist in the gateway.

Verdict: PASS for this module boundary. Not a whole-repo proof.

## 18.4 Debt Summary

Primary debt:
- Strict typing is not enforced.
- MT5 helper exceptions are collapsed to `None` in multiple places.
- Broad repo quality cannot be certified without a full lint/type/test pass.

Validation run during this audit:
- `python -m pytest tests/test_cost_unit_regression.py tests/test_lookahead_regression.py tests/test_feature_parity.py tests/test_label_shuffling.py -q --tb=short` passed: 19 tests.

