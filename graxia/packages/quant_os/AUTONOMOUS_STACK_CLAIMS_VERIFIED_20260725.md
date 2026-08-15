# "Autonomous Stack" Report — Verified, Not Accepted As-Is (2026-07-25)

A separately-sourced report claimed `autonomous/orchestrator.py` + `execution/adapters/*` + `risk/engine.py` form a "production-ready," "live-capable" execution path. The files exist. Most specific behavioral claims do not survive verification. **This stack is not wired to any runnable entrypoint — it is unused code with two test-only callers, not a production system.**

## Per-claim verdicts

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | Orchestrator wires ChartMonitor→DecisionEngine→OrderExecutor | CONFIRMED wiring exists, but **the class is currently broken** — `__init__` has a typo (`self._ymbols` vs `self._symbols`) that raises `AttributeError` on default construction |
| 2 | OrderExecutor calls real broker dispatch | CONFIRMED call is real, but **default mode is `paper`, not live** (`AUTO_TRADING_MODE` env var) |
| 3 | MT5Adapter does real `order_send` | CONFIRMED — genuinely real MT5 integration, not a stub. But no graceful degradation: every method dereferences `mt5.` directly with no None-guard once past `connect()`, so it's functionally inert without a real MT5 terminal |
| 4 | `live_trading_enabled` switch gates live dispatch | **MISLEADING** — this switch is real and well-guarded, but it belongs to a *different* code path (`BrokerManager.from_config()`, used by `api/main.py`/`api/webhook.py`). The orchestrator under review never calls `from_config()` — it has its own separate, less-guarded `TradingMode.LIVE_MICRO` check instead |
| 5 | mt5_gateway.py is read-only, adapters/mt5.py is separate | CONFIRMED, and the split is intentional (comment explains it exists to stop scripts bypassing orchestrator/KillSwitch safety) |
| 6 | 4-layer risk gate, each failure blocks | CONFIRMED — real hard-reject logic, not just logging |
| 7 | Circuit breaker wired | CONFIRMED wired, but instantiated with no persistence (`state_file`) and no link to KillSwitch — a trip here doesn't cascade |
| 8 | Position sizer (Kelly/fixed-fractional) wired into executor | **FALSE** — `risk/position_sizer.py` is imported only by test files. The executor uses its own separate hand-rolled sizing logic. Dead code from the live path's perspective |
| 9 | Daily loss limit active | **OVERSTATED** — the check runs and would reject on breach, but the PnL value it checks (`_daily_realized_pnl`) is never written anywhere except a midnight reset to 0. It can never actually trigger |
| 10 | Kelly sizer wired (backtest path) | CONFIRMED, and confirmed backtest-only as the original claim itself stated — zero references from `autonomous/` or `execution/adapters/` |
| 11 | `TradingMode.LIVE_MICRO` exists with micro-specific behavior | **OVERSTATED** — the enum exists and picks the broker adapter, but `OrderExecutor.execute` treats it identically to any other live mode (no reduced size cap). Bonus bug: `LIVE_LIMITED`/`LIVE_CONTROLLED` modes silently fall through to the paper adapter instead of erroring |

## The one finding that matters most

**`AutonomousOrchestrator` is referenced only by its own file and two test files** (`tests/test_autonomous_chaos.py`, `tests/test_autonomous_chaos_extended.py`). `docker-compose.yml`'s five real services (`graxia-api`, `graxia-trainer`, `graxia-signal`, `graxia-executor`, `graxia-mt5`) do not import it. The system that actually deploys is a **different, third stack**: an XGBoost signal service + paper executor + a Wine/MQL5 EA (`GRAXIA_EA.mq5`) + a FastAPI webhook layer using `BrokerManager.from_config()`.

That means this codebase currently has **at least three distinct, partially-overlapping execution architectures**:
1. The legacy path audited earlier this session (`execution/manager.py`, `risk/position_sizer_v2.py`, `risk/kill_switch.py`) — real, has known open bugs (no stop-loss retry, placeholder margin check).
2. The `autonomous/` stack this report is about — real, reasonably well-built safety logic, **but dead code, unreferenced by anything that runs.**
3. The actually-deployed stack (`api/main.py`, `api/webhook.py`, MQL5 EA, `BrokerManager.from_config()`) — not yet audited this session.

**Architectural sprawl across three parallel execution stacks is itself a readiness risk**, independent of any single bug: it's easy to audit or fix the wrong one, and easy for a future change to wire the wrong stack into production by accident. This should be resolved (pick one, delete or clearly mark the others as dead) before any live-trading decision, not just have its bugs patched in isolation.

**Bottom line on the pasted report: reject the "production-ready" framing.** The code quality of the `autonomous/` stack itself is genuinely decent, but "exists and is well-written" is not "production-ready" when nothing invokes it. The strategy-edge portion of that report (12/13 hypotheses REJECTED, 1 INSUFFICIENT_DATA) is consistent with this session's independently-verified findings and can be trusted.
