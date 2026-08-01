# INTRABAR_EXECUTION_FIDELITY.md — Phase 4

## 4.1 — Same-Bar SL/TP Ambiguity Resolution

**Implementation**: `execution/ambiguous_bar_resolver.py:40-86` and `execution/execution_simulator.py:292-340`

**Resolution method**: **ADVERSE-FIRST (SL wins ties)** — when both SL and TP are reachable on the same bar, the stop-loss is assumed to have triggered first.

**Code evidence**:
- `execution/ambiguous_bar_resolver.py:63-65`: `is_ambiguous = sl_triggered and tp_triggered` → if ambiguous, returns SL trigger
- `execution/execution_simulator.py:292-294`: "Ambiguous bars (both SL and TP could hit) are resolved ADVERSE first"
- `execution/execution_simulator.py:337`: `event_type=EventType.AMBIGUOUS` with `reason="ambiguous_bar_adverse_sl"`

**PASS** — Conservative default per R17. The backtest does NOT assume favorable outcome.

**Test coverage**: `tests/test_phase_3_1_engine_integration.py:330-355` and `tests/chaos/test_execution_untested.py:165-227` confirm adverse-first resolution.

## 4.2 — Fill Price Assumption Within the Bar

- **Entry**: Signal at bar close → fill at **next bar open** (realistic). `backtest/engine.py:870-872` uses `_execute_signal()` with `bar_open` as entry price.
- **SL/TP exit**: Fill at exact SL/TP price OR at next-bar bid/ask depending on path. `execution/execution_simulator.py:305-306` evaluates against bar high/low.
- **Slippage**: Applied via `backtest/dynamic_spread_model.py` (session-aware) + `execution/conservative_bar_model.py` (bid/ask estimation from bar OHLC).
- **Verdict**: PASS — entry at next bar open is realistic. SL/TP fills at exact levels (no slippage-through-the-level for stop orders during fast markets) — **P2 FINDING**.

## 4.3 — Sub-Bar Replay Validation

**NEVER PERFORMED.** No tick-level replay of historical trades exists to validate bar-level assumptions.

**[NEVER CHECKED]** — this is a scope limitation of the audit's backtest fidelity claims.

## 4.4 — Gap-Through-Level Handling

`execution/fill_model.py:66-76` and `execution/execution_simulator.py:293-306`:
- For exits: checks `bar_low <= stop_loss` (long) or `bar_high >= stop_loss` (short)
- Does NOT model gap-through (price skipping the stop level entirely)
- For a true gap (weekend gap, news spike), the backtest assumes the stop level was hit — this is CONSERVATIVE (favorable assumption would be: gap through stop with no fill, continue to TP)

**Verdict**: PASS — conservative gap handling.

## 4.5 — Close-Price-Fill Status Check

`backtest/engine.py:870`: Entry uses `bar_open` of next bar — NOT close-price fill. **CONFIRMED FIXED** from prior state.

`execution/execution_simulator.py:221-222`: Entry intent uses `snapshot.bid/ask` from bar-level estimation — not close price.

**Per-asset-class severity of remaining bar-level limitation**:
- Crypto (BTCUSD/ETHUSD): Can move 1-2% within a single M1 bar. Bar-level fill assumption understates slippage more severely than for FX.
- Metals (XAUUSD): Can move $10-20 within M15 bar. Moderate impact.
- FX majors: Tightest, least impact from bar-level assumption.

**P2 FINDING**: Bar-level fill simulation (not tick-level) is acceptable for initial validation but understates execution cost, especially for crypto.

---

**P0 Findings**: 0
**P1 Findings**: 0
**P2 Findings**: 2 (no slippage-through-level for stops, bar-level fills for crypto)
**P3 Findings**: 1 (no sub-bar replay validation)
