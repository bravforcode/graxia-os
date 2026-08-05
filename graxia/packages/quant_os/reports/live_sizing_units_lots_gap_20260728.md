# Live position-sizing: units-vs-lots gap (2026-07-28)

## STATUS UPDATE (2026-07-29): partially fixed

`execution/adapters/mt5.py` now converts raw-unit `order.quantity` to MT5
lots (divide by `core.contract_specs.get_spec(symbol).contract_size`) at a
single point, immediately before every `mt5.order_send()` call — in
`submit_order()`, `close_position()`, and the lots-to-units reverse
conversion in `get_positions()` and both fill-result paths. Fails closed
(`OrderStatus.FAILED`) if the symbol has no entry in `core/contract_specs.py`,
per the same fail-closed principle used for `InlineContractSpec`. Verified
via `tests/test_mt5_live_order_e2e.py` (updated `test_buy_order_fills` /
`test_sell_order_fills` to pass realistic raw-unit quantities and assert the
broker receives the converted lot volume, not the raw units) — passes, plus
full existing suite passes with only 2 pre-existing (unrelated) failures.

**Not yet done**: `risk/engine.py::_layer4()` still has its own independent
raw-units formula (not reached today per the equity=0 hardcoding, but should
still be fixed or removed to avoid a second copy of this logic drifting).
The proper broker-native sizer (`risk/position_sizer_v2.py::size_position()`)
already computes lots correctly and independently but is still unwired from
the live path — `core/trading_loop.py` imports the module but never calls the
function; wiring it in fully (requires a real MT5-native `contract_spec`
object, live `calc_profit_fn`/`calc_margin_fn`) is a separate, larger task
deliberately not rushed here.

## Summary

Two independent live-reachable position-sizing implementations compute
`approved_quantity` as **raw units of the underlying** (e.g. troy ounces
for XAUUSD), via the same formula:

```
risk_budget = equity * risk_pct
approved_quantity = risk_budget / abs(entry_price - stop_loss)
```

No code between signal generation and the MT5 adapter converts this
units-based quantity into **lots** (MT5's native order-volume unit,
where e.g. 1.00 lot of XAUUSD = 100 oz). `execution/adapters/mt5.py`
sends `float(order.quantity)` directly as MT5's `"volume"` field with
no division by contract size.

**If ever wired to a live/funded MT5 account with real equity, a
"1%-risk" signal would size a position ~100x too large for XAUUSD**
(scales differently — up to 100,000x — for FX pairs, given their
100,000-unit lot convention). This was found while investigating the
user's request to check whether the F27/Trial-2001 contract-spec bug
had a live-capital analogue — it does, but it's a separate defect in a
separate code path, not the same bug.

## Evidence (empirical, not inferred)

Ran `core/agents/portfolio_manager.py`'s `PortfolioManagerAgent` end to
end with a realistic XAUUSD signal (script:
`test_sizing_reachability.py`, not committed — scratch):

- entry=2400.0, stop=2380.0 ($20 stop distance), equity=$10,000, risk_pct=1%
- **Real, executed result**: `approved_quantity = 5.0`
- If sent to MT5 as `volume=5.0` (lots): 5.0 lots x 100 oz/lot = 500 oz
  notional (~$1.2M on a $10k account). If stop is hit: real loss =
  5.0 x 100 x $20 = **$10,000 — the entire account**, against an
  intended 1% ($100) risk budget.

Traced the full path from signal to broker call with no unit/lot
conversion found at any hop:
- `core/agents/portfolio_manager.py::act()` — computes raw units (as above)
- `core/trading_loop.py::on_signal()` — passes `quantity` through unchanged
  (`quantity = signal.metadata.get("approved_quantity", 0.0)`)
- `execution/manager.py::submit_order()` / `_to_adapter_order()` — passes
  `quantity` through unchanged
- `execution/adapters/mt5.py` — `qty_float = float(order.quantity)`,
  sent directly as MT5's `"volume"` parameter (lots)

`risk/engine.py::_layer4()` has the identical raw-units formula
(`approved_qty = risk_budget / risk_per_unit`), but is reached via
`RiskEngine.check_order()`, which **hardcodes
`AccountState(equity=0.0, balance=0.0)`** (comment: "broker unavailable
-> zero-equity account"). Layer 3 rejects on `equity <= 0` before
Layer 4 ever computes a quantity. So the webhook -> `OrderManager` ->
`RiskEngine.check_order()` path currently **rejects every order
unconditionally** (safe, but also non-functional -- a separate,
lower-severity gap) and does not currently reach the buggy formula.

`PreTradeRiskGate.check_order_sync()` (risk/pre_trade_gate.py) checks
kill switch, circuit breaker, and price-sanity only -- no
volume/notional/margin sanity check exists anywhere in this stack that
would catch an oversized order before it reaches the broker.

## Which pipeline is actually "live" right now

**Neither.** The only process currently running against this codebase
is the tick/spread recorder (`run_shadow.py` equivalent, per the
in-progress multi-day cost-calibration collection) -- it does not
touch position sizing or order submission at all. Both the webhook
path and the orchestrator/`PortfolioManager` path exist as reachable
code but are not currently deployed against a funded account.

## Severity framing

This is a **before-live blocker**, not an active incident -- nothing
is connected to real capital right now (consistent with everything the
user has been told this session). It belongs on the same pre-live
checklist as the funding-arb rigor items: whichever pipeline is
eventually chosen to place real orders (webhook or orchestrator) must
have this fixed and covered by a test asserting the final broker
`volume` equals intended-risk-dollars / (contract-size-scaled
per-lot-loss), before any live wiring happens.

## Fix sketch (not yet implemented — flagging for a deliberate follow-up, not a rushed patch)

Both `risk/engine.py::_layer4()` and
`core/agents/portfolio_manager.py::act()` need to divide their raw-unit
`approved_quantity` by the symbol's `contract_size` (from the new
`core/contract_specs.py` canonical table added today) before it is
treated as "lots" downstream — or, equivalently, `execution/adapters/mt5.py`
needs to perform that division once, in one place, immediately before
calling the broker. A single conversion point is preferable to fixing
it in both sizing implementations separately, since there are already
two independently-drifting copies of this formula (itself an echo of
the exact multiple-source-of-truth problem F27 already found once).
