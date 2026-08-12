# Research Status — 26 Jun 2026

## What We Found

### Carry Trade — HAS EDGE
- **USDJPY LONG**: +29.6% return over 5.7 years (SL=2%, TP=6%)
- **XAUUSD SHORT**: +$618 from swap income
- **EURUSD SHORT**: +$73 from swap income
- **Strategy**: Hold position to earn swap income, SL protects capital

### Other Approaches — NO EDGE
- **ML on price returns**: 50% accuracy = random
- **Mean reversion**: -$13.66 after costs
- **Momentum**: -$3.31 after costs
- **Volatility breakout**: +$1,744 gross but -$4,383 after costs

### What's Working
1. Carry trade on USDJPY LONG (SL=2%, TP=6%)
2. Risk management (1% per trade, position sizing)
3. Data collection (swap rates, calendar)

### What's Not Working
1. ML-based strategies (no edge after costs)
2. News trading (no calendar data yet)
3. XAUUSD carry trade (tight SL causes frequent stops)

## Files Created
- `carry_trade_runner.py` — Paper trade bot for carry trade
- `collect_calendar.py` — Economic calendar collector
- `research_dashboard.py` — Measurement dashboard
- `research_final.py` — Comprehensive test script

## Next Steps
1. Run carry_trade_runner.py for 30 days
2. Collect calendar data daily
3. Test news trading when data available
4. Monitor swap rates for changes
