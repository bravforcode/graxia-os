# Pre-Registration — Trial 9002: Forex 4-Pair RSI Mean-Reversion (Direction H)

**Status:** RESOLVED — REJECTED 2026-08-06 (verdict stamped with provenance)
**Direction H** (`reports/stopping_rule_2026_08_06_direction_h.md`, ledger `research/trial_ledger_h.json`)

## RESULT (2026-08-06)

| Pair | Trades | PF | NW t | Sharpe |
|------|--------|-----|------|--------|
| USDCAD | 1,407 | 0.898 | -1.84 | -2.17 |
| USDCHF | 1,435 | 0.883 | -2.16 | -2.15 |
| AUDUSD | 1,375 | 0.917 | -1.50 | -1.48 |
| NZDUSD | 1,392 | 0.874 | -2.51 | -2.54 |

**Pooled DK t = -4.549, Sharpe > 0 in 0/4 assets → REJECT.** The fade-extremes
mechanism loses on all 4 pairs at measured costs (incl. fill-simulator P90
slippage). Combined with 9001 (ML direction classifier), **both the momentum
and mean-reversion families fail on these pairs** — strongly suggesting no
simple rule-based edge at H1 on USDCAD/USDCHF/AUDUSD/NZDUSD after real costs.
Direction H consecutive-fail count: **2/3** (§4.4 — one more consecutive
REJECT stops the direction).

## Hypothesis

Fading RSI extremes on the 4 forex pairs (USDCAD/USDCHF/AUDUSD/NZDUSD, H1)
produces net-of-measured-cost edge. Trial 9001 (XGBoost next-bar-direction
classifier, same pairs + costs) REJECTED with t = -8.2 to -17.4 — the
**momentum/continuation** family loses significantly. Mean reversion is the
**structurally opposite** mechanism: buy oversold (RSI < 30), sell overbought
(RSI > 70), expecting reversion rather than continuation. Distinct from the
closed spaces: 1005/1006 were XAUUSD-only regime/spread MR; 1034/1035 were
M15 scalpers without filter (post-mortem); 8001-8003 were BTCUSD/EURUSD
trend. This is the first RSI-MR test on these 4 pairs at H1.

## Frozen parameters (LOCKED 2026-08-06 — no tuning after this point)

- **Strategy**: `RSIMeanReversion` (`strategies/rsi_mean_reversion.py`)
- **Signal**: RSI(14) < 30 → BUY; RSI(14) > 70 → SELL (Wilder smoothing)
- **EMA filter**: disabled (ema_period=0) — pure fade-extremes mechanism
- **Risk**: ATR(14), SL = 2.0×ATR, TP = 3.0×ATR
- **Sizing**: risk_per_trade_bps=50, max_positions=1
- **Timeframe**: H1, full 50,000 bars (2018-06 → 2026-07)
- **Instruments**: USDCAD, USDCHF, AUDUSD, NZDUSD (same 4 as 9001)
- **Costs**: measured FROM_TICKS from config/cost_calibration.json
  (USDCAD 14.14 rt bps, USDCHF 14.25, AUDUSD 14.28, NZDUSD 14.68) —
  `SymbolCostProfile.for_symbol` fail-closed path; no default-cost fallback
- **Engine**: BacktestEngine measured-cost path (slippage_pips=None → profile)

## Gates (frozen, pooled Driscoll-Kraay on daily cross-sectional means)

- **GO**: DK t > 2.0 AND Sharpe > 0 in >= 3/4 assets
- **MARGINAL**: DK t > 1.5 OR Sharpe > 0 in >= 2/4 assets
- **REJECT**: otherwise
- **Min trades**: >= 100 per pair (template gate; fail-closed if underpowered)

## Stopping-rule bookkeeping

Direction H consecutive-fail count: 1/3 entering this trial (9001 REJECT).
A REJECT here → 2/3; a third consecutive REJECT triggers Direction H stop (§4.4).

## Provenance

Stamped at verdict time via `research/registry_schema.stamp_trial_entry()`
(trial_number=9002, id=DIRH-FX4-RSI-MR-H1). Pre-registration discipline (F27):
this file exists BEFORE any backtest runs — FROZEN 2026-08-06 prior to execution.

## Sacred holdout

NOT used (LOCKED, Phase 4.5 only).
