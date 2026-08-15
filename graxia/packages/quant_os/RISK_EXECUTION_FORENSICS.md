# RISK_EXECUTION_FORENSICS.md — Phase 9

## 9.1 — Position Sizing

- **Formula**: `risk/position_sizer.py:50-87` — `kelly_fraction()` and `FixedFractionalSizer.calculate()`
- **Max lot size**: Capped by `_apply_limits()` in `position_sizer.py:243-270` — applies max position size and max exposure limits
- **SYMBOL_VOLUME_MAX check**: NOT explicitly checked against MT5's `SYMBOL_VOLUME_MAX`. **P2 FINDING**.
- **SYMBOL_VOLUME_STEP check**: Rounding via `quantize(ROUND_DOWN)` to volume_step. **PASS**
- **Insufficient margin**: `risk/pre_trade_risk.py` checks margin level before submission. **PASS**

## 9.2 — Risk Limits & Kill Switches

| Risk Control | In Code | Tested | Active in Live |
|---|---|---|---|
| Maximum daily loss limit | `risk/risk_policy.py:14` + `risk/pre_trade_risk.py` | Yes | Yes |
| Maximum drawdown kill switch | `risk/kill_switch.py` (persistent JSON) | Yes | Yes |
| Maximum position size cap | `risk/position_sizer.py:243` | Yes | Yes |
| Maximum number of open positions | `backtest/engine.py:862`, `risk/pre_trade_risk.py` | Yes | Yes |
| Maximum consecutive losses | NOT IMPLEMENTED | N/A | N/A |
| Account balance floor | NOT IMPLEMENTED | N/A | N/A |
| Emergency close-all-positions | `risk/kill_switch.py:enforce()` with CLOSE_ALL mode | Yes | Yes |
| Manual override / pause switch | Telegram `/kill_all`, `/pause`, `/resume` commands | Yes | Yes |

### Kill Switch Persistence
- **Persisted**: `risk/kill_switch.py:60` — state stored in `data/kill_switch_state.json` via atomic write (temp file + rename)
- **Survives restart**: YES — `_load()` reads from JSON on init. Corrupted state defaults to ACTIVE (fail-closed). **PASS**
- **Cross-store sync**: `core/state_coordinator.py` syncs kill switch to 5 stores + EventBus. **PASS**

## 9.3 — MT5 Connection Resilience

- **Reconnect loop**: `execution/adapters/mt5.py:138-153` — 3 retries with exponential backoff (2s, 4s, 8s)
- **Alert on disconnect**: Logged via structlog. Telegram notification via `monitoring/telegram.py`. **PASS**
- **Requote handling**: `execution/adapters/mt5.py:277` — TRADE_RETCODE_INVALID_PRICE (10014) triggers retry with prior-fill check. **PASS**
- **Partial fills**: `execution/adapters/mt5.py:263-271` — detected and returned as PARTIALLY_FILLED. `core/trading_loop.py:420-438` handles partial fill branch. **PASS**
- **Timeout**: Returns TIMEOUT status after 3 retries exhausted. **PASS**
- **Duplicate order protection**: Comment field set to MD5 hash of order_id for idempotency. **PASS**

## 9.4 — Order Lifecycle Tracking

- **Magic Number**: NOT used for order identification. Comment field used instead. **P3 FINDING**.
- **Order states**: Tracked via `execution/order_state_machine.py` (PENDING → SUBMITTED → FILLED/REJECTED/CANCELLED)
- **Reconciliation**: `execution/reconciler.py::PositionReconciler` — runs in `core/orchestrator.py:300-345` during live sync loop. **PASS**

## 9.5 — Crash Recovery

- **Orphaned positions**: `core/orchestrator.py:300-345` reconciles internal state with MT5 actual positions on startup. **PASS**
- **Startup check**: Orchestrator reads MT5 positions via `broker/mt5_gateway.py::get_positions()`. **PASS**

### External Watchdog (Recommended, Not Yet Built)

- `monitoring/health_check.py:watchdog_loop` exists — monitors `data/heartbeat.txt` staleness:
  - 15 min stale → attempts local restart via `subprocess.Popen`
  - 30 min stale → triggers standby VPS failover
- `monitoring/dead_mans_switch.py` — in-process DMS (protects against stall, not crash)
- **NOT wired into main app lifespan** — must be run as a separate process (`python monitoring/health_check.py`)
- **In-process limitation**: If the Python process dies (OOM, segfault), the watchdog dies with it. A true external supervisor (systemd, PM2, Docker healthcheck) is needed for crash recovery.
- **Status**: RECOMMENDED — heartbeat file mechanism is implemented, but no production-grade external supervisor is configured.

## 9.6 — Latency

- **Expected latency**: Signal generation → order submission: ~1-5 seconds (Python processing). Not measured in code. **[LATENCY NOT MEASURED]**
- **For M15 system**: 5-10 seconds is acceptable. For M1 system: would be problematic. System currently trades M15 as primary timeframe. **PASS for current use case.**

## 9.7 — Broker-Specific Execution Quirks

- **Stop-out level**: NOT hardcoded in risk model. Uses MT5 account info. **PASS**
- **Swap triple-day**: `core/risk/swap_cost.py:44` — reads from MT5 `swap_rollover3days`. Default Wednesday. **PASS**
- **Account type**: Config assumes Pepperstone Razor (spread-only for metals, spread+commission for FX). **CONFIRMED** via `core/cost_model.py:46-66`.

## 9.8 — Per-Asset-Class Cost Model Audit

| Asset Class | Instruments | Broker Fee Structure | Code Assumed | Match? | Error Direction |
|---|---|---|---|---|---|
| FX majors | EURUSD etc. | Spread + $7/lot RT commission | `core/cost_model.py:63`: spread_bps=1.0, commission=$7 | **YES** | — |
| Metals | XAUUSD etc. | Spread-only (commission embedded) | `core/cost_model.py:53`: spread_bps=12.0, commission=$0 | **YES** in cost_model.py | — |
| Metals (backtest) | XAUUSD etc. | Same as above | `backtest/engine.py:206`: commission_per_lot=3.5 | **NO — DOUBLE-COUNT** | Understates edge |
| Crypto | BTCUSD etc. | Spread-only (commission embedded) | `core/cost_model.py:73`: spread_bps=5.0, commission=$0 | **YES** in cost_model.py | — |
| Indices | NAS100, US30 | Spread + commission (varies) | **NOT DEFINED** in cost_model.py | **UNVERIFIED** | Unknown |

## 9.9 — Swap/Overnight & Funding-Rate Model Wiring

- `core/risk/swap_cost.py` exists with `get_live_swap_rates()` and `get_swap_cost_for_trade()`
- `backtest/engine.py:1207-1240` — optional wiring via `_SWAP_COST_AVAILABLE` flag
- **Live path**: Swap cost is NOT calculated in live execution (`core/trading_loop.py` does not call swap cost). **P1 FINDING** — every backtested Sharpe/return figure for overnight-holding strategies is missing a real cost component in the live path.
- **Crypto funding rates**: `market_data/ccxt_feeder.py` has `fetch_funding_rate()` but is **ORPHANED** — not wired into execution.
- **Indices dividend adjustment**: NOT modeled. **[UNVERIFIED]**

## 9.10 — Ensemble-Level Risk Control Cross-Check

`alpha/engine.py:185-210`: Consensus SL/TP resolver computes median of strategy SL/TP values. If all strategies return None for SL/TP, the resolver returns (None, None).

`core/trading_loop.py:230-240`: Golden Rule check rejects signals with `stop_loss <= 0`. **PASS** — signal with SL=None is rejected before execution.

**BUT**: If `take_profit` is None while `stop_loss` is valid, the order is submitted without TP. This is acceptable (trailing stop or manual exit) but should be documented.

## 9.11 — Session-Hours & Trading-Calendar Handling

- `risk/market_session_guard.py` — session-aware blocking (Asian, London, NY, rollover)
- `core/rollover_filter.py` — rollover dead zone filter (**ORPHANED**)
- **FX/Metals**: Session hours enforced via `market_session_guard.py` (partially wired)
- **Crypto**: `market_session_guard.py:135-142` blocks crypto during rollover window — **INCORRECT** for crypto (24/7 market). **P1 FINDING** if wired.
- **Indices**: No specific session handling for index maintenance windows. **[UNVERIFIED]**

---

**P0 Findings**: 1 (metals commission double-count in backtest — from Phase 3)
**P1 Findings**: 3 (swap cost not in live path, crypto blocked during rollover if wired, drift detection orphaned)
**P2 Findings**: 1 (no SYMBOL_VOLUME_MAX check)
**P3 Findings**: 1 (no magic number for order identification)
