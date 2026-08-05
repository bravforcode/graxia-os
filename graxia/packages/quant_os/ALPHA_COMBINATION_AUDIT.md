# ALPHA_COMBINATION_AUDIT.md — Phase 14

## 14.1 — Ensemble Architecture

- **3-strategy weighted voting**: MTM (0.40), MRB (0.25), MLR (0.35)
- **Weights defined**: `core/config.py:70-75` — config-driven, not dynamically derived
- **Confidence threshold**: `ensemble_confidence_threshold = 0.60` (`core/config.py:76`)

## 14.2 — Weight Derivation

- Weights appear to be manually assigned (no optimization or derivation from backtest data found)
- **[WEIGHTS NOT DERIVED FROM DATA — MANUALLY ASSIGNED]**
- **P2 FINDING**: Ensemble weights should be derived from per-strategy OOS performance, not manually set

## 14.3 — Signal Conflict Resolution

`alpha/engine.py:170-210`: Consensus resolver takes median of strategy SL/TP values
- If strategies agree on direction → signal emitted
- If strategies disagree → no signal (consensus not reached)
- **PASS** — conservative conflict resolution

## 14.4 — Null Signal Handling

- Strategies returning `SignalType.HOLD` or `SignalType.NO_TRADE` → ignored by ensemble
- `alpha/engine.py:394`: Only BUY/SELL signals with conviction > 0.6 are emitted
- **PASS**

## 14.5 — Per-Strategy Edge Independence

- MTM: Multi-timeframe momentum — time-series momentum
- MRB: Mean reversion Bollinger — contrarian
- MLR: ML-enhanced breakout — pattern-based
- **These are semi-independent** (momentum vs mean-reversion vs ML). Cross-correlation not measured. **P2 FINDING**.

## 14.6 — Ensemble-Level Metrics

- No ensemble-specific Sharpe/win-rate computed separately from individual strategies
- **[ENSEMBLE METRICS NOT REPORTED SEPARATELY]**

## 14.7 — Consensus SL/TP Resolver

`alpha/engine.py:185-210`:
```python
stop_losses = [s["stop_loss"] for s in dominant if "stop_loss" in s]
take_profits = [s["take_profit"] for s in dominant if "take_profit" in s]
```
If all strategies return SL/TP → median used. If some return None → those are excluded from median.

**CRITICAL**: If a strategy returns `stop_loss=0` or missing key, it's excluded from the median — the remaining strategies' SL/TP is used. If ALL return None, the resolver returns `(None, None)`.

`core/trading_loop.py:230-240`: Golden Rule check rejects signals with `stop_loss <= 0`. **PASS** — signal with SL=None or SL=0 is rejected before execution.

## 14.8 — Ensemble Weight-Optimization Audit

- No weight optimization performed (grid search, Bayesian optimization, etc.)
- Weights are static and manually assigned
- **P2 FINDING**: Static weights may not be optimal across different market regimes

---

**P0 Findings**: 0
**P1 Findings**: 0
**P2 Findings**: 3 (manually assigned weights, no cross-correlation measurement, no weight optimization)
