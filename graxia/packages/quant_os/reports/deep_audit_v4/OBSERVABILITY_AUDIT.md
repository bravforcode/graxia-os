# PHASE 21 — OBSERVABILITY & MONITORING AUDIT
**Date**: 2026-07-05 | **Scope**: Full codebase | **Severity Scale**: P0=Critical P1=High P2=Medium P3=Low

---

## 21.1 Logging Inventory

### Logging Infrastructure
| Component | Module | Sink | Status |
|-----------|--------|------|--------|
| structlog (core) | `core/observability.py:137-193` | Console (always), Loki (optional), File (optional) | ✅ Deployed |
| FileSink | `core/observability.py:106-134` | JSONL file with rotation (10MB limit, 5 backups) | ✅ |
| LokiSink | `core/observability.py:27-103` | HTTP POST to /loki/api/v1/push, 5s buffer | ⚠️ Optional — requires LOKI_URL env var |
| Structured formatter | `monitoring/structured_formatter.py` | JSON structured output | ⚠️ Requires `structured=True` flag |
| Log rotation | `monitoring/log_rotation.py:19-117` | Size-based (10MB) + time-based (daily) rotation, gzip compression, 30-day retention | ✅ |
| Log aggregation | `monitoring/log_aggregator.py:52-160` | Scans JSONL files, classifies by error/warning/trade/risk categories, supports tailing | ✅ |
| Prometheus metrics | `monitoring/prometheus_metrics.py` | Prometheus exporter on port 9090 | ⚠️ Configured but wiring status unknown |
| Metrics collector | `monitoring/metrics.py:23-72` | In-memory trade counter, win/loss tracking | ✅ Basic |

### What's Logged

| Event | Logged? | Format | Module |
|-------|---------|--------|--------|
| Signal generation | ⚠️ Indirect | Trade execution events | `core/trading_loop.py:403-411` |
| Order submission | ✅ | `trading_loop.paper_fill` / `trading_loop.live_fill` | `core/trading_loop.py:403,455` |
| Order fill | ✅ | FillEvent published to EventBus | `core/trading_loop.py:386-398` |
| Order rejection | ✅ | `trading_loop.rejected_*` events | `core/trading_loop.py:245-305` |
| Kill switch activation | ✅ | `trading_loop.kill_switch_triggered` | `core/trading_loop.py:226-236` |
| Strategy signal details | ❌ | No structured log of raw signal generation | Gap |
| Feature computation | ❌ | No logging of feature values or pipeline state | Gap |
| Position state change | ✅ | `reconciliation.*` events | `execution/reconciler.py` |

### ⚠️ GAP — P2: Log levels
- Paper fills use `logger.info` — reasonable
- Kill switch uses `logger.critical` — correct
- **Missing**: WARNING level for near-limit conditions (e.g., "daily loss at 1.8%, limit is 2.0%")
- **Missing**: DEBUG level for per-bar decision reasoning (why a signal was rejected)

---

## 21.2 Silent Failure Detection

| Failure Mode | Detected? | How (file:line) | Alert Sent? |
|---|---|---|---|
| **MT5 feed stale** (no new bars for N minutes) | ⚠️ Partial | `monitoring/alert_rules.py:93-108` DataStalenessAlert: checks `data_age_seconds > max_age` (default 60s). Also `risk/risk_policy.py:20` `reject_if_data_stale_seconds: 5`. **But** neither is proven to be wired to the live bar ingestion loop. | ⚠️ AlertEngine must be explicitly run — not automatic |
| **Feature computation returning NaN/Inf** | ❌ NOT DETECTED | No NaN/Inf guard in any strategy `_calculate_indicators()` method. `pandas_ta` may propagate NaN silently. The strategies check `if not indicators: return {}` but not for NaN within valid arrays. | ❌ No alert |
| **Model prediction returning NaN/Inf** | ❌ NOT DETECTED | `strategies/mlb.py:289-306` `_predict()` returns 0.5 on any exception but does NOT check for NaN in prediction output. The numpy `isnan` check is missing. | ❌ No alert |
| **Order submission failing silently** | ⚠️ Partial | `core/trading_loop.py:358-365` catches exception and logs error + sets `tracked.status = "failed"`. This IS detected. But `size_position_v2.py:116-123` catches and silently sets `one_lot_loss = None` with NO logging. | ⚠️ For trading_loop: yes (logged). For position_sizer_v2: NO |
| **Position unexpected** (open when should be flat) | ⚠️ On reconnect only | `core/reconciler.py:30-95` `StateReconciler.reconcile()` runs **after MT5 reconnect events only**. NOT per bar/tick. `execution/reconciler.py:105-364` `PositionReconciler` compares internal vs broker but must be called explicitly. | ⚠️ If called (manual/reconnect), logged. Not automatic per loop. |
| **Account balance below threshold** | ⚠️ Not in real-time | `risk/pre_trade_risk.py:59-74` checks loss limits as fractions of equity — this is a relative check, not an absolute minimum balance check. No `if account_balance < MIN_BALANCE` check. | ❌ No dedicated alert |
| **System clock drift vs MT5 server time** | ❌ NOT DETECTED | No clock synchronization check exists. MT5 server time vs local time discrepancy could cause bar misalignment. | ❌ No alert |
| **Disk full / log write failure** | ⚠️ Silent failure | `core/observability.py:122-123` FileSink catches OSError and **passes** — log write failures are silently swallowed. `LokiSink._flush:102` similarly passes on HTTP errors. | ❌ No alert. Log loss undetectable. |
| **Memory usage spike** | ❌ NOT DETECTED | No memory monitoring. `pandas_ta` in strategies computes indicators on full OHLCV arrays — unbounded memory growth possible. | ❌ No alert |
| **Spread explosion** | ⚠️ Designed, not wired | `monitoring/alert_rules.py:73-90` SpreadWideningAlert checks `current_spread > normal × 3.0`. `risk/risk_policy.py:21` `reject_if_spread_multiplier_above: 2.0`. **But** no evidence either is called from live trading loop. | ⚠️ If AlertEngine running — but AlertEngine must be polled |

### ⚠️ CRITICAL — P0: 7 of 10 failure modes NOT detected in live path
The monitoring infrastructure exists but is **opt-in/poll-based** — nothing runs automatically in the main trading loop. The `AlertEngine` (`monitoring/alerting.py:94-474`) requires explicit `check_alerts(system_state)` calls per loop iteration — there is no evidence this call exists in the live trading loop.

---

## 21.3 Alerting

### Alert Channels
| Channel | Module | Status |
|---------|--------|--------|
| Telegram (notifications) | `monitoring/telegram.py:19-421` | ✅ Fully implemented — async + sync, trade notif, kill switch, daily report, commands |
| Telegram (core notifier) | `core/telegram_notify.py:44-203` | ✅ Duplicate implementation — trade opened/closed, heartbeat, failover |
| Telegram (alert engine) | `monitoring/alerting.py:313-350` | ✅ Wired to AlertEngine — sends formatted HTML messages |
| Email | — | ❌ Not implemented |
| SMS | — | ❌ Not implemented |
| Prometheus/Grafana | `monitoring/prometheus_metrics.py` | ⚠️ Configured but live integration status unclear |
| Sentry | `core/config.py:138` | ⚠️ Config field exists, no evidence of SDK initialization |

### Dead Man's Switch
- **`monitoring/dead_mans_switch.py:27-249`**: Fully implemented! Monitors heartbeat, triggers after 300s (5 min) timeout. Sequence: halt → close positions → CRITICAL alert. Has `create_mt5_close_all_callback()` for MT5 position flattening.
- **`monitoring/health_check.py:25-83`**: Separate watchdog implementation. Checks heartbeat file every 300s. 15-min stale → local restart. 30-min stale → standby VPS failover via POST to STANDBY_WEBHOOK_URL.
- **`monitoring/heartbeat_monitor.py:108-161`**: Third heartbeat monitor for TSM paper trading bot. 1h stale → Telegram warning, 4h stale → kill switch activation.

### ⚠️ P1 — Three overlapping heartbeat systems
Three different heartbeat/health-check implementations exist (dead_mans_switch, health_check, heartbeat_monitor) with different timeouts, different state keys, and different escalation paths. This is confusion-prone — which one is actually running in production?

### Heartbeat
`core/telegram_notify.py:157-189` `heartbeat()` sends a daily summary (trades today, win rate 7d, balance, Monte Carlo P(ruin)). This is a push-based heartbeat — but it requires explicit invocation.

---

## 21.4 Audit Trail

### Can you reconstruct exactly what happened from logs alone?
**Partially.** The structured logging pipeline captures:

**What IS reconstructable:**
- Order lifecycle: SignalEvent → OrderEvent → FillEvent → TradeClosedEvent (published on EventBus, logged)
- Kill switch events: activation with trigger type and reason logged
- Reconciliation: ghost/orphan detection with timestamps logged
- Trade metrics: P&L, win/loss counts tracked in `monitoring/metrics.py`

**What IS NOT reconstructable:**
- **Why a signal was generated**: Strategy decision logic (which indicators triggered, what values they had) is NOT logged — only the final output
- **Why a signal was rejected**: Rejection reasons are logged as structured warnings in `core/trading_loop.py:246-305` (e.g., `rejected_no_sl`, `rejected_daily_limit`) — this IS reconstructable
- **Raw market data at decision time**: The OHLCV data that fed signal generation is NOT logged alongside signals
- **Feature drift over time**: Feature distributions not tracked or logged
- **System resource state**: CPU, memory, disk at time of each decision not logged

### ⚠️ GAP — P2: Decision replay impossible
You cannot replay a trading decision from logs alone because the input data (OHLCV arrays) and intermediate computations (indicator values, model feature vectors) are not preserved. The audit trail captures outcomes but not inputs.

---

## 21.5 Reconciliation Math Specification

### Reconciliation Implementations (three separate)

| Implementation | Module | Trigger | Action on Mismatch |
|---|---|---|---|
| StateReconciler (v1, deprecated) | `core/reconciler.py:17-178` | `mt5_ingester.reconnected` event | Ghosts: mark CLOSED_BY_DISCONNECT. Orphans: INSERT into shadow_trades. |
| PositionReconciler (v2, current) | `execution/reconciler.py:105-364` | Explicit call required | Discrepancies classified by type/severity. Auto-fix small qty differences (<0.01). Manual review for critical. |
| KillSwitch reconciliation | `risk/kill_switch.py:269-304` | After kill-switch enforce() | Verifies closed positions are gone from broker. Returns True/False. |

### Formula (PositionReconciler v2)
```
For each symbol in union(internal_positions, broker_positions):
  if internal only:  → BROKER_MISSING (WARNING)
  if broker only:    → POSITION_MISSING (WARNING)
  if both:           → compare side → SIDE_MISMATCH (CRITICAL) if different
                     → compare qty  → QTY_MISMATCH (WARNING if diff < 0.01, else CRITICAL)
                     → compare price → PRICE_MISMATCH (INFO)
```

### ⚠️ GAP — P0: Reconciliation is NOT continuous
- `StateReconciler` runs only on MT5 reconnect events — not per bar or per loop iteration
- `PositionReconciler` must be called explicitly — there is no evidence it runs in the main trading loop
- If the bot and broker diverge mid-session (e.g., manual close in MT5, partial fill, broker-side cancellation), the divergence persists until the next reconnect or manual reconciliation

### Reconciliation Frequency
| When | What Runs |
|------|-----------|
| MT5 reconnect | `StateReconciler.reconcile()` (if wired) |
| Kill switch enforce | `KillSwitch._reconcile_broker_state()` |
| Every loop iteration | ❌ NOTHING |
| Startup | ❌ Nothing explicit |

### ⚠️ Defined action on mismatch:
- **Ghost trades** (DuckDB says OPEN, MT5 says flat): Auto-close in DuckDB as CLOSED_BY_DISCONNECT (`core/reconciler.py:138-146`)
- **Orphan trades** (MT5 has position, DuckDB doesn't): Auto-import with `close_reason='MT5_IMPORT'` (`core/reconciler.py:149-174`)
- **Qty mismatch** (<0.01): Auto-fix internal to match broker (`execution/reconciler.py:278-327`)
- **Side mismatch**: MANUAL REVIEW required — CRITICAL severity, no auto-fix
- **Qty mismatch** (>0.01): MANUAL REVIEW required — CRITICAL severity
- **Price mismatch**: INFO only — no action taken
- **NO ALERT IS SENT** for any of these mismatches unless the AlertEngine is explicitly wired

---

## Top Findings (Phase 21)

| # | Severity | Finding |
|---|----------|---------|
| 1 | **P0** | 7 of 10 critical failure modes (NaN/Inf propagation, model drift, clock drift, memory, disk full, unexpected positions mid-session) NOT detected in automated path |
| 2 | **P0** | Reconciliation runs ONLY on MT5 reconnect — not per bar/loop iteration. Mid-session divergence persists undetected |
| 3 | **P0** | AlertEngine exists but must be explicitly polled — no evidence `check_alerts()` is called from main trading loop |
| 4 | **P1** | Three overlapping heartbeat systems (dead_mans_switch, health_check, heartbeat_monitor) with different timeouts — unclear which runs in production |
| 5 | **P2** | Decision replay impossible — signal inputs (OHLCV data, indicator values) not preserved in audit trail; only outputs logged |
