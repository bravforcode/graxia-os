# WallStreet-style Asian Scalper (Trial 1035)

- **Trial:** 1035
- **Track:** EA-BENCH (benchmark of EA-style scalpers vs existing quant_os strategies)
- **Registered:** 2026-08-04
- **Status:** PRE-REGISTERED (NOT yet backtested formally)
- **Sacred holdout:** LOCKED — `data/sacred_holdout/holdout.csv` NOT touched
- **Cumulative trial count entering:** 1050+ (per `validation/n_trials` reconciliation)
- **Post-cap note:** Trial 1035 is post-cap (cap=1022 consumed; extended per stopping_rule_2026_07_30). Recorded for audit trail — same precedent as 1028/1031/1032/1033.

---

## 1. Why this trial exists (honest lineage)

**Motivation (verified research, 2026-08-04):** WallStreet Robot is the only
other verifiable long-lived EA on MyFxBook (15+ years, win 76%, avg win 8.3
pips, PF 1.37, account 10254966). Its public profile is a high-win-rate,
small-target scalper trading the Asian session. FXStabilizer/Money Tree (the
high-win% alternatives) were identified as martingale family and are NOT
benchmarked (DD 25-50% structural).

**This trial:** benchmark the closest *honest, non-martingale* approximation
of WallStreet Robot's profile — an Asian-session (00:00-08:00 UTC) range
scalper on the 3 cost-calibrated FX pairs with tight ATR SL/TP, small target,
session-boundary exit — against measured costs from
`config/cost_calibration.json` (FROM_TICKS: EURUSD round_trip_bps_p95 = 7.352,
GBPUSD 7.302, USDJPY 7.372) and the same gate stack as trials 1028/1032/1033.

**Transparency:** parameters are frozen BEFORE any backtest of this benchmark
runs (no data peek — parameters mirror the EA's public behavior profile, not
fitted to the data). No parameter search after results.

## 2. Strategy specification (FROZEN)

```
asian_scalper (EURUSD, GBPUSD, USDJPY — M15):
  Session (UTC): Asian 00:00-08:00 only (bar open hour); no trades outside
  Range:         prior 20-bar high/low channel (as-of prior close)
  Entry long:    close < range_low AND RSI(14) < 30   (oversold fade)
  Entry short:   close > range_high AND RSI(14) > 70  (overbought fade)
  Stop-loss:     1.0 × ATR(14)
  Take-profit:   1.2 × ATR(14)   (small target, high win rate — WallStreet profile)
  Max positions: 1 (engine max_positions=1; no martingale, no grid)
  Exit:          SL / TP / TIME_STOP session exit (engine max_bars_open=32
                 M15 bars ≈ 8h = Asian session 00:00-08:00 UTC; prevents
                 holding into London session reversal)
```

- **Universe (FROZEN):** `EURUSD, GBPUSD, USDJPY` (WallStreet trades FX majors;
  these 3 are the only FX pairs with FROM_TICKS measured costs)
- **Timeframe:** M15, `data/{SYMBOL}_M15.csv` (50k-60k bars, 2024-01 → 2026-06)
- **Costs:** engine measured path — `SymbolCostProfile.for_symbol()` per pair
  (EURUSD 0.088/7, GBPUSD 0.076/7, USDJPY 0.124/7 spread_bps/commission_bps),
  `enable_swap=False` (no swap fields in calibration — fail-closed otherwise)
- **BacktestConfig:** `spread_pips=None, slippage_pips=None, enable_swap=False, strict_mtf=False`

## 3. FROZEN parameters

| Param | Value | Rationale |
|---|---|---|
| timeframe | M15 | scalper (WallStreet trades M5-M15) |
| session | 00:00-08:00 UTC | Asian session |
| range_lookback | 20 | M15 intraday channel |
| rsi_period | 14 | standard |
| rsi_oversold | 30 | fade entry |
| rsi_overbought | 70 | fade entry |
| atr_period | 14 | standard |
| atr_sl_mult | 1.0 | tight scalp stop |
| atr_tp_mult | 1.2 | small target (high win rate) |
| max_positions | 1 | no martingale/grid |

Frozen. If the backtest fails → REJECT and stop. No threshold tuning.

## 4. Success criteria (pre-registered — identical gates to 1028/1032/1033 + SP2)

Primary:
- **Pooled HAC t > 2.0** (`edge_search_all.run_pooled_hac_test`, verified Newey-West)
- **DSR p < 0.05** with N=1050 (`dsr_from_annualized`, unit-correct daily, ann=252)

Secondary (SP2 institutional gates — 2-of-3 required for GO):
- **WFA (purged-CV 5f):** mean OOS Sharpe > 0
- **Bootstrap CI:** lower bound > 0
- **MinBTL:** sufficient = True

Additional (all required):
- **Min trades:** >= 30 per asset
- **Cost-stress:** Sharpe > 0 at 1.5x and 2.0x total trade costs
- **Label-shuffle:** p <= 0.05
- **Jackknife:** per-symbol drop delta < 0.5 Sharpe
- **PBO:** N/A — single frozen config (no search space) — same rationale as SP2

NOTE on positive_sharpe_count: same documented deviation as trial 1034 —
4-asset benchmark universe makes the edge_search_all `positive_sharpe_count >= 5`
GO rule unreachable; REPORTED but NOT gated.

## 5. Stopping rule

- ONE hypothesis. Run once. Primary fails → REJECT, stop. No tuning.
- Sacred holdout remains LOCKED until Phase 4.5.
- Result recorded in `research/trial_ledger.json` + `research/hypothesis_registry.json`.

## 6. What happens next if PASS

If all primary + secondary gates pass: compare against verified WallStreet
Robot track record (win 76%, avg win 8.3 pips, PF 1.37) in
`reports/edge_search_m15_scalper_core4.json` benchmark table. NOT an immediate
live promotion — next step is Phase 4 paper trading readiness.
