# MATH_CORRECTNESS_AUDIT.md — Phase 3

## 3.1 — Return Calculation

- **Formula**: Simple returns via `pct_change()` — `close[t]/close[t-N] - 1`
- **Code location**: `ml/pipeline.py:95-98`, `scripts/build_features.py:314-317`
- **Units**: Percentage returns (not log returns)
- **Consistency**: Returns used in feature engineering are percentage. Backtest P&L uses price units × quantity × contract_size.
- **Verdict**: PASS — returns are correctly computed

## 3.2 — Transaction Cost Model

### Raw Inputs (from `core/cost_model.py`)
| Asset Class | Spread (bps) | Commission/Lot | Slippage (bps) |
|---|---|---|---|
| METALS (XAUUSD) | 12.0 | $0 (embedded) | 0.5 |
| FOREX (EURUSD) | 1.0 | $7.00 RT | 0.3 |
| CRYPTO (BTCUSD) | 5.0 | $0 (embedded) | 2.0 |

### Backtest Cost (`backtest/engine.py:204-206`)
```python
slippage_pips: float = 0.5
spread_pips: float = 2.0  # Configurable spread in pips
commission_per_lot: Decimal = Decimal("3.5")
```

### BUG CONFIRMED: Metals Double-Count
`backtest/engine.py:206` defaults to `commission_per_lot=3.5` for ALL instruments including metals. But `core/cost_model.py:53` correctly sets metals `commission_per_lot=0.0` (embedded in spread). The backtest engine does NOT use `core/cost_model.py` by default — it uses its own hardcoded defaults.

**P0 FINDING**: Every metals backtest double-counts commission ($3.50/lot on top of the spread that already includes it). This UNDERSTATES net edge for metals.

### Cost Computation Chain
```
spread_pips × pip_value × lots = spread_cost
commission_per_lot × lots = commission_cost
slippage_pips × pip_value × lots = slippage_cost
total = spread_cost + commission_cost + slippage_cost
```

### Hardcoded Price Constant Bug (3.8)
`scripts/backtest_cost.py:116`: `price_arr = np.full(len(target_return), 2350.0)` — hardcoded gold price used for cost-to-return conversion. **CONFIRMED BUG** — should use actual price series.

`scripts/backtest_cost.py:249`: `avg_price = float(np.mean(close_trades)) if close_trades is not None else 2350.0` — another hardcoded fallback.

`scripts/run_lagged_wf.py:107-108`: `gross = (wins * 0.0001 - losses * 0.00005) * 2350.0` — hardcoded price in P&L calculation. **CONFIRMED BUG**.

`gold_bot/core/engine.py:402`: `base_price = 2350.0  # Current gold price approx` — hardcoded in engine initialization.

## 3.3 — Performance Metrics Formulas

### Sharpe Ratio
**Canonical implementation**: `backtest/metrics.py:403-426`
```python
def _sharpe_ratio(returns, risk_free_rate, bars_per_year):
    bar_rf = risk_free_rate / bars_per_year
    excess_returns = [r - bar_rf for r in returns]
    avg_excess = sum(excess_returns) / len(excess_returns)
    std_return = (sum((r - avg_excess)**2 for r in excess_returns) / (len(excess_returns)-1)) ** 0.5
    return (avg_excess / std_return) * math.sqrt(bars_per_year)
```
**Formula**: `(mean(r) - rf) / std(r) × sqrt(bars_per_year)` — **CORRECT**

**Annualization factor lookup**: `backtest/metrics.py:20-48` has `BARS_PER_YEAR` dict mapping (asset_class, timeframe) → bars_per_year. For M15 forex: 24,192. For D1: 252. **PASS**

### Multiple Sharpe Implementations (RISK)
At least 6 different Sharpe implementations exist across the codebase:
1. `backtest/metrics.py:403` — canonical, uses `bars_per_year` parameter
2. `backtest/phase_3b_metrics.py:100` — uses `periods_per_year` parameter
3. `validation/walk_forward.py:255` — uses `bars_per_year` parameter
4. `validation/overfitting_detector.py:234` — hardcoded `sqrt(252)`
5. `execution/tca_framework.py:156` — hardcoded `sqrt(252)`
6. `donchian_deep_dive.py:149` — hardcoded `sqrt(252)`

**P1 FINDING**: Inconsistent annualization across modules. Modules using hardcoded `sqrt(252)` will produce WRONG results for intraday data (M15, H1).

### Max Drawdown
`backtest/metrics.py:355-382`: Calculated from equity curve. **PASS** — correctly computed on equity curve (including costs).

## 3.4 — Signal/Prediction Direction

- Positive signal → BUY. Negative → SELL. Defined in `core/enums.py:SignalType`
- Convention consistent from feature → model → order: `ml/pipeline.py:211` classifies `forward_return > threshold` as BUY (label=1)
- **PASS**

## 3.5 — Position Sizing Mathematics

`risk/position_sizer.py:50-87`: Kelly fraction formula `f* = (b*p - q) / b` — **CORRECT**
`backtest/engine.py:115-135`: `_historical_size()` uses risk_budget / (stop_distance × tick_value) — **CORRECT**
Rounding: `quantize(ROUND_DOWN)` to volume_step — **PASS**
Floor check: returns Decimal("0") if below volume_min — **PASS

## 3.6 — Implausible-Result Forensic Protocol

No Sharpe ratios above ~3-4 observed in the current codebase's canonical metrics. Historical 84.6 and 100.9 Sharpe figures mentioned in the audit protocol are from prior code states — **[HISTORICAL BUG NOT RE-VERIFIED]**.

## 3.7 — Deflated & Probabilistic Sharpe Ratio

- **DSR**: Implemented in `validation/deflated_sharpe.py:39` — `deflated_sharpe_ratio()` function
- **PBO**: Implemented in `validation/probability_overfitting.py:59` — `calculate_pbo_from_matrix()` function
- Both wired into `validation/overfitting_detector.py` and `validation/pipeline/runner.py`
- **PASS** — both metrics are computed and integrated

## 3.8 — Hardcoded-Price-Constant Forensic Sweep

| File | Line | Hardcoded Value | Impact |
|---|---|---|---|
| `scripts/backtest_cost.py:116` | `2350.0` | Gold price for cost conversion | P&L error proportional to price deviation |
| `scripts/backtest_cost.py:249` | `2350.0` | Fallback avg price | Same |
| `scripts/run_lagged_wf.py:107-108` | `2350.0` | P&L calculation | Direct P&L error |
| `gold_bot/core/engine.py:402` | `2350.0` | Base price for signals | Signal quality affected |
| `backtest/xauusd_liquidity_sweep_fixture.py:23` | `2350.0` | Test fixture price | Test only |
| `demo_campaign/drills.py:94,122,192,215` | `2350.0` | Drill entry prices | Drill only |

**CONFIRMED**: 4 instances in production/backtest code (not just tests) that use hardcoded gold price. At current ~$3,200 gold price, these produce ~37% P&L error.

---

**P0 Findings**: 1 (metals commission double-count)
**P1 Findings**: 2 (inconsistent Sharpe annualization, hardcoded price constants)
**P2 Findings**: 0
