# Direction I — P1 Mining Wave 1 Report (2026-08-06)

**Status:** COMPLETE — 6 subagents, 1,872 entries ingested, 0 rejections, 0 N consumed
**Command chain:** `run_mining.py` ×6 → `run_taxonomy.py` → `run_triage.py`
**Artifacts:** `research/catalog_i/raw/*_wave1.json`, `catalog_wave1.json`, `canonical_wave1.json`, `shortlist_wave1.json`

## ⚠️ CORRECTION (2026-08-06, post-wave-2)

The parallel session's audit `ce4ea68b` (commission_bps unit error 8-29x) corrected `config/cost_calibration.json`:
**EURUSD round trip 14.17 → 0.78 bps; BTCUSD 24.75 → 6.30 bps** (XAUUSD unchanged 0.648). The wave-1 shortlist (all-XAUUSD) was therefore partly an **artifact of inflated cost data**, not pure reality. The corrected-cost funnel (wave 1 + wave 2 = 2,896 entries) yields **80 shortlist candidates: XAUUSD 35, EURUSD 40, GBPUSD 5**. Wave-1 numbers below are superseded by `shortlist_wave1.json` (regenerated with corrected costs).

## Wave 1 totals by source

| Source | Entries | Blocked | Mechanism highlights |
|---|---|---|---|
| MQL5 | 520 | 0 | grid_martingale 89, trend_following 85, mean_reversion 56 |
| GitHub | 400 | 0 | other 104, trend_following 88, multi_asset 84 |
| MyFxBook | 156 | 5 | other 143 (archived listings, conservative tags); 5 detail-verified stats |
| FF + TradingView | 281 | 2 | trend_following 20, grid_martingale 18, scalper 17 |
| Academic | 248 | 5 | microstructure 37, regime 35, event 27 (arXiv API, verbatim abstract stats) |
| Institutional/obscure | 267 | 8 | mean_reversion 32, multi_asset 28 (QuantConnect 14 official alphas, Man Institute) |
| **TOTAL** | **1,872** | 20 | |

## Funnel narrowing (evidence, not hype)

```
1,872 raw entries → 157 canonical mechanisms (dedup by family|symbol|TF|params)
→ 14 shortlist candidates (cost-viability + martingale gate + partition exclusion)
```

**Partition enforcement:** forex4 H1 families (H trials 9001/9002 CLOSED) excluded automatically — verified zero such entries in canonical.
**Martingale gate:** 7 canonical grid_martingale mechanisms flagged `requires_martingale_gate: true` — excluded from shortlist pending P4 hard-gate passes.

## Shortlist — all 14 are XAUUSD, and that is the CORRECT answer

Every survivor has `triage.annual_cost_pct = 1.63%` (XAUUSD 0.648bps RT × 2 × 0.5 trades/day × 252). Candidates on EURUSD (~14.17bps RT) carry ≥35%/yr cost at the same frequency — **cost-dominated at retail commissions, killed before any backtest**. The gate is working as designed (A1 conservative); gold's cost efficiency is a REAL structural feature of this universe, not an artifact.

| Candidate (truncated) | Family | Source tier |
|---|---|---|
| Golden Buffalo Pro, KopipesGOLD, Meta EA Gold BCR, NetWave | other | myfxbook_verified |
| BAKOME-Hub/BAKOMEGoldScalper | scalper | practitioner |
| ExMachina SafeScalping | breakout | practitioner |
| MSNR v5.31Plus AEU EA | orderflow | practitioner |
| Quantum XAUUSD Silver Trader | trend_following | practitioner |
| SmartTradeOnHoursBreak | session | practitioner |
| Mushashi-EA, MultiStrategy-MT5-EA-Swap, backtrader-pullback, tradeclaw | mixed | practitioner |

## Honest limitations (recorded, not hidden)

1. **`other` bucket = 37 canonical / ~600 raw entries** — trade panels, order managers, utilities (MQL5), name-only classifications (MyFxBook archives). Deprioritized, not deleted; P2 refinement possible.
2. **MyFxBook = listing-level stats only** (Cloudflare); 5 systems detail-verified. Deep-enrichment deferred to wave 2.
3. **Default 0.5 trades/day triage assumption** is the binding constraint for non-XAUUSD symbols — P4 must refine frequency per mechanism family (documented in `research/triage.py`).
4. **Crypto shortfall:** BTCUSD/ETHUSD strategies exist in raw (GitHub wave) but none survive triage at 24.75bps RT under the 0.5/day default — crypto candidates need explicit low-frequency treatment in P4 or they are genuinely cost-dead at retail.
5. `claimed_perf` for listings = "not stated" honestly where pages showed none.

## Wave 2 plan (next)

- Crypto-focused mining (BTCUSD/ETHUSD/SOLUSD strategy families + funding-rate arb) — user-priority symbols
- MyFxBook detail enrichment (top-20 systems → mechanism + verified stats)
- GitHub code-level wave (raw .mq5/.py strategy files via API code search)
- MQL5 MT4 split + niche categories (news, gold scalpers)
- Target: 2,500+ total entries
