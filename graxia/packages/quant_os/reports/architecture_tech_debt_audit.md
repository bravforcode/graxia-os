# Architecture & Tech Debt Report — Graxia OS

**Audit Date:** 2026-07-03
**Auditor:** Ruflow Auditor Agent
**Scope:** `graxia/packages/quant_os`

---

## CRITICAL (Blocks progress)

### [DEBT-001] Duplicate `SignalValidationEvent` Definition
- **Files:** `core/events.py:88-99` AND `core/events.py:219-230`
- **Impact:** Two conflicting `SignalValidationEvent` dataclasses in the same file. The first (line 88) has `red_flags: tuple[str, ...]` and `tier_used: int`. The second (line 220) has `red_flags: list[str]` and `tier_used: str`. The second definition silently overwrites the first at import time. `signal_validator.py` uses the first definition's tuple type, but the second definition uses list — **type mismatch at runtime**.
- **Fix:** Delete the duplicate at lines 219-230. Keep one canonical definition.

### [DEBT-002] Circular Import Between `core/orchestrator.py` and `execution/`
- **Files:** `core/orchestrator.py:22-24` imports from `execution.adapters.base`, `execution.adapters.mt5`, `execution.oms`. `execution/manager.py` imports from `core.config`, `core.enums`, `core.exceptions`, `core.golden_rules`.
- **Impact:** `core/` imports `execution/` and `execution/` imports `core/`. This creates a fragile import ordering that breaks if either changes. The `try/except ImportError` around `SignalValidatorAgent` (line 40-43) is a symptom of this coupling.
- **Fix:** Extract interfaces to a shared `contracts/` module or use dependency injection.

### [DEBT-003] `api/webhook.py` Creates Tight Coupling Across All Layers
- **Files:** `api/webhook.py:35-41` imports from `core.config`, `core.enums`, `core.exceptions`, `data.models`, `execution.adapters.manager`, `execution.manager`, `risk.engine`
- **Impact:** Single API endpoint depends on 6 different modules across 4 layers. Any change in risk, execution, or data breaks the API. This is a "god import" pattern.
- **Fix:** Use dependency injection or a service layer to decouple API from domain logic.

---

## HIGH (Causes bugs or slowness)

### [DEBT-004] Inconsistent HTTP Client Usage
- **Files:**
  - `requests`: `core/telegram_notify.py`, `core/data/fred_client.py`, `monitoring/health_check.py`, 5+ scripts
  - `httpx`: `api/telegram_server.py`, `api/telegram_commands.py`, `core/agents/centaur_telegram.py`, `core/agents/llm_router.py`, 8+ modules
  - `aiohttp`: `core/multi_source_pipeline.py`, `monitoring/telegram.py`
- **Impact:** Three different HTTP clients with different async/sync APIs, error handling, and timeout behaviors. Increases dependency surface and makes consistent error handling impossible.
- **Fix:** Standardize on `httpx` (supports sync+async). Replace `requests` and `aiohttp`.

### [DEBT-005] Inconsistent Logging — `print()` vs `logging` vs `structlog`
- **Files:**
  - `print()`: `api/main.py` (12 print statements), `backtest/engine.py`, `core/holdout_validation.py`, `analysis/expectancy.py`, 10+ scripts
  - `logging`: `core/orchestrator.py`, `execution/oms.py`, `risk/engine.py`, 20+ modules
  - `structlog`: `core/agents/*.py`, `execution/quality_tracker.py`, `monitoring/alerting.py`, 30+ modules
- **Impact:** Three logging approaches means logs are inconsistent, hard to filter, and some go to stdout while others go to structured log sinks. Production debugging is painful.
- **Fix:** Standardize on `structlog` for all production code. Keep `print()` only in CLI scripts.

### [DEBT-006] Excessive Bare `except Exception` Clauses (100+ instances)
- **Files:** `live_readiness/mt5_readonly_client.py` (15 instances), `run_paper_trading.py` (9 instances), `data/quality_gate.py`, `strategies/*.py`, 30+ files
- **Impact:** Many catch-and-swallow patterns that hide real errors. Some log but continue, some silently pass. This makes debugging production issues extremely difficult.
- **Fix:** Audit each instance. Use specific exception types. Add structured logging with context.

### [DEBT-007] Heavy `type: ignore` Usage (70+ instances)
- **Files:** `execution/adapters/mt5.py` (18 instances), `execution/oms.py` (4 instances), `core/smc_detectors.py`, `scripts/tsm_ensemble_backtest.py`
- **Impact:** Type safety is effectively disabled for critical execution paths. The MT5 adapter has 18 `type: ignore` comments — the entire adapter is untyped.
- **Fix:** Add proper type stubs for `mt5` package. Fix OMS type issues. Remove `type: ignore` where possible.

### [DEBT-008] Module-Level Global State in `api/telegram_server.py`
- **Files:** `api/telegram_server.py:131-133` — `_callback_handler`, `_command_handler`, `_polling_loop` are module-level singletons
- **Impact:** Global mutable state makes testing impossible, creates race conditions in multi-worker deployments, and leaks state between test runs.
- **Fix:** Use FastAPI dependency injection or app.state instead of module globals.

---

## MEDIUM (Maintainability risk)

### [DEBT-009] Dead Code — Duplicate Modules
- **Files:**
  - `canary/micro_live_policy.py` AND `micro_live/micro_live_policy.py` — identical re-exports
  - `core/reconciler.py` AND `execution/reconciler.py` — two reconciler implementations
  - `execution/ledger.py` AND `execution/trade_ledger.py` — two ledger implementations
- **Impact:** Confusion about which module to use. Maintenance burden doubles.
- **Fix:** Consolidate to single implementations.

### [DEBT-010] Unused `__all__` Exports
- **Files:** `core/__init__.py` exports `GOLDEN_RULES` but most consumers import directly from `core.golden_rules`. `execution/__init__.py` is empty — no public API defined.
- **Impact:** `__all__` is defined but not enforced. Consumers bypass the public API.
- **Fix:** Either enforce `__all__` or remove it.

### [DEBT-011] Inconsistent Config Patterns
- **Files:**
  - `core/config.py`: `dataclass`-based config with `get_config()` singleton
  - `config/tv_config.py`, `config/tv_cdp_config.py`: Separate TOML-based configs
  - Environment variables: `api/telegram_server.py`, `api/telegram_commands.py` use `os.getenv()` directly
  - `pyproject.toml`: Project-level config
- **Impact:** Four different config patterns. No single source of truth for configuration.
- **Fix:** Centralize config in `core/config.py`. Use Pydantic Settings for env var binding.

### [DEBT-012] `api/telegram_commands.py` — `_edit_last_message` is a No-Op
- **Files:** `api/telegram_commands.py:479-487`
- **Impact:** The method says "Placeholder — in production, store and use message_id" but is called in production code paths (`kill:confirm`, `kill:cancel`). Kill switch confirmation message is never actually edited — user sees a new message instead.
- **Fix:** Track `last_message_id` per chat or remove the edit call.

### [DEBT-013] `api/telegram_commands.py` — `_cmd_status` Silently Swallows Errors
- **Files:** `api/telegram_commands.py:206-221`
- **Impact:** Two `except Exception: pass` blocks hide state store access errors. User sees "unknown" mode with no indication of why.
- **Fix:** Log the error and show diagnostic info to user.

### [DEBT-014] `execution/obsidian_export.py` — `_get_trade_by_id` Loads All Trades
- **Files:** `execution/obsidian_export.py:205-217`
- **Impact:** `self._ledger.get_trades()` loads ALL trades then iterates to find one by ID. O(n) for every single trade lookup. Will be slow with thousands of trades.
- **Fix:** Add `get_trade_by_id()` to ledger interface or use an index.

---

## LOW (Minor cleanup)

### [DEBT-015] `noqa` Suppressions for Pyarrow Workaround
- **Files:** `core/position_manager.py:33`, `core/data/point_in_time_store.py:11`, `core/data/fred_client.py:9`, `backtest/data_loader.py:263`
- **Impact:** Multiple `import pyarrow.parquet as _pq  # noqa: F401` scattered across codebase. This is a known pandas/pyarrow import ordering workaround.
- **Fix:** Centralize in one module or add to `conftest.py` (already partially done).

### [DEBT-016] `core/events.py` — `to_dict()` Uses `__dict__` on Frozen Dataclass
- **Files:** `core/events.py:35-38`
- **Impact:** `self.__dict__` on frozen dataclass works but is fragile. If a field has a non-serializable default (e.g., `uuid4()`), serialization will fail silently.
- **Fix:** Use `dataclasses.asdict()` with a custom serializer.

### [DEBT-017] Inconsistent Error Messages in Telegram Commands
- **Files:** `api/telegram_commands.py` — error messages use emoji (`⚠️`, `⛔`, `❓`) inconsistently
- **Impact:** Minor UX inconsistency. Some errors show raw exception, others show formatted message.
- **Fix:** Standardize error message format.

### [DEBT-018] `core/orchestrator.py` — Hardcoded MT5 Adapter
- **Files:** `core/orchestrator.py:63-69`
- **Impact:** Orchestrator directly instantiates `MT5Adapter`. Adding a new broker requires modifying orchestrator.
- **Fix:** Use `BrokerManager.from_config()` pattern (already exists in `execution/adapters/manager.py`).

---

## Dead Code Inventory

| Module | Status | Notes |
|--------|--------|-------|
| `canary/micro_live_policy.py` | Duplicate | Identical to `micro_live/micro_live_policy.py` |
| `execution/ledger.py` | Superseded | `execution/trade_ledger.py` is the active implementation |
| `core/reconciler.py` | Superseded | `execution/reconciler.py` is used |
| `shadow/shadow_pipeline.py` | Unused | `shadow/pipeline.py` is the active implementation |
| `monitoring/telegram.py` (TelegramAlerts) | Unused | `api/telegram_commands.py` replaces it |
| `run_scheduled.py` | Dead | No imports found outside of itself |
| `test_shadow.py` (root) | Dead | Superseded by `tests/test_phase_6_shadow.py` |
| `check_data_count.py` | Dead | One-off diagnostic script |
| `check_quality.py` | Dead | One-off diagnostic script |
| `download_d1.py` | Dead | One-off download script |
| `download_mt5.py` | Dead | One-off download script |
| `download_mt5_symbols.py` | Dead | One-off download script |
| `download_xauusd_multi_tf.py` | Dead | One-off download script |
| `verify_bootstrap.py` | Dead | One-off verification script |

---

## Inconsistency Map

### HTTP Clients
```
requests:    core/telegram_notify, core/data/fred_client, monitoring/health_check, 5 scripts
httpx:       api/telegram_server, api/telegram_commands, core/agents/centaur_telegram, 8 modules
aiohttp:     core/multi_source_pipeline, monitoring/telegram
```

### Logging
```
print():     api/main.py, backtest/engine, core/holdout_validation, 10+ scripts
logging:     core/orchestrator, execution/oms, risk/engine, 20+ modules
structlog:   core/agents/*, execution/quality_tracker, monitoring/alerting, 30+ modules
```

### Config Sources
```
dataclass:   core/config.py (QuantConfig, get_config)
toml:        config/tv_config.py, config/tv_cdp_config.py
env vars:    api/telegram_server.py, api/telegram_commands.py (os.getenv direct)
pyproject:   Project-level settings
```

### Error Handling
```
raise specific:     core/exceptions.py, execution/order.py
catch+log:          execution/oms.py, risk/engine.py
catch+pass:         live_readiness/mt5_readonly_client.py (15 instances)
catch+print:        scripts/*
bare except:        100+ instances across codebase
```

---

## New Module Review

### `core/agents/signal_validator.py` — GOOD
- Clean async agent pattern following existing `Agent` base class
- Proper timeout handling with `asyncio.wait_for`
- Deterministic fallback on LLM failure (never blocks pipeline)
- JSON parsing with regex fallback
- **Issues:** Accesses private `router._call_llm_chain()` (line 165) — should use public API

### `api/telegram_server.py` — GOOD with issues
- Clean FastAPI router pattern
- HMAC verification for webhooks
- Polling loop with exponential backoff
- **Issues:** Module-level global state (DEBT-008), `_verify_telegram_signature` receives empty body `b""` (line 205) — signature is never actually verified against body content

### `api/telegram_commands.py` — GOOD with issues
- Clean command registry pattern with decorator
- Authorization check on every command
- Kill switch requires inline keyboard confirmation (good safety)
- **Issues:** `_edit_last_message` is a no-op (DEBT-012), silent error swallowing (DEBT-013), `_cmd_resume` directly mutates state store without audit trail

### `execution/obsidian_export.py` — GOOD
- Clean dataclass-based export format
- Atomic writes with temp file + rename
- Proper error handling with logging
- **Issues:** `_get_trade_by_id` loads all trades (DEBT-014), `regime` field maps to `execution_quality` (line 234) — semantic mismatch

---

## Recommendations (Prioritized)

1. **[P0]** Fix duplicate `SignalValidationEvent` (DEBT-001) — will cause runtime type errors
2. **[P0]** Fix `api/webhook.py` god-imports (DEBT-003) — blocks safe refactoring
3. **[P1]** Standardize HTTP client on `httpx` (DEBT-004) — reduces dependency surface
4. **[P1]** Standardize logging on `structlog` (DEBT-005) — critical for production debugging
5. **[P1]** Audit and fix bare `except Exception` clauses (DEBT-006) — start with `live_readiness/` and `run_paper_trading.py`
6. **[P2]** Remove dead code inventory (14 modules) — reduces confusion
7. **[P2]** Consolidate duplicate modules (DEBT-009) — single source of truth
8. **[P2]** Fix module-level global state in telegram modules (DEBT-008)
9. **[P3]** Centralize config pattern (DEBT-011)
10. **[P3]** Add type stubs for `mt5` package (DEBT-007)

---

## Summary Statistics

| Category | Count |
|----------|-------|
| Critical issues | 3 |
| High issues | 5 |
| Medium issues | 6 |
| Low issues | 4 |
| Dead modules | 14 |
| `type: ignore` instances | 70+ |
| Bare `except Exception` | 100+ |
| `print()` in production | 50+ |
| HTTP client libraries | 3 |
| Logging frameworks | 3 |
