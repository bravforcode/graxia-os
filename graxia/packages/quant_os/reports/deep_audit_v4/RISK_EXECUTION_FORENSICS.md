# PHASE 9 — RISK & EXECUTION FORENSICS
**Quant OS Deep Audit v4.0 | Date: 2026-07-05 | Auditor: auditor agent**

---

## 9.1 Position Sizing

### Formula
- **FixedFractionalSizer** (`risk/position_sizer.py:255-305`): `units = risk_amount / price_risk` where `risk_amount = equity × risk_pct / 100`. Lots = units / contract_size, rounded DOWN to 0.01 (`position_sizer.py:284`).
- **PositionSizerV2** (`risk/position_sizer_v2.py:23-220`): Uses MT5-native `order_calc_profit()` then `risk_budget / one_lot_loss` → rounded DOWN to `volume_step`.

### Max Lot Size — CRITICAL GAP
- **position_sizer.py**: `_apply_limits()` (line 212-240) checks `max_position_size` from config and `max_portfolio_exposure_pct`. Does **NOT** check against MT5 `SYMBOL_VOLUME_MAX`. If config limits are unset (`float("inf")`), no ceiling.
- **position_sizer_v2.py**: Checks `volume_min` (line 162) and `volume_step` (line 143), but **does NOT check `volume_max`**. Line 143-155 rounds DOWN to volume_step, and line 162 rejects if below volume_min. **No volume_max ceiling check anywhere.**
- **Severity**: MEDIUM — a bug in config or oversized risk_pct could produce a lot size exceeding broker maximum, causing MT5 rejection at order_send time rather than being caught pre-trade.

### Insufficient Margin Check
- **position_sizer_v2.py**: Line 201-203: `# Full margin check would compare margin to available margin from account info. ponytail: defer full margin check to pre_trade_risk — that's where equity lives.` — Margin is calculated (line 192-199) but never validated against available margin. **Deferred but never completed.**
- **pre_trade_risk.py**: Line 85-87 checks `margin_level_pct < min_margin_level_pct` but this is post-hoc (checking current margin level, not projected post-trade margin).
- **RiskPolicy** (`risk/risk_policy.py:19`): `reject_if_margin_level_below_pct: int = 500` — 500% margin level floor (conservative). But no projected-margin check before order.

---

## 9.2 Risk Limits & Kill Switches

| Risk Control | In Code (file:line) | Tested | Active in Live |
|---|---|---|---|
| Max daily loss limit | `risk/pre_trade_risk.py:58-62` | Unit tested | ✅ RiskLedger persisted to disk |
| Max drawdown kill switch | `risk/auto_stop.py:153` (15% threshold) | Unit tested | ✅ Persists via `data/auto_stop_state.json` |
| Max position size cap | `risk/position_sizer.py:221` (config-based) | Partially | ⚠️ No volume_max check |
| Max number of open positions | `risk/pre_trade_risk.py:77-78` (max_positions=5) | Unit tested | ✅ RiskLedger persisted |
| Max consecutive losses | `risk/circuit_breaker.py:140` (3 losses default) | Unit tested | ✅ Persists via `data/circuit_breaker_state.json` |
| Account balance floor | **NOT FOUND** | N/A | ❌ No balance floor check anywhere |
| Emergency close-all | `risk/kill_switch.py:182-257` (`enforce()` + `/kill_all`) | Unit tested | ✅ Telegram command + enforce on activated |
| Manual override/pause | `risk/kill_switch.py:103-116` (`/pause`, `/resume`) | Unit tested | ✅ Telegram commands |

### Kill Switch Persistence Across Restart — ✅ PASS
- `kill_switch.py:387-411`: Atomic write via tempfile + os.replace. State survives restart.
- **Current state** (`data/kill_switch_state.json`): `state: "INACTIVE"`, reason "Ready for paper trading - 7 day test". History shows heavy unit test churn but current state is clean.
- `kill_switch.py:317-322`: `_get_state_enum()` — corrupted state defaults to ACTIVE (fail-closed). ✅
- `auto_stop.py`: Persists via `data/auto_stop_state.json`. 15% DD threshold. Manual reset only. ✅
- `circuit_breaker.py`: Persists via state file. Corrupted/empty file → fail-closed (all tripped). ✅

---

## 9.3 MT5 Connection Resilience

### Architecture
- **mt5_gateway.py**: `broker/mt5_gateway.py` — READ-ONLY. No reconnect loop. Lazy-import `MetaTrader5`.
- **broker_reconnector.py**: `execution/broker_reconnector.py` — Full reconnect framework BUT ***designed for IB TWS*** (lines 10-14, 39, 191-221 reference IB-specific pacing rules). MT5 adapter does NOT wire into this reconnector.
- **execution/adapters/mt5.py**: Needs review for actual reconnect logic.

### Critical Gaps
| Feature | Status | Detail |
|---|---|---|
| Disconnect detection | ⚠️ | `broker_reconnector.py:125-141` — heartbeat timeout 90s. But not wired to MT5. |
| Reconnect loop | ⚠️ | `broker_reconnector.py:143-177` — exponential backoff, max 5 attempts. For IB only. |
| Retry / backoff | ✅ | 5s base × 2.0^n, cap at 60s (`broker_reconnector.py:161-163`) |
| Alerting on disconnect | ❌ | No SMS/Telegram alert on disconnect event |
| Weekend gap handling | ❌ | No explicit weekend gap detection or position flattening |
| Requote handling | ❌ | No requote/retry logic in order flow |
| Partial fill handling | ⚠️ | OrderStateMachine supports PARTIAL_FILL state (`order_state_machine.py:34-36`), but MT5 adapter partial-fill behavior unconfirmed |
| Timeout | ⚠️ | `broker_reconnector.py:37` — heartbeat_timeout_sec=90s |
| Duplicate order protection | ✅ | `execution/idempotency.py:38-76` — sha256 of (symbol:side:qty:strategy:signal:time-bucket-60s) |

---

## 9.4 Order Lifecycle Tracking

### State Machine
- `execution/order_state_machine.py`: 16 states with enforced transitions (line 9-96).
- Terminal states: REJECTED, EXPIRED, AUDITED, CRITICAL_INCIDENT.
- After FILLED: must go through PROTECTIVE_STOPS_PENDING → VERIFIED → POSITION_RECONCILED → CLOSED → DEAL_RECONCILED → AUDITED.

### Magic Number — ❌ NOT FOUND
- No MT5 `magic_number` used for strategy identification. MT5 `ORDER_TYPE_BUY`/`SELL` constants used for order type but no magic number to distinguish from manual/other-EA orders.
- `order.py:33-37`: strategy_id and signal_id stored in Order object but not transmitted as MT5 magic number.

### Lost Acknowledgment Handling
- `execution/manager.py:292-340`: `_submit_to_broker()` — after broker submission, transitions to ACKNOWLEDGED (not FILLED). If ack lost, order remains in SENT_TO_BROKER state.
- `execution/recovery.py:261-322`: `_resolve_orphaned_orders()` — on startup, queries broker for orders with uncertain state. But relies on `broker_position_id` being set, which depends on successful broker acknowledgment.

### Startup Reconciliation
- `execution/recovery.py:127-259`: `on_startup()` performs:
  1. Reconcile all venues
  2. Resolve orphaned orders
  3. Check drawdown (15% limit)
  4. Check daily loss (2% limit)
  5. Check for broker-only (unknown) positions
  - Returns verdict: RESUME / HALT / DEGRADED

---

## 9.5 Crash Recovery

### Crash With Open Position
- **recovery.py:127-259**: On restart, runs `reconciler.reconcile_all_venues()` to compare internal ledger vs broker positions.
- **recovery.py:261-322**: `_resolve_orphaned_orders()` — for local-only positions, queries broker order status. If filled at broker but not locally: confirms fill. If canceled/expired at broker: closes local position.
- **recovery.py:293**: Positions local-only with no broker_position_id → `MARKED_ERROR` (unresolved).
- **Ledger** (`execution/ledger.py`): SQLite backend. WAL mode. Survives restart.

### Startup Check for Orphaned Positions
- ✅ recovery.py:212-225 checks for broker-only positions (positions at broker not in local ledger).
- ✅ recovery.py:167-179 resolves orphaned orders per-venue.
- ⚠️ Gap: No check for POSITIONS THAT WERE OPEN AT CRASH but disappeared from broker (e.g., stopped out during downtime). The reconciliation cycle might miss this if the position was closed before restart.

---

## 9.6 Latency

### Expected Latency — NO MEASUREMENT INFRASTRUCTURE
- `execution/order_latency.py` exists per directory listing but contents not analyzed in this audit.
- `risk/pre_trade_gate.py:19`: `reject_if_data_stale_seconds=5` — 5-second data staleness threshold.
- For 1-min trading system: bar close → signal generation → risk checks → order submission. No latency budget defined or benchmarked.

---

## 9.7 Broker-Specific Execution Quirks

### Pepperstone Profile
- `core/cost_model.py:50-58` (METALS): Pepperstone Razor — commission embedded in spread, `commission_per_lot=0.0`. Spread 12 bps typical.
- `core/cost_model.py:60-67` (FOREX): $7/lot round-trip commission, 1 bps spread.
- `core/cost_model.py:69-76` (CRYPTO): Commission embedded in spread, 5 bps spread, 2 bps slippage.
- **Stop-out level, margin call level**: NOT hardcoded. Relies on MT5 `account_info()` at runtime.
- **Swap triple-day**: `execution/swap_model.py:23` — `rollover_day: int = 3` (Wednesday for FX/metals). Crypto uses funding rate (not swap), modeled at `swap_long_bps=-10.0`, `swap_short_bps=-5.0`.
- **Account type**: MT5 `account_info().server` used to infer broker (`broker/mt5_gateway.py:80`).

---

## 9.8 Per-Asset-Class Cost Model Audit (R22)

### Broker (Pepperstone Razor) vs Code Assumption

| Asset Class | Broker Actual | Code (core/cost_model.py) | Match? |
|---|---|---|---|
| FX Majors | Raw spread + $3.50/lot/side commission | FOREX: 1 bps spread, $7/lot round-trip (line 63) | ✅ $3.50×2 = $7 round-trip |
| Metals (XAUUSD) | Commission embedded in spread | METALS: 12 bps spread, commission=0 (line 54) | ✅ Bug #2 fixed |
| Crypto (BTC/ETH) | Spread-based (no separate commission) | CRYPTO: 5 bps spread, commission=0 (line 72) | ✅ |
| Indices (US30, NAS100, SPX500) | CFD spread + possibly swap | **NOT IN `_SYMBOL_TO_PARAMS`** (line 89-107) | ❌ Falls back to METALS params |

### Critical Finding — R22 Violation
- **`core/cost_model.py:119`**: `return _SYMBOL_TO_PARAMS.get(symbol.upper(), METALS)` — Unknown symbols default to METALS cost parameters. Indices (US30, NAS100, SPX500, GER40, UK100, JP225) have NO cost params and will silently use metals spreads/commission. This is WRONG: indices have different spread structures, possible commissions, and dividend/futures-roll costs that differ completely from metals.

---

## 9.9 Swap/Overnight & Funding-Rate Wiring

### Swap Model Status
- `execution/swap_model.py`: Standalone swap calculation module. Has `SwapMode.NONE|FIXED|HISTORICAL`.
- `execution/swap_model.py:36-75`: `calculate_swap()` — daily rate × volume × effective days (Wed × 3 for triple swap).
- **Wiring to backtest path**: ❌ NOT WIRED. Grep for `calculate_swap` or `SwapPolicy` in backtest engine — no import found.
- **Wiring to live path**: ❌ No wiring in `execution/manager.py` or `execution/adapters/mt5.py` order flow.

### Per-Asset-Class Swap
| Asset Class | Swap Modeled? | Detail |
|---|---|---|
| FX | ⚠️ | `swap_long_bps=-0.1, swap_short_bps=-0.1` (FOREX cost_params). Triple-swap Wednesday = rollover_day=3. |
| Metals | ⚠️ | `swap_long_bps=-0.5, swap_short_bps=0.2` (METALS). Triple-swap Wednesday. |
| Crypto | ⚠️ | `swap_long_bps=-10.0, swap_short_bps=-5.0` (CRYPTO) — high funding cost. But crypto has funding rate every 8h, not daily swap. |
| Indices | ❌ | No swap data at all (not in cost_params map) |

---

## 9.10 Ensemble-Level Risk Control Cross-Check

### SL=None / TP=None from Ensemble
- **`strategies/ensemble.py:296-316`**: When ensemble generates a signal, it calls `_consensus_levels()` (line 302) for SL/TP.
- **`strategies/ensemble.py:425-459`**: `_consensus_levels()` filters votes with SL/TP set. If NO sub-strategy provides SL or TP, returns `(None, None)`.
- **RiskPolicy** (`risk/risk_policy.py:23`): `require_stop_loss: bool = True` — BUT this is a policy declaration, not enforced in the order-manager flow for ensemble-generated orders.
- **`execution/manager.py:103-113`**: `create_order()` accepts `stop_price` and `take_profit` as optional. If `None`, the Order is created without SL. The risk engine receives this order, but `pre_trade_risk.py` does NOT check for SL requirement (it only checks sizing result, kill switch, circuit breaker, daily/weekly/drawdown limits, position count, order rate, margin).
- **pre_trade_gate.py**: Kill switch + circuit breaker + price sanity. NO stop-loss requirement check.
- **Result**: If ensemble emits signal with SL=None, order goes through with NO stop-loss.

---

## 9.11 Session-Hours Per Asset Class

- **`risk/market_session_guard.py:34-45`**: Hardcoded session hours (not pulled from MT5):
  - Metals: 01:00–21:55 UTC (nearly 24h via Comex+spot)
  - Forex: 01:00–21:55 UTC
  - Crypto: 24/7 (rollover window 21:55–22:16 blocked for all)
  - Indices: 13:00–21:00 UTC (US indices via CFD)
- **Daily break**: Metals have a 1-hour break at 21:55–01:00 (Comex daily settlement). Modeled as closed during this window.
- **Weekend**: Sunday 22:00 UTC open to Friday 22:00 UTC close. Modeled via session bounds.
- **Accuracy**: Static hardcoded sessions. MT5 `symbol_info().session_deals`/`session_trade` NOT consulted for dynamic session hours. Anomalous holiday hours would NOT be detected if MT5 trade_mode check fails.

---

## TOP FINDINGS — Phase 9

| # | Severity | Finding |
|---|---|---|
| 1 | P0 | **No volume_max check**: Position sizers never cap lots at broker's volume_max. Config-dependent max only. |
| 2 | P0 | **No projected margin check**: Sizer defers to pre_trade_risk, but pre_trade_risk only checks current margin level. |
| 3 | P0 | **Indices cost model missing**: US30/NAS100/SPX500/GER40 default to metals cost params silently. |
| 4 | P0 | **SL/TP=None from ensemble passes risk gate**: `require_stop_loss=True` in RiskPolicy is declarative only, not enforced. |
| 5 | P0 | **Swap model not wired**: `swap_model.py` is standalone. Backtest and live paths ignore overnight costs. |
| 6 | HIGH | Broker reconnector designed for IB TWS, not MT5. MT5 reconnect path unclear. |
| 7 | HIGH | No account balance floor check anywhere. |
| 8 | MEDIUM | Session hours are hardcoded, not pulled from MT5 dynamic data. |
| 9 | MEDIUM | No magic number for strategy identification in MT5 orders. |
