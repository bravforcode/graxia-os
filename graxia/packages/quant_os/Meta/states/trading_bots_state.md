# Trading Bots State — 2026-06-26

## System Overview
- **Date**: Fri Jun 26 2026
- **MT5 Account**: phirawit jitnarong | Balance: $49,940.92
- **MT5 Connection**: Connected | Trade Allowed: Yes

---

## Bot 1: XAUUSD Paper Trade Bot

| Field | Value |
|-------|-------|
| **Script** | `scripts/paper_trade_bot.py` |
| **PID** | 7604 (hermes venv) |
| **Status** | RUNNING |
| **Model** | `xgboost_live_20260626_161034.pkl` (retrained) |
| **Interval** | 60 seconds |
| **Lot** | 0.01 |
| **B2 Stop** | $6.30 |
| **Min Confidence** | 0.85 |
| **Latest Signal** | conf=0.557 (< 0.85, no trade) |
| **Telegram** | ✅ Active — Bot Online sent |
| **Log** | `data/bot_xauusd.log` |

**Notes**: No positions open. No elevated confidence signals detected.

---

## Bot 2: Multi-Symbol Bot

| Field | Value |
|-------|-------|
| **Script** | `scripts/multi_symbol_bot.py` |
| **PID** | 34392 (hermes venv) |
| **Status** | RUNNING |
| **Interval** | 300 seconds |
| **Log** | `data/bot_multi.log` |

### Symbols & Models

| Symbol | Model | Lot | Stop $ | Min Conf | Latest Signal |
|--------|-------|-----|--------|----------|--------------|
| XAUUSD | `xgboost_XAUUSD_20260626_160329.pkl` | 0.01 | $6.30 | 0.85 | conf=0.520 ↓ |
| EURUSD | `xgboost_EURUSD_20260626_160329.pkl` | 0.01 | $5.00 | 0.80 | conf=0.708 ↓ |
| US30 | `xgboost_US30_20260626_160329.pkl` | 0.01 | $10.00 | 0.80 | conf=0.585 ↓ |
| NAS100 | `xgboost_NAS100_20260626_160329.pkl` | 0.01 | $10.00 | 0.80 | conf=0.754 ↓ |
| BTCUSD | `xgboost_BTCUSD_20260626_160330.pkl` | 0.001 | $20.00 | 0.85 | conf=0.771 ↓ |

**Notes**: All 5 models loaded successfully. MT5 connected. No trades — all confidence below thresholds.

---

## Files

| File | Description |
|------|-------------|
| `scripts/paper_trade_bot.py` | XAUUSD single-symbol bot v1.0 |
| `scripts/multi_symbol_bot.py` | 5-symbol bot v1.0 |
| `scripts/run_all_bots.ps1` | Script to start both bots |
| `scripts/start_bots.py` | Python launcher for both bots |
| `data/bot_xauusd.log` | XAUUSD bot log |
| `data/bot_multi.log` | Multi-symbol bot log |

---

## Commands

```
# Check logs
cmd /c type data\bot_xauusd.log | more
cmd /c type data\bot_multi.log | more

# Check processes
Get-Process -Name python | Where-Object CommandLine -Match "paper_trade|multi_symbol"

# Restart bots
python scripts/start_bots.py
```
