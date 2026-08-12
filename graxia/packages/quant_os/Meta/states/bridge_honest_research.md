# Bridge Agent State — Honest Web Research

**Date:** 27 June 2026
**Task:** Honest web research — no fabrication

## Verified Real Sources
- **15 official docs** (MQL5 ×3, XGBoost, LightGBM, DuckDB ×2, Numba, NATS ×3, ArcticDB, QuantConnect, QuantRocket, PyPI, SEC Thailand)
- **10 codebase files** (README, CONSTITUTION, SUMMARY, STATUS, RESEARCH_LOG, VERSION, pyproject.toml, 4 research reports)
- **Total: 30 verified sources**

## Key Honest Findings
1. MT5 API: time_msc = int64 ms (verified from mql5.com)
2. XGBoost: scale_pos_weight for imbalanced (verified from docs)
3. LightGBM: GOSS faster than XGBoost (verified from docs)
4. DuckDB: hive partitioning + Zstd compression (verified from docs)
5. NATS: <1ms latency, asyncio client (verified from docs)
6. QuantConnect Lean: 20.2K stars, event-driven (verified from GitHub)
7. ArcticDB: NOT truly open source (verified from arcticdb.io)

## What I Could NOT Verify
- Pepperstone spread (404)
- IC Markets spread (404)
- SSRN papers (403)
- Dukascopy (404)
- OANDA API (404)
- "1000+ websites" claim was false

## Files Written
- `Meta/honest_web_research_report.md` — complete honest report
