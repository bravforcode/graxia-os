# Sizing Safety Floor Rationale

## Floor Values

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `min_stop_distance` | 0.1% of entry price | XAUUSD Razor spread = 0.20-0.50. At entry 2000, 0.1% = 2.0 = 4-10x spread. Stops tighter than spread killed by execution costs. 0.1% = minimum viable stop that survives real-world slippage + spread. |
| `vol_floor` | 0.03 (3% annualized) | XAUUSD normal realized vol = 10-20% ann. 3% = 6x below normal = extreme anomaly regime. Moskowitz et al. (2012) vol-scaling uses similar floor — below floor, signal has no statistical power. Floor prevents vol_scale explosion when realized vol → 0. |

## Why NOT other values

- **0.05% stop floor**: Too tight. Would still allow positions 2x larger than 0.1% floor. Spread alone eats 0.01-0.025% of entry on XAUUSD.
- **0.01 vol floor (old)**: Allows vol_scale = 10x. At 3% realized vol, strategy sizing 3.3x normal — still aggressive but bounded.
- **0.05 vol floor**: Too conservative. Would cap vol_scale at 2x even during genuine low-vol trending regimes.

## Design principle

Floor = "below this, data has no signal". Not "tune until backtest passes".
