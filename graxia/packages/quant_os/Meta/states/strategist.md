# Strategist State — 2026-07-05 FINAL

## Paper Trading Bot Ready

### Bot Configuration
- **Symbol**: XAUUSD
- **Timeframe**: M1
- **Position Size**: 0.01 lot (micro)
- **Stop Loss**: 50 points ($5)
- **Take Profit**: 100 points ($10)
- **Max Trades/Day**: 10
- **Max Risk/Trade**: 2% of balance

### Current Status
- **MT5 Connected**: Pepperstone Demo 61547941
- **Balance**: $49,844.48
- **Model Accuracy**: 62.3% (training)
- **Current Signal**: SHORT conf=64.3% @ $4174.97

### Files Created
- `scripts/paper_trade_xauusd_m1.py` — Main trading bot
- `artifacts/paper_trades/trades_XAUUSD_M1.json` — Trade log

### How to Run
```bash
python scripts/paper_trade_xauusd_m1.py
```

### Monitoring
- Trade log: `artifacts/paper_trades/trades_XAUUSD_M1.json`
- Check MT5 terminal for open positions
- Monitor balance and equity

### Next Steps
1. Run bot for 1 week
2. Check trade log daily
3. If profitable → scale up position size
4. If not profitable → stop or adjust strategy
