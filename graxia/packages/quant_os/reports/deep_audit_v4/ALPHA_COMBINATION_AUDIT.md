# PHASE 14 — ALPHA COMBINATION & ENSEMBLE CONSTRUCTION AUDIT (Tier 1! R23 applies)
**Quant OS Deep Audit v4.0 | Date: 2026-07-05 | Auditor: auditor agent**

---

## 14.1 Combination Methodology

### How Signals Are Combined
- **`strategies/ensemble.py:197-345`**: `get_ensemble_signal()` collects sub-signals from all registered strategies.
- Weighted voting: each strategy's `confidence × weight` contributes to `buy_score` or `sell_score` (line 256-259).
- Normalized by total_weight (line 266-267).
- Decision: highest score below 0.60 threshold → NO_TRADE. If both > 0.4 → conflict → NO_TRADE. Otherwise: BUY or SELL (line 275-285).

### Weight Source
- **`strategies/ensemble.py:469-473`**: Hardcoded `STRATEGY_WEIGHTS = {"mtm": 0.40, "mrb": 0.25, "mlb": 0.35}`.
- **`strategies/ensemble.py:368-421`**: `adjust_weights()` — online rebalancing via rolling Sharpe proxy (mean/std of recent PnLs). Blended with learning_rate=0.10.
- **Initial weights assigned** via `add_strategy()` (line 147-172): If no weight given, even distribution (1/N).

---

## 14.2 Independence of Combined Signals

### Strategy Correlation
- **No cross-strategy correlation matrix** found in the codebase.
- `risk/ewma_correlation.py` and `risk/correlation_provider.py` exist for portfolio-level correlation tracking but are NOT used to measure strategy signal correlation.
- MTM (momentum/trend), MRB (mean reversion/breakout), MLB (machine learning) are nominally different approaches, but:
  - In trending regimes: MTM and MLB may both be long, creating pseudo-independence.
  - In mean-reverting regimes: MRB may be short while MTM is long — these cancel, reducing ensemble signal.
- **Without correlation measurement**: Cannot verify `|ρ| < 0.7` independence threshold. The ensemble may be combining redundant strategies with correlated errors.

---

## 14.3 Marginal Contribution Test

### Status: ❌ NOT PERFORMED
- No ablation study found where each component is removed and OOS degradation measured.
- If removing MRB improves ensemble Sharpe → MRB is dead weight.
- If removing MLB drops Sharpe by 50% → ensemble overdependent on one component.

---

## 14.4 Ensemble-Level Multiple Testing

### Combination Method Selection
- **`strategies/ensemble.py:275-285`**: Decision rules:
  1. `best_score < 0.60` → NO_TRADE
  2. `norm_buy > 0.4 AND norm_sell > 0.4` → NO_TRADE (conflict)
  3. Else → BUY or SELL by majority
- These thresholds (0.60, 0.40) appear hand-set, not cross-validated. If multiple thresholds were tried on the same backtest data and the best one selected, that IS an additional hypothesis test inflating Type I error.
- **No correction** (Bonferroni, Holm, Benjamini-Hochberg) applied for:
  - Multiple strategy selection (choosing 3 of N possible strategies)
  - Multiple threshold optimization
  - Multiple weight configurations

---

## 14.5 Ensemble Weight Derivation

### Current Weights
- **`strategies/ensemble.py:469-473`**:
  ```python
  STRATEGY_WEIGHTS = {
      "mtm": 0.40,
      "mrb": 0.25,
      "mlb": 0.35,
  }
  ```

### Origin of Weights
- **No documentation** found explaining how 40/25/35 was derived.
- Possible sources (none confirmed):
  1. Hand-set based on intuition
  2. Optimized on in-sample data (p-hacking risk)
  3. Equal risk contribution
  4. Backtest grid search

### Sensitivity Analysis — NOT PERFORMED
Required comparisons (none found):
| Weight Config | MTM | MRB | MLB | Expected Impact |
|---|---|---|---|---|
| Current | 0.40 | 0.25 | 0.35 | Headline Sharpe |
| Equal | 0.33 | 0.33 | 0.33 | Baseline test |
| MTM-only | 1.00 | 0 | 0 | Is ensemble adding value? |
| MRB-only | 0 | 1.00 | 0 | Dead weight check |
| MLB-only | 0 | 0 | 1.00 | ML dependency check |
| Permuted A | 0.25 | 0.40 | 0.35 | Weight permutation |
| Permuted B | 0.35 | 0.25 | 0.40 | Weight permutation |

**If Sharpe peaks sharply at exactly 40/25/35 and degrades at 33/33/33, the weights were optimized on in-sample data and the ensemble Sharpe is upward-biased.**

---

## 14.6 Signal-Conflict Threshold and NO_TRADE Logic

### `norm_buy > 0.4 && norm_sell > 0.4` → NO_TRADE
- **`strategies/ensemble.py:278-281`**: "strong disagreement" → NO_TRADE.
- **Origin of 0.4**: Unknown. No calibration documentation.
- **Fraction of historical bars**: Unknown. Never measured.
- **Only handling mechanism**: This is the ONLY conflict-handling mechanism in the ensemble. There is no:
  - Signal strength override
  - Regime-based override
  - Partial sizing for conflicted signals
  - Escalation to human review

---

## 14.7 ⚠️ ENSEMBLE CONSENSUS SL/TP NULL-VALUE AUDIT — P0 CANDIDATE ⚠️

### Current Code State (Verified 2026-07-05)
**`strategies/ensemble.py:425-459` — `_consensus_levels()`**:

```python
@staticmethod
def _consensus_levels(
    votes: Sequence[EnsembleVote],
    current_price: Decimal,
) -> tuple[Decimal | None, Decimal | None]:
    """
    Weighted-average stop-loss / take-profit across winning-side votes.
    Falls back to ``None`` when no sub-signal provided SL/TP.
    """
    if not votes:
        return None, None          # ← Line 436

    votes_with_sl = [v for v in votes if v.stop_loss is not None]   # ← Line 439
    votes_with_tp = [v for v in votes if v.take_profit is not None]  # ← Line 440

    consensus_sl = None             # ← Line 442
    consensus_tp = None             # ← Line 443

    if votes_with_sl:               # ← Only if sub-strategies provide SL
        # ... weighted average ...
    if votes_with_tp:               # ← Only if sub-strategies provide TP
        # ... weighted average ...

    return consensus_sl, consensus_tp   # ← Line 459: May return (None, None)
```

### Trace Downstream
1. **Ensemble** calls `_consensus_levels()` at `ensemble.py:302`
2. Result passed to `Signal.create()` at `ensemble.py:308-316` with `stop_loss=consensus_sl, take_profit=consensus_tp`
3. **If sub-strategies don't provide SL/TP**: Signal is created with `stop_loss=None, take_profit=None`
4. **Order flow**: `execution/manager.py:103-113` — `create_order()` accepts optional `stop_price`. Order created without SL.
5. **Risk gate**: `pre_trade_risk.py:25-98` — does NOT check for SL presence. `require_stop_loss=True` in RiskPolicy (line 23) is **declarative only, never enforced by any check**.
6. **Result**: Order submitted to broker with **NO STOP-LOSS**.

### Trade Record Status
- **No evidence** that an ensemble-generated live/paper trade was submitted without stop-loss (need to check trade logs for `stop_price IS NULL` entries).
- **Per R23**: Absence of historical incident does NOT reduce severity. This is a latent P0 bug waiting to manifest.

### Previous Audit Finding Reference
- `AUDIT_INDEX.md` or previous audit files may have documented this as a `TODO("Fill from sub-strategies SL/TP")`. The code now has weighted averaging logic (lines 439-457), which is an improvement, but it still returns `(None, None)` when sub-strategies don't provide levels.

---

## 14.8 Cross-Strategy Position Netting Logic

### Duplicate Order Protection
- **`execution/idempotency.py:38-76`**: Idempotency key = `sha256(symbol:side:qty:strategy:signal:time_bucket_60s)`.
- **`execution/manager.py:116`**: Checks idempotency before order creation.

### Same-Instrument, Same-Direction from Different Strategies
- **Scenario**: MTM generates BUY XAUUSD at T=0. MLB generates BUY XAUUSD at T=1 (different minute bucket).
- **Idempotency check**: Different time bucket → different key → passes. Orders NOT deduplicated.
- **No position netting**: The OMS would submit two separate orders, resulting in two separate MT5 positions on the same instrument in the same direction.
- **Risk**: Double exposure. If both positions have no SL (see 14.7), total risk is 2× intended.

### Cross-Strategy Position Limit
- **`risk/pre_trade_risk.py:77`**: `max_positions = 5`. But this counts all positions across all instruments. No per-instrument stacking limit.

---

## TOP FINDINGS — Phase 14

| # | Severity | Finding |
|---|---|---|
| 1 | P0 | **Ensemble SL/TP = (None, None)**: `_consensus_levels()` returns `(None, None)` when sub-strategies don't provide SL/TP. `require_stop_loss=True` in RiskPolicy is NEVER enforced. Orders can go live with NO stop-loss. |
| 2 | P0 | **No cross-strategy position netting**: MTM and MLB both signaling BUY on same instrument → two separate orders, double exposure, two MT5 positions. No per-instrument stacking limit. |
| 3 | P0 | **Weight derivation unknown**: 40/25/35 weights have no documented origin. If optimized on in-sample data, ensemble Sharpe is overstated. Sensitivity analysis not performed. |
| 4 | P0 | **No adversarial testing of ensemble**: Zero of 7 adversarial tests run at ensemble level. |
| 5 | HIGH | **No marginal contribution test**: Cannot distinguish between ensemble adding value vs ensemble being dead-weight average of correlated strategies. |
| 6 | HIGH | **Multiple testing uncorrected**: Strategy selection + threshold selection + weight selection are all hypothesis tests inflating Type I error with no correction. |
| 7 | MEDIUM | **Conflict threshold untested**: 0.4 threshold origin unknown, fraction of bars hitting it unknown. Only conflict-handling mechanism. |
