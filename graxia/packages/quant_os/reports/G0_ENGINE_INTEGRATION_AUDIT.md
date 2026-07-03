# G0.7 — Engine Integration Audit

**Date:** 2026-06-22
**Scope:** `backtest/engine.py` — gaps blocking Phase 3.1 canonical engine integration
**Files read:** `backtest/engine.py`, `gold_bot/strategy_adapter.py`, `gold_bot/run.py`, `gold_bot/run_demo.py`, `risk/position_sizer_v2.py`, `execution/trade_ledger.py`, `execution/order_state_machine.py`, `execution/order.py`

---

## 1. Current Fill Model

**Location:** `backtest/engine.py:308-382` (entry), `384-454` (exit)

The engine uses **close-price fills with pip-based slippage on entry only**.

- **Entry:** Signal executes at `close[i]`, then adds/subtracts slippage based on signal direction (line 358-363). Slippage is `slippage_pips * pip_value` (0.0001 for forex, 0.01 for JPY).
- **Exit (SL/TP):** Checked against `high[i]`/`low[i]` intrabar range, but fill is at the **exact SL/TP price** — no slippage, no spread. (lines 394-408, 414-416)
- **Exit (end-of-backtest):** `_close_all_positions` fills at `close[-1]` with zero slippage. (line 459)

**Gap:** Close-price fills are unrealistic for short-term strategies. No bid/ask modeling. Exit slippage is missing — SL fills will be optimistic.

**Risk: Medium** — Acceptable for D1/H1 strategies; M15 scalping backtests will overstate performance.

---

## 2. Current MTF Handling

**Location:** `backtest/engine.py:116-145` (cursor setup), `180-185` (strict guard), `217-219` (injection)

The engine **supports point-in-time MTF via `MultiTimeframeCursor`**, but defaults to no cursor.

- `set_multi_timeframe()` creates a cursor from `mtf_cursor.py` (line 139-145)
- On each bar, if cursor exists and strategy has `_set_mtf_cursor`, sliced data is injected (lines 217-219)
- `strict_mtf=True` raises `StrictMTFViolation` if no cursor set (lines 181-185)
- **Default: `strict_mtf=False`** (line 38)

The adapter (`strategy_adapter.py:34-40`) falls back to static `multi_tf_data` when no cursor is present — this is the leaky path.

**Gap:** Cursor works but defaults are permissive. Static fallback is still reachable. Phase 3.1 should flip default to strict or remove the fallback entirely.

**Risk: Low** — Cursor exists and works. Only an issue if someone runs backtests without calling `set_multi_timeframe()`.

---

## 3. Current Cost Model

**Location:** `backtest/engine.py:353-368` (entry), `426-429` (exit)

Costs are **lot-based commission only**, applied symmetrically on entry and exit.

- Commission: `lots * commission_per_lot` (default: 3.5 per lot)
- Applied on entry (line 366-368) and exit (line 427-429)
- Slippage applied on entry only (line 354-363)

**Missing:**
- **Spread cost** — No bid/ask spread modeling. The `TradeRecord` ledger has a `spread_cost` field (trade_ledger.py:38) but the engine never populates it.
- **Exit slippage** — SL/TP fills are at exact price.
- **Swap/rollover** — Not modeled.
- **Market impact** — Not modeled (acceptable for backtest).

**Gap:** Engine's cost model is too simple. Ledger expects richer cost data that the engine can't provide.

**Risk: Medium** — Commission-only costs underestimate total friction. Strategies with tight stops will appear more profitable than they are.

---

## 4. Current Sizing

**Location:** `backtest/engine.py:322-351`

The engine uses **inline risk-based sizing** — completely independent of `position_sizer_v2`.

- Calculates `risk_amount = balance * risk_per_trade_pct / 100` (line 335)
- Divides by `risk_per_unit` (distance to SL) to get quantity (line 336)
- Caps at 50% notional exposure (lines 348-351)
- Has per-symbol minimum SL checks (XAU: 5.0, JPY: 0.05, forex: 0.0005) — lines 325-330
- Falls back to fixed 50-pip SL if signal has no stop_loss (lines 338-342)

**`position_sizer_v2.size_position()`** (position_sizer_v2.py:33-230) provides:
- Broker-native `calc_profit_fn` / `calc_margin_fn` for accurate loss-at-stop
- `ContractSpec` validation (volume_step, volume_min, stops_level)
- Post-rounding loss verification
- `SizingResult` with full provenance (risk_amount, margin_estimate, rejection_reasons)

**Gap:** Engine ignores broker contract specs, volume rounding, margin checks, and stops_level validation. Sizing results are not tracked.

**Risk: Critical** — Backtest sizes will diverge from live execution. Over-sizing in backtest → false confidence; under-sizing → missed trades in live.

---

## 5. Current Ledger

**Location:** `backtest/engine.py:439-454` (trade recording), `500-537` (results)

The engine returns results as **in-memory dicts** — no ledger integration.

- Trades stored as `List[BacktestTrade]` (line 105)
- Results returned as dict with `"trades"` key containing plain dicts (lines 509-527)
- Equity curve returned as dict (lines 528-537)

**`TradeLedger`** (trade_ledger.py:73-127) provides:
- `TradeRecord` with provenance fields: `contract_snapshot_id`, `risk_policy_version`, `dataset_manifest_id`, `cost_scenario`, `git_commit`
- JSON file persistence per trade
- Ambiguous trade detection

**Gap:** Engine writes nothing to the ledger. No provenance tracking. No persistence. Backtest results are ephemeral.

**Risk: High** — No audit trail for backtest results. Reproducibility is impossible without manual data capture.

---

## 6. Current Order State Machine

**Location:** `backtest/engine.py:370-382` (position creation)

The engine **does not use the Order entity or OrderStateMachine at all**.

- `_execute_signal()` directly creates `BacktestPosition` objects (lines 370-382)
- No `Order` object created
- No `OrderStateMachine` transitions
- No `RISK_CHECKED`, `ORDER_SUBMITTED`, `FILLED` states recorded
- Close path also bypasses orders — directly pops position and creates trade (lines 416-454)

**Two state machines exist:**
1. `execution/order.py:81-265` — `OrderStateMachine` with `OrderStatus` enum (16 states including `PENDING_HUMAN`, `COMPLIANCE_APPROVED`)
2. `execution/order_state_machine.py:79-110` — Standalone `OrderStateMachine` with `OrderState` enum (16 states including `PROTECTIVE_STOPS_PENDING`, `POSITION_RECONCILED`)

Neither is referenced by the backtest engine.

**Gap:** Backtesting skips the entire order lifecycle. Any signal → position transition is instantaneous with no state tracking.

**Risk: Critical** — Backtest cannot validate order lifecycle correctness. Risk checks, compliance, and reconciliation logic is untested in backtest.

---

## 7. Gap Summary

| # | Gap | What Exists | What It Should Be | Risk |
|---|-----|-------------|-------------------|------|
| 1 | **Fill model** | Close ± slippage, entry only | Bid/ask with spread; slippage on exits | Medium |
| 2 | **MTF default** | `strict_mtf=False`, static fallback available | Default strict or remove static fallback | Low |
| 3 | **Spread cost** | Not modeled | Model spread as explicit cost component | Medium |
| 4 | **Exit slippage** | None — SL/TP at exact price | Slippage applied to SL/TP fills | Medium |
| 5 | **Sizing engine** | Inline risk-based (engine:322-351) | `position_sizer_v2.size_position()` with ContractSpec | **Critical** |
| 6 | **Ledger integration** | In-memory dict, no persistence | `TradeLedger.record_trade(TradeRecord)` with provenance | High |
| 7 | **Order state machine** | None — direct BacktestPosition creation | `Order` → `OrderStateMachine` through full lifecycle | **Critical** |
| 8 | **Swap/rollover** | Not modeled | Optional per-bar swap deduction | Low |
| 9 | **BacktestTrade → TradeRecord** | Separate dataclasses, no mapping | Unified or mapped trade record for ledger | High |
| 10 | **SizingResult provenance** | Not captured | `contract_snapshot_id`, `rejection_reasons` in results | High |

---

## Architecture Summary

```
engine.py (538 lines)
├── Fill model:       Close ± pip slippage (entry only)
├── MTF:              Cursor-based, optional, default off
├── Costs:            Lot-based commission × 2
├── Sizing:           Inline risk / risk_per_unit (no broker specs)
├── Ledger:           None (in-memory BacktestTrade list)
├── Order lifecycle:  None (signal → BacktestPosition directly)
└── Results:          Dict with trades[], equity_curve[]

phase-3 components (exist but not wired):
├── position_sizer_v2.py    — Broker-native sizing with ContractSpec
├── trade_ledger.py         — JSON-file ledger with provenance
├── order.py                — Order entity + OrderStateMachine (OrderStatus)
└── order_state_machine.py  — Standalone OrderStateMachine (OrderState)
```

**Highest-risk gap:** Sizing engine (#5) and Order state machine (#7) — both Critical. Sizing divergence between backtest and live will cause silent over-exposure or missed trades. Missing order lifecycle means risk checks and reconciliation are untested in backtest.

**Total gaps:** 10 (2 Critical, 3 High, 4 Medium, 2 Low)
