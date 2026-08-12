# Research Log — Quant OS

## Format
Each experiment follows:
1. **Hypothesis** — what we think will work
2. **Method** — what we test
3. **Result** — measured outcome
4. **Verdict** — PASS/FAIL with evidence

## Experiments

### EXP-001: Baseline (no edge)
- **Date**: 26 Jun 2026
- **Hypothesis**: XGBoost on price returns has edge
- **Method**: Walk-forward on XAUUSD H1, 8.5 years
- **Result**: Net -$1,225 vs BH +$2,888. Sharpe 0.3
- **Verdict**: **FAIL** — no edge after costs

### EXP-002: Session filter (pending)
- **Hypothesis**: Trading only during London/NY reduces cost
- **Method**: Filter trades by hour, compare cost/move ratio
- **Status**: NOT STARTED

### EXP-003: Limit order simulation (pending)
- **Hypothesis**: Limit orders save half-spread
- **Method**: Simulate limit fills at bid/ask midpoint
- **Status**: NOT STARTED

---

*Last updated: 26 Jun 2026*
