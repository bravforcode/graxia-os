# MATH CORRECTNESS AUDIT
**Phase 3 | 2026-07-05**

---

## 3.1 — Return Calculation
- Walk-forward uses fractional returns (`target_return` column) — correct
- Returns are forward-looking (label at t+1, features at t) — alignment confirmed in `scripts/walk_forward.py:41-48`

## 3.2 — Transaction Cost Model

### Backtest Engine (`backtest/engine.py`)
- **Spread:** Configurable via `BacktestConfig.spread_pips` (default 2.0 pips). Dynamic spread model available via `backtest/dynamic_spread_model.py`.
- **Commission:** `BacktestConfig.commission_per_lot` = $3.50/lot/side. Applied on entry and exit.
- **Slippage:** Modeled via `ExecutionSimulator` with half-spread + latency + market impact + adverse selection.
- **Cost calculation in engine:** `execution/execution_simulator.py:170-180` uses `calculate_trade_costs()` from `execution/cost_model.py`.
- **Unit chain verified:** spread_points × contract_size × volume = spread_cost in account currency. ✅

### Walk-Forward Script (`scripts/walk_forward.py`)
- **BUG CONFIRMED:** Line 88: `price_mult = 2350.0` — hardcoded after assertion checks
- Line 90: `raw_pnl_dollars = dir_mask * rets * (close_prices[mask] if close_prices is not None else 2350.0)` — uses actual close prices ✅
- Line 91: `cost_per_dollars = (spread_cost + slippage_p90) * price_mult` — uses 2350.0 ❌
- **Impact:** Costs are computed at XAUUSD=$2350 price level. At current XAUUSD ~$3300, costs are understated by ~1.4×. For other instruments (EURUSD ~1.08), costs are overstated by ~2170×.
- **Severity:** P0 — this directly corrupts walk-forward net PnL figures.

### Previous ~2000x Cost Bug Status
- Prior audit found missing `*2350` multiplier in `compute_fold_pnl`. Current code has the multiplier but it's hardcoded to 2350.0 instead of using actual prices for cost calculation.
- **Status:** `[FIX PARTIALLY VERIFIED — raw PnL uses real prices, cost calc still hardcoded]`

## 3.3 — Performance Metrics Formulas

| Metric | Implementation | Annualization Factor | Status |
|---|---|---|---|
| Sharpe Ratio | `backtest/metrics.py` + `walk_forward.py:109` | `sqrt(252 * 390)` (walk-forward) — this is for M1 bars with ~390 trading minutes/day | **INCORRECT for 24h markets** — FX/crypto trade ~1440 min/day, not 390 |
| Win Rate | `walk_forward.py:102` | N/A | ✅ |
| Max Drawdown | `walk_forward.py:99-100` | N/A | ✅ (cumulative min) |

### Sharpe Annualization Factor Issue
- `walk_forward.py:109`: `sharpe = sr_mean / sr_std * np.sqrt(252 * 390)`
- 390 = US equity market minutes (6.5 hours). FX trades 24h, crypto 24/7.
- For M1 FX data: correct factor should be `sqrt(252 * 1440)` ≈ 602, not `sqrt(252 * 390)` ≈ 312.
- **Impact:** Sharpe ratios from walk-forward are **understated by ~1.93×** for FX instruments. This is a conservative error (makes results look worse than reality).

## 3.8 — Hardcoded-Price-Constant Forensic Sweep

**Confirmed instances of 2350.0 hardcoded:**

| File | Line | Context | Status |
|---|---|---|---|
| `scripts/walk_forward.py` | 88 | `price_mult = 2350.0` (fallback after assertions) | **BUG** — cost calc uses this |
| `scripts/backtest_cost.py` | 116 | `price_arr = np.full(len(target_return), 2350.0)` | **BUG** — fallback price |
| `scripts/backtest_cost.py` | 249 | `avg_price = ... if ... else 2350.0` | **BUG** — fallback |
| `scripts/research_approaches.py` | 61, 105, 151, 192 | `trades.sum() * 2350` | **BUG** — dollar conversion |
| `execution/broker_adapter.py` (PaperBroker) | ~380 | `base_prices["XAUUSD"] = Decimal("3300.00")` | OK — updated fallback price |

**Verdict:** The 2350.0 hardcoded constant appears in 5+ locations across scripts. The main walk-forward path has it at line 88 where it affects cost calculations. Raw PnL calculation (line 90) correctly uses actual close prices when available.
