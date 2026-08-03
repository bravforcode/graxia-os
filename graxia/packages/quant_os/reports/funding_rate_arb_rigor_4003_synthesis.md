# Funding Rate Arbitrage — Trial #4003 Rigor Synthesis

**Date:** 2026-08-03
**Status:** CONDITIONAL PASS (deployability constrained — see §4)
**Sources (all auditable artifacts, no simulation):**

| Artifact | Path |
|---|---|
| Rigor (long history) | `reports/funding_rate_arb_rigor_20260728.json` |
| Rigor (recent 33d) | `reports/funding_rate_arb_rigor_recent33d_20260728.json` |
| Pilot (feasibility, PASS) | `reports/funding_rate_arb_pilot_20260727.json` |
| Live T-bill | FRED `DGS3MO` via `core/data/fred_client.py` (fetched 2026-08-03) |
| Paper track record | `reports/paper_trading/funding_arb_state.json` (Trial #4001, +40 events to 2026-08-03) |

---

## 1. Verdict

**CONDITIONAL PASS.** The funding carry on **Binance BTC/USDT** over ~1,600 days of real funding history
(4,800 × 8h periods) is statistically significant (Newey-West t = 12.02, p < 1e-5), remains positive
through 1.5× cost stress, and beats the **real 3-month T-bill (3.82% FRED DGS3MO)** by ~2.8pp net.
It is **not deployable** on Bitget (33 days of history; fails cost stress at 1.5×), and **not on ETH-only**
(recent-33d net yield negative). Deployment requires a ≥180-day holding horizon and a live entry
funding gate (see §4).

## 2. Evidence table (net annualized yield after assumed 32bps round-trip cost, 1.0×)

| Instrument | N periods | Days | % positive | Raw yield/yr | Net @1.0× | Net @1.5× | NW t (p) | Excess vs real T-bill (3.82%) |
|---|---|---|---|---|---|---|---|---|
| Binance BTC/USDT | 4,800 | 1,599.7 | 84.62% | 6.676% | **6.603%** | 6.566% | 12.02 (<1e-5) | **+2.78pp** |
| Binance ETH/USDT | 4,800 | 1,599.7 | 81.90% | 6.115% | 6.042% | 6.005% | 8.06 (<1e-5) | +2.22pp |
| Binance BTC (recent 33d) | 99 | 32.7 | 98.99% | 6.323% | 2.748% | 0.960% | 9.43 (<1e-5) | −1.07pp |
| Binance ETH (recent 33d) | 99 | 32.7 | 86.87% | 3.520% | **−0.056%** | −1.843% | 4.53 (<1e-5) | −3.88pp |
| Bitget BTC/USDT | 100 | 33.0 | 81.00% | 4.537% | 0.998% | −0.772% | 3.89 (1e-4) | −2.82pp |
| Bitget ETH/USDT | 100 | 33.0 | 86.00% | 3.585% | 0.045% | −1.724% | 4.63 (4e-6) | −3.78pp |

Cost model: 32bps round trip = 2 × (spot 10 + perp 4 + spread 2) bps, same as the feasibility pilot.

## 3. T-bill benchmark correction (assumed → real)

The rigor JSONs carry `tbill_assumption: ~4.5%/yr` explicitly flagged
*"NOT fetched live … Re-verify against FRED DGS3MO"*. Live verification:

- **FRED DGS3MO latest = 3.82%** (observation 2026-07-30; fetched 2026-08-03; preceding obs: 3.83, 3.90, 3.96).
- Rebased excess over T-bill: Binance BTC **+2.78pp** (was +2.10pp at assumed 4.5%); Binance ETH **+2.22pp**.
- Conclusion unchanged at the true benchmark: long-history Binance carry clears T-bill; recent-33d and Bitget do not.

## 4. Crash resilience (Binance long-history windows)

| Crash window (2022) | BTC/USDT cum bps | ETH/USDT cum bps |
|---|---|---|
| Terra/LUNA (05-07 → 05-13) | **+1.43** (positive) | **+0.64** (positive) |
| Celsius/3AC (06-13 → 06-19) | −1.36 | −12.10 |
| FTX collapse (11-06 → 11-14, 8.3d) | **−25.96** | −22.13 |

- Funding is not reliably positive in contagion windows; the FTX window alone is ≈ −0.26% of notional (BTC),
  enough to erase ~2–6 months of carry.
- Funding is positive ~85% of periods, so a **long holding horizon is the mitigation**, not timing.

## 5. Deployability criteria (evidence-derived)

1. **Binance only** — Bitget fails cost stress (1.5× negative) and T-bill comparison on 33d history.
2. **BTC primary** — passes all cost stress; ETH recent-33d net yield is negative (−0.056%).
3. **≥180-day holding horizon** — carry is positive ~85% of periods; crashes (FTX −26bps) recover over longer windows.
4. **Live entry funding gate ≥ 4.5–5%/yr annualized** — enter only when current funding clears T-bill + crash cushion.
   The strategy module (`strategies/funding_rate_arb.py`) currently gates at `min_annual_rate = 10%` (stricter, conservative).
5. Costs assumed at 32bps round trip; 1.5× stress still positive for Binance BTC.

## 6. Risks & caveats

- **Paper/notional evidence only — NOT live-profit proof** (CONSTITUTION invariant).
- **Exchange counter-party risk**: FTX episode shows funding can go deeply negative while the venue becomes insolvent.
- Funding is regime-dependent; the recent-33d window (net 2.75% BTC) is already weaker than the 1,600-day average.
- Delta-neutral construction assumes simultaneous spot/perp legs; execution basis/spread risk applies.
- T-bill is near-risk-free; carry carries crypto volatility + counterparty risk — the ~2.8pp excess is the compensation, not a floor.
- The strategy's 10%/yr gate means few entries; the paper track record will show how often the gate fires in practice.

## 7. Next steps

- Paper account (Trial #4001) continues accumulating real funding events every 8h via
  `QuantOS-FundingArb` scheduled task (40 events recorded to 2026-08-03; BTC +1.3290, ETH +0.6454 USD).
- Live gate remains an open decision: keep 10% (conservative) vs relax toward the 4.5–5% rigor floor —
  requires a change request against the strategy parameters before any real-capital deployment.
- Re-run the rigor script periodically (e.g., monthly) to refresh the long-history + recent windows.
