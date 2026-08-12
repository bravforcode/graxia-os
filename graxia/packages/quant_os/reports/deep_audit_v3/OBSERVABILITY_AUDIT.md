# PHASE 21 — OBSERVABILITY & MONITORING
*Per R1–R18. A silent failure must be detected, not discovered in account statements.*

---

## 21.1 — Logging Inventory

- **Framework**: `structlog` (`requirements.txt:86`) with a Loki sink (`core/observability.py:26-60` `LokiSink`) → structured logs to Grafana Loki + console + optional file. `setup_logging()` (`observability.py`) called from `run_paper_trading.py:115-116`.
- **Levels**: `structlog` standard; `monitoring/telegram.py:48-50` maps `IncidentSeverity` (P0=🚨, P1=⚠️, …) to emoji + Telegram.
- **Disk vs stdout**: both — Loki HTTP push + console + `logs/*.jsonl` file (`run_paper_trading.py:116`).
- **Log rotation**: `[NOT FOUND]` — `logs/` grows unbounded. `app.log`, `debug.log`, `data/bot.log`, `data/bot_err.log` present. → P2 (disk-fill risk → Phase 21.2 "disk full" failure mode).
- **Signal-time logging**: `run_paper_trading.py` tracks `self._open_trades`, `self.total_signals`; per-trade CSV (`data/paper_trade_log.csv` exists). Granularity `[partially verified]`.
- **Order/fill logging**: `execution/trade_ledger.py`, `execution/ledger.py`, `core/structured_trades.py` exist → trade-level provenance ledger present. ✓

## 21.2 — Silent Failure Detection

| Failure Mode | Detected? | How | Alert Sent? |
|---|---|---|---|
| MT5 feed stale (no new bars for N min) | **YES** | `monitoring/heartbeat.py` + `DeadMansSwitch` (300s timeout, `dead_mans_switch.py:21`) | YES (Telegram P0) |
| Feature computation returning NaN/Inf | **PARTIAL** | `data/quality_gate.py`, `tick/data_quality.py` exist; explicit NaN-check at order path `[UNVERIFIED]` | partial |
| Model prediction returning NaN/Inf | **UNVERIFIED** | `ml/drift_monitor.py` exists; NaN guard at inference `[not traced]` | unknown |
| Order submission failing silently | **PARTIAL** | `execution/order_state_machine.py` tracks REJECTED; alerting on REJECTED `[UNVERIFIED]` | partial |
| Position unexpected (open when should be flat) | **YES** | `execution/reconcile.py` compares local vs broker (`QTY_TOLERANCE=0.0001`) | via mismatch → alert |
| Account balance below threshold | **PARTIAL** | `RiskPolicy` has limits; `monitoring/health_check.py` exists | `[unverified trigger]` |
| System clock drift vs MT5 server time | **UNVERIFIED** | `shadow/canonical_time_authority.py`, `mql5/terminal_time_probe.mq5` exist | `[unverified]` |
| Disk full / log write failure | **NO** | no disk-space monitor found | NO → P2 |
| Memory usage spike | **NO** | no memory monitor found | NO → P2 |

## 21.3 — Alerting

- **Telegram**: `monitoring/telegram.py` (`TelegramNotifier`), `monitoring/alerting.py` (`AlertEngine`), wired in `run_paper_trading.py:67-73, 99-102`. ✓
- **Dead-man's switch**: `monitoring/dead_mans_switch.py` — heartbeat-based, fires close-all + halt + Telegram P0 after 300s silence. ✓ (but in-process — see Phase 9.2).
- **Sentry**: `run_paper_trading.py:107-113` initializes `sentry_sdk` if `SENTRY_DSN` set (`.env:24` is empty). Crash reporting *available*, not currently configured. → P2.

## 21.4 — Audit Trail

- Can a day be reconstructed from logs? `data/paper_trade_log.csv`, `execution/trade_ledger.py` (tamper-evident per `tests/test_ledger_tamper_evidence.py`, `test_engine_ledger_tamper.py`), `state/audit_log.jsonl`. **Trade-level provenance is present and tamper-tested.** ✓ This is a genuine strength.
- Per-trade: signal, order, fill, slippage, P&L — `BacktestTrade` (`engine.py:167-191`) carries `entry_spread_cost`, `entry_slippage_cost`, `exit_slippage_cost`, `ambiguous_bar`, `execution_quality`. ✓ Rich.

## 21.5 — Reconciliation Math Specification

- `execution/reconcile.py:19-20`: `EQUITY_TOLERANCE=$10`, `QTY_TOLERANCE=0.0001 lot`. Compares local `Ledger` positions vs `BrokerAdapter.BrokerPosition`.
- **Frequency**: `[UNVERIFIED]` — `reconcile()` is callable; whether `run_paper_trading.py` calls it every loop, on startup, or never `[not traced this phase]`. → P1.
- **Action on mismatch**: `MismatchType` (LOCAL_ONLY/BROKER_ONLY/QTY/SIDE/PNL) classified with severity; `PositionMismatchError` (`core/exceptions.py`) exists. Whether it auto-flattens, alerts, or halts `[UNVERIFIED]`. → P1.

---

## Phase 21 — Verdict

**STATUS: PARTIAL (good bones, several unverified triggers).**

**Strengths:** Structured logging to Loki+console+file; tamper-evident trade ledger with rich per-trade provenance; Telegram alerting + in-process dead-man's switch; reconciliation module with defined tolerances.

**Gaps:**
1. **No log rotation** → unbounded `logs/` growth → disk-fill can cause silent log-write failure (and the disk-full failure mode is itself undetected). → P2
2. **No memory / disk-space monitor.** → P2
3. **Reconciliation call-site and mismatch-action unverified** — the module exists but whether it runs every loop and what it does on mismatch is unconfirmed. → P1
4. **Clock-drift, model-NaN, order-REJECTED alerting** unverified. → P1/P2.
5. **Sentry DSN empty** — crash reporting not active. → P2.
