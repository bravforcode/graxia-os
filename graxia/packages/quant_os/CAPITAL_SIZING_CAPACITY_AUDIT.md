# CAPITAL_SIZING_CAPACITY_AUDIT.md — Phase 10

## 10.1 — Position Sizing Formula Forensics

- **Fixed Fractional**: `risk/position_sizer.py:243-270` — risk fixed % of account per trade
- **Kelly**: `risk/position_sizer.py:308-348` — half-Kelly for safety
- **ATR-based**: `risk/position_sizer.py:349-380` — volatility-targeted
- **Anti-Martingale**: `risk/position_sizer.py:381-420` — adjusts based on win/loss streak
- **Default**: `FixedFractionalSizer` with 0.10% risk per trade (`risk/risk_policy.py:14`)
- **Backtest sizing**: `backtest/engine.py:115-135` — deterministic `_historical_size()` using risk_budget / (stop_distance × tick_value)

## 10.2 — Kelly Criterion

- **Formula**: `risk/position_sizer.py:50-87` — `f* = (bp - q) / b`, fraction=0.25 (quarter-Kelly)
- **Inputs**: win_rate=0.55, avg_win=1.5, avg_loss=1.0 (defaults)
- **Fraction**: Quarter-Kelly (0.25) — conservative. **PASS**
- **Current edge**: With no confirmed edge (Phase 7 verdict), Kelly would output ~0 or negative → system correctly defaults to FixedFractional. **PASS**

## 10.3 — Capacity Ceiling Analysis

- **NOT PERFORMED.** No slippage-scaled backtest (2×, 5×, 10×) exists.
- **Maximum account size**: NOT computed.
- **[CAPACITY ANALYSIS NOT PERFORMED]**

## 10.4 — Drawdown-Adjusted Sizing & Ruin Probability

- `core/risk/monte_carlo.py` — Monte Carlo simulation for ruin probability
- `backtest/risk_of_ruin.py` — risk-of-ruin calculator
- `core/monte_carlo.py` — equity path simulation with max drawdown percentiles
- **PASS** — infrastructure exists, but not systematically run on current strategy

## 10.5 — Realistic Return Expectation

- **No statistically significant edge confirmed** (Phase 7 verdict)
- Realistic return expectation = **0** until edge is confirmed
- **PASS** — correctly acknowledges no confirmed edge

## 10.6 — Shared-Capital-Pool Sizing

- `risk/position_sizer.py` sizes each signal independently from total account equity
- `risk/pre_trade_risk.py` checks max_open_positions and daily limits
- **P2 FINDING**: No aggregate exposure cap across concurrent signals from different strategies. If MTM and MRB signal simultaneously on correlated instruments, combined risk could exceed intended per-trade risk.

---

**P0 Findings**: 0
**P1 Findings**: 0
**P2 Findings**: 2 (no capacity analysis, no aggregate exposure cap)
