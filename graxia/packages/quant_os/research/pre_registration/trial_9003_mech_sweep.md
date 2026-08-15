# Pre-Registration — Trial 9003: USDCAD/USDCHF Mechanism Sweep (Direction H)

**Status:** RESOLVED — REJECTED 2026-08-06 (verdict stamped with provenance)
**Direction H** (`reports/stopping_rule_2026_08_06_direction_h.md`, ledger `research/trial_ledger_h.json`)

## RESULT (2026-08-06)

| Arm | USDCAD dk_t | USDCHF dk_t | Verdict |
|-----|------------|------------|---------|
| HybridMomMR | -2.19 (3368t) | -2.60 (3286t) | REJECT |
| VolumeBreakout | -0.85 (623t) | -0.68 (627t) | REJECT |
| LiquiditySweepV2 | -0.78 (772t) | -2.23 (870t) | REJECT |
| SessionPattern | +0.004 (33.5kt) | +0.004 (33.2kt) | REJECT (flat/noise) |
| MeanRevBollinger | INSUFFICIENT | INSUFFICIENT | wall-clock filter bug |
| MultiTFMomentum | INSUFFICIENT | — | needs multi-TF data |

**Trial verdict: REJECT** — no rule-based mechanism shows edge on the two
INCONCLUSIVE pairs at corrected costs. Best arm dk_t = -0.68. Consecutive-fail
count now **2/3** (9002 + 9003; 9001 mixed not counted).

## Background

After the cost-model fix (2026-08-06, reports/audit_trial_9001_9002_cost_model.md),
Trial 9001 restamped: USDCAD (t=-1.82) and USDCHF (t=-0.68) are **INCONCLUSIVE**
— not significant losses. True round-trip costs are only **0.84 / 0.95 bps**,
so the cost hurdle is tiny. AUDUSD/NZDUSD remain REJECT (t=-4.34/-3.22) —
mechanism family fails there regardless of cost.

This trial sweeps the remaining **economically-plausible rule-based mechanisms**
on the two INCONCLUSIVE pairs. The two already-tested families (ML direction
classifier 9001, RSI mean-reversion 9002) both failed; this trial covers
structurally different signal families.

## Hypothesis

One or more of the swept rule-based mechanisms produces net-of-true-cost edge
on USDCAD and/or USDCHF at H1, where the 9001 family showed no significant
edge once costs were corrected.

## Arms (FROZEN — default params of each strategy, no tuning)

| Arm | Strategy | Family | Frozen params (strategy defaults) |
|-----|----------|--------|-----------------------------------|
| 9003a | `HybridMomMR` | momentum+MR hybrid | strategy defaults |
| 9003b | `VolumeBreakout` | breakout w/ volume confirmation | strategy defaults |
| 9003c | `MultiTimeframeMomentum` | MTF momentum | strategy defaults |
| 9003d | `MeanReversionBollinger` | BB mean reversion | strategy defaults |
| 9003e | `LiquiditySweepV2` | liquidity sweep | strategy defaults |
| 9003f | Session Pattern (`compute_sp_signals`) | FX session-conditional | SPConfig defaults (session_window=20, threshold=0.5*ATR) — pre-registered Trial 1004 params |

ML strategies (MLBreakout, MLMeanReversion) EXCLUDED — need trained models,
not rule-based; would stack model complexity on top of an untested mechanism.

## Method

- Instruments: USDCAD, USDCHF (H1, 50,000 bars)
- Engine: BacktestEngine measured-cost path (`slippage_pips=None` → SymbolCostProfile),
  `commission_per_lot=7.0` ($/lot — verified correct path), trailing-window
  subclass for O(n) indicator computation
- Costs: true FROM_TICKS calibration (USDCAD rt 0.84 bps, USDCHF 0.95 bps)
- Per-arm verdict per pair: pooled DK t on daily returns
- Arm verdict: GO if DK t > 2.0 AND Sharpe > 0; MARGINAL if t > 1.5 or
  Sharpe > 0 in 1/2; REJECT otherwise
- Trial verdict: PROMOTE if ANY arm GO on either pair; CONDITIONAL if MARGINAL;
  REJECT if no arm reaches MARGINAL

## Stopping-rule bookkeeping

Consecutive-fail count entering: 1/3 (9002). A full REJECT here → 2/3.

## Provenance

Stamped via `research/registry_schema.stamp_trial_entry()` (trial 9003,
id DIRH-FX-MECH-SWEEP). Pre-registered BEFORE any backtest runs (F27).

## Sacred holdout

NOT used (LOCKED).
