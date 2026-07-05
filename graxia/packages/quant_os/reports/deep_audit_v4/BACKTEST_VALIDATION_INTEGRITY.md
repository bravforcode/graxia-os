# BACKTEST VALIDATION INTEGRITY
**Phase 7 | 2026-07-05 | TIER 1**

---

## 7.1 — Transaction Cost Model (Final Verification)
- **Where costs are subtracted:** `backtest/engine.py:_close_position()` — commission deducted from PnL
- **Spread model:** `backtest/dynamic_spread_model.py` — time-of-day spread variation
- **Slippage model:** Half-spread + latency + market impact + adverse selection (`execution_simulator.py:158-165`)
- **Swap costs:** `enable_swap=True` in config but `swap_cost.py` not wired — **cost model incomplete**
- **Worst-case scenario test:** Not found — no 2× spread re-run

## 7.2 — Fold Construction
- `scripts/walk_forward.py:163-180`: Sliding window with `train_window`, `test_window`, `step`
- No gap between train-end and test-start — potential autocorrelation bleed
- Row-count based folds (variable time length)

## 7.3 — Order Execution Realism
- **Signal timing:** Signal from closed bar N → fill on bar N+1 (`execution_simulator.py:145`)
- **Fill price:** Bid/ask estimated from next bar OHLC + spread + slippage
- **Realistic:** Yes — next-bar fill with bid/ask estimation

## 7.6 — Final Verdict

> **Is there currently a statistically significant, cost-adjusted, out-of-sample edge?**
> **INSUFFICIENT EVIDENCE**

- Number of OOS trades: Unknown (walk-forward exists but has cost calculation bugs)
- Sharpe ratio with CI: Not computed with correct annualization
- p-value: Not computed with multiple-testing correction
- Multiple-testing correction: Not applied

## 7.9 — Per-Instrument Walk-Forward Coverage Table

| Instrument | Asset Class | Walk-Forward Run? | OOS Sharpe | Meets Data Sufficiency? |
|---|---|---|---|---|
| EURUSD | FX | YES | [BUGGY — 2350 cost] | NO (5,001 M1 rows) |
| GBPUSD | FX | NO | — | NO |
| USDJPY | FX | NO | — | NO |
| USDCAD | FX | NO | — | NO |
| USDCHF | FX | NO | — | NO |
| AUDUSD | FX | NO | — | NO |
| NZDUSD | FX | NO | — | NO |
| BTCUSD | Crypto | NO | — | NO |
| ETHUSD | Crypto | NO | — | NO |
| NAS100 | Indices | NO | — | NO |
| US30 | Indices | NO | — | NO |
| XAUUSD | Metals | YES | [BUGGY — 2350 cost] | NO (5,001 M1 rows) |
| XAGUSD | Metals | NO | — | NO |
| XPDUSD | Metals | NO | — | NO |
| XPTUSD | Metals | NO | — | NO |

**13 of 15 instruments have NO OOS EVIDENCE.**
