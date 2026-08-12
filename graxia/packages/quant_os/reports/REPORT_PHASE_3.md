# Phase 3 Report — Realistic Execution and Cost Model

## Scope
Bid/ask fill model, cost stress matrix, order state machine, trade ledger, conservative bar model, execution quality labels.

## Commit
- Phase 3 commit: `8a13ca5` feat(quant_os): Phase 3 — bid/ask execution + cost model + order lifecycle

## Environment
- Python 3.12.10, Windows, pytest 8.4.2
- No MT5 connection, no live orders, no credentials

## Implemented changes

| File | Purpose |
|------|---------|
| `execution/fill_model.py` | Bid/ask entry/exit rules, SL/TP trigger sides, ambiguous bar adverse ordering, next-bar fill timing |
| `execution/cost_model.py` | 4 cost scenarios (base/1.5×/2×/3×) + stress matrix runner |
| `execution/order_state_machine.py` | 15-state lifecycle per Master Plan §14.3 |
| `execution/trade_ledger.py` | JSON-file trade records with full provenance + integrity hash |
| `execution/conservative_bar_model.py` | Bar-based bid/ask estimation + next-bar fill |
| `tests/test_phase_3.py` | 28 tests (bid/ask, SL/TP, ambiguous, next-bar, cost, state machine, ledger, safety) |
| `tests/test_phase_3_order.py` | 20 tests (full lifecycle, invalid transitions, critical incident, ledger) |

## Test evidence

```
48 passed in 1.95s

Bid/ask rules (4): entry at ask/bid, exit at bid/ask ✓
SL/TP triggers (5): long SL on bid, short SL on ask, no false triggers ✓
Ambiguous bars (2): adverse ordering (SL first) for both long and short ✓
Next-bar fill (2): same-bar fill rejected, next-bar fill allowed ✓
Cost model (4): base, stress_1 (1.5×), stress_3 (3×), matrix runner ✓
Order state machine (5): happy path, invalid transition, terminal states ✓
Trade ledger (4): record, retrieve, hash, summary ✓
Integration + safety (12): full flow, no order_send, execution quality ✓
```

## Execution quality labels

```text
BAR_ONLY          — legacy close-price fills (NOT for promotion evidence)
CONSERVATIVE_BAR  — bid/ask from bar high/low (eligible)
TICK_REPLAY       — actual tick data (eligible)
LIVE_OBSERVED     — live broker feed (eligible)
```

## Bid/ask rules implemented

```text
Long entry  = ask + slippage      ✓
Short entry = bid - slippage      ✓
Long exit   = bid - slippage      ✓
Short exit  = ask + slippage      ✓
Long SL     = bid <= stop_loss    ✓
Long TP     = bid >= take_profit  ✓
Short SL    = ask >= stop_loss    ✓
Short TP    = ask <= take_profit  ✓
```

## Cost scenarios

| Scenario | Spread | Slippage | Purpose |
|----------|--------|----------|---------|
| Base | 1× | 1× | Baseline |
| Stress 1 | 1.5× | 1.5× | Moderate |
| Stress 2 | 2× | 2× | Adverse |
| Stress 3 | 3× | 3× | Severe |

## Order state machine

15 states: SIGNAL_CREATED → RISK_CHECKED → ORDER_PRECHECKED → ORDER_SUBMITTED → ORDER_ACKNOWLEDGED → FILLED → PROTECTIVE_STOPS_VERIFIED → POSITION_RECONCILED → CLOSED → DEAL_RECONCILED → AUDITED

Terminal states: AUDITED, REJECTED, EXPIRED, CRITICAL_INCIDENT

## Gate checklist

```
[✓] Every trade includes entry/exit spread, slippage, fee, execution-quality label
[✓] Same-candle signal/fill leakage is impossible and tested
[✓] Ambiguous bars are visibly accounted for
[✓] Conservative-bar execution works on bar datasets
[✓] Cost stress matrix is produced for every candidate
[✓] No order_send in any Phase 3 code path
[✓] 48/48 tests pass
```

## Known limitations

1. **No tick replay yet** — only conservative bar model implemented
2. **Swap not modeled** — set to 0 in cost calculations
3. **No historical spread model** — uses fixed spread estimate
4. **Backtest engine not yet wired** — engine still uses close-price fills
5. **No claim of validated edge** — liquidity_sweep remains CANDIDATE_ONLY

## Decision

**PASS_TO_PHASE_1R**

Phase 3 execution model is built and tested. The next phase per the approved order is Phase 1R (Repository Intelligence) — but Phase 3B (Locked XAUUSD Revalidation) requires the backtest engine to be wired to the new fill model first.

## Next permitted action

Wire the new fill model into backtest/engine.py so backtests use bid/ask fills instead of close-price fills. This is prerequisite for Phase 3B.

## Explicitly prohibited actions

- Do NOT claim liquidity_sweep has a validated edge
- Do NOT claim the strategy is profitable or demo-ready
- Do NOT run live orders
- Do NOT start EURUSD research (Phase 4)
- Do NOT optimize strategy parameters
