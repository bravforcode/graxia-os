# PHASE 4 — INTRABAR PATH & EXECUTION SIMULATION FIDELITY
*Per R17 (same-bar SL/TP must default to conservative).*

---

## 4.1 — Same-Bar SL/TP Ambiguity Resolution

**This is the one area where the code is genuinely well-built.** Tracing `execution/execution_simulator.py`:

- `check_sl_tp_trigger` (`fill_model.py:67-87`) returns `"SL"` when both SL and TP are hit in the same bar (lines 81-84: `if sl_hit and tp_hit: return "SL"`). **Conservative-first by construction.**
- `evaluate_open_positions` (`execution_simulator.py:263-348`) calls `check_sl_tp_trigger` with `market.bid/ask` (lines 282-285). When the trigger returns `"SL"` **and** TP was also hit (`tp_hit` check at `execution_simulator.py:287-292`), it routes to `_resolve_adverse` (`execution_simulator.py:354-367`) which sets `exit_price = pos.stop_loss` and records `event_type=AMBIGUOUS` with `reason="ambiguous_bar_adverse_sl"`.

**Verdict: R17 SATISFIED.** Ambiguous bars resolve ADVERSE (SL first), and are flagged `ambiguous_bar=true` for later analysis (`engine.py:911, 934`). The protocol's specific concern — "a backtest that silently assumes the favorable outcome on every ambiguous bar" — **does not apply to this engine**. This is a real strength and is stated plainly.

**Caveat (R-self-check #5)**: this is the *canonical* `BacktestExecutionSimulator`. The *other* backtest path (`scripts/backtest_suite.py`) has **no SL/TP at all** — it cannot have this bug because it has no stops. So the favorable-assumption risk is absent there too, for a different (worse) reason.

### Quantification of ambiguous bars

`[NOT QUANTIFIED this session]` — would require running the engine over the 7-day M1 data and counting `ambiguous_bar=true` trades. The plumbing to count exists (`BacktestTrade.ambiguous_bar`, `engine.py:189`). → P2 evidence item, runnable.

## 4.2 — Fill Price Assumption Within the Bar

- **Entry**: `execution_simulator.py:183-208` — fills on `bar_index + 1` (`fill_idx = bar_index + 1`), entry = `fill_bar["open"]` then bid/ask-adjusted via `estimate_bid_ask_from_bar` using the fill bar's high/low. **Entry uses next-bar open + spread/slippage — realistic, no intrabar peek.** ✓
- **Slippage_entry**: `execution_simulator.py:197` `slippage_entry = market.spread / 2` — half-spread. Conservative-ish (real market slippage can exceed half-spread in fast markets, but this is a reasonable model).
- **Exit via SL/TP**: `_resolve_exit` (`execution_simulator.py:369-382`) assumes fill at **exactly** `pos.stop_loss` / `pos.take_profit`. **This does NOT model slippage-through-the-level** — in a fast market a stop fills at the next available price, which can be worse than the stop level. → Phase 4.4 / 12 concern.

## 4.3 — Sub-Bar Replay Validation

`[NEVER PERFORMED / NOT FOUND]`. `ExecutionQuality.TICK_REPLAY` enum exists (`fill_model.py:15`) and `tick/` infrastructure exists, but no tick-level replay of bar-level trades was found as a script or artifact. → P1 gold-standard check, runnable if tick data available (`data/ticks/` is empty, so currently blocked on tick collection).

## 4.4 — Gap-Through-Level Handling

- `_resolve_exit` assumes fill at exactly the SL price. **If price gaps past SL in a single bar (e.g., weekend gap, news spike), the engine still books the loss at the SL level, not the (worse) gapped fill price.** This **overstates** exit fills during gaps → inflates backtest results in exactly the tail scenarios Phase 12 cares about.
- No `gap_slippage` or "fill at next-available-price" logic found in `fill_model.py` or `execution_simulator.py`. → **P1 finding.** This is the gap-through bug the protocol warns about (R-tail).

---

## Phase 4 — Verdict

**STATUS: PARTIAL (good on the headline R17 item, weak on tail fills).**

- **R17 (same-bar ambiguity)**: **PASS** — conservative-by-default, properly flagged. This is a genuine strength.
- **Fill realism (entries)**: PASS — next-bar-open + spread/slippage.
- **Gap-through / slippage-through-SL**: **FAIL** — exits assumed at exact SL/TP price; no gap-slippage model. Overstates fills in tail events.
- **Sub-bar tick replay**: NOT PERFORMED — capability exists, data absent.
