# PHASE 2 — DATA INTEGRITY & INDEPENDENT FEED CROSS-VALIDATION
*Per R1–R18.*

---

## 2.1 — Bad Tick / Price Spike Detection

- `data/quality_gate.py`, `tick/data_quality.py`, `tick/feed_health.py`, `data/check_quality.py` exist. **Filter logic for erroneous single-tick spikes `[NOT TRACED this phase]`** — these modules exist but the actual outlier-rejection threshold (e.g., `abs(return) > N·σ`) was not read.
- **Manual outlier scan ever performed?** `research_data_quality.md` (30KB) and `reports/data_quality_research_2026.md` exist on disk → suggests scans have been done, but **not verified for the specific 7-day M1 window used in the headline backtest**. `[PARTIAL]`

## 2.2 — Independent Reference Feed Comparison

`[NEVER PERFORMED / NOT VERIFIABLE THIS SESSION]`. No comparison artifact (e.g., XAUUSD close-to-close vs Dukascopy/HistData for the same window) found in `reports/` or `data/`. `scripts/download_duka.py` exists (Dukascopy downloader) but no output diff report.

**Per protocol, state explicitly: without this check, the entire backtest rests on the unverified assumption that this one broker's (Pepperstone, per `.env`) historical feed is accurate.** This matters specifically because Pepperstone is a market-maker/ECN hybrid broker; such brokers construct their own historical price feeds. → **P1 finding.** Cannot be closed from code alone; requires running the download + diff.

The Dukascopy downloader script (`scripts/download_duka.py`, 731 LOC) means the capability exists — the *evidence of execution* is missing.

## 2.3 — Gap & Missing-Bar Forensics

- `% of expected bars missing*: `[NOT QUANTIFIED this phase]`. `data/check_data_count.py` exists and could compute this, but was not run. For XAUUSD M1 over a ~7-day window, missing-bar % is likely low (continuous market) but during the weekend gap and daily rollover it is non-trivial.
- Concentration of gaps (Asian session vs NY) not analyzed. → P2.

## 2.4 — Vendor / Source Changeover Detection

- Three broker identities referenced (Phase 0.4 #3). If the historical CSVs were collected from one server and the live system connects to another, a discontinuity exists.
- `data/manifests/` (8 entries) and `Meta/data_manifest.json` exist → manifest *infrastructure* exists, but whether a changeover boundary was detected `[UNVERIFIED]`. → P2.

---

## Phase 2 — Verdict

**STATUS: BLOCKED / PARTIAL.** The phase's core requirement — independent feed cross-validation — has **never been performed (or at least no evidence exists)**. The capability exists (`scripts/download_duka.py`) but the comparison output is absent. Combined with the market-maker-broker caveat, **every headline number in `SUMMARY.md`/`results/` rests on an unverified single-broker feed**. This does not by itself prove the data is wrong, but it means data correctness is an *assumption*, not a *finding*.
