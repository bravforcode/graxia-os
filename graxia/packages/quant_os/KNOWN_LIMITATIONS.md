# Known Limitations

1. `broker/mt5_gateway.py` is read-only by design (forbids order_send/order_modify/order_close,
   see its own module docstring) — but `execution/adapters/mt5.py` is a SEPARATE, live-order-capable
   adapter that DOES submit real orders under TRADING_MODE=LIVE_MICRO/LIVE_LIMITED/LIVE_CONTROLLED +
   LIVE_TRADING_ENABLED=true. Do not read "MT5 gateway is read-only" as "MT5 integration is safe by
   default" — only `broker/mt5_gateway.py` is; `execution/adapters/mt5.py` is not, and is the one on
   the live order-placement path. (Corrected 2026-07-29 — this line previously conflated the two and
   could mislead a reader into believing live order placement was not possible.)
2. Margin estimate from `order_calc_margin()` does not account for existing positions
3. Swap cost — **FIXED on the paper/live path 2026-08-06** (was: wired into the BACKTEST engine
   (`backtest/engine.py:79-83,1131,1141,1172` calls `core/risk/swap_cost.py`,
   `BacktestConfig.enable_swap=True` by default) but confirmed via grep across
   every live-path file (`execution/oms.py`, `execution/manager.py`,
   `execution/adapters/mt5.py`, `execution/adapters/manager.py`,
   `core/trading_loop.py`, `risk/`) to have ZERO call sites of the swap model —
   0 matches for "swap" in any of them. `execution/ledger.py` has a `swap_cost`
   schema field but nothing on the live path ever writes a nonzero value into
   it. This meant backtest P&L includes swap but live P&L would NOT — a
   backtest/live cost-accounting mismatch.)
   Fix (2026-08-06, approved combined governance+P0 workstream): `execution/adapters/paper.py`
   now realizes swap on position close via `execution/swap_model.py::SwapPolicy`, fed by the SAME
   measured rates the backtest uses (`config/cost_calibration.json`, bps of notional:
   XAUUSD -0.5/+0.1, USDJPY -0.3/+0.1, OIL -1.5/+0.3; NAS100 still `UNVERIFIED_NO_DATA` →
   fail-closed NONE). Symbols without swap data get `SwapMode.NONE` (zero swap, never assumed).
   While wiring, also fixed a REAL pre-existing bug: `PaperAdapter` never credited realized
   price PnL to cash on close (fees only moved cash) — every realized gain/loss evaporated
   from equity when the position was deleted. Both verified via
   `tests/test_paper_adapter_swap.py` (7 tests) + `tests/test_optimization_atr_kelly_cost.py`.
   Note: the same swap data (XAUUSD/USDJPY entries) was present in the working tree from a
   prior session but uncommitted — committed together with the wiring.
4. Backtest engine uses close-price fills — Phase 3.1 addressed bar-level resolution; tick-level fill pending
5. ContractSpec snapshots have placeholder SHA-256 hashes
6. No EURUSD or GBPUSD research started
7. Walk-forward implemented for XAUUSD/EURUSD at 15min/1min. DSR and PBO analysis not yet standardized.
8. `execution/adapters/mt5.py::_ensure_connected()` raises `ConnectionError` on reconnect exhaustion.
   Fixed (2026-07-29) in `submit_order()` — both call sites now catch it and return
   `OrderResult(status=TIMEOUT)` instead of propagating an uncaught exception (see
   `tests/test_mt5_live_order_e2e.py::TestMT5E2EErrorRecovery`). Revised (2026-07-29 WS-D review):
   - `cancel_order()` / `close_position()` — catch `ConnectionError`, return
     `OrderStatus.TIMEOUT` (transient, matches `submit_order()` so retry/reconcile logic behaves).
   - `get_positions()` / `get_account_info()` — `ConnectionError` is intentionally
     NOT swallowed; it propagates to callers (`reconcile.py`, `kill_switch.py`,
     `orchestrator.py`, `oms.py`, `manager.py`) which already wrap these calls in
     `try/except` and handle the error correctly. Returning `[]` / zeroed
     `AccountInfo` would route around that handling and make a kill-switch believe
     there are no positions to close — a safety failure.
   - `set_stop_loss()` — returns `False` (boolean success indicator; acceptable).
9. `core/rollover_filter.py::RolloverFilter` — real, complete class, confirmed via grep
   to have zero call sites in `execution/` or `risk/` (only its own docstring example
   and chaos tests reference it). **Deferred, not wired** (2026-07-29): every candidate
   trading edge in this project's history is REJECTED/FAIL_RIGOR and there is a standing
   no-live-capital mandate, so wiring a rollover-session filter into a live signal path
   that has no approved live signal yet would be premature, unverifiable work. Revisit
   if/when a strategy actually reaches live candidacy.
10. `core/risk_budget.py::RiskBudget` — real, complete class, confirmed via grep to have
    zero call sites in `execution/` or `risk/engine.py` (only used by
    `scripts/dashboard_streamlit.py`, a read-only display, and its own tests). Note a
    SEPARATE, differently-scoped `RiskBudget` class also exists in `micro_live/risk_check.py`
    — do not conflate the two if revisiting this. **Deferred, not wired** (2026-07-29):
    same reasoning as #9 — no live-approved strategy exists yet to enforce a budget for.
11. Paper/live execution parity — confirmed via `Glob` that no test named `*parity*`
    tests paper-vs-live order-execution equivalence; the one parity test that exists
    (`tests/test_feature_parity.py`) covers feature computation, not order execution.
    **Deferred** (2026-07-29): a real parity test would need to run both adapters against
    equivalent inputs, which given zero live-approved strategies and no live MT5 access in
    this environment, cannot currently be constructed as more than a trivial/vacuous test
    — writing one now risks giving false assurance rather than real evidence. Revisit when
    live MT5 access is available (same blocker as P0-2/`size_position()` wiring).
12. `strategies/ensemble.py::get_ensemble_signal()` — FIXED (2026-07-29). Bug: a
    sub-strategy that returned `None`/`NO_TRADE` still had its weight added to
    `total_weight` before the None-check, diluting the ensemble's normalized
    conviction (`buy_score/total_weight`) as if a no-signal strategy were a
    dissenting vote rather than an abstention. Fix: moved `total_weight += rec.weight`
    to after the None/NO_TRADE check, so only participating strategies' weight is
    counted. Verified via `tests/test_ensemble_c3.py` + `test_ensemble_binarize_adapter.py`
    + `test_strategies.py` (49 passed, 0 regressions) run through the absolute
    interpreter path.
13. Trial-registry/ledger numbering — found a genuine, UNRESOLVED collision while
    re-auditing the consolidation work: `research/hypothesis_registry_c.json` records
    the BTC-volume-divergence trial (`BTCVD`, p=0.5533, dated 2026-07-13) as
    `trial_number: 3001`, while `research/trial_ledger_c.json` records the SAME trial
    (identical date, identical p-value, id `btc_vol_divergence`) as `trial_number: 3004`.
    One trial, two different registered numbers, across two files that are both
    currently live in the repo. Also: `hypothesis_registry_b.json` is missing trials
    2008 and 2012 that exist in `trial_ledger_b.json`; `trial_ledger.json`'s
    `next_available_trial_number` field is stale (says 1022, but 1022-1027 already
    exist in the registry). **Not fixed this session** — deliberately not renumbering
    trial ledgers without explicit sign-off, since silently changing trial IDs in a
    project this focused on trial-registry integrity is exactly the kind of change
    that should be reviewed, not auto-corrected.
14. Trailing-stop / post-fill stop-loss is DEAD CODE on the live fill path — the
    original "circuit_breaker trailing-stop broken" claim pointed at the wrong file
    (`git log --all -S "highest_equity"` across full history returns zero commits;
    that mechanism never existed in `risk/circuit_breaker.py`). The REAL bug, confirmed
    by direct grep (2026-07-29): `execution/adapters/mt5.py::update_trailing_stop()`
    (line 598) and `execution/oms.py::_setup_post_fill_stop_loss()` (line 679) both have
    ZERO callers anywhere outside their own test files
    (`tests/test_stop_loss_and_price_sanity.py`, `tests/test_optimization_atr_kelly_cost.py`).
    Both are correctly unit-tested in isolation (32/32 and 5/5 passing respectively) but
    disconnected from the runtime order-fill path. `TrailingStopConfig.stop_mode` is set
    per-symbol in `oms.py` but never read/branched on anywhere. Note: an INITIAL stop-loss
    CAN still reach the broker if the upstream strategy signal populates `order.stop_loss`
    directly — `mt5.py::submit_order()` forwards `order.stop_loss` into the MT5 request's
    `sl` field unconditionally when present. What's confirmed dead is (a) the ATR-proxy
    fallback stop-loss for orders that arrive WITHOUT an explicit stop, and (b) ALL
    trailing-stop ratcheting after fill, regardless of `stop_mode` config. **Not fixed
    this session** — wiring either back in touches the live fill path and needs its own
    review of ATR-proxy correctness (a separate audit already flagged
    `default_atr_pct=0.02` as a crude proxy, see `reports/DEEP_TRADING_LOGIC_RISK_AUDIT.md:50`)
    before being trusted.
15. `risk/position_sizer.py::AntiMartingaleSizer` — audited 2026-07-29, verdict "broken
    but currently safe (inert)". Its win/loss-streak adjustment math (`adjustment ∈
    [0.25, 2.0]`) cannot itself produce negative risk — 5/5 tests in
    `tests/test_antimartingale_tiers.py` pass. Negative risk IS reproducible
    (`AntiMartingaleSizer(base_risk_pct=-0.5, ...)` → negative lots/notional/risk_amount)
    because the constructor never validates `base_risk_pct >= 0`, and `_apply_limits()`
    only clamps the upper bound, not negative values. However: `AntiMartingaleSizer` is
    NOT wired into any live/paper call path — `get_default_sizer()` only ever returns
    `FixedFractionalSizer`, and the actual live caller
    (`autonomous/order_executor.py:390-399`) uses `FixedFractionalSizer` exclusively with
    an internally-clamped, always-positive risk_pct. `AntiMartingaleSizer` currently
    appears only in test files. **Not fixed this session** — low priority given it's
    unreachable from any live path; if it's ever wired in, add `base_risk_pct = max(0.0,
    base_risk_pct)` validation to the constructor first.
16. `docker/requirements.api.txt` CVEs — FIXED (2026-07-29), user-approved. `aiohttp`
    bumped 3.11.16 → 3.14.1 (cleared 31 CVEs), `pydantic-settings` bumped 2.14.1 → 2.14.2
    (cleared 1 CVE). Re-ran scoped `pip-audit -r docker/requirements.api.txt` after the
    bump: "No known vulnerabilities found". `docker/requirements.trainer.txt` scan (which
    previously timed out) was rerun to completion: also clean, 0 vulnerabilities. Neither
    package is directly imported/called anywhere in this repo's own code (aiohttp/pydantic
    only used transitively via fastapi/uvicorn/httpx), so blast radius of the version bump
    is low, but full API service startup was NOT integration-tested against the new pins
    in this environment (no running deployment to verify against) — worth a real
    `docker-compose up` smoke test before deploying this change.