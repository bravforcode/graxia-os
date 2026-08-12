# Repository Guidelines

## Project Structure & Module Organization
`quant_os` is a Python package organized by trading-system concern. Core domain logic lives in `core/`, `execution/`, `risk/`, `validation/`, and `strategies/`. Runtime and external integration code lives in `api/`, `broker/`, `live_readiness/`, `market_data/`, `shadow/`, and `canary/`. Historical research and simulations live in `backtest/`, `oracle/`, `micro_live/`, and `expansion/`. Tests are split between top-level `tests/` and module-local `test_*.py` files. Evidence, compliance output, and release artifacts belong in `reports/`, `artifacts/`, and `shadow_results/`; treat these as auditable outputs, not scratch space.

## Build, Test, and Development Commands
Run commands from the monorepo root when paths are absolute to `graxia/packages/quant_os`.

- `python -m pytest graxia/packages/quant_os/tests/ --tb=short -q`
  Runs the main regression suite.
- `python -m pytest graxia/packages/quant_os/tests/test_phase_10_micro_live.py -q`
  Runs a focused phase test while iterating.
- `python scripts/run_release_gate.py`
  Executes the repo release gate and writes artifacts under `artifacts/release_gate/`.
- `python api/main.py`
  Starts the FastAPI surface for local API work using configured host/port values.

## Coding Style & Naming Conventions
Use 4-space indentation, type hints, and small focused modules. Follow existing snake_case for files, functions, and test names; use PascalCase for classes and dataclasses. Keep risk, execution, and dataset rules explicit and fail-closed. Prefer immutable or frozen policy objects when modifying governance-sensitive code. Place generated evidence in existing artifact/report directories rather than mixing it with source.

## Testing Guidelines
Pytest is the project standard. Name tests `test_<behavior>.py` and keep module-local tests near the code when they validate a specific subsystem; cross-cutting regressions belong in `tests/`. Preserve quarantine discipline: skipped tests must stay consistent with `quarantine_manifest.json`. Any change affecting strategies, risk, execution, or datasets should include targeted tests plus a full `tests/` run before merge.

## Commit & Pull Request Guidelines
Recent history uses Conventional Commits with scope, e.g. `feat(quant_os): ...` or `security(quant_os): ...`. Write commits in imperative mood and include the affected phase or subsystem when relevant. PRs should summarize behavior changes, list exact test commands run, and attach/report generated evidence when touching release gates, shadow runs, broker readiness, or compliance logic.

## Safety & Change Control
Do not overwrite locked experiment outputs. Changes to strategy logic, parameters, datasets, execution models, or risk policy require a change request recorded against the current phase. Keep `CONSTITUTION.md` invariants intact and never present backtest or demo results as live-profit proof.
