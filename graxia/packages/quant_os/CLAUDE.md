# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`quant_os` is a Python algorithmic-trading framework for research, backtesting, paper trading, and live
execution against MetaTrader 5 (Pepperstone). It is `graxia/packages/quant_os` inside the larger `graxia os`
monorepo and is imported as the `graxia.packages.quant_os` package (not `quant_os` directly).

Read `RUNBOOK.md` before operating the system (start/stop paper trading, emergency shutdown, env vars,
common failure modes) and `CONSTITUTION.md` + `SECURITY_BOUNDARIES.md` before touching risk/execution code
— they define invariants (INV-001–011) that tests enforce and that must never be violated in a change.
`KNOWN_LIMITATIONS.md` lists confirmed gaps (e.g. swap cost not modeled, tick-level fills pending) — treat
it as current truth, not aspirational.

## Working directory gotcha

This Makefile's targets and `RUNBOOK.md`'s commands assume **cwd = the monorepo root**
(`C:\Users\menum\graxia os`, one level above `graxia/`), because paths are written relative to it
(e.g. `graxia/packages/quant_os/tests/`). If your shell is already inside this `quant_os` directory,
those exact paths won't resolve — run pytest/ruff/mypy directly against local relative paths instead:

```bash
# From inside quant_os/ (this directory):
python -m pytest tests/ -q --tb=short              # full suite
python -m pytest tests/test_foo.py::test_name -q   # single test
python -m pytest tests/chaos/ -q --tb=short         # chaos suite
python -m ruff check .
python -m ruff format .
python -m mypy .

# From the monorepo root (as RUNBOOK.md / Makefile assume):
make -C graxia/packages/quant_os test
python graxia/packages/quant_os/run_paper_trading.py --duration 60
```

`conftest.py` inserts the monorepo root onto `sys.path` by walking 4 parents up from itself, so test
imports (`from graxia.packages.quant_os.core.config import ...`) resolve correctly regardless of which of
the two cwd conventions above you use — it's specifically the *Makefile's hardcoded relative paths* that
require the monorepo-root cwd.

## Commands

| Purpose | Command (run from this directory) |
|---|---|
| Full test suite | `python -m pytest tests/ -q --tb=short` |
| Single test | `python -m pytest tests/path/to/test_file.py::test_name -q` |
| Chaos suite | `python -m pytest tests/chaos/ -q --tb=short` |
| Lint | `python -m ruff check .` |
| Format | `python -m ruff format .` |
| Type check | `python -m mypy .` (strict/`disallow_untyped_defs` only for `risk.*`, `execution.*`, `core.*`) |
| Coverage | `python -m pytest tests/ --cov=. -q` |
| Backtest (synthetic) | `python run_backtest.py` |
| Backtest (real data) | `python run_backtest_real.py` |
| ML training | `python run_ml_train.py` (requires real historical data — will raise if none found) |
| Paper trading | `python run_paper_trading.py --duration 60` (`--duration 0` = run forever) |
| Scheduler (paper + periodic jobs) | `python run_scheduled.py` |
| Shadow mode (read-only dry-run vs live ticks) | `python run_shadow.py` |
| API server | `python api/main.py` (FastAPI, default port 8000) |
| DB migrations | `python -m alembic upgrade head` / `downgrade base` |

Tests require `.env` (copy from `.env.example`); minimum for paper trading is `MT5_LOGIN`, `MT5_PASSWORD`,
`MT5_SERVER`. `TRADING_MODE` defaults to `paper`; MT5 live order submission is gated separately by
`live_trading_enabled` in config (see below) — always check both before assuming a run is safe.

## Architecture — three parallel signal pipelines (important)

There are **three distinct, independently-wired paths** from "signal" to "order" in this codebase. They do
not call each other. When changing signal/risk/execution logic, first work out which pipeline the caller
is actually in — a fix applied to one does not propagate to the others.

1. **`strategies/ensemble.py`** — `StrategyEnsemble.get_ensemble_signal()` runs weighted voting over three
   strategies (`STRATEGY_WEIGHTS = {"mtm": 0.40, "mrb": 0.25, "mlb": 0.35}`). This is tested
   (`tests/test_ensemble_c3.py`, `tests/test_strategies.py`) and used by research/backtest scripts
   (`scripts/train_*`, `scripts/tsm_ensemble_backtest*.py`), but is **not called by `run_paper_trading.py`
   or `api/main.py`** — it is not in the live/paper critical path.
2. **`regime/` package** — this is what `run_paper_trading.py` actually runs, printed literally as
   `Regime Detector -> Liquidity Map -> Sweep Classifier -> Entry Executor -> Risk Overlay -> Monitor`:
   `RegimeDetector.detect()` → `LiquidityMap.build()` → `SweepClassifier.classify()` →
   `EntryExecutor.evaluate()` → `RiskOverlay.approve()` → `Monitor.report_order/report_fill` →
   `PaperBroker.place_order()`. Orders from this path carry `strategy_id="liquidity_sweep"`.
3. **`core/orchestrator.py`** (`TradingOrchestrator`) — wired by `api/main.py`'s FastAPI lifespan handler:
   `EventBus → PortfolioManagerAgent / RiskAuditorAgent → TradingLoop → OMS/PaperExecutor →
   PositionManager`. This is the path driven by the TradingView webhook (`api/webhook.py`,
   HMAC-SHA256-signed) and admin endpoints, and is also independent of both the ensemble and the
   `regime/` pipeline.

## Config and risk

- `core/config.py::QuantConfig` is the central config dataclass — `trading_mode: TradingMode` (default
  `PAPER`), `live_trading_enabled: bool = False`, and a nested `risk_policy: RiskPolicy`. Get/reset via
  `get_config()` / `reset_config()`, not by constructing `QuantConfig` directly in most call sites.
- `risk/risk_policy.py::RiskPolicy` is a **frozen** dataclass with all limits in basis points
  (`risk_per_trade_bps`, `max_daily_loss_bps`, etc.) — never percentage floats (INV-001/INV-002). Note
  `QuantConfig` also exposes legacy `*_pct` properties for backward compatibility; setting one of these
  directly on a config instance shadows the property with an instance attribute rather than mutating
  `risk_policy` — prefer setting `risk_policy` fields directly when writing new code.
- `risk/kill_switch.py` persists its tripped state to a JSON file so a process restart cannot silently
  clear it (INV-008). `canary/` has a *separate* kill switch (`emergency_kill_switch.py`) for the
  progressive live-micro rollout campaign — the two are not the same mechanism.
- **INV-003 ("no `order_send` in backtest or risk modules")** is enforced by a family of isolation/
  firewall tests, not a single linter: `shadow/test_runtime_firewall.py` monkeypatches
  `mt5.order_send`/`order_check`/`order_modify`/`history_deals_get` to raise, and asserts shadow-mode
  reader classes don't even expose those attributes. Related tests: `tests/test_backtest_isolation.py`,
  `tests/test_oracle_isolation.py`, `tests/test_canonical_runtime_import_isolation.py`,
  `events/test_event_isolation.py`. Any change touching `backtest/`, `shadow/`, or `risk/` that imports
  MT5 order-submission functions should expect one of these to fail.
- MT5 live order submission itself lives in `execution/adapters/mt5.py::MT5Adapter.submit_order()`. Per
  `KNOWN_LIMITATIONS.md`: the older `broker/mt5_gateway.py` is a deprecated read-only stub — do not assume
  the *system* is read-only because of it; `MT5Adapter` can place real orders when `live_trading_enabled`
  is true. Always verify current trading mode before relying on either assumption.
- Multi-broker support is real, not aspirational: `QuantConfig` has `primary_broker`/`fallback_broker_1`/
  `fallback_broker_2` fields, and `execution/adapters/manager.py::BrokerManager` implements failover;
  `governance/multi_broker_policy.py` governs promotion/rollout policy for it.

## Other cross-cutting systems worth knowing before you touch them

- **`canary/`** — a real progressive live-rollout system (`demo_canary_runner.py`, `micro_live_policy.py`,
  `protective_stop_verifier.py`, `weekly_report.py`, `demo_scorecard.py`), independent of paper trading.
- **`governance/`** — policy/gating modules (`ml_policy.py`, `expansion_policy.py`, `trial_budget.py`,
  `experiment_registry.py`) that gate promotion of new strategies/brokers rather than just documenting them.
- **`core/agents/llm_router.py`** — a tiered LLM cascade (Groq → Cerebras → OpenRouter → Gemini cron) for
  news/sentiment classification feeding a macro-regime cache. Explicitly documented as "no HTTP calls in
  the hot path" — it does not sit on the order-submission path.
- **`api/admin.py`** — `POST /admin/mode` enforces an explicit trading-mode state machine (e.g.
  `PAPER -> LIVE_MICRO` is valid, `PAPER -> LIVE_LIMITED` directly is not) and requires constant-time HMAC
  comparison against `config.admin_api_key`.

## Testing layout

`tests/` (~195 files) includes `tests/chaos/` (resilience/failure-injection, run via `make test-chaos`),
`tests/integration/`, `tests/unit/`, many `test_phase_N_*.py` phase-gated tests (development here is
phase-based per `CONTRIBUTING.md`/`STATUS.md` — check `STATUS.md` for the current phase and its verdict
before starting new work), and `*_isolation.py` firewall tests. Additional test files live outside
`tests/` next to the code they guard: `canary/test_*.py`, `shadow/test_*.py`, `regime/test_*.py`,
`events/test_event_isolation.py` — don't assume `tests/` is the only place coverage lives for a module.

## Conventions

- Conventional Commits with `feat/`, `fix/`, `security/`, `chore/` prefixes (see `CONTRIBUTING.md`).
- Every development phase must resolve to exactly one verdict: `PASS_TO_NEXT_PHASE` | `CONDITIONAL_PASS` |
  `NO_GO` | `ARCHIVE_NO_EDGE` | `INSUFFICIENT_SAMPLE` (`CONSTITUTION.md`). Don't declare a phase done
  without stating one of these.
- Never claim guaranteed profit/win-rate, treat a backtest result as live-trading evidence, or treat demo
  performance as proof of real-money profitability — these are constitutional rules, not style preferences.
