# ALPHA COMBINATION AUDIT
**Phase 14 | 2026-07-05 | TIER 1**

---

## 14.1 — Combination Methodology
- **Method:** Weighted voting (`strategies/ensemble.py`)
- **Weights:** MTM=40%, MRB=25%, MLB=35% (`ensemble.py:443-447`)
- **Derivation:** `[UNVERIFIED — no code found deriving these weights from optimization]`. Appears to be hand-set constants.

## 14.5 — Ensemble Weight Derivation Audit
- Weights are defined as module-level constants, not computed from any optimization
- No evidence of weight fitting on training data
- No sensitivity check found (equal weight 33/33/33, permuted weights, etc.)
- **Status:** `[UNVERIFIED — weights appear arbitrary]`

## 14.6 — Signal-Conflict Threshold
- `ensemble.py:274-276`: When `buy_score > 0.4 AND sell_score > 0.4`, returns `NO_TRADE`
- The 0.4 threshold is a suspiciously round number (R14) — no optimization evidence
- No other netting logic beyond this single conflict rule

## 14.7 — Ensemble Consensus SL/TP Null-Value Audit (P0, R23)

### CONFIRMED BUG
```python
# strategies/ensemble.py:421-433
@staticmethod
def _consensus_levels(
    votes: Sequence[EnsembleVote],
    current_price: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    # For simplicity, return None — callers can override with their own levels.
    return None, None
```

### Impact Analysis
- Every signal emitted by `StrategyEnsemble.get_ensemble_signal()` carries `SL=None, TP=None`
- **Backtest path:** `backtest/engine.py:_execute_signal()` line ~460: `if not signal.stop_loss or signal.stop_loss <= 0: return` — signals are **silently dropped**. No trades are taken. This means the ensemble has **never produced a backtest trade** through the canonical engine.
- **Live path:** Must trace `core/orchestrator.py` → `TradingLoop` → `OMS` → `MT5Adapter.submit_order()` to determine if `SL=None` results in:
  - (a) Order rejection (safe)
  - (b) Order with no stop-loss (P0 unbounded risk)
  - (c) Some fallback default substitution (needs verification)

### Severity
**P0 per R23** — a risk control that can silently degrade to `None`/no-op. The ensemble is the system's primary signal source, and it currently cannot produce valid SL/TP levels.

---

## 14.8 — Cross-Strategy Position Netting
- No evidence of position deduplication when multiple strategies signal same direction on same instrument
- `backtest/engine.py:_execute_signal()` checks `for pos in self.positions.values(): if pos.symbol == signal.symbol: return` — prevents duplicate positions per symbol in backtest
- Live path deduplication not confirmed
