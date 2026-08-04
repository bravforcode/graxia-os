# Happy Gold-style M15 Gold Scalper (Trial 1034)

- **Trial:** 1034
- **Track:** EA-BENCH (benchmark of EA-style scalpers vs existing quant_os strategies)
- **Registered:** 2026-08-04
- **Status:** PRE-REGISTERED (NOT yet backtested formally)
- **Sacred holdout:** LOCKED — `data/sacred_holdout/holdout.csv` NOT touched
- **Cumulative trial count entering:** 1050+ (per `validation/n_trials` reconciliation)
- **Post-cap note:** Trial 1034 is post-cap (cap=1022 consumed; extended per stopping_rule_2026_07_30). Recorded for audit trail — same precedent as 1028/1031/1032/1033.

---

## 1. Why this trial exists (honest lineage)

**Motivation (verified research, 2026-08-04):** independent verification of the
MyFxBook EA landscape identified **Happy Gold** as the best-verified retail EA
family (4 brokers, all accounts active, DD 8-26%, PF 2.0-3.5, monthly 6.9-8.3%).
Every other "top EA" candidate was either an affiliate product (ForexRoasted,
EA Automatic, Bullcharge), a managed service (Team POW), a grid/martingale
(FXStabilizer Turbo +3696%/DD 13.26%, Money Tree DD 46.5%), or marginal
(Pips Master Pro PF 1.15). WallStreet Robot (15+ years, win 76%, avg win 8.3
pips, PF 1.37) is the only other verifiable long-lived EA.

**This trial:** benchmark the closest *honest, non-martingale* approximation of
Happy Gold's public profile — a London/NY-session gold breakout scalper with
ATR-based SL/TP — against measured costs from `config/cost_calibration.json`
(FROM_TICKS: XAUUSD round_trip_bps_p95 = 0.852) and the same gate stack as
trials 1028/1032/1033. It is a NEW hypothesis (no prior quant_os strategy
trades XAUUSD M15 London/NY breakout).

**Transparency:** parameters are frozen BEFORE any backtest of this benchmark
runs (no data peek — parameters mirror the EA's public behavior profile, not
fitted to the data). No parameter search after results.

## 2. Strategy specification (FROZEN)

```
happy_gold_scalper (XAUUSD, M15):
  Sessions (UTC): London 08:00-16:00 OR NY 13:00-21:00 (bar open hour)
  Trend filter:   EMA(50) on M15 closes
                    long  allowed iff close > EMA(50)
                    short allowed iff close < EMA(50)
  Entry long:     close breaks above prior 20-bar high (as-of prior close)
  Entry short:    close breaks below prior 20-bar low (as-of prior close)
  Stop-loss:      1.5 × ATR(14)
  Take-profit:    2.0 × ATR(14)   (RR 1.33 — moderate, matches verified PF band)
  Max positions:  1 (engine max_positions=1; no pyramiding, no grid, NO martingale)
  Exit:           SL / TP / TIME_STOP session exit (engine max_bars_open=52
                  M15 bars ≈ 13h = London 08:00 through NY close 21:00 UTC)
```

- **Universe (FROZEN):** `XAUUSD` only (Happy Gold trades gold)
- **Timeframe:** M15, `data/XAUUSD_M15.csv` (50,000 bars, 2024-05-03 → 2026-06-20)
- **Costs:** engine measured path — `SymbolCostProfile.for_symbol("XAUUSD")`
  (FROM_TICKS: spread 0.324 bps, p95 0.426 bps, commission 0), `enable_swap=False`
  (XAUUSD has no swap fields in calibration — fail-closed otherwise)
- **BacktestConfig:** `spread_pips=None, slippage_pips=None, enable_swap=False, strict_mtf=False`

## 3. FROZEN parameters

| Param | Value | Rationale |
|---|---|---|
| timeframe | M15 | scalper (EA family trades M5-M15) |
| session_london | 08:00-16:00 UTC | Happy Gold active London/NY |
| session_ny | 13:00-21:00 UTC | NY + overlap |
| ema_period | 50 | trend filter |
| breakout_lookback | 20 | M15 intraday channel |
| atr_period | 14 | standard |
| atr_sl_mult | 1.5 | fixed |
| atr_tp_mult | 2.0 | fixed (RR 1.33) |
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

NOTE on positive_sharpe_count: the benchmark universe is 4 cost-calibrated
assets by design (XAUUSD + EURUSD + GBPUSD + USDJPY); the edge_search_all GO
rule `positive_sharpe_count >= 5` is unreachable at N=4 and is therefore
REPORTED but NOT gated in this trial (documented deviation — gate would make
the benchmark verdict meaningless).

## 5. Stopping rule

- ONE hypothesis. Run once. Primary fails → REJECT, stop. No tuning.
- Sacred holdout remains LOCKED until Phase 4.5.
- Result recorded in `research/trial_ledger.json` + `research/hypothesis_registry.json`.

## 6. What happens next if PASS

If all primary + secondary gates pass: compare against verified Happy Gold
track record (monthly 6.9-8.3%, DD 8-26%) and WallStreet Robot (PF 1.37) in
`reports/edge_search_m15_scalper_core4.json` benchmark table. NOT an immediate
live promotion — next step is Phase 4 paper trading readiness.
