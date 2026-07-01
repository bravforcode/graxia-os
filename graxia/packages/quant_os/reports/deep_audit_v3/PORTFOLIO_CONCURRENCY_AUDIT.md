# PHASE 15 — PORTFOLIO, CORRELATION & CONCURRENT-STRATEGY AUDIT
*Per R1–R18. Tier 2.*

---

## 15.1 — Concurrent Strategies/Instruments

- `core/config.py:52-54` default `symbols` = 8 (EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD, XAUUSD). **Multi-symbol is the configured design intent.**
- `gold_bot/` is a **second, parallel bot** (36 entries, own `core/engine.py` 951 LOC) — appears to be a separate system that may run concurrently. `[Status of gold_bot vs quant_os primary: UNVERIFIED — developer must confirm whether both run on the same account/capital.]`
- `STATUS.md:18-22`: only `liquidity_sweep / XAUUSD` is `CANDIDATE_ONLY`; EURUSD/GBPUSD `NOT STARTED`. So as of `STATUS.md` (2026-06-22), **only XAUUSD is live-intended**, others are configured-but-inactive.

**Current scope (per evidence): intended multi-symbol, currently single-symbol (XAUUSD) candidate.** Stated explicitly, not assumed.

## 15.2 — Correlation & Aggregate Risk
- `risk/portfolio.py`, `core/portfolio_risk.py`, `risk/correlation_provider.py`, `core/correlation.py` exist → capability extensive.
- Correlation matrix of concurrent strategy equity curves: `[NOT COMPUTED/REPORTED]`.
- Portfolio-level risk limit distinct from per-strategy: `core/config.py:65` `max_portfolio_exposure_pct=50`, `risk_policy.py:16-17` `max_symbol_exposure_bps/max_gross_exposure_bps` → limits exist in code. `[Whether enforced in live path UNVERIFIED]`. → P2.

## 15.3 — Capital Allocation Logic
- `strategies/ensemble.py`, `core/orchestrator.py` exist → ensemble/orchestration capability.
- Allocation method (fixed split / risk-parity / performance-weighted): `core/config.py:71-77` `strategy_weights` = fixed (mtm 0.40, mrb 0.25, mlb 0.35). **Fixed-weight ensemble.** `[Whether these weights are applied in live path UNVERIFIED]`.
- **Fraction of capital to an unconfirmed-edge strategy**: given Phase 7/10 verdict (no confirmed edge, net-negative costed run), the correct fraction is **0**. Any nonzero allocation today is a mismatch with the evidentiary status — itself a capital-allocation finding independent of the strategy's math.

---

## Phase 15 — Verdict

**STATUS: N/A (single-symbol candidate as of STATUS.md) + a capital-allocation finding.** Marked N/A for the multi-strategy correlation analysis because only XAUUSD is a candidate. **But the capital-allocation point stands: deploying any capital to a system with no confirmed edge is itself the finding.** If/when multi-symbol activates, Phase 15.2 correlation work becomes P1.
