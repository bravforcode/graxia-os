# Trading Logic & Risk Audit Report — Graxia OS

**Auditor:** Ruflow Auditor Agent
**Date:** 2026-07-03
**Scope:** Full trading logic, risk controls, execution, backtest parity, data integrity, AI validator, constitutional compliance
**Methodology:** Static code audit of all critical trading paths

---

## CRITICAL (Could cause financial loss)

### [RISK-001] Circuit breaker state file race condition — no atomic write
**File:** `risk/circuit_breaker.py:181-188`
**Scenario:** `_save()` uses `write_text()` which is non-atomic. If the process crashes mid-write, the state file becomes corrupted JSON. On next load, `_load()` catches `JSONDecodeError` and silently ignores it (`pass` at line 199-200), meaning the circuit breaker resets to defaults (all zeros, open=False). A circuit breaker that was tripped due to consecutive losses would silently reset, allowing further trading during a drawdown.
**Impact:** A crash during a losing streak could disable circuit breaker protection, allowing the system to continue hemorrhaging.
**Fix:** Write to a temp file, then `os.replace()` (atomic on POSIX). Add explicit error logging instead of bare `pass`.

### [RISK-002] Kill switch `enforce()` blocks on position close — no timeout
**File:** `risk/kill_switch.py:161-236`
**Scenario:** `enforce()` iterates positions and calls `broker_adapter.close_position()` synchronously. If the broker adapter hangs (network timeout, MT5 freeze), the kill switch enforcement blocks indefinitely. The kill switch state is set to ACTIVE before `enforce()` is called (line 313-314), so the system IS blocked from new orders, but existing positions remain open during the hang.
**Impact:** During a flash crash, positions that should be closed immediately could remain open for minutes while the adapter hangs.
**Fix:** Wrap each `close_position()` call in a thread with timeout (e.g., 10s). If timeout, log and move to next position.

### [RISK-003] OMS `submit_order` persists to ledger AFTER risk check but BEFORE broker call — gap window
**File:** `execution/oms.py:327-346`
**Scenario:** The order is added to `self._orders` dict (line 328) before the risk check (line 339), but the ledger is NOT written until `_update_ledger()` at line 348 (only on rejection). If the process crashes between lines 328 and 446 (broker submission), the order exists in memory but NOT in the ledger. On restart, `_load_ledger()` won't find it, and the same signal could be resubmitted — violating idempotency.
**Impact:** Duplicate orders after crash recovery. A signal that was partially processed could be re-submitted to the broker.
**Fix:** Call `_update_ledger(order)` immediately after creating the Order object (line 328), BEFORE the risk check.

### [RISK-004] Risk engine crash = no risk check, order proceeds
**File:** `execution/oms.py:338-363`
**Scenario:** If `self._risk_engine.check_order_sync(order)` raises an exception (line 355), the order is correctly rejected. However, if `risk_engine` is `None` (line 339 check), the order BYPASSES the risk gate entirely. The constructor allows `risk_engine=None` if not explicitly set (line 111: `risk_engine: Any = ...`), and the `...` sentinel is only caught at line 116-119. But if someone passes `None` explicitly, risk is skipped.
**Impact:** If the risk engine reference becomes None (e.g., initialization error, import failure), all orders bypass risk checks.
**Fix:** Make `risk_engine` a required non-None parameter. Add a runtime assertion that `self._risk_engine is not None` before each check.

### [RISK-005] `pre_trade_risk.py` uses `>=` for loss limits — off-by-one allows exact-limit trades
**File:** `risk/pre_trade_risk.py:60-71`
**Scenario:** The daily/weekly/drawdown checks use `>=` (greater-than-or-equal). If `daily_loss == max_daily`, the check triggers. However, the check uses `Decimal` comparison, and the `risk_ledger.daily_realized_loss` is a float (line 41: `Decimal(str(risk_ledger.daily_realized_loss))`). Float-to-Decimal conversion can introduce rounding errors. A loss of exactly 0.50% could be represented as 0.4999999... after float conversion, passing the check.
**Impact:** The system could trade when at exactly the daily loss limit.
**Fix:** Use `Decimal` throughout the risk ledger, or add a small epsilon buffer to the threshold.

### [RISK-006] Signal ID collision — 16-char hex from truncated SHA-256
**File:** `core/signal_gateway.py:73-76`
**Scenario:** `signal_id` is derived from `sha256(f"{symbol}:{side}:{strategy}:{timestamp_min}")[:16]`. The timestamp is truncated to minute precision (`%Y%m%d%H%M`). Two signals for the same symbol/side/strategy within the same minute will have identical signal IDs, causing deduplication. More critically, the 16-char hex (64 bits) has a birthday-paradox collision probability of ~1 in 4 billion — but the minute-precision timestamp makes this trivially collidable.
**Impact:** Valid signals within the same minute for the same symbol/strategy are silently dropped.
**Fix:** Include seconds or milliseconds in the timestamp hash. Or use the full SHA-256.

### [RISK-007] Post-fill stop-loss uses hardcoded 2% ATR proxy — not actual ATR
**File:** `execution/oms.py:773-776`
**Scenario:** `_setup_post_fill_stop_loss()` uses `default_atr_pct = 0.02` (2% of price) as an ATR proxy when real ATR is unavailable. For XAUUSD at $2300, this sets SL at $46 away — potentially too tight or too loose depending on actual volatility. The method also doesn't fetch real ATR from the data pipeline.
**Impact:** Stop-losses are placed at arbitrary distances that don't reflect current market conditions. In high-volatility regimes, stops are too tight (whipsawed out). In low-volatility, they're too wide (excessive risk).
**Fix:** Wire the ATR data pipeline into the OMS. If ATR unavailable, reject the order instead of using a guess.

### [RISK-008] Circuit breaker auto-recover can silently resume trading
**File:** `risk/circuit_breaker.py:59-68`
**Scenario:** `is_open()` checks `elapsed > cooldown_minutes * 60` and auto-resets the circuit breaker. The default cooldown is 30 minutes. After 3 consecutive losses trip the breaker, trading automatically resumes after 30 minutes — no human approval required.
**Impact:** A strategy in a losing streak will automatically resume trading after a short pause, potentially continuing the drawdown.
**Fix:** Auto-recover should downgrade to a "cautious" mode (reduced size) rather than full resume. Or require manual reset.

---

## HIGH (Significant risk, unlikely to cause immediate loss)

### [RISK-009] Order state machine has TWO parallel state systems — OMS uses `OrderStatus`, engine uses `OrderState`
**File:** `execution/oms.py` vs `execution/order_state_machine.py`
**Scenario:** The OMS uses `OrderStatus` (PENDING, SUBMITTED, FILLED, etc.) from `adapters/base.py`, while the `OrderStateMachine` uses `OrderState` (SIGNAL_CREATED, RISK_CHECKED, etc.) from `core/enums.py`. The OMS calls `sm.advance()` but catches all exceptions silently (lines 335-336, 344-347, etc.). If the state machine rejects a transition, the OMS ignores it and continues.
**Impact:** The state machine provides no real safety guarantee — invalid transitions are silently swallowed. The audit trail is unreliable.
**Fix:** Either unify the two state systems, or make state machine failures halt order processing.

### [RISK-010] `_poll_fill` breaks immediately if `broker_order_id` is None
**File:** `execution/oms.py:604-607`
**Scenario:** After a partial fill, `_poll_fill()` checks `if order.broker_order_id is None: break`. But if the adapter returned a partial fill without setting `broker_order_id` on the result (some adapters return it in `broker_id` field), the poll loop exits immediately and marks the order as TIMEOUT.
**Impact:** Partially filled orders are abandoned as TIMEOUT, leaving orphaned positions at the broker.
**Fix:** Verify `broker_order_id` is set from `result.broker_id` before entering the poll loop.

### [RISK-011] Binance adapter assumes all closes are SELL-side
**File:** `execution/adapters/binance.py:284`
**Scenario:** `close_position()` hardcodes `side = "sell"` with comment "assume BUY position being closed; flip if needed". For SELL positions being closed, this creates a SECOND sell order instead of a buy-to-close.
**Impact:** Closing a short position on Binance opens a larger short instead of closing.
**Fix:** Query the position side from the adapter or pass the original order side.

### [RISK-012] Kill switch `enforce()` uses `pnl < 0` to determine "risk-increasing" positions
**File:** `risk/kill_switch.py:203-204`
**Scenario:** `CLOSE_RISK_INCREASING_ONLY` mode closes positions where `pnl < 0`. But a position with pnl = -$0.01 is treated the same as pnl = -$1000. There's no threshold or prioritization.
**Impact:** All losing positions are closed simultaneously, including those that might recover. No triage by severity.
**Fix:** Sort by PnL descending (worst first) and add a threshold parameter.

### [RISK-013] Signal validator fallback passes ALL signals through unchanged
**File:** `core/agents/signal_validator.py:249-256`
**Scenario:** When LLM parsing fails (`_default_parse`), the signal passes through with `valid=True` and original confidence. When LLM times out (`_fallback_event`), same thing. When ALL LLM providers fail, same thing.
**Impact:** If the LLM service is down, the validator becomes a no-op — every signal passes. The "advisory only" design means the validator can never actually block a bad signal.
**Fix:** On persistent LLM failure, reduce confidence by a fixed amount (e.g., -0.1) rather than passing through unchanged.

### [RISK-014] Backtest engine `_check_exits` uses bar close for bid/ask estimation — not OHLC
**File:** `backtest/engine.py:891`
**Scenario:** `estimate_bid_ask_from_bar(Decimal("0"), bar_high, bar_low, bar_close, spread)` passes `Decimal("0")` as `bar_open`. The `conservative_bar_model` may use the open price for certain estimation strategies. Passing zero distorts the bid/ask midpoint.
**Impact:** Exit prices in backtests may be inaccurate, inflating or deflating P&L.
**Fix:** Pass the actual `bar_open` value.

### [RISK-015] ExecutionSimulator `evaluate_open_positions` has unconditional TIME_STOP
**File:** `execution/execution_simulator.py:336-353`
**Scenario:** The `elif max_bars_open > 0` block fires for ANY position that didn't trigger SL/TP, regardless of whether it actually exceeded `max_bars_open`. The condition `hasattr(pos, "signal_bar_index")` is always true for Position objects. There's no actual check of `current_bar_index - pos.signal_bar_index > max_bars_open`.
**Impact:** Every position that doesn't hit SL/TP is force-closed as a TIME_STOP on every bar, even if it's been open for only 1 bar.
**Fix:** Add actual bar count check: `if bar_index - pos.signal_bar_index > max_bars_open`.

---

## MEDIUM

### [RISK-016] Risk policy aliases (`max_risk_per_trade_pct`) divide by 100 instead of 10000
**File:** `risk/risk_policy.py:49-51`
**Scenario:** `max_risk_per_trade_pct` returns `risk_per_trade_bps / 100`. For 10 bps, this returns 0.10 (10%), not 0.001 (0.10%). The correct conversion for bps→pct is `/10000`, not `/100`.
**Impact:** Any code using the `_pct` aliases will interpret risk as 100x larger than intended.
**Fix:** Change to `/10000` or deprecate the misleading aliases.

### [RISK-017] `circuit_breaker._save()` overwrites file without fsync
**File:** `risk/circuit_breaker.py:187-188`
**Scenario:** `write_text()` doesn't call `fsync()`. On power loss, the OS buffer may not have flushed. The file could be empty or partially written on recovery.
**Impact:** Circuit breaker state lost on power failure.
**Fix:** Use `open(f, 'w')` + `f.flush()` + `os.fsync(f.fileno())`.

### [RISK-018] OMS ledger append is not fsynced
**File:** `execution/oms.py:209-210`
**Scenario:** `_persist()` and `_update_ledger()` append to JSONL without fsync. On crash, recent ledger entries may be lost.
**Impact:** Order state lost on crash. Duplicate orders possible after recovery.
**Fix:** Add `fh.flush(); os.fsync(fh.fileno())` after each write.

### [RISK-019] `position_sizer_v2` calculates margin but doesn't enforce it
**File:** `risk/position_sizer_v2.py:191-203`
**Scenario:** Margin is calculated (step 8) but the check is deferred to `pre_trade_risk` (step 9 comment). If `calc_margin_fn` fails, margin defaults to 0 and the position passes sizing.
**Impact:** Positions that exceed available margin can be sized and submitted.
**Fix:** If margin calculation fails, reject the sizing result.

### [RISK-020] No validation that `stop_loss` and `take_profit` are on correct side of entry
**File:** `core/signal_gateway.py:133-138`
**Scenario:** `validate_levels_positive` only checks `> 0`. It doesn't validate that BUY signals have SL < entry < TP, or SELL signals have TP < entry < SL.
**Impact:** A BUY signal with SL above entry passes validation and reaches the execution layer.
**Fix:** Add side-aware validation in `RawSignalPayload`.

### [RISK-021] Feed health monitor doesn't trigger trading halt on DISCONNECTED
**File:** `market_data/feed_health.py:112-113`
**Scenario:** `FeedHealthMonitor` transitions to `DISCONNECTED` after 3 consecutive stale checks, but there's no integration with the risk engine or kill switch. The state is purely informational.
**Impact:** Trading continues with stale/missing data.
**Fix:** Wire `FeedHealthMonitor` state to `pre_trade_risk` — reject orders when feed is DISCONNECTED.

### [RISK-022] `data/quality_gate.py` hardcodes price range 0.5-200 for OHLCV outliers
**File:** `data/quality_gate.py:372`
**Scenario:** Range check `val < 0.5 or val > 200` rejects XAUUSD data (price ~2300), BTC data (price ~60000), and NAS100 data (price ~20000).
**Impact:** Quality gate fails on valid data for non-FX instruments.
**Fix:** Use per-symbol configurable ranges.

---

## LOW

### [RISK-023] `_load_allowed_users` returns empty set if env var missing
**File:** `risk/kill_switch.py:286-289`
**Scenario:** If `TELEGRAM_ALLOWED_USERS` is not set, `_allowed_users` is empty, and `_is_authorized()` returns `False` for all users. All Telegram commands are rejected.
**Impact:** Kill switch cannot be activated via Telegram in misconfigured deployments.
**Fail-safe note:** This is actually correct behavior — fail-closed.

### [RISK-024] `FakeSignalFilter.quick_check` uses `max_dd < 25` (25%)
**File:** `core/signal_filter.py:189`
**Scenario:** The quick check allows up to 25% drawdown. The risk policy's `max_total_drawdown_bps` is 300 (3%).
**Impact:** Quick check is 8x more permissive than the actual risk policy.
**Fix:** Align with risk policy or document as intentional "rough filter".

### [RISK-025] Binance adapter `_order_symbols` dict is in-memory only
**File:** `execution/adapters/binance.py:62`
**Scenario:** If the adapter restarts, the `broker_order_id → symbol` mapping is lost. `get_order_status()` and `cancel_order()` will return "Unknown symbol" for all prior orders.
**Impact:** Cannot cancel or check status of orders from previous sessions.
**Fix:** Persist the mapping to the ledger or reconstruct from `fetch_orders()`.

---

## Invariant Compliance Table

| ID | Invariant | Enforced? | Gaps |
|----|-----------|-----------|------|
| INV-001 | Risk policy is frozen dataclass | ✅ YES | `@dataclass(frozen=True)` on `RiskPolicy` |
| INV-002 | All loss limits in basis points | ⚠️ PARTIAL | `risk_policy.py` uses bps, but `engine.py` uses `_Layer3` with float percentages (0.02, 0.05, 0.15). The `_pct` aliases divide by 100 instead of 10000. |
| INV-003 | No `order_send` in backtest/risk | ✅ YES | Backtest uses `ExecutionSimulator`, risk uses `pre_trade_check` |
| INV-004 | Strict MTF blocks static fallback | ✅ YES | `StrictMTFViolation` raised when `strict_mtf=True` and no cursor |
| INV-005 | Every dataset has SHA-256 manifest | ⚠️ PARTIAL | Manifests exist for some datasets (`data/manifests/`), but `quality_gate.py` returns WARN (not FAIL) when manifest missing |
| INV-006 | ContractSpec validates on creation | ❌ NO | `InlineContractSpec` in `backtest/engine.py` has no `validate()` method. `ContractSpec` in `execution_simulator.py` is a frozen dataclass with no validation. |
| INV-007 | Volume rounds down to broker step | ✅ YES | `position_sizer_v2.py` uses `ROUND_DOWN` |
| INV-008 | Kill switch persists across restart | ✅ YES | JSON file with fail-closed on corruption |
| INV-009 | Pre-trade risk gate mandatory before any order | ⚠️ PARTIAL | `oms.py` runs risk check, but `orchestrator.py:69` creates OMS with `risk_engine` defaulting to `...` sentinel. If constructor arg is wrong, risk is skipped. |
| INV-010 | Missing/invalid contract data = reject + fail closed | ⚠️ PARTIAL | `position_sizer_v2` rejects on zero stop distance, but doesn't validate contract_spec fields (e.g., `trade_tick_size > 0`) |
| INV-011 | Every sizing bound to immutable contract_snapshot_id | ⚠️ PARTIAL | `SizingResult` has `contract_snapshot_id` field, but it's set from `contract_spec.snapshot_hash` which defaults to "inline" in backtest — not a real hash. |

---

## Edge Case Inventory

| # | Edge Case | Current Behavior | Risk |
|---|-----------|-----------------|------|
| E01 | Risk engine crashes mid-trade | Exception caught → order rejected ✅ | LOW |
| E02 | Risk engine is None | Order proceeds without check ❌ | CRITICAL |
| E03 | Network timeout on broker submit | Binance retries 3x ✅, MT5 adapter unknown | MEDIUM |
| E04 | Partial fill, no broker_order_id | `_poll_fill` breaks immediately, marks TIMEOUT | HIGH |
| E05 | Kill switch file corrupted | Fail-closed: ACTIVE ✅ | LOW |
| E06 | Circuit breaker file corrupted | Silent reset to defaults ❌ | CRITICAL |
| E07 | LLM validator down | All signals pass unchanged | HIGH |
| E08 | LLM returns `valid: false` for everything | Confidence reduced but signal still passes (advisory only) | MEDIUM |
| E09 | Feed drops mid-session | No halt, trading continues with stale data | MEDIUM |
| E10 | Duplicate signal within same minute | Deduplicated by hash collision | HIGH |
| E11 | Two signals same symbol same minute | Second signal dropped (hash collision) | HIGH |
| E12 | Backtest uses 0 for bar_open in exit calc | Distorted bid/ask estimation | HIGH |
| E13 | TIME_STOP fires on every position every bar | All positions force-closed immediately | CRITICAL |
| E14 | Binance close_position on SHORT | Opens larger short instead of closing | HIGH |
| E15 | XAUUSD data fails quality gate price range | Valid data rejected (price > 200) | MEDIUM |

---

## Recommendations (Prioritized)

### P0 — Fix immediately (before any live trading)

1. **Fix execution_simulator TIME_STOP bug** [RISK-015]: Add actual bar count check. This bug makes ALL backtest results unreliable.
2. **Fix Binance close_position** [RISK-011]: Query position side before closing. This will cause catastrophic losses on short positions.
3. **Fix circuit breaker silent reset** [RISK-001]: Add atomic write + explicit error logging.
4. **Fix OMS crash-safety gap** [RISK-003]: Persist order to ledger immediately after creation, before risk check.
5. **Fix RiskPolicy `_pct` aliases** [RISK-016]: Division by 100 → 10000. Any code using these aliases has 100x wrong risk.
6. **Fix quality gate price range** [RISK-022]: Make per-symbol configurable.

### P1 — Fix before live trading

7. **Wire feed health to risk engine** [RISK-021]: Reject orders when feed is DISCONNECTED.
8. **Fix backtest exit calculation** [RISK-014]: Pass actual bar_open instead of Decimal("0").
9. **Add ATR pipeline to OMS** [RISK-007]: Use real ATR for post-fill stops, not hardcoded 2%.
10. **Make risk_engine mandatory** [RISK-004]: Constructor should raise if None.
11. **Add fsync to critical writes** [RISK-017, RISK-018]: Kill switch, circuit breaker, and ledger files.
12. **Unify order state systems** [RISK-009]: Either use OrderState everywhere or make failures non-silent.

### P2 — Fix before production scaling

13. **Signal ID collision** [RISK-006]: Include sub-minute timestamp precision.
14. **LLM validator degraded mode** [RISK-013]: Reduce confidence on persistent LLM failure.
15. **Kill switch enforcement timeout** [RISK-002]: Add per-position close timeout.
16. **ContractSpec validation** [INV-006]: Add `validate()` method to all contract specs.
17. **Margin enforcement** [RISK-019]: Reject sizing if margin calculation fails.

---

## Honest Assessment

This system has **good architectural bones**: frozen dataclasses for risk policy, fail-closed kill switch, JSONL event-sourced ledger, 4-layer risk engine, circuit breaker with auto-recovery. The design intent is clearly safety-first.

However, **the execution has critical bugs that would lose real money**:

- The TIME_STOP bug (#E13) makes every backtest result a lie — positions are force-closed on the very next bar.
- The Binance close_position bug (#E14) would open larger positions instead of closing them.
- The circuit breaker silent reset (#RISK-001) means the primary drawdown protection can disappear after a crash.
- The risk engine None bypass (#RISK-004) means a single initialization error disables all risk.

**Verdict: NOT READY for live trading.** The P0 items must be fixed and tested before any real money touches this system.

---

*Report generated by Ruflow Auditor Agent — Project Gracia*
