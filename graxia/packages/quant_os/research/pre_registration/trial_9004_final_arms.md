# Pre-Registration — Trial 9004: USDCAD/USDCHF Final Mechanism Arms (Direction H)

**Status:** RESOLVED — REJECTED 2026-08-06 → **DIRECTION H STOPPED (§4.4)**
**Direction H** (`reports/stopping_rule_2026_08_06_direction_h.md`, ledger `research/trial_ledger_h.json`)

## RESULT (2026-08-06)

| Arm | USDCAD dk_t | USDCHF dk_t | Verdict |
|-----|------------|------------|---------|
| Momentum12M | -1.955 (3365t) | -2.113 (3355t) | REJECT |
| TSMDXYDivergence (DXY injected) | -1.928 (789t) | -0.432 (783t) | REJECT |

**Trial verdict: REJECT → consecutive-fail 3/3 → Direction H STOPPED (§4.4).**
Every mechanism family tested across 4 trials (ML classifier, RSI-MR, hybrid
MOM+MR, volume breakout, liquidity sweep, session pattern, momentum 12m,
DXY-divergence) fails on USDCAD/USDCHF/AUDUSD/NZDUSD at true costs
(0.6-1.9 bps rt). No further trials may be registered without a new
stopping-rule document + human approval.

## Background

9003 swept 5 rule-based families — all REJECT. Remaining untested mechanisms
that are implementable with in-repo data:

1. **Momentum12M** (`strategies/momentum_12m.py`) — time-series momentum
   (Moskowitz-Ooi-Pedersen family, long-horizon). Was only ever tested on
   XAUUSD; never on USDCAD/USDCHF.
2. **TSMDXYDivergence** (`strategies/tsm_dxy_divergence.py`) — TSMOM gated by
   DXY divergence. USDCAD/USDCHF are USD-quoted pairs — DXY direction is a
   *structurally relevant* filter for them (unlike XAUUSD-only prior use).
   DXY data exists: `data/DXY_D1.csv` (2018-01 → 2026-07).
3. **Carry** — EXCLUDED: no interest-rate differential data in repo
   (pre-reg 3008's FX-carry data gap stands).

## Arms (FROZEN — default params, no tuning)

| Arm | Strategy | Params | DXY data |
|-----|----------|--------|----------|
| 9004a | `Momentum12M` | defaults (lookback 12m H1) | — |
| 9004b | `TSMDXYDivergence` | defaults, dxy_csv_path=data/DXY_D1.csv | injected |

## Method

- Instruments: USDCAD, USDCHF (H1, 50k bars)
- Engine: BacktestEngine measured-cost path (commission_per_lot=$7/lot),
  trailing-window subclass, true costs (USDCAD rt 0.84, USDCHF 0.95 bps)
- Per-arm: pooled DK t on per-trade returns; GO t>2.0 & Sharpe>0,
  MARGINAL t>1.5, else REJECT
- Trial: PROMOTE if any GO; CONDITIONAL if any MARGINAL; REJECT otherwise

## Stopping rule

Consecutive-fail entering: **2/3** (9002, 9003). REJECT here → **3/3 → Direction H STOPS** (§4.4).

## Provenance

Stamped via `research/registry_schema.stamp_trial_entry()` (trial 9004,
id DIRH-FX-FINAL-ARMS). Pre-registered BEFORE any backtest (F27).

## Sacred holdout

NOT used (LOCKED).
