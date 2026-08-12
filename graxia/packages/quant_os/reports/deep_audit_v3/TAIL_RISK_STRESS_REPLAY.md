# PHASE 12 — TAIL RISK, STRESS-EVENT REPLAY & FLASH-CRASH SURVIVAL
*Per R1–R18, R18 (calm-market backtest ≠ survival evidence). Tier 2.*

---

## 12.1 — Historical Coverage of Known Tail Events

XAUUSD M1 data starts **2026-06-22** (Phase 0.5, verified). Today is 2026-06-29. **The backtest window is 7 days of late-June 2026.**

| Known FX/gold tail event | In window? |
|---|---|
| Jan 2015 SNB CHF de-peg | NO (pre-data) |
| Jun 2016 Brexit | NO |
| Mar 2020 COVID shock | NO |
| Aug 2024 yen carry-trade unwind | NO |
| Any 2026 gold flash-crash | **UNKNOWN / not visible in 7-day calm window** |

**Per R18, stated explicitly: the reported Sharpe ratio and drawdown figures characterize behavior in calm-to-normal markets only. Tail-event survival is untested by the backtest itself.** This is not a minor caveat — it is the difference between "the strategy works" and "the strategy works in the conditions we happened to test."

## 12.2 — Explicit Stress-Event Replay
- `[NOT PERFORMED]`. No synthetic-shock replay script run, no result. The capability exists (`risk/stress_test.py`, `scripts/stress_test.py` 1092 LOC) but `[no artifact]`. → P1.
- Would the SL trigger as designed, or gap through it? **Phase 4.4 established the engine books the exit at the exact SL price with no gap-slippage** → in a tail event the *modeled* loss understates the *real* loss. The kill switch (Phase 9.2) would activate but could not guarantee a fill during the liquidity vacuum.

## 12.3 — Margin & Stop-Out Under Extreme Moves
- `RiskPolicy.reject_if_margin_level_below_pct=500` (5:1) (`risk_policy.py:18`) — hardcoded. Pepperstone actual stop-out `[UNVERIFIED]`.
- At what adverse move is the account forcibly stopped out by the broker? `[NOT COMPUTED]`. → P1.
- Negative balance protection unknown (Phase 11.1). **Without it, a gap-through could produce loss > equity.** → Critical.

## 12.4 — Correlated Cascade Risk
- Single-symbol focus (XAUUSD primary). But `core/config.py:52` lists 8 symbols; if multiple are traded concurrently, gold + JPY + risk-off FX all move together in a stress event.
- `risk/portfolio.py`, `core/portfolio_risk.py`, `risk/correlation_provider.py` exist → aggregate-risk capability present. `[Not confirmed active in live path]`. → P2.

## 12.5 — Tail-Risk Summary Table

| Scenario | In backtest data? | Replay performed? | Survives? | Evidence |
|---|---|---|---|---|
| SNB-style single-pair shock | NO | NO | UNVERIFIED | 7-day calm window |
| Flash crash (10×+ range) | NO | NO | UNVERIFIED | no tick replay + Phase 4.4 gap bug |
| Weekend gap beyond normal | NO | NO | UNVERIFIED | gap handling absent (Phase 1.8) |
| Correlated multi-pair cascade | NO | NO | UNVERIFIED | portfolio risk `[unverified active]` |
| Broker outage / stop-out during shock | NO | NO | UNVERIFIED | DMS in-process (Phase 9.2) |

---

## Phase 12 — Verdict

**STATUS: FAIL (by precondition).** The backtest data contains no tail event, so no headline number from it has earned the right to imply survival. Combined with the Phase 4.4 gap-through bug (exits booked at exact SL, not gapped fill) and unknown negative-balance protection, **the system's behavior in the kind of event that ends accounts is entirely untested — and the one execution-fidelity gap we did find points in the wrong direction (overstating exit fills).**

This is not a fixable code bug alone; it requires (a) longer data spanning a real shock, (b) a synthetic-shock replay suite that is actually run, and (c) confirmed negative-balance protection from the broker.
