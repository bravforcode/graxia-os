# G2 Broker Preflight Dry-Run Summary

**Test:** `g2_broker_preflight_dry_run`  
**Environment:** Pepperstone MT5 (DEMO)  
**Terminal:** `C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe`  
**Generated (UTC):** `2026-06-23T09:58:16`

---

## Connection & Identity

| Field | Value |
|---|---|
| `profile_fingerprint` (truncated) | `b2a952e42de3af5e...` |
| `terminal_fingerprint` (truncated) | `ade8f62fe5607126...` |
| `account_mode` | **DEMO** (`trade_allowed=True`) |
| `balance` | Redacted (hash: `-6657312864048568267`) |

## Contract Spec (XAUUSD)

| Parameter | Value |
|---|---|
| `contract_size` | 100.0 |
| `volume_min` | 0.01 |
| `volume_max` | 50.0 |
| `volume_step` | 0.01 |
| `point` | 0.01 |
| `tick_size` | 0.01 |
| `tick_value` | 1.0 |

## Market Snapshot

| Field | Value |
|---|---|
| `bid` | 4120.18 |
| `ask` | 4120.35 |
| `spread` | **0.17** (17 ticks) |
| `positions_count` | 0 |
| `orders_count` | 0 |

## Margin Estimates (0.01 lot)

| Side | Margin |
|---|---|
| BUY @ ask (4120.35) | $20.60 |
| SELL @ bid (4120.18) | $20.60 |

## Read-Only Validation

| Check | Result |
|---|---|
| `order_check_passed` | ❌ **FAIL** (retcode=10016, `"Invalid stops"`) |
| `order_submission_count` | **0 ✅** |

**Note:** The `order_check` failure is expected — SL/TP at ±10 points (0.10) on XAUUSD triggers a minimum-stop-distance rejection. This exercises the validation code path without any order submission. Zero `order_send` calls were made.

## Verdict

```
PASS_CHECK_NOT_REQUIRED
```

**order_submission_count=0 confirmed.** No orders were submitted. The preflight successfully connected to Pepperstone MT5 (DEMO), read account info, contract specs, positions, orders, and market data, and validated the preflight pipeline end-to-end.
