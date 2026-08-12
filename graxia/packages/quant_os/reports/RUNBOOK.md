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

---

## Incident Runbooks

### MT5 Disconnect

**Symptom:** Broker adapter reports `is_connected = False`, orders fail with `BrokerError`.

**Detection:**
- Health endpoint shows `broker_connected: false`
- Telegram alert: "Broker disconnected"
- Logs: `adapter.connect_failed` or `broker_connection_lost`

**Response:**
1. Check MT5 terminal on VPS — is it running? Is there a login prompt?
2. Check network: `ping <broker-server>` from VPS
3. Check MT5 logs: `data/mt5/Logs/` for auth errors or server maintenance
4. If MT5 crashed: restart via `wine MT5.exe` or systemd service
5. If network issue: check VPS provider status, ISP, firewall rules
6. Once MT5 is back: system auto-reconnects on next `submit_order` call
7. Verify: `GET /health` → `broker_connected: true`

**Escalation:** If >15 min downtime, send `/kill_all` to prevent stale signal accumulation.

---

### Stale Data

**Symptom:** Model predictions based on outdated bars, confidence degrades.

**Detection:**
- Signal service logs: `signal.feature_time_ms` > 500ms
- Bar timestamps in `/api/signal` request are >30 min old
- Drift monitor alerts: `accuracy_window` declining

**Response:**
1. Check EA is running in MT5 — look for recent bar sends in `data/ea_logs/`
2. Check signal service health: `GET /api/health` → `model_loaded: true`
3. If EA stopped: restart the EA in MT5 (drag onto chart, enable auto-trading)
4. If signal service stale: check container health `docker ps` and logs
5. Verify: send test bar payload, confirm fresh timestamp in response

**Prevention:** EA has a built-in 5-min heartbeat check. Signal service has 30 req/min rate limit.

---

### Drawdown Breach

**Symptom:** `Recovery.on_startup()` returns `HALT` verdict, or runtime drawdown exceeds 15%.

**Detection:**
- Startup: `verdict=HALT`, `drawdown` check failed
- Runtime: Telegram alert "Drawdown exceeded 15%"
- Logs: `risk.drawdown_breach`

**Response:**
1. **Immediate:** System auto-halts (kill switch triggers). Do NOT manually override.
2. Check positions: `GET /api/v1/positions` — are there open losers?
3. Analyze: was it a single bad trade or a streak? Check `trade_log.jsonl`
4. If single trade: review SL placement, check if SL was slipped
5. If streak: review regime — is the strategy wrong for current market?
6. **Do not resume** until root cause identified and fix applied
7. Resume: fix issue → `/resume` → monitor closely for 24h

**Escalation:** If drawdown >20%, stop all trading and conduct full post-mortem.

---

### Risk Denial

**Symptom:** Orders rejected by risk engine, `RiskViolationError` in webhook response.

**Detection:**
- Webhook response: `status: "rejected"`, `error: "Risk violation: ..."`
- Logs: `risk_engine.check_order` failed

**Response:**
1. Read the specific violation type from the error message
2. Common violations:
   - `MAX_POSITIONS`: too many open positions. Wait for a close or increase limit.
   - `MAX_DAILY_LOSS`: daily loss limit hit. Trading paused until next day.
   - `MAX_RISK_PER_TRADE`: position size too large. Reduce lot size in config.
   - `MISSING_RISK_ENGINE`: risk engine not initialized. Check startup logs.
3. If legitimate: adjust config in `data/config.json` and restart
4. If false positive: check risk engine logic in `risk/engine.py`

**Never bypass risk checks.** Risk denials are fail-closed by design.

---

### Trainer Hang

**Symptom:** `graxia-trainer` container unhealthy, no new models produced.

**Detection:**
- Docker: `docker ps` shows `graxia-trainer` as `unhealthy`
- Healthcheck: `trainer_heartbeat` file older than 30 minutes
- No new `.pkl` files in `data/models/`

**Response:**
1. Check trainer logs: `docker logs graxia-trainer --tail 50`
2. Common causes:
   - OOM during XGBoost training → reduce `n_estimators` or increase memory limit
   - Data file missing → check `data/` for CSV/parquet files
   - Python exception → check traceback in logs
3. Restart: `docker restart graxia-trainer`
4. If persistent: run manually to debug:
   ```bash
   docker exec -it graxia-trainer python scripts/train_all_models.py
   ```
5. Verify: heartbeat file timestamp is fresh, new model appears in `data/models/`

**Note:** Trainer runs on supercronic cron. If it hangs, the next cron tick will also hang. Fix root cause before restart.

---

### DB Rollback

**Symptom:** Database migration failed, or data corruption detected.

**Detection:**
- Alembic migration error in logs
- API returns 500 errors on DB queries
- Data integrity check fails

**Response:**
1. **Stop all services** that write to DB:
   ```bash
   docker stop graxia-api graxia-executor graxia-webhook
   ```
2. Check current migration version:
   ```bash
   docker exec graxia-db psql -U graxia -d quant_os -c "SELECT version_num FROM alembic_version;"
   ```
3. If rollback needed:
   ```bash
   docker exec graxia-api python -m alembic downgrade -1
   ```
4. If full restore needed:
   ```bash
   docker stop graxia-db
   # Restore from backup
   cp data/postgres/backup_before_migration.sql data/postgres/
   docker start graxia-db
   docker exec -i graxia-db psql -U graxia -d quant_os < data/postgres/backup_before_migration.sql
   ```
5. Restart services:
   ```bash
   docker start graxia-db graxia-api graxia-executor graxia-webhook
   ```
6. Verify: `GET /health` returns healthy, orders can be listed

**Prevention:** Always backup DB before migrations:
```bash
docker exec graxia-db pg_dump -U graxia quant_os > data/postgres/backup_$(date +%Y%m%d).sql
```
