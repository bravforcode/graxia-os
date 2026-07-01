# Quant OS Operational Runbook

## Start Paper Trading
```bash
cd "C:\Users\menum\graxia os"
python graxia/packages/quant_os/run_paper_trading.py
```

## Start Shadow Mode
```bash
python graxia/packages/quant_os/run_shadow.py
```

## Emergency Stop
1. Press Ctrl+C in terminal (graceful shutdown)
2. OR send `/kill_all` via Telegram bot
3. OR manually close positions in MT5 terminal

## Check System Status
- Dashboard: http://localhost:8080
- Health: http://localhost:8000/health
- Logs: logs/paper_trading.jsonl
- Trades: logs/trades_*.csv

## Kill Switch
- `/kill_all` — halt all trading
- `/kill_forex` — halt forex only
- `/resume` — resume trading
- State persists across restart in `data/kill_switch_state.json`

## Crash Recovery
On startup, the system runs `Recovery.on_startup()` which:
1. Reconciles local state vs broker positions
2. Checks drawdown limits
3. Emits verdict: RESUME / HALT / DEGRADED

## Log Files
- `logs/paper_trading.jsonl` — structured logs (rotated at 10MB)
- `logs/trades_*.csv` — trade history per session
- `logs/summary_*.json` — session summary

## Alert Channels
- Telegram: trade opens/closes, daily PnL, errors
- Sentry: crash reports (if SENTRY_DSN set)
- Prometheus: metrics on port 9090 (if enabled)
