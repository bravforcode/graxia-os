# ADR-005: Multi-Agent Ensemble Strategy

## Status
Accepted — Phase A (Week 1-2)

## Context
Single-strategy approaches (MTM, MRB, MLB) have regime-specific weaknesses. An ensemble combining multiple strategies with weighted voting reduces variance and improves robustness. The multi-agent framework in `core/agents/` provides the infrastructure; `strategies/ensemble.py` implements the signal aggregation.

## Decision
Implement two complementary ensemble patterns:

### 1. Strategy-Level Ensemble (`strategies/ensemble.py`)
Weighted vote from three sub-strategies:
- MTM (Multi-Timeframe Momentum): 40% weight
- MRB (Mean Reversion Bollinger): 25% weight
- MLB (ML Breakout): 35% weight

Execution gate: confidence >= 0.60, no conflicting signals (both sides > 0.40).

Key code path:
```python
# strategies/ensemble.py:40-164
def get_ensemble_signal(mtm_signal, mrb_signal, mlb_signal, regime, weights):
    votes = {"buy": 0.0, "sell": 0.0, "neutral": 0.0}
    # ... weighted accumulation per strategy
    best_direction = max(votes, key=votes.get)
    confidence = votes[best_direction]
    if confidence < MIN_ENSEMBLE_CONFIDENCE:
        return DecisionType.NO_TRADE, confidence, details
```

### 2. Agent-Based Pipeline (`core/agents/`)
Four specialized agents connected via EventBus:
- `TechnicalAnalystAgent` — SMA crossover + momentum (emits SignalEvent)
- `BullBearResearcherAgent` — majority vote from analysts (emits consensus)
- `RiskAuditorAgent` — confidence/R:R/duplicate checks (emits RiskEvent)
- `PortfolioManagerAgent` — final assembly + position limits (emits final SignalEvent)

```python
# core/agents/base.py:14-41
class Agent(ABC):
    def observe(self, event: Event) -> None: ...
    def act(self) -> Optional[Event]: ...
    def reset(self) -> None: ...
```

## Consequences
+ Ensemble reduces regime-specific drawdowns
+ Agent pipeline provides audit trail for every decision
+ Weights configurable via `QuantConfig.strategy_weights`
+ Sub-strategies can be swapped without changing ensemble logic
- Weight tuning requires backtesting (current weights from blueprint)
- Agent pipeline adds ~50µs latency (negligible for M15)

## Configuration
```python
# core/config.py:72-77
strategy_weights: dict = field(default_factory=lambda: {
    "mtm": 0.40,
    "mrb": 0.25,
    "mlb": 0.35,
})
ensemble_confidence_threshold: float = 0.60
```

## Alternatives Considered
1. **Stacking ensemble** — rejected: requires trained meta-model, overfitting risk
2. **Bayesian model averaging** — rejected: complex, marginal benefit over weighted vote
3. **Single agent with rules** — rejected: no separation of concerns

## References
- `strategies/ensemble.py:40-164` — weighted vote logic
- `core/agents/analyst.py:28-150` — technical analyst agent
- `core/agents/researcher.py:24-90` — consensus aggregator
- `core/agents/risk_auditor.py:33-134` — risk gatekeeper
- `core/agents/portfolio_manager.py:24-92` — final signal assembly
