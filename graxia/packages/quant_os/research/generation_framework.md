# Hypothesis Generation Framework — 7 Categories

**Prior probability reminder:** RYDC Arm A returned p=0.9680 — strong null. New hypotheses have LOW prior probability. Each must justify why structurally different from RYDC.

**Sacred holdout is one-shot.** Opening = 1 trial. Phase 4.5 only.

---

## 1. Cross-Asset Momentum

**Mechanism:** Returns in one asset predict returns in another over multi-day horizon. Persistent because cross-asset rebalancing dominated by slow institutional mandates.

**Data:** Cross-asset daily/H1 (equities, bonds, commodities, FX). 5+ years.

**Pitfalls:** Search #1 already scanned crudely. Cross-asset correlations drift with regime. FX/equity carry flows dominate 1-5 day windows.

---

## 2. Volatility Risk Premium (VRP)

**Mechanism:** Implied vol > realized vol. Sell-vol strategies collect premium from hedgers overpaying for protection.

**Data:** VIX/GVZ daily, realized vol series, option chain data.

**Pitfalls:** Tail-risk events blow up short-vol. Realized vol subject to look-ahead bias. Broker margin/assignment rules make backtest non-replicable.

---

## 3. Session-Based Patterns

**Mechanism:** Returns/spreads/volatility vary by trading session. Persistent because liquidity providers differ by session.

**Data:** Tick/minute-bar with timezone. 3+ years.

**Pitfalls:** Most "session patterns" are post-hoc single-instrument scans. Broker session ≠ underlying market hours. DST shifts boundaries. Funding costs destroy cross-session edges.

---

## 4. Orderflow Imbalance

**Mechanism:** Net aggressive buy/sell orderflow predicts short-term price moves. Persistent because not all participants see full order book.

**Data:** L2/L3 order book, trade tape with aggressor flag.

**Pitfalls:** Historical orderbook backtest rarely faithful. Tape-reading alpha decays fast in liquid markets. CFD orderbook ≠ exchange orderbook.

---

## 5. Macro Regime

**Mechanism:** Returns/vol/correlation vary by macro state (recession, hiking, cutting). Persistent because macro states last months-to-years.

**Data:** NBER dates, FFR, CPI, 10Y yield, credit spreads. 5+ years.

**Pitfalls:** <30 trades per regime = meaningless. NBER dates backfilled. Macro factor models heavily arbitraged.

---

## 6. Carry + Momentum

**Mechanism:** Carry (positive expected return from holding premium asset) + momentum (recent returns continue). Combo works because carry pays for being wrong about slow factor, momentum pays for fast factor.

**Data:** Daily forward points/term premium, asset returns. 5+ years.

**Pitfalls:** Carry crashes wipe out years of small wins. Swap costs on retail CFDs often exceed implied carry. Lookback-period choice = overfitting source.

---

## 7. Mean Reversion with Regime

**Mechanism:** Short-term overshoots revert, but speed/direction depend on regime. Persistent because behavioral overreaction coexists with persistent regimes.

**Data:** Price series with z-score, regime classifier, transaction costs. 5+ years.

**Pitfalls:** Exactly the post-hoc rationalization the framework prevents. Regime classifiers fitted = lower OOS accuracy. MR in trending assets = known loser. Transaction costs destroy intraday MR.

---

## Cross-Cutting Requirements

1. Pre-registration mandatory before any backtest
2. Arm selection one-way — pick one, write it down
3. Validation gates fixed — no relaxation
4. Sample size checked before running
5. Cumulative trial count sacred — DSR input always cumulative
6. Sacred holdout one-shot — Phase 4.5 only
7. Document hashing at lock

## Forbidden

- "Let me see what parameters fit best" = Search #1
- "Try opposite arm" without new pre-registration = PBO=0.5
- "Lower gate slightly" = invalid test
- "Just one more backtest" past 20 = cap is real
- "Peek at holdout" = opening IS the test
