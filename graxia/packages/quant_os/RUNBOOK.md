# Quant OS — Operational Runbook

## System Overview

Quant OS is a modular Python framework for algorithmic trading research, backtesting, and live execution. It provides:

- **Multi-strategy ensemble** — Liquidity Sweep, MTM, MRB, MLB strategies with regime-aware filtering
- **Paper trading** — Full pipeline on live MT5 data without real money
- **Backtesting** — Deterministic, MT5-independent engine with walk-forward validation
- **ML training** — XGBoost/CatBoost signal prediction with drift detection
- **Risk management** — Pre-trade risk checks, kill switch, circuit breakers, daily loss limits
- **Monitoring** — Structured logging (structlog), Prometheus metrics, Telegram alerts, heartbeats
- **API** — FastAPI surface for TradingView webhooks, order management, and admin

**Version:** 0.2.0-dev

---

## Prerequisites

| Dependency | Version | Purpose |
|------------|---------|---------|
| Python | 3.11+ | Runtime |
| MetaTrader 5 | Latest | Broker connection (demo or live) |
| PostgreSQL | 15+ | Trade ledger (optional for paper mode) |
| Redis | 7+ | Rate limiting, cache (optional) |

### Python Dependencies

```bash
pip install -e graxia/packages/quant_os/
```

Or use the requirements file:

```bash
pip install -r requirements.txt
```

### Required Environment Variables

Copy `.env.example` to `.env` and fill in:

```bash
cp .env.example .env
```

Minimum for paper trading: `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER`.

---

## How to Start Paper Trading

### Quick Start (60-minute session)

```bash
cd "C:\Users\menum\graxia os"
python graxia/packages/quant_os/run_paper_trading.py --duration 60
```

### Custom Duration and Symbols

```bash
python graxia/packages/quant_os/run_paper_trading.py \
  --duration 360 \
  --symbols XAUUSD EURUSD GBPUSD
```

### Long-Running (24/7)

```bash
python graxia/packages/quant_os/run_paper_trading.py --duration 0
```

### Via Scheduler (recommended for production)

The scheduler runs paper trading + periodic tasks (log snapshots, spread heatmaps):

```bash
python graxia/packages/quant_os/run_scheduled.py
```

### Via Docker

```bash
docker build -f docker/Dockerfile.executor -t quant-os-executor .
docker run --env-file .env quant-os-executor
```

### Verification

While running, check:
- Console output shows `[OK]` trade entries
- `logs/paper_trading.jsonl` is being written
- `logs/trades_*.csv` appears after shutdown
- Telegram notifications arrive (if configured)

---

## How to Run Backtests

### Basic Backtest

```bash
python graxia/packages/quant_os/run_backtest.py
```

### Real Data Backtest

```bash
python graxia/packages/quant_os/run_backtest_real.py
```

### ML Training Pipeline

```bash
python graxia/packages/quant_os/run_ml_train.py
```

This requires historical data in `data/EURUSD=X.csv`. Generate it first via backtest.

### Walk-Forward Validation

The ML trainer includes walk-forward validation by default (3 windows). Results are saved to `results/ml_training_results.json`.

---

## How to Run the Data Pipeline

### MT5 Data Download

```bash
python graxia/packages/quant_os/download_mt5.py
python graxia/packages/quant_os/download_mt5_symbols.py
python graxia/packages/quant_os/download_xauusd_multi_tf.py
```

### Data Quality Check

```bash
python graxia/packages/quant_os/check_quality.py
python graxia/packages/quant_os/check_data_count.py
```

### Shadow Mode (dry-run parallel to live)

```bash
python graxia/packages/quant_os/run_shadow.py
```

---

## Common Failure Modes and Recovery

### 1. MT5 Connection Lost

**Symptom:** `mt5.initialize()` returns False, no trades executing.

**Recovery:**
1. Verify MetaTrader 5 terminal is running
2. Check `MT5_SERVER` and `MT5_LOGIN` in `.env`
3. Ensure the MT5 path in config matches your installation:
   - Pepperstone: `C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe`
   - Default: `C:\Program Files\MetaTrader 5\terminal64.exe`
4. Restart the paper trading script — it calls `mt5.initialize()` on startup

### 2. Kill Switch Activated

**Symptom:** `Kill switch: [R] ACTIVE` in summary, no new trades.

**Cause:** Daily loss limit (default 2%) or max drawdown (15%) exceeded.

**Recovery:**
1. Check `risk_status` in the summary output
2. Wait for the next trading day (daily loss resets)
3. Or restart the script to reset the risk overlay
4. Adjust limits in config if needed: `config.max_daily_loss_pct`

### 3. Heartbeat / Dead Man's Switch Triggered

**Symptom:** `EMERGENCY HALT triggered by Dead Man's Switch` in logs.

**Cause:** System failed to send a heartbeat within the allowed window.

**Recovery:**
1. Check if the trading loop is stuck (high CPU, blocked I/O)
2. Review `logs/paper_trading.jsonl` for errors before the halt
3. Restart the script — the DMS resets on startup
4. If recurring, check MT5 connection stability

### 4. API Server Won't Start

**Symptom:** `uvicorn` fails or port 8000 already in use.

**Recovery:**
1. Check if another instance is running: `netstat -ano | findstr :8000`
2. Kill the conflicting process
3. Verify `DATABASE_URL` is reachable if using PostgreSQL
4. Check `API_HOST` and `API_PORT` in `.env`

### 5. Telegram Notifications Not Working

**Symptom:** No trade alerts received.

**Recovery:**
1. Verify `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env`
2. Test manually: `curl -X POST "https://api.telegram.org/bot<TOKEN>/sendMessage" -d "chat_id=<CHAT_ID>&text=test"`
3. Ensure bot is not blocked by the chat

### 6. ML Training Fails with "No Data"

**Symptom:** `RuntimeError: ML TRAINING REQUIRES REAL DATA`

**Recovery:**
1. Run `python run_backtest.py` first (downloads real data)
2. Or manually place `EURUSD=X.csv` in the `data/` folder
3. Never train on synthetic data for live trading

---

## Emergency Shutdown

### Graceful Shutdown (SIGTERM/SIGINT)

All standalone scripts (`run_paper_trading.py`, `run_scheduled.py`, `run_ml_train.py`) handle SIGTERM and SIGINT:

```bash
# Option 1: Ctrl+C in the terminal
# Option 2: Send SIGTERM
kill -TERM <PID>

# Option 3: On Windows
taskkill /PID <PID> /F
```

On receiving the signal:
1. The shutdown flag is set immediately
2. The current trading cycle completes
3. Open positions are summarized
4. Trade log and summary JSON are saved to `logs/`
5. Telegram summary is sent (if configured)
6. MT5 connection is shut down cleanly

### Force Kill

If graceful shutdown hangs:

```bash
# Linux/Mac
kill -9 <PID>

# Windows
taskkill /PID <PID> /F
```

### Docker Shutdown

```bash
docker stop <container>    # sends SIGTERM
docker kill <container>    # sends SIGKILL after timeout
```

### API Server Shutdown

The FastAPI lifespan handler ensures:
1. Orchestrator is stopped
2. Broker connection is disconnected
3. All pending requests complete

```bash
# Via the admin endpoint
curl -X POST http://localhost:8000/api/v1/admin/shutdown
```

---

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `MT5_LOGIN` | Yes | `0` | MT5 account login number |
| `MT5_PASSWORD` | Yes | — | MT5 account password |
| `MT5_SERVER` | Yes | `Pepperstone-Demo` | MT5 broker server name |
| `MT5_TIMEOUT_MS` | No | `15000` | MT5 connection timeout (ms) |
| `FRED_API_KEY` | No | — | FRED API key for economic data |
| `TV_WEBHOOK_SECRET` | No | — | TradingView webhook auth secret |
| `ADMIN_API_KEY` | No | — | Admin API authentication key |
| `TELEGRAM_BOT_TOKEN` | No | — | Telegram bot token for alerts |
| `TELEGRAM_CHAT_ID` | No | — | Telegram chat ID for alerts |
| `DATABASE_URL` | No | `postgresql+asyncpg://...` | PostgreSQL connection string |
| `REDIS_URL` | No | — | Redis connection string |
| `TRADING_MODE` | No | `paper` | Trading mode: `paper` or `live` |
| `MAX_RISK_PER_TRADE_PCT` | No | `0.5` | Max risk per trade (%) |
| `API_HOST` | No | `0.0.0.0` | API server bind address |
| `API_PORT` | No | `8000` | API server port |
| `SENTRY_DSN` | No | — | Sentry DSN for crash reporting |
| `LOKI_URL` | No | — | Grafana Loki URL for log shipping |
| `LOKI_TENANT_ID` | No | — | Loki tenant ID |

---

## Monitoring and Observability

### Logs

- **Paper trading:** `logs/paper_trading.jsonl` (structured JSON)
- **Scheduler:** `logs/scheduler_YYYYMMDD.log`
- **Trades:** `logs/trades_YYYYMMDD_HHMMSS.csv`
- **Summary:** `logs/summary_YYYYMMDD_HHMMSS.json`

### Metrics

Prometheus metrics are exposed at `:9090/metrics` (if `start_metrics_server()` is called):

- `positions` — Current open position count
- `drawdown_pct` — Current daily drawdown percentage
- `trades_total` — Total trades by symbol/side

### Health Checks

```bash
# API health
curl http://localhost:8000/health

# Full system status
curl http://localhost:8000/status
```

### Heartbeat Monitor

The paper trader sends heartbeats every cycle. If the heartbeat stalls:
- Dead Man's Switch triggers after the configured timeout
- All positions are closed
- An alert is sent via Telegram

---

## Deployment

### Docker

```bash
# Build all images
docker build -f docker/Dockerfile.api -t quant-os-api .
docker build -f docker/Dockerfile.executor -t quant-os-executor .
docker build -f docker/Dockerfile.signal -t quant-os-signal .
docker build -f docker/Dockerfile.trainer -t quant-os-trainer .

# Run via docker-compose
docker-compose up -d
```

### GitHub Actions

- **CI** runs on push to `staging`/`main` and all PRs
- **CD** (`.github/workflows/deploy.yml`) triggers on push to `main`:
  1. Runs full test suite
  2. Builds Docker image
  3. Deploys to staging environment
  4. Requires environment protection approval

---

## Troubleshooting Checklist

- [ ] `.env` file exists and has correct values
- [ ] MT5 terminal is running with the correct account
- [ ] Python 3.11+ is installed with all dependencies
- [ ] `logs/` directory exists (created automatically)
- [ ] PostgreSQL is running (if using database features)
- [ ] Redis is running (if using rate limiting)
- [ ] Firewall allows connections on API port (8000)
- [ ] Telegram bot is not blocked (if using alerts)
