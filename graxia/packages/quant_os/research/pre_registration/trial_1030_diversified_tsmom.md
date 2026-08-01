# Trial #1030: Diversified Time-Series Momentum (DTSMOM)

**Status**: PENDING  
**Registered**: 2026-07-30  
**Strategy File**: `strategies/diversified_tsmom.py`  
**Validation Runner**: `scripts/validate_dtsmom_strategy.py`

## Hypothesis

Diversified TSMOM across all 16 assets with inverse-vol weighting and threshold rebalancing produces a robust edge with Sharpe > 0.5, dk_t > 2.0, and survives jackknife leave-one-out without single-asset dependency.

## Economic Rationale

1. **Moskowitz, Ooi, Pedersen (2012)**: TSMOM across 58 futures yields Sharpe 1.0+
2. **Pitkajarvi (2020)**: Cross-asset TSMOM yields Sharpe +45% vs single-asset
3. **Barroso (2015)**: Vol targeting doubles Sharpe vs naive TSMOM
4. **Vanguard (2024)**: Threshold rebalancing beats calendar-based by 15-25 bps
5. **Springer (2026)**: 1/N is "remarkably difficult to outperform"

## Pre-Registered Parameters (FROZEN)

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `universe` | ALL 16 assets | Maximize diversification |
| `mom_lookback` | 252 days | Classic 12-month TSMOM window |
| `vol_target` | 0.10 | 10% annual vol per asset (Barroso 2015) |
| `vol_lookback` | 63 days | 3-month vol estimation |
| `rebalance_drift` | 0.05 | 5% drift threshold (Vanguard 2024) |
| `max_position_pct` | 0.15 | 15% max per asset |
| `min_history_days` | 504 | 2 years (12mo lookback + warmup) |

## Key Differentiators vs Trial #1029 (RAM)

1. **TSMOM signal** (sign of 12mo return) not regime-conditional momentum/mean-reversion switching
2. **Inverse-vol weighting** not equal-weight
3. **Threshold rebalancing** not daily rebalancing
4. **All 16 assets** not 7
5. **Simpler → more robust** (YAGNI principle)

## Validation Gates

1. **dk_t > 2.0**: Driscoll-Kraay t-statistic for pooled significance
2. **WFE > 0.3**: Walk-forward efficiency (OOS/IS Sharpe)
3. **Majority positive OOS**: More than half of walk-forward windows positive
4. **Cost stress > 0**: Sharpe remains positive at 1.5x costs
5. **No sign flip**: Jackknife leave-one-out doesn't flip sign on any single asset

## Expected Outcome

Based on equal-weight baseline analysis:
- Equal-weight across 16 assets = Sharpe 0.491, Max DD -22.74%, Return 4.21%
- Average cross-asset correlation = 0.110 (excellent diversification)
- With inverse-vol weighting + TSMOM signal, expected Sharpe improvement: +20-40%

## Risk Factors

- Transaction costs on 16 assets could erode edge
- Threshold rebalancing may miss optimal entry/exit points
- 12-month lookback may be too slow for fast-moving markets
- BTC/ETH may dominate portfolio due to higher vol
