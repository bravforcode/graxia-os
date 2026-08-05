# MODULE_WIRING_AND_CAPABILITY_AUDIT.md — Phase 0.10–0.11

## 0.10 — Module Wiring & Orphaned-Feature Census

| Module/Class | Purpose | Called From (Live) | Called From (Backtest) | Tested? | Verdict |
|---|---|---|---|---|---|
| `validation/regime_detector.py::RegimeDetector` | Regime-aware filtering/sizing | `alpha/engine.py:425,444` (lazy load), `strategies/liquidity_sweep.py:53` | `backtest/engine.py:745` (optional), `run_paper_trading.py:491` | Yes (regime/test_detector.py) | **WIRED — confirmed on live and backtest path, tested** |
| `core/risk/swap_cost.py::get_live_swap_rates()` | Swap/overnight cost accounting | Not called from live execution path | `backtest/engine.py:1225` (via `_calculate_swap_cost`), but guarded by `_SWAP_COST_AVAILABLE` flag | Yes (test_swap_cost.py if present) | **PARTIALLY WIRED — backtest has optional wiring; live path never calls swap cost** |
| `governance/multi_broker_policy.py::BrokerRequirements` | Multi-broker governance | No call sites on live path | No call sites on backtest path | Yes (test only) | **ORPHANED — present but not wired in** |
| `BrokerManager._failover()` | Broker failover on outage | `execution/adapters/manager.py` — exists but zero configured secondary brokers | N/A | No real test with second broker | **ORPHANED — present but never successfully executed** |
| `DriftDetector` (ml/pipeline.py) | Automated retrain on drift | `scripts/auto_retrain.py` (cron script, not wired into live loop) | N/A | No | **ORPHANED — script exists but not called from live execution path** |
| `execution/broker_reconnector.py::BrokerReconnector` | Broker reconnection | `run_paper_trading.py:119-124` (paper trading bot only) | N/A | Partial | **WIRED — paper trading path only** |
| `monitoring/heartbeat.py::HeartbeatMonitor` | Heartbeat monitoring | `run_paper_trading.py:109`, `run_shadow.py:58` | N/A | Yes | **WIRED — paper/shadow paths** |
| `monitoring/dead_mans_switch.py::DeadMansSwitch` | Emergency close on stall | `run_paper_trading.py:106-107` | N/A | Yes | **WIRED — paper trading path** |
| `risk/market_session_guard.py` | Rollover/session filter | `core/trading_loop.py` (imported but unclear if enforced) | Not in backtest | No | **PARTIALLY WIRED — imported but enforcement unverified** |
| `core/rollover_filter.py::RolloverFilter` | Rollover dead zone filter | Not called from TradingLoop | Not called from backtest | No | **ORPHANED — present but not wired in** |
| `execution/swap_model.py` | Explicit swap model | Not called from live path | Not called from backtest path | No | **ORPHANED — present but not wired in** |
| `backtest/dynamic_spread_model.py` | Session-aware spread | `backtest/engine.py:908-912` (lazy import) | Yes | Yes | **WIRED — backtest path only** |
| `execution/ambiguous_bar_resolver.py` | Adverse-first SL/TP | `execution/execution_simulator.py` | Yes | Yes | **WIRED — backtest path** |
| `core/cross_validation.py::walk_forward_cpcv()` | CPCV with embargo | `validation/walk_forward.py` | Yes | Yes | **WIRED — validation pipeline** |
| `validation/overfitting_detector.py` | DSR, PBO, bootstrap | `backtest/engine.py:1385` (auto-run after backtest) | Yes | Yes | **WIRED — backtest auto-evaluation** |
| `execution/tca_framework.py` | Transaction cost analysis | Not called from live path | Not called from backtest path | No | **ORPHANED — present but not wired in** |
| `monitoring/metrics_exporter.py` | Prometheus metrics | `run_paper_trading.py:288` (paper only) | N/A | Partial | **WIRED — paper trading path only** |
| `core/telegram_callback.py` | Telegram callback handler | `api/main.py:66` (wired at startup) | N/A | Yes | **WIRED — live API path** |
| `core/risk_budget.py` | Daily/weekly risk budget | `api/health.py:172` (read-only endpoint) | N/A | No | **PARTIALLY WIRED — read-only, not enforced in TradingLoop** |

### R19 Violation Summary
**ORPHANED modules that would be false if cited as "handled":**
1. Multi-broker failover → counterparty risk is NOT diversified
2. Drift-triggered retraining → model decay is NOT automatically detected in live
3. Rollover filter → rollover risk is NOT filtered in live or backtest
4. Swap model → overnight cost is NOT modeled in live execution
5. TCA framework → transaction cost analysis is NOT wired into execution
6. Risk budget → daily/weekly risk limits are NOT enforced via risk_budget module (enforced elsewhere)

---

## 0.11 — Live-Order-Capability Ground-Truth Check

### `MT5BrokerAdapter.submit_order()` (execution/adapters/mt5.py:169-330)

**Does it call a real MT5 order-submission function?**
YES. Line 222: `result = mt5.order_send(request)` — this is the real MetaTrader5 Python API call that submits orders to the broker.

**Is there a mode flag gating this?**
NO. There is no paper/live/dry-run flag inside `submit_order()`. The method always calls `mt5.order_send()`. The gating happens at the *caller* level:
- `core/trading_loop.py:350-358`: checks `TradingMode.PAPER` → calls `PaperExecutor`, otherwise calls `_execute_live()` → `OMS.submit_order()` → `MT5Adapter.submit_order()`
- `core/config.py:154-155`: `TRADING_MODE` env var defaults to `PAPER`

**Could any currently-runnable command path result in a real order?**
YES — if `TRADING_MODE=LIVE_MICRO` (or LIVE_LIMITED/LIVE_CONTROLLED) is set AND `LIVE_TRADING_ENABLED=true` AND valid MT5 credentials are configured, then `api/main.py` lifespan creates `MT5Adapter` and `TradingLoop` will route orders through `OMS` → `MT5Adapter.submit_order()` → `mt5.order_send()`.

**`broker/mt5_gateway.py` vs `execution/adapters/mt5.py`:**
- `broker/mt5_gateway.py` is explicitly READ-ONLY (line 204: "This module must NEVER contain order_send"). Has safety assertion.
- `execution/adapters/mt5.py` is the LIVE-CAPABLE adapter with `submit_order()`, `close_position()`, `cancel_order()`.

### **VERDICT: CONFIRMED LIVE-CAPABLE — `MT5BrokerAdapter.submit_order()` can submit a real order under conditions: `TRADING_MODE` != PAPER, `LIVE_TRADING_ENABLED=true`, valid MT5 credentials.**

### **KNOWN_LIMITATIONS.md Resolution:**
`KNOWN_LIMITATIONS.md` line 1 states: "MT5 gateway is read-only stub — not tested live"

This is **PARTIALLY ACCURATE**:
- `broker/mt5_gateway.py` IS read-only — correct
- `execution/adapters/mt5.py` IS live-capable — **KNOWN_LIMITATIONS.md does not mention this file**
- The limitation doc refers to the gateway module, not the adapter. But the document is misleading because it implies the system cannot place orders, when in fact `execution/adapters/mt5.py` CAN.

**R20 Finding**: `KNOWN_LIMITATIONS.md` is currently **inaccurate** in its implication. It should either:
1. Clarify that `broker/mt5_gateway.py` is read-only but `execution/adapters/mt5.py` is live-capable, OR
2. State that the system is live-capable but has not been tested in live mode

**Severity**: P0 — this determines whether someone could unknowingly send real orders.

---

*Next: See DOC_CODE_CONTRADICTION_AUDIT.md for Phase 0.12–0.13*
