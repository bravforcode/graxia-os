# PHASE 9 — RISK & EXECUTION FORENSICS (MT5-SPECIFIC)
*Per R1–R18. Focus: are risk limits in code (not docs), and does the kill switch persist across restart?*

---

## 9.1 — Position Sizing

- Canonical backtest sizing: `backtest/engine.py:92-118` `_historical_size` — risk-budget / stop-distance / tick-value. Floor at `volume_min` ✓. **No `volume_max` check** (Phase 3.5 bug) — P1.
- Live sizing: `risk/position_sizer.py`, `risk/position_sizer_v2.py`, `risk/historical_sizing_provider.py` exist → dedicated sizing modules. `[Not fully traced]`.
- MT5 `SYMBOL_VOLUME_MAX` / `SYMBOL_VOLUME_STEP` checks: `mt5_connector/connection.py:137-158` `get_symbol_info` exposes `max_volume`, `volume_step`, `min_volume`. **Whether the live order path actually consults these before submitting `[UNVERIFIED]`** — the data is fetched; the gate is not confirmed. → P1.
- Insufficient margin pre-check: `RiskPolicy.reject_if_margin_level_below_pct=500` (`risk_policy.py:18`) exists as a field; enforcement point `[UNVERIFIED]`.

## 9.2 — Risk Limits & Kill Switches

| Risk Control | In Code | Tested | Active in Live |
|---|---|---|---|
| Max daily loss | `risk_policy.py:11` (50bps), `engine.py:959-961` (backtest halt) | `tests/test_risk_edge_cases.py` exists | `[UNVERIFIED live path]` |
| Max drawdown kill | `risk_policy.py:13` (300bps), `engine.py:953-956` | yes (backtest) | `[UNVERIFIED live]` |
| Max position size cap | `config.py:95,100` micro/limited modes | `[partially]` | mode-gated |
| Max open positions | **CONFLICT**: `config.py:66`=5 vs `risk_policy.py:14`=1 | `[unverified which wins]` | **AMBIGUOUS** |
| Max consecutive losses | `[NOT FOUND]` | n/a | **ABSENT** |
| Account balance floor | `[NOT FOUND as explicit gate]` | n/a | **ABSENT** |
| Emergency close-all | `monitoring/dead_mans_switch.py:53` `close_all_positions` callback; `canary/emergency_kill_switch.py` | `canary/test_*` exist | wired in `run_paper_trading.py:78-85` |
| Manual override / pause | `risk/kill_switch.py:64-112` Telegram `/kill_all`, `/pause`, `/resume` | `[partially]` | wired |

### Kill switch persistence — THE CRITICAL CHECK (protocol 9.2)

**`risk/kill_switch.py:30`** `state_file="data/kill_switch_state.json"`.
- `_load()` (`kill_switch.py:145-151`) reads the JSON file on construction.
- `_save()` (`kill_switch.py:153-155`) writes the JSON file on every state change.
- `activate()` / `_set_state()` / `_cmd_kill_all` all call `_save()`.

**Verdict: kill switch state PERSISTS across process restart.** ✓ This is a genuine strength — a crash does not silently reset the kill switch to "off". The state lives in `data/kill_switch_state.json`, a durable file. This satisfies the protocol's hardest requirement.

**Caveat**: persistence is only meaningful if the live trading loop **reads** `KillSwitch.is_active()` before every order. `[NOT TRACED into run_paper_trading.py's order submission path this phase]` — the kill switch *object* is constructable and persistent, but the call-site gate `[UNVERIFIED]`. → P1 (must confirm `if kill_switch.is_active(): skip` exists in the live order path).

### Dead Man's Switch (process-level watchdog)

`monitoring/dead_mans_switch.py:21` `DEFAULT_TIMEOUT=300.0` (5 min). It runs as an `asyncio.Task` (`dead_mans_switch.py:74`) — **in-process**, not a separate OS process. **If the entire Python process crashes (OOM, segfault), the asyncio task dies with it → no close-all fires.** The DMS protects against a *stalled* loop (heartbeat stops but process alive), NOT against a *dead* process. For a solo-developer unattended system this is a meaningful gap. → **P1: DMS is in-process; a true external watchdog (systemd, PM2, separate healthcheck process) is needed for crash recovery.**

## 9.3 — MT5 Connection Resilience

- Reconnect loop: `mt5_connector/connection.py:103-114` `reconnect(max_retries=3, delay_sec=5.0)` with **exponential backoff** (`delay * 2**attempt`). ✓ Good.
- `is_connected()` (`connection.py:88-101`) actually verifies via `terminal_info()` (not just cached flag) — P1-fixed per the docstring. ✓
- Broker downtime / weekend gap handling: `[NOT FOUND as explicit logic]`. → P2.
- Requote / partial fill / timeout / duplicate-order protection: `execution/idempotency.py`, `execution/order_state_machine.py`, `execution/recovery.py` exist → infrastructure present. Specific handling `[UNVERIFIED]`. → P1.

## 9.4 — Order Lifecycle Tracking

- States: `execution/order_state_machine.py` `OrderState` (RISK_CHECKED → ORDER_PRECHECKED → ORDER_SUBMITTED → ORDER_ACKNOWLEDGED → FILLED / REJECTED). `execution_simulator.py:210-215` advances through these. ✓
- Magic Number: `[NOT FOUND in mt5_connector/connection.py]` — `get_account_info`/`get_symbol_info` don't set magic; the live order submission path `[not traced]`. → P1 (if MT5 orders are placed without a magic number, the bot cannot distinguish its own orders from manual ones).
- Ack-lost reconciliation: `execution/reconcile.py` (compares local ledger vs broker, `QTY_TOLERANCE=0.0001`, `EQUITY_TOLERANCE=$10`) — present. ✓
- Startup reconciliation: `execution/recovery.py`, `canary/position_reconciler.py` exist. `[UNVERIFIED if called on boot]`. → P1.

## 9.5 — Crash Recovery

- On restart, does the bot read MT5's actual open positions and reconcile? `execution/reconcile.py` + `canary/position_reconciler.py` exist → capability. **Whether `run_paper_trading.py` calls reconcile on startup `[UNVERIFIED this phase]`**. → P1.
- The risk per protocol: "a crash leaves orphaned positions with no management." The *plumbing* to prevent this exists; the *wiring on boot* is unconfirmed.

## 9.6 — Latency

`execution/quality_tracker.py`, `cost/pipeline_latency.py` exist → latency measurement infrastructure. `[No latency measurement output found]`. → P2.

## 9.7 — Broker-Specific Execution Quirks

- Stop-out / margin-call levels: `RiskPolicy.reject_if_margin_level_below_pct=500` (5:1 = 500%) (`risk_policy.py:18`) — hardcoded assumption. Whether it matches Pepperstone Razor's actual stop-out `[UNVERIFIED — requires broker TOS]`. → P2.
- Triple-swap day: `[NOT FOUND]`. → P2 (moot unless overnight positions).
- Account type (ECN/Razor vs standard): `.env`/creds say Razor; `dynamic_spread_model.py` docstring says "Pepperstone Razor". Consistent. ✓

---

## Phase 9 — Verdict

**STATUS: PARTIAL (one genuine strength, several unverified gates).**

**Strengths (stated plainly):**
1. Kill switch persists to `data/kill_switch_state.json` — survives restart. ✓ (protocol 9.2 hardest requirement MET at the storage layer)
2. MT5 reconnect with exponential backoff; `is_connected()` actually verifies. ✓
3. Order state machine + reconciliation module present. ✓

**Failures / gaps:**
1. **`max_open_positions` conflict** (5 vs 1) between two policy objects — ambiguous which governs. ✗
2. **Dead Man's Switch is in-process** — does not protect against process crash (OOM/segfault). Needs external watchdog. ✗
3. **Kill switch call-site gate unverified** — the object is persistent, but whether the live order path checks it before every order is unconfirmed. ✗ (P1)
4. **Max consecutive losses / account balance floor** — absent as code gates. ✗
5. **Magic Number, startup reconciliation, broker TOS-level stop-out** — unverified. P1/P2.

**The persistence of the kill switch is real and is the headline positive. But persistence is worthless if the order path doesn't read it — that gate is unverified.**
