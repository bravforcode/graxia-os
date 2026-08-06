# Pre-Registration — Trial 3011: XAUUSD H1 Intraday Mechanisms (Direction J)

**Status:** RESOLVED — REJECTED 2026-08-06 (3 arms, best dk_t=0.94)
**Direction J** (`reports/stopping_rule_2026_08_06_direction_j.md`, ledger `research/trial_ledger_j.json`)

## Hypothesis

Intraday (H1) rule-based mechanisms on XAUUSD produce net-of-true-cost edge.
XAUUSD H1 data (50k bars) + true costs (0.65 bps rt, commission=0) enable
high-frequency testing that weekly COT could not. Arms are the engine-compatible
strategies NOT yet tested on XAUUSD H1.

## Arms (FROZEN — strategy defaults)

| Arm | Strategy | Family |
|-----|----------|--------|
| 3011a | `VolumeBreakout` | breakout w/ volume |
| 3011b | `HybridMomMR` | momentum+MR hybrid |
| 3011c | `LiquiditySweepV2` | liquidity sweep |

(These were tested on forex H1 in 9003 — REJECT there — but NEVER on XAUUSD
H1, whose cost (0.65 bps) is ~40% lower and whose microstructure differs.)

## Method

- XAUUSD H1 (50k bars), BacktestEngine measured-cost path, trailing-window
- Per-arm: pooled DK t on per-trade returns; GO t>2.0 & Sharpe>0, MARGINAL t>1.5, REJECT otherwise
- Trial: PROMOTE if any GO; CONDITIONAL if any MARGINAL; REJECT otherwise
- Min trades >= 100 per arm

## Stopping rule

Consecutive-fail entering: 1/3 (3003). REJECT here -> 2/3.

## Provenance

Stamped via registry_schema.stamp_trial_entry() (trial 3011, id DIRJ-XAU-H1-MECH).
