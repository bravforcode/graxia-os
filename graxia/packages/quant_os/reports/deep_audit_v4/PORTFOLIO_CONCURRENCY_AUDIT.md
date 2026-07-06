# PHASE 15 — PORTFOLIO, CORRELATION & CONCURRENT-STRATEGY AUDIT
**Date**: 2026-07-05 | **Scope**: Full codebase | **Severity Scale**: P0=Critical P1=High P2=Medium P3=Low

---

## 15.1 Inventory of Concurrent Strategies/Instruments

### Strategies (run concurrently)
| Strategy | Module | Symbols | Timeframes | Regime Filter |
|----------|--------|---------|------------|---------------|
| MTM (Multi-Timeframe Momentum) | `strategies/mtm.py:37-50` | EURUSD, GBPUSD, USDJPY, AUDUSD, XAUUSD | M15, H1, H4 | TREND_STRONG_UP, TREND_STRONG_DOWN, TREND_WEAK |
| MRB (Mean Reversion Bollinger) | `strategies/mrb.py:42-52` | EURUSD, GBPUSD, USDCHF, AUDUSD | M15 | RANGE_BOUND, LOW_VOLATILITY |
| MLB (ML-Enhanced Breakout) | `strategies/mlb.py:47-62` | EURUSD, GBPUSD, USDJPY, XAUUSD | M15 | TREND_STRONG_UP, TREND_STRONG_DOWN, HIGH_VOLATILITY |

### Instruments (15 total from ASSET_CLASS_COMMANDS)
`risk/kill_switch.py:22-27`:
- Metals (4): XAUUSD, XAGUSD, XAUEUR, XAUJPY
- Crypto (5): BTCUSD, ETHUSD, SOLUSD, ADAUSD, XRPUSD
- Forex (10): EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, EURGBP, EURJPY, GBPJPY
- Indices (6): US30, NAS100, SPX500, GER40, UK100, JP225

### Potential concurrency matrix
| | MTM | MRB | MLB |
|---|---|---|---|
| EURUSD | ✅ | ✅ | ✅ |
| GBPUSD | ✅ | ✅ | ✅ |
| USDJPY | ✅ | — | ✅ |
| AUDUSD | ✅ | ✅ | — |
| XAUUSD | ✅ | — | ✅ |
| USDCHF | — | ✅ | — |

**EURUSD, GBPUSD, and XAUUSD can receive signals from 2 strategies simultaneously.** USDJPY can receive from 2. This creates real concurrent-signal risk.

---

## 15.2 Correlation & Aggregate Risk

### Correlation Infrastructure
- `core/correlation.py:30-132` `CorrelationFilter`: Pearson correlation of returns, 100-bar lookback. Returns multipliers: 1.0 (no corr), 0.5 (>0.7), 0.0 (>0.9). Tracked per-symbol.
- `core/portfolio_risk.py:38-162` `PortfolioRisk`: Hardcoded CORRELATED_PAIRS set (EURUSD/GBPUSD, AUDUSD/NZDUSD, XAUUSD/XAGUSD). Checks correlated_risk ≤ 3%.
- `risk/portfolio.py:43-217` `PortfolioRisk` (different class!): Computes per-position VaR/CVaR, correlation matrix from position returns.

### ⚠️ GAP — P0: Correlation filters not wired to pre-trade gate
- `core/correlation.py:84-122` `get_multiplier()` checks correlation with open positions and returns a multiplier
- **But this multiplier is never consumed by any pre-trade risk gate**
- The `CorrelationFilter` must be explicitly called — it's not integrated into the trading loop
- `risk/pre_trade_risk.py:25-98` does NOT check correlation at all — only position count, daily loss, drawdown, margin

### ⚠️ GAP — P1: Portfolio-level risk limit vs per-strategy limits
- Each strategy has `risk_per_trade_pct: 1.0` (MTM), `0.8` (MRB), `1.0` (MLB) — all defined independently
- `risk/portfolio_heat.py:82` flags positions with >2% individual heat, but this is post-facto monitoring, not a pre-trade gate
- No global check: "total portfolio risk from all strategies must not exceed X%"
- `core/portfolio_risk.py:50` defines `MAX_TOTAL_RISK_PCT = 0.05` but `can_add()` is not called from the live trading loop

---

## 15.3 Capital Allocation Logic

### Current allocation
`core/config.py:93-99`:
```python
strategy_weights = {
    "mtm": 0.40,
    "mrb": 0.25,
    "mlb": 0.35,
}
```

### ⚠️ CRITICAL — P0: Strategy weights are NOT used for position sizing
- The strategy weights exist in config but are **never referenced by PositionSizer or any sizing logic**
- Each strategy's `calculate_position_size()` methods use the **full account balance**, not `balance × strategy_weight`
- The weights appear to be for ensemble signal voting only, not capital allocation

### Ad hoc or systematic?
**Ad hoc.** The weights are hardcoded magic numbers (0.40/0.25/0.35). There is no:
- Risk-parity allocation
- Performance-weighted rebalancing
- Minimum variance optimization
- Equal risk contribution

### Fraction of capital allocated
If no edge is confirmed: **the honest answer is 0%**. The research (`Meta/research_edge_cost_report.md`) shows net negative after costs. Any positive capital allocation to the current models is inconsistent with the evidentiary standard.

---

## 15.4 Full Cross-Asset Correlation Matrix

### BTCUSD-NAS100 correlation
**Not computed in codebase.** The `SYMBOL_ASSET_CLASS` mapping in `core/trading_loop.py:51-72` includes both indices (NAS100) and crypto (BTCUSD) but no cross-class correlation infrastructure exists. The `CorrelationFilter` in `core/correlation.py` computes pairwise return correlations but requires price series to be fed via `update()` — it is not driven by live market data feeds.

### Tail correlation
**Not addressed.** No tail-dependency measure (Kendall's tau, copula, or extreme value theory) is implemented. The standard Pearson correlation in `core/correlation.py:59-82` and `risk/portfolio.py:203-217` assumes linear dependence and is known to be unreliable during crisis events when correlations spike.

### Regime-dependent correlation
`core/kelly.py:115-127` `kelly_adjust_for_regime()` adjusts Kelly fraction by regime (NORMAL=1.0, HIGH_UNCERTAINTY=0.5, CRISIS=0.0) — but this is a factor on Kelly, not on correlation assumptions.

---

## 15.5 Portfolio-Level VaR / Concentration Limits

### VaR/CVaR
- `risk/portfolio.py:158-170` `estimate_var()`: Historical simulation VaR from position returns, weighted by market value. Returns `Decimal` at 95% confidence.
- `risk/portfolio.py:172-187` `_compute_var()`: Internal method producing both VaR_95 and CVaR_95.
- **These are computed from position returns but not used as pre-trade gates.**

### Concentration Limits
- `core/portfolio_risk.py:51` `MAX_PER_SYMBOL_PCT = 0.02` (2% per symbol)
- `core/portfolio_risk.py:131` checks per-symbol risk
- No per-asset-class limit (e.g., "max 30% of risk budget in crypto")
- No per-strategy limit

### ⚠️ GAP — P1: Uncorrelated assumption
Both `risk/portfolio.py:158-170` VaR and the portfolio checks assume independent positions when correlation data hasn't been fed. The `get_correlation_matrix()` at `risk/portfolio.py:134-156` computes correlations from position returns — but if positions have no return history, correlation is 0.0 (implicitly assuming independence).

---

## 15.6 Strategy-Level Correlation (MTM/MRB/MLB)

### Signal Correlation
The three strategies operate on different regimes:
- MTM: Trend-following (EMA crossovers, RSI momentum)
- MRB: Mean-reversion in ranges (Bollinger Bands, Stochastic, ADX<25)
- MLB: Breakout with ML confirmation

**Signal correlation during transitions**: In a market shifting from range to trend, MRB could signal mean-reversion (fading a breakout) while MLB simultaneously signals breakout continuation. These opposing signals could cancel on the same instrument BUT could fire on correlated instruments (e.g., MTM long XAUUSD, MRB short EURUSD).

### Return Correlation
**Not computed.** No backtest or live analysis has measured the pairwise correlation of strategy equity curves. The expected result for MTM/MRB is low or negative correlation (trend vs mean-reversion), but this is untested.

### Actual Diversification or Same Bet Repackaged?
- MTM and MRB target **different regimes** (trend vs range) with different signal logic — genuine diversification
- MTM and MLB are **both momentum/trend-focused** — likely correlated
- The ensemble `strategies/ensemble.py` exists but strategy correlation is not measured

---

## 15.7 Concurrent-Strategy Status Confirmation

### ⚠️ CRITICAL — P0: N/A path DOES NOT apply
The system architecture supports:
- 3 strategies (MTM/MRB/MLB) running on the same event bus
- Shared capital pool (all strategies reference same account balance via `get_config()`)
- 15 instruments (8 in default symbols + 7 more in kill-switch asset class lists)
- Multiple instruments sharing signal paths (EURUSD, GBPUSD, XAUUSD)

**The concurrent-strategy, shared-capital, multi-instrument scenario is NOT hypothetical — it is the design intent of the system.** The N/A designation for concurrent-strategy controls is **incorrect and dangerous**. The system MUST implement:
1. Strategy-level capital allocation (not just unused config weights)
2. Pre-trade combined-risk gate across all strategies
3. Correlation-adjusted portfolio heat limits
4. Cross-strategy position limit enforcement

---

## Top Findings (Phase 15)

| # | Severity | Finding |
|---|----------|---------|
| 1 | **P0** | Strategy weights exist but are NOT used for capital allocation — all strategies use full account balance, enabling 3× combined risk |
| 2 | **P0** | CorrelationFilter exists but is NOT wired to any pre-trade gate — correlated positions slip through unchecked |
| 3 | **P0** | Portfolio-level risk limits (MAX_TOTAL_RISK_PCT=5%) defined but `can_add()` never called from live trading loop |
| 4 | **P1** | No per-asset-class concentration limits (e.g., crypto max exposure) — 5 crypto + 4 metals + 10 forex in same pool |
| 5 | **P1** | VaR/CVaR computed from position returns but assumes independence when positions lack return history (implicitly rho=0) |
