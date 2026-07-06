# INTRABAR EXECUTION FIDELITY — Phase 4
## Deep Audit v4.0 | 2026-07-05

---

### 4.1 Same-Bar SL/TP Ambiguity Resolution

#### 4.1.1 Core Logic

The primary ambiguity resolution occurs in `execution/execution_simulator.py:277-379` in `evaluate_open_positions()`:

```python
# execution_simulator.py:319-334
if trigger == "SL" and pos.take_profit is not None:
    tp_hit = (pos.side == Side.BUY and market.bid >= pos.take_profit) or (
        pos.side == Side.SELL and market.ask <= pos.take_profit
    )
    if tp_hit:
        exit_price, pnl = self._resolve_adverse(pos, market)
        event = ExecutionEvent(
            trade_id=pos.trade_id,
            event_type=EventType.AMBIGUOUS,
            ...
        )
```

**Resolution policy: ADVERSE-FIRST (SL wins)**:
1. If SL is triggered, check if TP is also triggered at current bid/ask (:320-323).
2. If BOTH triggered → `_resolve_adverse()` is called (:324) → SL price with slippage applied (:385-395). Trade recorded with `EventType.AMBIGUOUS`.
3. If only SL → exit at SL price with slippage (:336-346).
4. If only TP → exit at exact TP price (:348-357).

**This is CONSERVATIVE**: SL always takes precedence in ambiguous bars. TP is treated as lost opportunity.

Backed by `execution/ambiguous_bar_resolver.py:40-89`:
```python
# ambiguous_bar_resolver.py:56-68
if side == Side.BUY:
    sl_triggered = bar_low <= stop_loss
    tp_triggered = bar_high >= take_profit
else:
    sl_triggered = bar_high >= stop_loss
    tp_triggered = bar_low <= take_profit

is_ambiguous = sl_triggered and tp_triggered

if is_ambiguous:
    resolved_reason = "SL"          # Adverse: SL wins
    resolution_price = stop_loss
```

**And in `fill_model.py:67-87`** (`check_sl_tp_trigger`):
```python
# fill_model.py:81-87
if sl_hit and tp_hit:
    return "SL"        # Both hit → SL wins (conservative)
if sl_hit:
    return "SL"
if tp_hit:
    return "TP"
return None
```

**Verdict**: PASS — Same-bar SL/TP ambiguity is resolved conservatively. SL always wins. No always-favorable bias.

#### 4.1.2 Ambiguous Bar Quantification

Each trade flagged as ambiguous has `ambiguous_bar=True` in `BacktestTrade` (`backtest/engine.py:1148`). The event type `EventType.AMBIGUOUS` is recorded at execution_simulator.py:327.

The ambiguous bar count is available from trade records but **not yet quantified** in reports. A simple filter on `t.ambiguous_bar == True` in results would reveal the count.

#### 4.1.3 Intra-Bar Additional Check

Beyond the bid/ask instantaneous check, the simulator also checks bar high/low for intra-bar SL/TP touch:

```python
# execution_simulator.py:308-317
if trigger is None:
    if pos.side == Side.BUY and bar_low <= pos.stop_loss:
        trigger = "SL"
    elif pos.side == Side.SELL and bar_high >= pos.stop_loss:
        trigger = "SL"
    elif pos.side == Side.BUY and bar_high >= (pos.take_profit or Decimal("0")):
        trigger = "TP"
    elif pos.side == Side.SELL and bar_low <= (pos.take_profit or Decimal("0")):
        trigger = "TP"
```

This catches cases where the **current bid/ask** doesn't show a trigger but intra-bar high/low extremes DID touch the level. This is a reasonable approximation for bar-only data.

**Caveat**: This doesn't account for the ORDER of intra-bar touches. If price touches TP first, then reverses and hits SL, the code still triggers SL (checking via market.bid/ask at :320-323 only within the SL-triggered branch). The intra-bar path check (:308-317) is only triggered when bid/ask doesn't trigger anything. Combined logic can miss the TP-first-then-SL scenario.

**Verdict**: PASS (conservative) — In the worst case, SL wins even if TP was touched first intra-bar.

---

### 4.2 Fill Price Assumption

#### 4.2.1 Entry Fill

`execution/execution_simulator.py:179-275` (`submit_intent`):
```python
fill_idx = bar_index + 1                    # Signal bar N → fill on N+1
fill_bar = bars[fill_idx]                  # Next bar's OHLCV
bid, ask = estimate_bid_ask_from_bar(...)   # Estimate bid/ask from bar OHLC
# ...
slippage_entry = market.spread / 2 + intent.latency_slippage + market_impact + adverse_selection
req = FillRequest(
    ...
    entry_price=Decimal(str(fill_bar["open"])),  # Bar open as reference
    ...
)
fill = simulate_entry(req, bid, ask, spread)
```

`fill_model.py:41-56` (`simulate_entry`):
```python
if req.side == Side.BUY:
    entry = ask + req.slippage_entry     # Buy at ask + slippage
else:
    entry = bid - req.slippage_entry     # Sell at bid - slippage
```

**Fill timing**: Signal from bar N → fill at bar N+1's **estimated bid/ask with slippage**. Uses bar N+1's open as entry_price reference and bid/ask estimated from N+1's OHLC.

**Conservative elements**:
- `slippage_entry = spread/2 + latency_slippage + market_impact + adverse_selection` (:211)
- Market impact uses sqrt model (Almgren-Chriss) from `execution/market_impact.py`
- Adverse selection adds half-spread cost for momentum entries (:921-925)

**Bid/Ask estimation** (`execution/conservative_bar_model.py:28-42`):
```python
mid = (high + low) / 2
bid = mid - spread_estimate / 2
ask = mid + spread_estimate / 2
```

This estimates bid/ask from bar mid ± half-spread. **Conservative**: uses bar high/low for mid estimate (wider than close-only would give).

#### 4.2.2 Exit Fill (SL/TP)

`execution/execution_simulator.py:397-414` (`_resolve_exit`):
```python
if trigger == "SL":
    if pos.side == Side.BUY:
        exit_price = pos.stop_loss - slippage   # SL worse than exact level
    else:
        exit_price = pos.stop_loss + slippage
else:
    exit_price = pos.take_profit or Decimal("0")  # TP at exact level
```

**SL fills**: Include slippage (worse than exact stop level). Conservative.
**TP fills**: At exact take-profit level. Potentially optimistic (real fills may miss TP by 1 tick).

#### 4.2.3 Spread-Aware Exit

Exit always considers bid/ask: LONG closes at bid, SHORT closes at ask (via `simulate_exit` at fill_model.py:59-64):
```python
if side == Side.BUY:
    return bid - slippage, slippage        # Sell long at bid
return ask + slippage, slippage             # Buy back short at ask
```

**Verdict**: PASS — Entry uses next-bar estimated bid/ask with multi-source slippage. Exit SL includes slippage. TP at exact level is the only potentially optimistic assumption.

---

### 4.3 Sub-Bar Replay Validation

#### 4.3.1 Tick Replay Capability

- `ExecutionQuality.TICK_REPLAY` is defined at `fill_model.py:16` — an enum value, not an implementation.
- **No tick replay implementation exists** in the `execution/` directory. The enum value is aspirational.
- The current execution model uses `ExecutionQuality.BAR_ONLY` for all fills (`execution_simulator.py:71` — default value).
- No module in the codebase reads finer-granularity tick data for replay validation.

**Verdict**: FAIL — Tick replay is not implemented. All execution simulation uses bar-level OHLCV data only. The `TICK_REPLAY` enum exists as a placeholder.

#### 4.3.2 Finer Timeframe Replay

- The MTF cursor system (`backtest/mtf_cursor.py`) could theoretically provide finer-timeframe data (M1 within M15), but this is used for **signal generation** (multi-timeframe analysis), NOT for execution simulation.
- No mechanism to replay a trade's entry/exit against M1 data when the strategy runs on M15.

**Verdict**: FAIL — No sub-bar replay validation performed. Bar OHLC-based fills are the only execution model.

---

### 4.4 Gap-Through-Level Handling

#### 4.4.1 Price Gapping Past Entry+SL

In `execution/execution_simulator.py:179-275`, the entry fill uses the NEXT bar's OHLCV to compute bid/ask. If the price gaps significantly from signal bar to next bar, the entry uses the gapped-to price — **realistic**.

However, the order of operations in `_check_exits` → `evaluate_open_positions` assumes within-bar triggers. For a gap through SL + TP in one bar:
- The bar OHLC extremes encompass the SL/TP levels → intra-bar check at :308-317 catches it.
- If both SL and TP were gapped-through, the conservative SL-first resolution applies (:319-334).
- The exit price is set to SL level + slippage (:389-394), NOT the gapped-through worse price.

**Gap-through slippage beyond SL level**: If price gaps from $2360 to $2340 (through SL at $2350), the code sets exit_price = $2350 - slippage. Real fill could be anywhere between $2350 and $2340. The code's fill at SL-level minus slippage is actually slightly BETTER than worst-case (which would be the low of the gap bar at $2340).

**Verdict**: MINOR OPTIMISM — Gap-through fills are simulated at SL level + slippage, not at the full gap-through price. Conservative-enough for most cases but could overstate recovery in extreme gap scenarios.

#### 4.4.2 Gap Protection

- **No explicit gap protection exists**. There's no logic to detect a gap > N× ATR and refuse fills or apply additional slippage.
- This is acceptable for forex majors (rarely gap significantly) but concerning for crypto and weekly openings in metals/index CFDs.

---

### 4.5 Close-Price-Fill Status Check

#### 4.5.1 Current Fill Architecture

The backtest engine does NOT use direct close-price fills. Instead:

1. **Entry**: `execution_simulator.py:194-205` — fills on bar N+1, uses `estimate_bid_ask_from_bar()` with bar N+1's OHLC, then applies slippage.
2. **Exit**: `execution_simulator.py:277-379` — evaluates SL/TP on current bar's estimated bid/ask with intra-bar high/low for additional trigger detection.

This is a **bar-based conservative model**, NOT a close-price fill model. The entry_price reference (`fill_bar["open"]`) at :218 is only used as a reference for the FillRequest data structure; the actual fill price is `ask + slippage` or `bid - slippage`.

**Verdict**: PASS — NOT close-price-fill. Uses bid/ask estimated from bar OHLC with explicit slippage.

#### 4.5.2 Per-Asset-Class Intrabar Severity

| Asset Class | Intrabar Range (Approx) | Bar OHLC Adequacy | Gap Risk |
|-------------|------------------------|-------------------|----------|
| **Forex majors** | 5-20 pips/M15 | Adequate — intrabar moves typically captured by high/low | Low (continuous market) |
| **XAUUSD** | $1-5/M15 | Marginally adequate — 20-50× tick_size range, OHLC captures extremes | Medium (weekend/open gaps) |
| **BTC/ETH** | $50-500/M15 | **INADEQUATE** — extreme intrabar spikes possible, OHLC-only misses path-dependent fills | High (24/7 but high volatility) |
| **Indices (NAS100)** | 20-100 points/M15 | Marginally adequate — but CFD pricing adds spread variability | Medium (session gaps) |
| **XAGUSD** | $0.10-1.00/M15 | Adequate — but wider spreads lower fill fidelity | Medium |

#### 4.5.3 Crypto Perpetual Execution (ccxt)

`market_data/ccxt_feeder.py` provides crypto OHLCV. The same execution simulator would be used for crypto backtesting, but:
- Crypto exchanges have different fee structures (maker/taker fees)
- Perpetual funding rates create unique cost flows
- Exchange-specific order book depth matters for fills
- 24/7 trading with extreme short-term volatility

The current execution model has **no crypto-specific adjustments** beyond the `BTCUSDT` contract spec at `backtest/engine.py:138-142` (contract_size=1, tick_size=0.01, tick_value=0.01).

**Verdict**: FAIL — Crypto execution model is generic. No exchange-specific fee structure, funding rate costs, or order book depth modeling.

---

### 4.6 Execution Quality Tracking

#### 4.6.1 Quality Enums

`execution/fill_model.py:13-17`:
```python
class ExecutionQuality(Enum):
    BAR_ONLY = "bar_only"
    CONSERVATIVE_BAR = "conservative_bar"
    TICK_REPLAY = "tick_replay"
    LIVE_OBSERVED = "live_observed"
```

Only `BAR_ONLY` is used in backtest mode. `TICK_REPLAY` and `LIVE_OBSERVED` are aspirational enum values — NOT implemented.

#### 4.6.2 Quality Breakdown in Results

`backtest/engine.py:1365-1371`:
```python
quality_counts: dict[str, int] = {}
for t in self.trades:
    q = t.execution_quality or "unknown"
    quality_counts[q] = quality_counts.get(q, 0) + 1
```

All backtest trades will show `quality_breakdown: {"bar_only": N}` since no other quality level is reachable.

#### 4.6.3 Cost Breakdown

Backtest results include (`backtest/engine.py:1421-1425`):
- `total_spread_cost`: Sum of entry spread costs
- `total_slippage_cost`: Sum of entry + exit slippage

These use the correctly-computed cost model values (see Phase 3 §3.2.4) — spread and slippage are computed correctly per-trade. However, the P&L these costs are netted against is wrong (P&L understatement bug from Phase 3 §3.2.1).

---

### 4.7 Dynamic Spread & Time-of-Day Modeling

`backtest/engine.py:884-891, 1006-1012`:
```python
try:
    from backtest.dynamic_spread_model import SpreadConfig
    _spread_config = SpreadConfig()
    bar_hour = current_time.hour if hasattr(current_time, "hour") else 12
    spread = Decimal("0.01") * _spread_config.get_spread(bar_hour)
except Exception:
    spread = Decimal("0.01") * Decimal(str(self.config.spread_pips))
```

**Dynamic spread**: Uses `dynamic_spread_model.py` to adjust spread by time of day (e.g., wider during Asian session, tighter during London/NY overlap). Falls back to config `spread_pips` if the model isn't available.

This is a **positive feature** — recognizes that spreads vary by session and that backtesting with constant spread is unrealistic.

**Verdict**: PASS — Dynamic spread by time of day is implemented.

---

### 4.8 Time Stop (Maximum Bars Open)

`execution/execution_simulator.py:360-377`:
```python
elif max_bars_open > 0 and (current_bar_index - pos.signal_bar_index) >= max_bars_open:
    mid = (market.high + market.low) / 2
    exit_price = mid ± spread/2  # mid ± half-spread
```

Positions auto-close after `max_bars_open` (default 50). The exit uses mid ± half-spread, which is slightly better than bid/ask fill. This is a **minor optimistic bias** for time-stop exits. The P&L effect is immaterial for normal spreads.

**Verdict**: PASS (minor) — Time-stop exit uses mid ± spread/2. Slightly optimistic but negligible.

---

### Summary: Phase 4 Critical Findings

| # | Severity | Finding | File:Line |
|---|----------|---------|-----------|
| 1 | **HIGH** | Tick replay is not implemented. All fills use bar OHLC only. `TICK_REPLAY` is an aspirational enum. | `fill_model.py:16` (enum only) |
| 2 | **HIGH** | No sub-bar validation ever performed. No trade replayed against finer timeframe data. | N/A |
| 3 | **HIGH** | Crypto execution has no exchange-specific modeling (maker/taker fees, funding rates, order book depth). | `ccxt_feeder.py` (data only, no execution) |
| 4 | **MEDIUM** | Gap-through fills use SL-level + slippage, not the full gap-through price. Slightly optimistic. | `execution_simulator.py:389-394` |
| 5 | **MEDIUM** | TP fills at exact level — no slippage or missed-fill modeling. | `execution_simulator.py:408` |
| 6 | **PASS** | Same-bar SL/TP: conservative adverse-first resolution. SL wins. | `execution_simulator.py:319-334` |
| 7 | **PASS** | Entry fills on next-bar estimated bid/ask with multi-source slippage. NOT close-price fill. | `execution_simulator.py:194-211` |
| 8 | **PASS** | Dynamic spread by time of day implemented. | `dynamic_spread_model.py` |
| 9 | **MINOR** | Time-stop exit uses mid ± spread/2 instead of bid/ask. Slightly optimistic. | `execution_simulator.py:361-366` |
