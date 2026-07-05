# INTRABAR EXECUTION FIDELITY
**Phase 4 | 2026-07-05 | TIER 1**

---

## 4.1 — Same-Bar SL/TP Ambiguity Resolution

### Implementation
`execution/execution_simulator.py:240-260` — `evaluate_open_positions()`:

```python
if trigger == "SL" and pos.take_profit is not None:
    tp_hit = (pos.side == Side.BUY and market.bid >= pos.take_profit) or (
        pos.side == Side.SELL and market.ask <= pos.take_profit
    )
    if tp_hit:
        exit_price, pnl = self._resolve_adverse(pos, market)
        # → EventType.AMBIGUOUS, resolved as SL (adverse)
```

### Verdict
**CONSERVATIVE — SL wins ambiguous bars** ✅

When both SL and TP are hit within the same bar, the simulator resolves as STOP_LOSS (adverse outcome). This is the correct default per R17.

### Additional: `_resolve_adverse()` applies slippage to SL fill
```python
# execution_simulator.py:305-313
if pos.side == Side.BUY:
    exit_price = pos.stop_loss - slippage  # worse than exact SL level
```

## 4.2 — Fill Price Assumption
- **Entries:** Fill on next bar's estimated bid/ask + half-spread + latency slippage + market impact + adverse selection
- **Exits via SL:** Fill at SL level ± slippage (worse than exact level)
- **Exits via TP:** Fill at exact TP level (conservative assumption)
- **Dynamic spread:** Time-of-day spread model (`backtest/dynamic_spread_model.py`)

## 4.3 — Sub-Bar Replay Validation
- **Not performed** — no tick-level replay found
- **Status:** `[NEVER PERFORMED]`

## 4.4 — Gap-Through-Level Handling
- Intra-bar check in `evaluate_open_positions()`: if `bar_low <= stop_loss` for BUY, triggers SL even if current bid/ask didn't reach it
- Gap slippage modeled via the SL fill slippage
- **Status:** Handled ✅

## 4.5 — Close-Price-Fill Status
- `KNOWN_LIMITATIONS.md:4` states "Backtest engine uses close-price fills"
- **Current reality:** Engine uses bid/ask estimation from OHLC bars with slippage model — NOT raw close-price fills
- **Status:** Document outdated; engine has been improved beyond close-price fills
