# Dry-Run Analysis Report
Date: 2026-06-29 15:03 - 16:03 (UTC+7)
Duration: 60 minutes | Interval: 60s

## Summary
- Total cycles: 60
- Approved trades: 11 (18.3% approval rate)
- Rejected trades: 49

## Signal Distribution
- BUY signals: 11 (approved: 4)
- SELL signals: 36 (approved: 7)
- HOLD signals: 13

## Price Movement
- Start: 4064.08
- End: 4048.72
- Change: -15.36 (-0.38%)
- Range: 4045.59 - 4066.80

## Approved Trades
- Cycle 5: BUY @ 4065.30 (Conf: 0.87, Guards: 9/9)\n- Cycle 10: BUY @ 4064.77 (Conf: 0.94, Guards: 9/9)\n- Cycle 16: BUY @ 4064.72 (Conf: 0.89, Guards: 9/9)\n- Cycle 21: SELL @ 4062.26 (Conf: 0.95, Guards: 9/9)\n- Cycle 27: SELL @ 4061.36 (Conf: 0.95, Guards: 9/9)\n- Cycle 32: BUY @ 4063.90 (Conf: 0.95, Guards: 9/9)\n- Cycle 37: SELL @ 4061.73 (Conf: 0.95, Guards: 9/9)\n- Cycle 42: SELL @ 4056.85 (Conf: 0.95, Guards: 9/9)\n- Cycle 48: SELL @ 4055.65 (Conf: 0.87, Guards: 9/9)\n- Cycle 53: SELL @ 4051.78 (Conf: 0.95, Guards: 9/9)\n- Cycle 58: SELL @ 4046.21 (Conf: 0.95, Guards: 9/9)\n
## Guard Rejection Breakdown
- 42x Cooldown active\n- 4x Low confidence: 0.00\n- 1x Low confidence: 0.31\n- 1x Low confidence: 0.34\n- 1x Low confidence: 0.33\n
## Signal Quality Analysis
- Cooldown is working correctly (42 rejections = prevented overtrading)
- Engine correctly identifies trend direction (SELL signals during downtrend)
- BUY signals during downtrend resulted in losses
- Overall: Engine is conservative and risk-aware

## Recommendation
The engine is working as designed:
1. Safety guards are active and effective
2. Cooldown prevents overtrading
3. Signal generation needs improvement for trend-following
4. Ready for extended dry-run testing
