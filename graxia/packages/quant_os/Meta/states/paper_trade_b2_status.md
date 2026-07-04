# Paper Trade B2 — สถานะล่าสุด

**Updated**: 2026-06-26 14:10 UTC

## สถานะปัจจุบัน
- **Bot**: v2.0 running, PID active, 0 errors
- **Model**: CalibratedClassifierCV, 40 OHLCV features, Platt scaling
- **Threshold**: conf ≥ 0.50 (locked)
- **Config**: B2 stop $3.00, EU session only, 15s interval, auto-retrain daily 06:00 UTC
- **Position**: LONG @ ~4060, PnL: +$14.27 (floating)

## ข้อมูลที่ต้องรู้
- **Pre-register**: `Meta/pre_register_b2.md` — locked, no changes until Jul 23
- **Bot log**: `data/bot_out.log`
- **Trade log**: `data/paper_trade_log.csv`
- **Model**: `ml/models/xgboost_live_20260626.pkl`
- **Launch**: `python scripts/launch_bot.py` (reliable) or `start_mega_bot.bat`

## Evaluate Jul 23
1. avg_net/trade ≥ $0.40
2. Win rate ≥ 55%
3. t-stat ≥ 2.0 (block bootstrap 95% CI)

## ถ้า bot หยุด
```bash
# Kill old
Get-Process python* | Where-Object { $_.CommandLine -like "*paper_trade*" } | Stop-Process -Force

# Restart
python scripts/launch_bot.py
```
