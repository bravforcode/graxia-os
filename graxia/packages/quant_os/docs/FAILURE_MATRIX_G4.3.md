# G4.3 Failure Matrix — submit_order_once

**Track:** A6 — Failure Matrix (G4.3)
**Generator:** `test_failure_matrix.py`
**Framework:** pytest with `unittest.mock` — no real MT5 calls

---

## Coverage

| Failure Mode | Retcode | What Triggers It | Handling | Test Status |
|---|---|---|---|---|
| **None result** | `-1` (SUBMISSION_UNKNOWN) | MT5 returns Python `None` (not `OrderSendResult`). Disconnected terminal, shutdown mid-flight, or internal C extension failure. | Returns `{"retcode": -1, "error": "SUBMISSION_UNKNOWN", ...}`. **No retry.** Most dangerous case — ambiguous state. | ✅ 14/14 pass |
| **REQUOTE** | `10004` | Price changed between order_check and order_send. Broker requotes. | Evidence dict returned with retcode. Orchestrator transitions to REJECTED. No retry. | ✅ |
| **REJECT** | `10006` | Broker or server rejects the order. | Evidence dict returned. No retry. | ✅ |
| **INVALID_STOPS** | `10016` | SL/TP distance violates broker stop level rules. | Evidence dict returned. No retry. | ✅ |
| **MARKET_CLOSED** | `10019` | Symbol trading hours ended between check and send. | Evidence dict returned. No retry. | ✅ |
| **NO_MONEY** | `10014` | Insufficient margin after preflight check (race condition). | Evidence dict returned. No retry. | ✅ |
| **TRADE_DISABLED** | `10007` | Trading disabled for symbol or account (server-side). | Evidence dict returned. No retry. | ✅ |
| **Disconnect** | `-1` (SUBMISSION_UNKNOWN) | `mt5.shutdown()` called externally before order_send. MT5 C extension returns `None` on disconnected `order_send` — no exception. | Behaviorally identical to None result. Returns SUBMISSION_UNKNOWN. No retry. | ✅ |
| **Unexpected exception** | propagates | `order_send` raises (e.g. `RuntimeError`, segmentation fault in theory). | Exception propagates to orchestrator. Orchestrator's `finally` block handles cleanup (gate off, kill on, mutex released, submission disabled). | ✅ |

## Per-Mode Guarantees

For every failure mode (including None):

```
1. submission attempt  = exactly one (assert_called_once)
2. retry               = zero (never retries)
3. submission gate     = enable before, disable after
4. evidence dict       = {retcode, deal, order, volume, price, comment, request_id, retcode_external}
5. exception          = propagates (orchestrator finally handles cleanup)
```

## None Result — System's Most Dangerous Case

```python
# Broker gateway invoked via submit_order_once
result = submit_order_once(request)

if result is None:
    return {"retcode": -1, "error": "SUBMISSION_UNKNOWN",
            "comment": "order_send returned None — ambiguous state"}
```

- MT5 returns `None` when the terminal is not initialized, shutdown externally, or an internal C extension error occurs.
- `None` is *not* an `OrderSendResult` — accessing `.retcode` on it would `AttributeError`.
- The function returns `SUBMISSION_UNKNOWN` (-1) with a clear comment.
- The state machine transitions to `SUBMISSION_UNKNOWN` (terminal state — no outgoing transitions).
- **No retry is attempted.** The `None` guard fires before any field access.
- The orchestrator must then reconcile (positions_get, orders_get, history_orders_get, history_deals_get) to determine if the order was actually placed.

## Verification Command

```powershell
cd packages\quant_os
python -m pytest execution/demo_canary/test_failure_matrix.py -v
```

Expected output: `14 passed`
