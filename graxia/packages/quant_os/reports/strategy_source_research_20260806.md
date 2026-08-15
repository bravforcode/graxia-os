# Strategy Source Research — Trial 8003 Selection (2026-08-06)

**Status:** COMPLETE — evidence asset for Direction G trials.
**Source:** Researcher agent web research (2026-08-06). All numbers verified from fetched primary sources. Nothing fabricated.

## Context: what already failed (must be structurally different)
| Trial | Mechanism | Result |
|---|---|---|
| 1034/1035 | M15 scalper (gold/FX) | REJECT (PF 0.68-0.95) |
| 8001 | BTCUSD H1 Donchian(20) breakout + vol filter | REJECT (Sharpe 0.24, PF 1.14, 1391 trades) |
| 8002 | EURUSD M15 London session breakout | REJECT (20 trades, Sharpe -0.07 — UNDERPOWERED) |

## Candidate sources evaluated

### 1. Baltas-Kosowski TSMOM (CHOSEN for 8003) — HIGH priority
- **What:** Improve time-series momentum on futures via (a) efficient volatility estimators (realized, Parkinson, Garman-Klass, Yang-Zhang) instead of raw price-range, (b) refined trend signals, (c) dynamic leverage using pairwise signed correlations.
- **Evidence:** SSRN 2140091 (2013), revised 2019, chapter in *Market Momentum: Theory and Practice* (Wiley 2020). Verified: efficient vol estimation + trend detection **cut turnover >1/3 with no significant performance degradation**; correlation-adjusted variant outperforms naive TSMOM, stronger post-2008; robust to transaction costs.
- **Structurally different from 8001:** vol-scaled position sizing (not fixed), efficient vol estimator (not ATR), correlation-adjusted leverage (not single-channel).
- **Caveat:** abstract-level results only — no verified Sharpe figures this session.

### 2. Faber 10-month MA (BTC regime filter) — MEDIUM-HIGH
- **What:** Hold asset when price > 10-mo SMA, else T-bills. *Journal of Wealth Management* Spring 2007 (SSRN 962461).
- **Verified (2013 update):** 10-asset portfolio 1973-2012 — timing cuts max DD 46%→<10%, only one down year worse than -1%.
- **BTC-specific: UNPROVEN** — Grobys et al 2019 (FRL): variable MA on 11 cryptos → BTC itself FAILED (+8.76%/yr for others excluding BTC); Resta et al 2020: buy-and-hold beat trend rules on BTC 2012-2019.

### 3. Moreira-Muir vol scaling (overlay) — MEDIUM (pairs with #1)
- **What:** Scale factor exposure by inverse of lagged realized variance. *Journal of Finance* 2017.
- **Verified (published JF PDF):** momentum managed alpha +12.51%/yr; Sharpe FF3+Mom 0.98→1.09; +25% buy-and-hold Sharpe (market).
- **Crypto application: no direct replication found** — treat as hypothesis.
- **Caveat literature:** "Volatility-Managed Portfolio: Does It Really Work?" (SSRN 3283395); "The disappearing profitability of volatility-managed equity factors" (2023 JFM).

### 4. Dual Thrust — LOW (rejected)
- Opening-range breakout (Chalek). Practitioner lore, **no academic paper**; naive version on SPY 2004-2017: **Sharpe -0.37, max DD 65.7%** (QuantConnect tutorial). Structurally similar to failed M15 breakout family.

### 5. MyFxBook verified EAs (EURUSD) — reference only
| EA | Live | Gain | MaxDD | PF | Sharpe | Note |
|---|---|---|---|---|---|---|
| Seagull (LinoCapital) | 2.6y | +603% | 20.5% | 4.37 | 0.29 | best; instrument unconfirmed |
| FXStabilizer EUR Turbo (forexstore) | 7.7y | +3,815% | 13.3% | 1.77 | 0.10 | win 63-65%, loss>win (no martingale signature) |
| FXTrackPRO EURUSD | 7.7y | +1,432% | **51.7%** | 1.72 | 0.16 | DD fails quality bar |
- MyFxBook has NO martingale flag; inferred from stats. No BTCUSD systems extractable (JS-rendered page).
- REJECTED candidates: AGI EA (+3.34M%, DD 5.7% — martingale profile), Money Tree (+23,377%, DD 46.5%), EuroStable (grid-like).

## ⚠️ Negative results that must be respected
1. **Grobys & Sapkota 2019** (Econ Letters): NO significant momentum payoffs in 143 cryptos 2014-2018.
2. **Grobys et al 2019** (FRL): 20-day MA on 11 cryptos — BTC itself failed.
3. **Resta et al 2020**: BTC 2012-2019 — buy-and-hold beat trend rules.
4. **Dual Thrust SPY**: Sharpe -0.37.
- All crypto negatives are 2012-2019 era; market structure changed. 8001 tested fast H1 Donchian — slow vol-scaled TSMOM is untested territory.

## Decision
Trial 8003 = **BTCUSD TSMOM with Yang-Zhang vol estimator + Moreira-Muir vol targeting overlay** (Baltas-Kosowski lineage). Evidence strongest + structurally distinct. Budget: Direction G 2/25 used, remaining 23. Consecutive fails 2/3 — 8003 REJECT triggers Direction G §4.4 stop.

## Sources
- SSRN 2140091 (Baltas-Kosowski) via Wayback: web.archive.org/web/2023id_/https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2140091
- Moreira-Muir JF PDF: amoreira2.github.io/alan-moreira.github.io/VolPortfolios_published.pdf
- Faber 2013: mebfaber.com/wp-content/uploads/2016/05/SSRN-id962461.pdf
- QuantConnect Dual Thrust tutorial (SPY backtest)
- MyFxBook live pages: /members/forexstore/fxstabilizer-eur-turbo/1614052, /members/LinoCapital/seagull-ea/10823424, /members/forexstore/fxtrackpro-eurusd/7438335
- Grobys & Sapkota 2019 (10.1016/j.econlet.2019.03.028), Grobys et al 2019 (10.1016/j.frl.2019.101396), Resta et al 2020 (10.3390/risks8020044), Shen/Urquhart/Wang 2021 (10.1111/fire.12290)
