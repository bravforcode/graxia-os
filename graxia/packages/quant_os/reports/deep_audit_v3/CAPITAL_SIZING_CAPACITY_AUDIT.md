# PHASE 10 — CAPITAL, POSITION SIZING & CAPACITY AUDIT
*Per R1–R18. Tier 2.*

---

## 10.1 — Sizing Formula
- Backtest: `backtest/engine.py:92-118` `_historical_size` — **fixed-fractional, risk-based** (`risk_budget = equity × risk_per_trade_bps/10000`, divided by per-lot loss to SL). Not Kelly, not volatility-targeted (size does not scale with 1/ATR; the SL distance absorbs volatility). → effectively fixed-fractional with vol-sensitivity only via SL distance.
- Live: `risk/position_sizer.py`, `position_sizer_v2.py` exist `[not traced]`.
- Volatility-targeted? **No** (no explicit 1/ATR or EWMA-vol scaling in `_historical_size`).

## 10.2 — Kelly / Optimal-f
- `[NOT DERIVED]`. No Kelly fraction computed or stated.
- Given confirmed state (no statistically significant edge; net-negative on the only costed run), **Kelly on current expectancy outputs ≤ 0.** Sizing any capital at a positive Kelly fraction today is a category error — there is no edge to size. `core/kelly.py` exists (module) but `[not run]`. → the honest answer to "what does Kelly output today?" is **0 (do not bet)**.

## 10.3 — Capacity Ceiling
- `[NOT COMPUTED]`. No slippage-vs-size curve (2×/5×/10×) run. `reports/capacity_ceiling.py` exists as a script but `[no output artifact]`.
- Intraday session liquidity (Asian vs London/NY) not checked → liquidity implicitly assumed infinite. → P2.
- Max account size at which returns hold: **"not computed."**

## 10.4 — Drawdown-Adjusted Sizing & Ruin Probability
- `backtest/risk_of_ruin.py`, `core/monte_carlo.py` exist → capability. **Result `[not reported]`.**
- Anti-martingale (reduce size after DD): `tests/test_antimartingale_tiers.py` exists → *tested*. ✓ (capability confirmed)
- Risk of ruin to margin-call level: `[not computed]`.

## 10.5 — Realistic Return Expectation (Net of Everything)
Constructing the chain with cited numbers (the only costed run, `SUMMARY.md`):
```
gross edge/trade: +$0.21 (67 trades, $14.31 gross)
− spread:         $0.17
− slippage (P90): $0.39
− commission:     [SUMMARY does not separate; engine charges $3.5/lot/side]
− swap:           [dead flag — Phase 7.1 — $0 modeled]
− FX friction:    [not modeled]
= net/trade:      −$0.35  (≈ −$23.21 / 67)
× frequency (67 trades / 7 days ≈ 9.6/day)
× realistic size
= ANNUALIZED, capital-aware return: NEGATIVE.
```
**There is no statistically significant edge; the realistic net expectation is negative.** Per protocol 10.5, I do not substitute a hypothetical number for a missing one. The honest estimate today is **≤ 0 net return; the comparison vs a passive benchmark (e.g., not trading, or a broad index fund) favors not trading this system.**

---

## Phase 10 — Verdict

**STATUS: FAIL / N/A-by-precondition.** No Kelly, no capacity ceiling, no ruin probability, no realistic positive return chain. **Critically: sizing capital for a non-edge is the error this phase exists to prevent.** The correct capital allocation to an unconfirmed-edge, net-negative-expectancy strategy is **0 until an edge is demonstrated.**
