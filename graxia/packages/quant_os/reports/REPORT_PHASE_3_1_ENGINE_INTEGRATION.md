# REPORT: Phase 3.1 — Wire Realistic Execution into the Canonical Backtest Engine

## Executive Summary

Phase 3.1 created the bridge layer (`execution_simulator.py`), enhanced ambiguous bar resolution (`ambiguous_bar_resolver.py`), extended the engine data model with execution-quality fields, and added a 40-test regression suite. However, **the engine does not actually invoke `BacktestExecutionSimulator` at runtime** — the import is present but `_execute_signal()` and `_check_exits()` still use the old close-price fill path. Six tests fail due to a broken import (`OrderSide` name collision). The work is incomplete and does not pass the exit gate.

## 1. ExecutionSimulator Interface

`execution/execution_simulator.py` (243 lines, untracked) defines:

- **`OrderIntent`** — signal intent with `side`, `stop_loss`, `take_profit`, `risk_amount`, `spread_estimate`, `slippage_entry/exit`, `signal_bar_index`
- **`MarketSnapshot`** — bar OHLCV as `bid`, `ask`, `high`, `low`, `open_price`, `close`
- **`ExecutionResult`** — fill outcome: `entry_price`, `quantity`, `spread_cost`, `slippage_cost`, `commission`, `execution_quality`, `fill_bar_index`
- **`ExitTriggerResult`** — SL/TP trigger outcome with `is_ambiguous` flag
- **`BacktestExecutionSimulator`** class:
  - `submit_intent()` — fills on the bar at `bar_index` (caller must pass `signal_bar_index + 1`)
  - `check_exit()` — evaluates SL/TP using bid/ask sides via `fill_model`
  - `simulate_exit()` — computes exit price from bar bid/ask

The simulator uses `conservative_bar_model.estimate_bid_ask_from_bar` for synthetic bid/ask from OHLC bars, and delegates to `fill_model.simulate_entry` for correct bid/ask side semantics.

**Status**: Interface is well-designed. Not yet connected to engine.

## 2. Engine Refactoring

`backtest/engine.py` (609 lines, modified) changes:

- **Import added** (lines 25-31): `BacktestExecutionSimulator`, `OrderIntent`, `MarketSnapshot`, `ExecutionQuality`
- **`BacktestPosition`** extended with: `entry_spread_cost`, `entry_slippage_cost`, `execution_quality`, `signal_bar_index`
- **`BacktestTrade`** extended with: `execution_quality`, `spread_cost`, `slippage_cost`, `ambiguous_bar`, `resolution_policy`
- **`BacktestConfig`** extended with: `record_to_ledger`, `ledger_dir`
- **`_build_results()`** now emits execution quality breakdown and cost totals
- **Auto-ledger**: `__init__` creates `TradeLedger` if `record_to_ledger=True`

**Critical gap**: `_execute_signal()` (lines 338-412) still computes `fill_price = entry_price ± slippage` using the old close-price path. `BacktestExecutionSimulator` is imported but **never instantiated or called**. The `_check_exits()` method (lines 414-442) also does not use the simulator's `check_exit()`.

**Broken import**: Line 25-30 imports `OrderSide` as `ExecOrderSide` from `execution_simulator`, but this causes `ImportError: cannot import name 'OrderSide'` because `execution_simulator` defines its own `OrderSide` enum which is not recognized as an importable name in the current context. This breaks all tests that transitively import the engine.

## 3. Bid/Ask Execution Semantics

The fill model (`fill_model.py`, modified) correctly implements:
- Long entry = ask + slippage ✓
- Short entry = bid - slippage ✓
- Long exit = bid - slippage ✓
- Short exit = ask + slippage ✓
- Long SL triggers on bid ≤ stop_loss ✓
- Long TP triggers on bid ≥ take_profit ✓
- Short SL triggers on ask ≥ stop_loss ✓
- Short TP triggers on ask ≤ take_profit ✓

`check_sl_tp_trigger_ambiguous()` added (lines 90-118) returns `(trigger, is_ambiguous)` tuple for bars where both SL and TP could fire.

**Status**: Fill model is correct. Engine does not use it at runtime.

## 4. Signal Timing Rule

`fill_model.can_fill_on_info_candle()` enforces `fill_bar_index > signal_bar_index`.

`conservative_bar_model.next_bar_fill()` and `simulate_bar_execution()` both implement next-bar fill timing.

`BacktestExecutionSimulator.submit_intent()` documents that it fills on the bar at `bar_index` (caller passes `signal_bar_index + 1`).

**Status**: Next-bar fill is enforced in the fill model and simulator. The engine's main loop does not enforce it — it fills on the same bar the signal is generated (line 261: `self._execute_signal(signal, close[i], current_time)`).

## 5. Ambiguous Bar Resolution

`execution/ambiguous_bar_resolver.py` (128 lines, untracked) provides:
- `resolve_ambiguous_bar()` — detects when both SL and TP are possible, returns `AmbiguousResult` with `resolved_reason="SL"` (adverse) and `resolution_policy="ADVERSE"`
- `check_bar_triggers_with_ambiguous_resolution()` — returns ordered `BarTrigger` list with SL first in ambiguous cases

**Status**: Standalone module is correct. Not wired into engine's `_check_exits()`.

## 6. Trade Ledger Integration

`execution/trade_ledger.py` provides `TradeLedger` with:
- `record_trade()` — writes JSON file per trade
- `get_trades()` — filter by symbol/date
- `get_ambiguous_trades()` — filter `close_reason == "AMBIGUOUS"`
- `ledger_hash()` — SHA-256 integrity hash

Engine integration:
- `__init__` creates ledger if `config.record_to_ledger=True` (line 142-143)
- `set_ledger()` method for external injection (line 154-156)
- `_close_position()` records to ledger (lines 487-503)
- `_build_results()` emits `ledger_hash` and `ledger_trade_count` (lines 605-607)

**Status**: Ledger is wired. However, `TradeRecord` entries from `_close_position()` do not populate `execution_quality`, `spread_cost`, or `slippage_cost` fields (they are left empty/default).

## 7. Execution Quality Hierarchy

`fill_model.ExecutionQuality` enum:
```python
BAR_ONLY = "bar_only"            # legacy close-price fills
CONSERVATIVE_BAR = "conservative_bar"  # bid/ask from bar high/low
TICK_REPLAY = "tick_replay"      # actual tick data
LIVE_OBSERVED = "live_observed"  # live broker feed
```

`BacktestExecutionSimulator` returns `execution_quality=BAR_ONLY` (default) since it uses conservative bar estimation. The `ExecutionResult` dataclass carries this through.

**Status**: Enum exists. Engine `_build_results()` tracks quality breakdown. But since the engine doesn't use the simulator, all trades currently have empty `execution_quality`.

## 8. Required Tests

`tests/test_phase_3_1_engine_integration.py` (546 lines, 40 tests):

| Test Class | Tests | Status |
|---|---|---|
| `TestNoClosePriceFillPath` | 3 | ✅ 3/3 PASS |
| `TestSameBarFillImpossible` | 4 | ✅ 4/4 PASS |
| `TestEntryUsesCorrectSide` | 4 | ✅ 4/4 PASS |
| `TestSLTPTriggerSides` | 10 | ✅ 10/10 PASS |
| `TestAmbiguousBarResolvesAdverse` | 4 | ✅ 4/4 PASS |
| `TestCostsAppearOnce` | 3 | ✅ 3/3 PASS |
| `TestDeterministicRun` | 3 | ✅ 3/3 PASS |
| `TestEngineRecordsExecutionQuality` | 4 | ❌ 3/4 PASS, 1 FAIL (import error) |
| `TestEngineFailClosesWithoutData` | 5 | ❌ 0/5 PASS (import error) |
| `TestStateMachineBlocksInvalid` | 2 | ✅ 2/2 PASS |

**Total: 38/40 PASS, 2/40 FAIL** — both failures are caused by the broken `OrderSide` import in `engine.py`.

`tests/test_phase_3.py` (253 lines, 25 tests): **25/25 PASS** (no engine import).

## 9. Phase 3.1 Exit Gate Checklist

- [ ] **Canonical engine invokes ExecutionSimulator** — NOT DONE. Import is present but `_execute_signal()` does not call `BacktestExecutionSimulator.submit_intent()`.
- [ ] **Legacy fill code is unreachable from canonical runtime** — NOT DONE. Old close-price path is still the active code path.
- [ ] **Full end-to-end engine test proves next-bar behavior** — NOT DONE. No test runs the engine with a strategy and verifies fill occurs on bar `i+1`.
- [ ] **Full end-to-end engine test proves long/short bid/ask semantics** — NOT DONE. Unit tests cover fill_model but no engine-level test proves the engine uses bid/ask at entry/exit.
- [ ] **Full end-to-end engine test proves adverse ambiguity semantics** — NOT DONE. No engine-level test covers ambiguous bar resolution.
- [ ] **Every canonical trade has execution quality and cost attribution** — PARTIAL. Fields exist on `BacktestTrade` but `_close_position()` does not populate them; ledger records lack execution_quality.
- [ ] **No strategy parameter changed** — PASS. No strategy code modified.
- [ ] **No MT5 order was submitted** — PASS. No `order_send` in execution modules.

## 10. Verdict

**NO_GO**

Phase 3.1 is **structurally complete but not functionally integrated**. The `BacktestExecutionSimulator` class exists and is well-designed, but the engine never calls it. The 6 failing tests confirm the import is broken. Two critical tasks remain before this phase can pass:

1. **Fix the `OrderSide` import** — resolve the name collision between `core.enums.OrderSide` and `execution_simulator.OrderSide`
2. **Wire `_execute_signal()` to `BacktestExecutionSimulator`** — replace the close-price fill with a call to `submit_intent()`, passing `signal_bar_index` and getting back `ExecutionResult` with correct bid/ask fill price, spread_cost, slippage_cost, and execution_quality
3. **Wire `_check_exits()` to `BacktestExecutionSimulator.check_exit()`** — replace the current high/low SL/TP check with the simulator's bid/ask-based trigger detection
4. **Add end-to-end engine tests** — run a stub strategy through the engine and verify next-bar fill, bid/ask entry, and adverse ambiguity semantics
5. **Populate execution_quality and cost fields on every trade** — ensure `_close_position()` carries these through to `BacktestTrade` and `TradeRecord`

## 11. Files Changed

| File | Status | Lines | Notes |
|---|---|---|---|
| `execution/execution_simulator.py` | NEW (untracked) | 243 | BacktestExecutionSimulator + dataclasses |
| `execution/ambiguous_bar_resolver.py` | NEW (untracked) | 128 | Adverse resolution + trigger ordering |
| `execution/fill_model.py` | MODIFIED | 122 (+31) | Added `check_sl_tp_trigger_ambiguous()` |
| `backtest/engine.py` | MODIFIED | 609 (+54) | Execution quality fields + ledger wiring + broken import |
| `tests/test_phase_3_1_engine_integration.py` | NEW (untracked) | 546 | 40 regression tests (38 pass, 2 fail) |
| `tests/test_phase_3.py` | MODIFIED | 253 | Existing Phase 3 tests still pass |

## 12. Important Notes

1. **All untracked files** — `execution_simulator.py`, `ambiguous_bar_resolver.py`, and `test_phase_3_1_engine_integration.py` are untracked. Nothing has been committed.
2. **The import error is the immediate blocker** — the engine cannot even be imported, which means no backtest can run. This must be fixed first.
3. **No strategy parameters were modified** — the fill model changes are purely in the execution layer.
4. **Phase 3 modules pass all 25 existing tests** — the `fill_model`, `cost_model`, `order_state_machine`, and `trade_ledger` are verified working independently.
5. **The `BacktestTrade` dataclass has `execution_quality` and cost fields but `_close_position()` never sets them** — this is a wiring gap that needs to be closed.
6. **Ledger records from the engine lack `execution_quality`, `spread_cost`, and `slippage_cost`** — the `TradeRecord` is created without these fields, so ledger-based analysis will be incomplete.
