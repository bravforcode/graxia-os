# PHASE 10 — CAPITAL, POSITION SIZING & CAPACITY AUDIT
**Date**: 2026-07-05 | **Scope**: Full codebase | **Severity Scale**: P0=Critical P1=High P2=Medium P3=Low

---

## 10.1 Position Sizing Formula Forensics

### Active Sizer Inventory

| Sizer | Module | Method | Formula |
|-------|--------|--------|---------|
| FixedFractionalSizer | `risk/position_sizer.py:243-305` | Fixed-fractional | `units = (balance × risk_pct/100) / abs(entry − stop)` → then `/ contract_size` → lots |
| KellySizer | `risk/position_sizer.py:308-399` | Half-Kelly (hardcoded) | `f = (b×p−q)/b × 0.5`, capped at `_DEFAULT_RISK_PCT` |
| ATRSizer | `risk/position_sizer.py:402-458` | ATR volatility-targeted | `units = risk_amount / (ATR × atr_multiple)`, falls back to FixedFractional if ATR=0 |
| AntiMartingaleSizer | `risk/position_sizer.py:461-560` | Streak-adjusted fixed-fractional | Reduces risk to 25% after 3 consecutive losses, increases to max 2x after 3 wins |
| size_position() | `risk/position_sizer_v2.py:23-220` | Broker-native (v2) | Uses MT5 `calc_profit_fn` for one-lot loss → `risk_budget / one_lot_loss` → rounds DOWN to `volume_step` |

### Primary Formula (FixedFractionalSizer — the default)
**`risk/position_sizer.py:255-305`**:
```
risk_amount = account_balance × (risk_pct / 100)
price_risk = |entry_price - stop_loss|
units = risk_amount / price_risk
lots = units / units_per_lot  → quantized to 0.01 (ROUND_DOWN)
```

### Formula (size_position v2 — broker-native)
**`risk/position_sizer_v2.py:53,138`**:
```
risk_budget = equity × risk_policy.risk_per_trade_fraction  (= equity × 100bps/10000 = 0.01×equity)
raw_volume = risk_budget / one_lot_loss
rounded_volume = ROUND_DOWN(raw_volume / volume_step) × volume_step
```

### Volatility Estimator Used
- **ATR(14)** in ATRSizer (`risk/position_sizer.py:412`) — classic Wilder's ATR
- **No** GARCH, Parkinson, or Yang-Zhang estimators
- **No** realized volatility from tick data
- Default sizer (FixedFractional) uses **no volatility estimator at all** — position size is purely a function of stop distance

### ⚠️ CRITICAL FINDING: Risk silently degrading to None (R23)
**`risk/position_sizer_v2.py:127-131`**: When `calc_profit_fn` returns None (e.g., MT5 unavailable, stale snapshot), the code falls back to a naive tick-value estimate:
```python
ticks = stop_distance / contract_spec.trade_tick_size
one_lot_loss = ticks * contract_spec.trade_tick_value
```
If `trade_tick_value` is also None/zero (uninitialized ContractSpec), `one_lot_loss = 0`, which means `raw_volume = Decimal("0")`. The position is silently zeroed — but **no alert is raised**. This is a **P0 risk control degradation**.

**`risk/position_sizer_v2.py:128-129`** comment says "ponytail: naive fallback" — the lack of alerting on fallback is a gap.

---

## 10.2 Kelly Criterion / Optimal-f Derivation

### Two Kelly Implementations (duplication)

| Implementation | Module | Kelly Fraction | Rationale |
|---|---|---|---|
| `kelly_fraction()` | `risk/position_sizer.py:50-87` | **Quarter-Kelly** (0.25) | Default argument, no stated rationale |
| `KellySizer` class | `risk/position_sizer.py:308-399` | **Half-Kelly** (0.5) | "Half-Kelly for safety" comment at line 319 |
| `kelly_fraction()` | `core/kelly.py:30-72` | **Half-Kelly** (0.5) | Third implementation! Clamped to `[0.01, 0.05]` (hard min 1%) |

### ⚠️ CRITICAL: Three conflicting Kelly implementations
- `risk/position_sizer.py` standalone: quarter-Kelly
- `risk/position_sizer.py` KellySizer class: half-Kelly
- `core/kelly.py`: half-Kelly with hard MIN_FRACTION=0.01 (always returns at least 1%)
- **This third one is dangerous**: even with negative edge, it returns MIN_FRACTION=0.01 (still risks 1%). The negative edge at `core/kelly.py:61-64` logs a warning but does NOT return 0.

### What single input flips "bet" to "don't bet"?
For full Kelly: `f* = (b×p − q)/b`. f* becomes ≤ 0 when `b×p ≤ q`, i.e., `win_rate × payoff_ratio ≤ loss_rate`.

With the actual KellySizer defaults (win_rate=0.55, avg_win=1.5, avg_loss=1.0 → b=1.5):
- f* = (1.5×0.55 − 0.45)/1.5 = (0.825−0.45)/1.5 = 0.375/1.5 = **0.25** (full Kelly)
- If win_rate drops 20% → 0.44: f* = (1.5×0.44−0.56)/1.5 = (0.66−0.56)/1.5 = 0.1/1.5 = **0.067** (still positive)
- If avg_win drops 20% → 1.2: b=1.2, f* = (1.2×0.55−0.45)/1.2 = (0.66−0.45)/1.2 = 0.175
- **Win rate below ~40%** (given b=1.5): f* = (1.5×0.40−0.60)/1.5 = 0 → **flips to zero**

### Kelly Output TODAY (honest assessment)
The research_edge_cost_report (`Meta/research_edge_cost_report.md`) documents: **58.2% OOS accuracy at conf≥0.75, net -$23.21**. With costs at 83% of gross edge, the strategy has **no statistically significant OOS edge**.

If win rate input = observed 58.2% with avg_win=avg_loss (break-even after costs):
- `core/kelly.py` would still return **MIN_FRACTION=0.01** (it always floors to 1%)
- `risk/position_sizer.py` standalone `kelly_fraction()`: f* = (1.0×0.582−0.418)/1.0 = 0.164 × 0.25 = **0.041 (4.1%)** — this is **wrong** because it doesn't account for costs
- **Honest Kelly output**: ~0 if net-of-costs edge is zero or negative. **The current code has no mechanism to input net-of-costs win_rate/payoff.**

---

## 10.3 Capacity Ceiling Analysis

### ⚠️ NOT COMPUTED — P1
- No capacity ceiling computation exists in the codebase
- No slippage market-impact model that scales with position size beyond the flat `backtest_slippage_pips=0.5` (`core/config.py:128`)
- No Asian vs London/NY overlap liquidity assumptions encoded
- `risk/slippage_model.py` exists but must be examined for dynamic scaling

### Slippage at scale
With the flat 0.5 pip slippage assumption:
- 2× base position: same slippage cost (unrealistic)
- 5× base position: same slippage cost (unrealistic)
- 10× base position: same slippage cost (unrealistic)
- **Infinite liquidity is implicitly assumed** — no volume profile check, no order-book depth check

### Maximum Account Size
**Not computed.** The infrastructure provides no mechanism to determine at what account size the strategy stops being viable. This is a **P1 gap**: without a capacity ceiling, a live account could silently transition from a valid-size strategy to an oversized, slippage-eroded one.

---

## 10.4 Drawdown-Adjusted Sizing & Ruin Probability

### Ruin Probability
- **`core/risk/monte_carlo.py:11-47`**: `bootstrap_equity_paths()` exists and IS implemented — computes `prob_ruin` from actual trade PnLs via bootstrapping. Returns probability of hitting `kill_switch_balance` within `n_trades_forward`.
- **`core/monte_carlo.py:95-265`**: Legacy MonteCarloSimulator computes `survival_rate` (fraction of sims with DD < threshold).
- **However**: Neither is called from the live trading loop. `bootstrap_equity_paths()` requires >=300 trades but is gated behind manual invocation — not automated.

### Anti-Martingale
- **`risk/position_sizer.py:461-560`**: `AntiMartingaleSizer` reduces size after consecutive losses. After 2 losses → 50%, after 3+ losses → 25%. Increases after wins: 2 wins → 1.25x, 3+ wins → 1.5x (capped at 2x).
- **But**: This sizer is NOT the default. `get_default_sizer()` at line 563 returns `FixedFractionalSizer` — constant risk regardless of streak.

### Probability of 20%/50% Drawdown
- The `core/monte_carlo.py:117` `max_drawdown_pct` parameter defaults to 20% but is only used as a threshold filter in `survival_rate` computation.
- No specific probability-metric for 50% drawdown computed anywhere.

---

## 10.5 Realistic Return Expectation (Net of Everything)

### Edge Chain (from code audit)
| Cost Layer | Source | Value |
|---|---|---|
| Gross edge (directional accuracy) | `Meta/research_edge_cost_report.md` | 58.2% @ conf≥0.75 |
| Round-trip spread (XAUUSD) | `core/cost_model.py:53` METALS.spread_bps | 12 bps (~0.12%) |
| Commission (XAUUSD Razor) | `core/cost_model.py:54` | $0 (embedded) |
| Commission (FOREX Razor) | `core/cost_model.py:63` | $7/lot RT |
| Slippage (typical) | `core/cost_model.py:45,63,73` | 0.3-2.0 bps |
| Swap long XAUUSD | `core/cost_model.py:56` | -0.5 bps/day |
| Swap short XAUUSD | `core/cost_model.py:57` | +0.2 bps/day |
| Cost/move ratio | `Meta/research_edge_cost_report.md:9` | **~83%** |

**Net edge per trade**: Gross ~58.2% accuracy − cost burden 83% = **effectively zero or negative net edge**.

### ⚠️ CRITICAL FINDING — P0
The `core/cost_model.py:89-107` maps symbols to cost params, but the backtest engine uses flat `backtest_slippage_pips=0.5` and `backtest_commission_per_lot=3.5` (`core/config.py:128-129`) — these are **generic defaults that don't match the per-asset-class CostParams**. The cost model exists but is not wired into the backtest cost calculation consistently.

### Honest annualized return expectation
**Cannot be stated as positive with confidence.** The research edge cost report explicitly states net -$23.21 on 67 trades. A statistically significant edge has not been demonstrated OOS. Stating a hypothetical positive return would violate the evidence standard.

---

## 10.6 Shared-Capital-Pool Sizing

### Architecture
- 3 strategies (MTM/MRB/MLB) share `strategy_weights` in `core/config.py:93-99`: MTM=40%, MRB=25%, MLB=35%
- 8 symbols in default config (`core/config.py:53-55`), 15 instruments total in ASSET_CLASS_COMMANDS (`risk/kill_switch.py:22-27`)
- **PositionSizer is NOT weight-aware**: Each strategy calls `PositionSizer.calculate()` independently with the full account balance, not its allocated fraction

### ⚠️ CRITICAL FINDING — P0: Combined Risk Not Limited
**`risk/portfolio_heat.py:34-95`** (`calculate_portfolio_heat`) computes total heat as sum of (entry−stop)×qty across all positions — this IS the mechanism. BUT:
- The pre-trade gate `risk/pre_trade_risk.py:25-98` checks `risk_ledger.open_positions >= risk_policy.max_positions` but does NOT compute combined heat before approving a new trade
- If MTM signals XAUUSD long (risk $100) and MRB simultaneously signals XAGUSD long (risk $50), the combined $150 risk could be approved if both pass individually, even though XAUUSD and XAGUSD are correlated (CORRELATED_PAIRS in `core/portfolio_risk.py:56-60`)
- **No real-time combined-risk check before order submission**

### Concrete example (dollars):
- Account: $10,000. RiskPolicy: 1% per trade ($100 risk budget per signal)
- MTM signals XAUUSD buy with risk $95 → approved individually
- MRB signals EURUSD buy with risk $85 → approved individually
- MLB signals GBPUSD buy with risk $90 → approved individually
- **Combined risk = $270 = 2.7% of account** — exceeds what any single strategy would risk, but no gate catches this because the three positions go through separate signal paths

---

## Top Findings (Phase 10)

| # | Severity | Finding |
|---|----------|---------|
| 1 | **P0** | Three conflicting Kelly implementations: quarter-Kelly vs half-Kelly vs MIN_FRACTION=0.01 (never returns 0) |
| 2 | **P0** | Combined risk across strategies not limited pre-trade — 3 strategies can simultaneously risk 3× the per-strategy limit |
| 3 | **P0** | `size_position()` falls back to naive tick-value without alerting (risk control silently degrading) |
| 4 | **P1** | No capacity ceiling computed — infinite liquidity assumed at all position sizes |
| 5 | **P1** | CostModel not wired into backtest — backtest uses flat generic costs, not asset-class-specific `CostParams` |
