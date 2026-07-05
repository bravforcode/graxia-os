# MODULE WIRING AND CAPABILITY AUDIT
**Phase 0.10–0.11 | 2026-07-05**

---

## 0.10 — Module Wiring & Orphaned-Feature Census

| Module/Class | Purpose | Called From (Live) | Called From (Backtest) | Tested? | Verdict |
|---|---|---|---|---|---|
| `core/risk/swap_cost.py` | Swap/overnight cost | **NONE** | **NONE** | Unit test only | **ORPHANED** |
| `core/regime_detector.py` | Regime-aware filtering | Not confirmed | `backtest/engine.py:58` (import, wired to `_get_regime_state()`) | Yes | **PARTIALLY WIRED** — backtest only |
| `governance/multi_broker_policy.py` | Multi-broker governance | Not confirmed | Not confirmed | Test file exists | **ORPHANED** |
| `BrokerManager._failover()` | Broker failover | `execution/broker_adapter.py:585` | N/A | No test with mock broker | **ORPHANED** — no configured secondary broker |
| `DriftDetector` retrain trigger | Automated retrain on drift | Not confirmed | Not confirmed | Not confirmed | **ORPHANED** |
| `execution/adapters/mt5.py:MT5Adapter` | Live MT5 order execution | `core/orchestrator.py:23`, `tsm_paper_trade.py:57` | N/A | Yes (`test_broker_adapters_unified.py`) | **WIRED — live path, tested** |
| `broker/mt5_gateway.py` | Read-only MT5 data access | `live_readiness/` modules | N/A | Yes | **WIRED — read-only data path** |
| `strategies/ensemble.py:StrategyEnsemble` | Multi-strategy combiner | `core/orchestrator.py` (via trading loop) | Not confirmed | Yes (unit tests) | **WIRED — but _consensus_levels() is no-op** |

### Key Finding (R19)
`swap_cost.py` is a confirmed orphan. It computes swap costs correctly but is never called from any execution or backtest path. Every overnight-holding strategy's backtested Sharpe/return figure is **missing a real cost component**.

---

## 0.11 — Live-Order-Capability Ground-Truth Check (R20)

### The Question
Can this system, as currently deployed, send a real order to a real account?

### The Evidence

**Path 1 (Canonical — LIVE-CAPABLE):**
- `core/orchestrator.py:23` imports `MT5Adapter` from `execution.adapters.mt5`
- `core/orchestrator.py:55-60`: if `config.live_trading_enabled` is True, creates `MT5Adapter` with real credentials
- `execution/adapters/mt5.py:195-225`: `MT5Adapter.submit_order()` calls `mt5.order_send(request)` with `TRADE_ACTION_DEAL`
- This is a real order submission path. No paper/live mode flag gates it — the flag is `live_trading_enabled` at the orchestrator level.

**Path 2 (Deprecated — also LIVE-CAPABLE):**
- `execution/broker_adapter.py:395-440`: `MT5BrokerAdapter.place_order()` also calls `self.mt5.order_send(request)`
- Same real order submission, different interface (async vs sync)

**Path 3 (Read-Only — SAFE):**
- `broker/mt5_gateway.py`: Has `_verify_readonly()` assertion at module level. Cannot send orders. This is what KNOWN_LIMITATIONS.md describes.

### The Resolution

> **CONFIRMED LIVE-CAPABLE** — `MT5Adapter.submit_order()` can submit a real order when:
> 1. MT5 terminal is running and connected
> 2. `config.live_trading_enabled = True`
> 3. Valid MT5 credentials are configured
>
> KNOWN_LIMITATIONS.md is **currently inaccurate** and must be corrected. The "read-only stub" claim applies only to the deprecated `broker/mt5_gateway.py` module, NOT to the canonical `execution/adapters/mt5.py` adapter.

### Could a Real Order Be Submitted Accidentally?
- `core/config.py` controls `live_trading_enabled` — default value must be checked
- If default is `False`, accidental live orders are unlikely but not impossible (config file could be edited)
- The `tsm_paper_trade.py:57` import suggests paper trading also uses MT5Adapter — need to confirm if paper mode uses a demo account or has order submission disabled at a different level
