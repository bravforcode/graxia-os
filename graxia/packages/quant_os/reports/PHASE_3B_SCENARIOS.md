# Phase 3B — Run Matrix

| Run | Execution | Spread | Swap | Trades | PnL | Win Rate | Status |
|---|---|---|---|---|---|---|---|
| R0 | Conservative bar | Base | Base | 4 | -0.01 | 0.0% | Complete |
| R1 | Conservative bar | 1.5x | Base | 4 | -0.01 | 0.0% | Complete |
| R2 | Conservative bar | 2.0x | 1.5x adverse | 4 | -0.01 | 0.0% | Complete |
| R3 | Conservative bar | 3.0x | 2.0x adverse | 4 | -0.02 | 0.0% | Complete |
| R4 | Tick replay | N/A | N/A | — | — | — | BLOCKED (no tick data) |
| R5 | VectorBT oracle | N/A | N/A | — | — | — | PENDING |
| R6 | Backtesting.py oracle | N/A | N/A | — | — | — | PENDING |

## Notes

- R0–R3 use synthetic M15 fixture (120 bars, base price 2350). Tiny PnL is expected — fixture validates engine wiring, not edge.
- Cost scenarios use `execution.cost_model` STRESS_1/2/3. Spread multiplier applied via `SpreadPatchedEngine`.
- R3 shows 2x PnL degradation vs R0 — spread effect scales as expected.
- R4–R6 require external dependencies (tick data, vectorbt, backtesting.py).
