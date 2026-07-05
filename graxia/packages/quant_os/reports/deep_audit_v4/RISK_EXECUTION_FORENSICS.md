# RISK EXECUTION FORENSICS
**Phase 9 | 2026-07-05 | TIER 1**

---

## 9.1 — Position Sizing
- **Formula:** `_historical_size()` in `backtest/engine.py:118-135`
- `risk_budget = equity × risk_per_trade_bps / 10000`
- `ticks = |entry - SL| / tick_size`
- `volume = risk_budget / (ticks × tick_value)`
- Rounded DOWN to `volume_step`, minimum `volume_min`
- **Bounded:** Yes — returns 0 if below minimum ✅

## 9.2 — Risk Limits & Kill Switches

| Risk Control | In Code | Tested | Active |
|---|---|---|---|
| Maximum daily loss limit | `risk/risk_policy.py` + `engine.py:_check_risk_halt()` | Yes | Yes (backtest) |
| Maximum drawdown kill switch | `risk/risk_policy.py:max_total_drawdown_fraction` | Yes | Yes (backtest) |
| Kill switch (Telegram) | `risk/kill_switch.py` — persistent, fail-closed | Yes | Yes (live) |
| Maximum position size cap | `backtest/engine.py:max_positions` (default 5) | Yes | Yes |
| Account balance floor | Not found | — | — |
| Emergency close-all | `kill_switch.py:_cmd_kill_all()` → `enforce(CLOSE_ALL)` | Yes | Yes |
| Manual override / pause | `kill_switch.py:_cmd_pause()` | Yes | Yes |
| **Kill switch persists across restart** | **YES** — `data/kill_switch_state.json` with atomic writes | Yes | **CONFIRMED** |
| **Kill switch fail-closed on corruption** | **YES** — defaults to ACTIVE on corrupted file | Yes | **CONFIRMED** |

## 9.3 — MT5 Connection Resilience
- `execution/adapters/mt5.py:_ensure_connected()` — 3 retries with exponential backoff (2s, 4s, 8s)
- Reconnect on `terminal_info()` failure
- **Operator alert:** Logging only — no external notification mechanism confirmed

## 9.5 — Crash Recovery
- `execution/position_reconciler.py` exists — position reconciliation
- `risk/kill_switch.py` persists state to disk — survives crashes
- **On restart:** Kill switch state is loaded from file; if ACTIVE, trading remains blocked

## 9.8 — Per-Asset-Class Cost Model Audit

| Asset Class | Broker's Actual Fee Structure | Code's Assumed Structure | Match? |
|---|---|---|---|
| FX majors | Variable spread + $3.50/lot/side commission (Razor) | `commission_per_lot=3.5` in config | **Likely match** |
| Metals | Spread-embedded commission (Razor) | Same $3.50/lot/side | **MISMATCH — double-counts** |
| Crypto | CFD with daily financing | Same FX cost model | **UNVERIFIED** |
| Indices | CFD with spread | Same FX cost model | **UNVERIFIED** |

**Confirmed:** Metals cost is double-counted — commission embedded in spread AND separately charged at $3.50/lot.

## 9.9 — Swap/Overnight Cost Wiring
- `core/risk/swap_cost.py` exists with full implementation
- **NOT wired** into `backtest/engine.py` — every overnight-holding result is `[COST MODEL INCOMPLETE]`
- Only imported in `core/__init__.py` and `tests/test_core_untested.py`

## 9.10 — Ensemble SL/TP Cross-Check
- Ensemble returns `(None, None)` for SL/TP (`strategies/ensemble.py:432-433`)
- Backtest engine rejects signals without SL (`engine.py:_execute_signal()`)
- **Live path behavior with SL=None:** UNVERIFIED — must trace through OMS
