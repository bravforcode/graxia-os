# Bot + Dashboard Test Results — 2026-06-26 16:30 ICT

## Bot Process Status

| PID | Process | StartTime | CPU (min) | Bot |
|-----|---------|-----------|-----------|-----|
| 7604 | python | 16:22 | 0.0 | paper_trade_bot.py (XAUUSD) |
| 7680 | python | 16:22 | 0.1 | multi_symbol_bot.py |
| 13836 | python | 16:22 | 0.4 | paper_trade_bot.py (duplicate) |
| 34392 | python | 16:22 | 0.0 | multi_symbol_bot.py (duplicate) |

**Total Python processes: 12** (includes bots, mega_download x3, run_upgrade_pipeline x2, graxia_tool.mcp, graphify.serve)

## Bot Log Activity

### XAUUSD Bot (PID 7604/13836) `data/bot_xauusd.log`
- Started: 09:22 UTC
- Model: xgboost_live_20260626_161034.pkl (XGBClassifier, 34 features)
- Config: Lot=0.01, Stop=$6.30, Min conf=0.85
- **Status: Running, no signals** — LONG conf stuck at 0.557 (below 0.85 threshold)
- XAUUSD price range: $4037–4053 during session
- No trades placed

### Multi-Symbol Bot (PID 7680/34392) `data/bot_multi.log`
- Started: 16:22 ICT
- Models loaded: 5 (XAUUSD, EURUSD, US30, NAS100, BTCUSD)
- **Status: Running, no signals** — all confs below thresholds

| Symbol | Model | Conf/Threshold |
|--------|-------|----------------|
| XAUUSD | xgboost_XAUUSD | 0.52-0.62 / 0.85 |
| EURUSD | xgboost_EURUSD | 0.62-0.71 / 0.80 |
| US30   | xgboost_US30   | 0.52-0.70 / 0.80 |
| NAS100 | xgboost_NAS100  | 0.69-0.76 / 0.80 |
| BTCUSD | xgboost_BTCUSD  | 0.77-0.83 / 0.85 |

### Errors
- `bot_err.log`: Empty
- `bot_multi_err.log`: Empty
- NAS100: `FAILED: Unsupported filling mode` (intermittent)
- BTCUSD: `FAILED: Unsupported filling mode` (intermittent)

### Session State `data/paper_trade_session.json`
- Config: B2 (conf>=0.85, stop $6.30)
- Symbol: XAUUSD, Lot: 0.01, Account: 61547941
- Broker: Pepperstone ECN Razor Demo
- Trades: 0, Last heartbeat: null

## Health Check Results — 7/7 PASSED

| # | Check | Result |
|---|-------|--------|
| 1 | MetaTrader5 | v5.0.5735 |
| 2 | MT5 connected | phirawit jitnarong, Bal=$49941 |
| 3 | Data files | 135 files, ~162.8 MB |
| 4 | ML models | 16, Latest: _20260626_160329.pkl |
| 5 | Pipeline manifest | Last run: 2026-06-26 09:24 |
| 6 | Scheduled tasks | 6 (Data/Sync/Upgrade/Quick/Daily/Research) |
| 7 | Data recency | ETHUSD_D1.csv: 1min old |

## Telegram Dashboard — SENT OK
- `telegram_dashboard.py`: "Dashboard sent to Telegram"
- `pipeline_alert.py`: "Alert sent to Telegram"
- Config: bot_token=8757840873:AAEA..., chat_id=8760327152

## MT5 Account

| Field | Value |
|-------|-------|
| Account | phirawit jitnarong |
| Server | Pepperstone-Demo |
| Balance | $49,940.92 |
| Equity | $49,954.82 |
| Profit | +$13.90 |
| Margin | $13.15 |
| Free Margin | $49,941.67 |
| Leverage | 1:200 |
| Trade Allowed | True |

**Open Positions: 2**
| Symbol | Vol | PnL | Magic |
|--------|-----|-----|-------|
| GBPUSD | 0.01 | +$6.69 | 2766200068 |
| GBPUSD | 0.01 | +$7.43 | 2054145661 |

## Summary
- Both bots running but no signals triggered (confidence below thresholds)
- Telegram sends working (dashboard + alert)
- MT5 connected to Pepperstone Demo, account healthy, 2 legacy GBPUSD positions open
- Health check: all 7 points passed
- Issues: intermittent "Unsupported filling mode" on NAS100/BTCUSD in multi-symbol bot
