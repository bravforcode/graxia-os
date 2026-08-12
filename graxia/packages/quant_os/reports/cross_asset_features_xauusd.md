# Cross-Asset Features for XAUUSD Trading Models — Research Findings

**Author:** researcher agent (Ruflow / Project Gracia)
**Date:** 2026-06-26
**Scope:** Specific, actionable cross-asset features for XAUUSD (gold) intraday models on M15 bars. Data sources, feature formulas, documented correlations, alignment strategy, and priority ranking.
**Status:** Research deliverable. Not live-profit proof. Correlations are time-varying and regime-dependent — treat as priors, not constants.

---

## TL;DR — Priority Ranking (most edge first)

| Rank | Feature family | Documented corr. with gold | Horizon best for | Intraday usable? | Lookahead risk |
|------|----------------|---------------------------|------------------|------------------|----------------|
| 1 | **10Y Real Yield (TIPS, DFII10)** | **−0.70 to −0.90** (monthly/quarterly) | Regime / direction bias | Daily→ffill (shift−1) | HIGH if not shifted |
| 2 | **DXY (ICE DX-Y.NYB)** | **−0.40 to −0.60** (daily/weekly) | Intraday co-movement | Native 1H/4H | Low (intraday) |
| 3 | **VIX (regime/percentile)** | Episodic, non-linear | Risk filter / sizing | Daily→ffill (shift−1) | Medium |
| 4 | **WTI Crude (DCOILWTICO / CL=F)** | Weak positive, unstable (~0.1–0.4) | Inflation regime context | Daily or 1H | Low |

**Bottom line:** Real yield is the single most robust macro driver of gold and should be the **primary regime feature**. DXY adds an intraday, high-frequency currency channel and is the best *intraday* co-movement signal. VIX is best used as a **risk-on/off gate**, not a directional primary. WTI is the weakest — keep as a secondary inflation-regime context feature, and expect low standalone edge.

> ⚠️ **Multicollinearity warning:** Real yield, DXY, and (to a lesser degree) VIX all share a Fed-policy / risk-sentiment common factor. Do NOT throw all of them raw into a linear model. Use real yield as the regime anchor; orthogonalize or use DXY as the intraday momentum carrier; use VIX as a categorical gate. Test VIF / condition number.

---

## 1. DXY (US Dollar Index)

### 1.1 What "DXY" actually is — two different indexes, pick deliberately
- **ICE US Dollar Index (`DXY` / `USDX`)**: trade-weighted basket of 6 currencies (EUR 57.6%, JPY 13.6%, GBP 11.9%, CAD 9.1%, SEK 4.2%, CHF 3.6%). This is what retail/CTA traders call "DXY". Base 1973=100. **This is the one to use for gold trading** — it's the market's reference and has intraday liquidity.
- **Fed Nominal Broad Dollar Index (`DTWEXBGS`)**: trade-weighted vs 26 trading partners, goods+services, base Jan 2006=100. More "fundamental", only **daily** on FRED, no clean intraday. Use only as a daily cross-check or for long-horizon regime work.

### 1.2 Free / historical data sources

| Source | Ticker / series | TF available | Cost | Notes |
|--------|----------------|--------------|------|-------|
| **yfinance** | `DX-Y.NYB` | 1m(7d)/5m(60d)/15m(60d)/**1h(730d)**/1d(max) | Free, no key | Best for 1H+4H. 1H max ~2y. Intraday tz = America/New_York → convert to UTC. |
| **Stooq** | `USDX` | daily (and intraday via stooq csv) | Free | `stooq.com/q/d/?s=usdx` — good for long daily history. |
| **FRED** | `DTWEXBGS` (broad), `DTWEXM` (major, discontinued) | daily only | Free, API key | Use for daily broad-dollar cross-check only. |
| **investing.com** | `DX` | 1m→1M | Free (scrape) / paid API | TOS-restricted scraping; avoid for automation. |
| **Dukascopy / HistData** | `USDIDX` | tick→1M | Free | JForex historical; needs their free account. |

**Recommended for this project:** `yfinance` `DX-Y.NYB` at `interval="60m"` for the 1H series, then **resample to 4H** in pandas (`resample("4H")`). Falls back to FRED `DTWEXBGS` daily only if yfinance is blocked.

### 1.3 Specific features to compute (on DXY 1H closes)

| Feature name | Formula | Rationale |
|--------------|---------|-----------|
| `dxy_ret_1h` | `log(close).diff(1)` | Instantaneous dollar pressure (gold's main intraday driver) |
| `dxy_ret_4h` | `log(close).diff(4)` | Aligned to gold 4H momentum |
| `dxy_rsi_14` | Wilder RSI(14) on 1H closes | Overbought dollar → gold-bullish prior |
| `dxy_roc_12` | `(close / close.shift(12) - 1) * 100` | 12h rate of change |
| `dxy_mom_ema21` | `close - EMA(close,21)` | Trend momentum vs mean |
| `dxy_zscore_20` | `(ret - ret.rolling(20).mean()) / ret.rolling(20).std()` | Standardized pressure; sign predicts gold direction inverse |
| `dxy_corr_gold_60` | `rolling(60).corr(xauusd_ret_1h)` | Regime diagnostic — when corr breaks, model regime changed |

### 1.4 Documented correlation with XAUUSD
- **Daily/weekly:** Pearson ≈ **−0.40 to −0.60** (negative; gold priced in USD → mechanical inverse). Documented across most macro textbooks and WGC commentary.
- **Intraday (1H):** typically **−0.30 to −0.55** during liquid sessions (London/NY overlap); weaker in Asia session.
- **Long horizon (monthly):** can reach **−0.60 to −0.75** in strong-dollar regimes; collapses toward 0 in rare "everything up" episodes.
- The correlation is **negative but regime-varying**; do not assume a constant. Track `dxy_corr_gold_60` to detect breaks.
- Sources: World Gold Council *Gold Investor* / market commentary; standard FX-macro literature (the USD-denomination mechanical inverse is uncontroversial).

### 1.5 Timestamp alignment with 15min XAUUSD bars
1. Fetch DXY 1H, ensure **tz-aware UTC**: `dxy.index = dxy.index.tz_convert("UTC")` (yfinance returns NY tz for US indices).
2. **Reindex DXY onto the gold M15 grid** with forward-fill — DXY 1H value is valid for all 4 M15 bars within that hour:
   ```python
   dxy_m15 = dxy.reindex(gold_m15.index, method="ffill")
   ```
3. **Lookahead guard:** an H1 bar timestamped `10:00` covers `10:00–11:00`; using its close at `10:00` would be lookahead. Use the **prior completed** bar: `dxy = dxy.shift(1)` **before** reindex, OR build DXY bars timestamped at the **open** and only consume bars whose close ≤ current gold bar time. This matches the project's `core/lookahead_guard.py` discipline — **fail-closed**.
4. Compute features on the aligned, shifted series so every feature value at gold bar `t` uses only DXY info observable strictly before `t`.

---

## 2. US 10Y Real Yield (TIPS) — DFII10

### 2.1 Data source
- **FRED series `DFII10`** — "Market Yield on U.S. Treasury Securities at 10-Year Constant Maturity, Inflation-Indexed". Source: Fed Board H.15. Units: percent. Frequency: **daily**. Confirmed live: 2026-06-24 = **2.23%**.
  - URL: https://fred.stlouisfed.org/series/DFII10
  - CSV: https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFII10
- Also useful: `DFII5` (5Y real), `DFII30` (30Y real), `T10YIE` (10Y breakeven inflation = nominal DGS10 − DFII10, a clean inflation-expectations feature).
- **Free API:** `fredapi` (needs free key from https://fred.stlouisfed.org/docs/api/api_key.html) or `pandas_datareader` (no key, rate-limited).

### 2.2 Documented gold–real-yield correlation
- This is **the single most robust macro correlation for gold** in the literature.
- **Erb & Harvey (2013), "The Golden Dilemma"** (Financial Analysts Journal): document a strongly negative relationship between real yields and gold; gold's real-return predictability is dominated by the real-rate channel. Frequently cited monthly/quarterly correlation in the **−0.70 to −0.90** range.
- **World Gold Council** research notes repeatedly identify real yields as the primary driver of gold demand (opportunity cost of holding non-yielding gold).
- **Baur & Glover (2014/2015)** caution the relationship is **time-varying** and weakens during low/negative-rate regimes (gold decouples from real yields when real yields are very low). → reinforces using it as a **regime** feature, not a static coefficient.
- Sign convention: **real yield ↑ → gold ↓** (negative). A falling real yield = bullish gold regime.

### 2.3 Regime features (daily → forward-filled into M15)
| Feature name | Formula | Type |
|--------------|---------|------|
| `real_yield_level` | `DFII10` (shifted −1 day, ffill) | level (percent) |
| `real_yield_dir_5d` | `sign(DFII10.diff(5))` | direction {−1,0,+1} |
| `real_yield_chg_5d` | `DFII10.diff(5)` | delta (bps-ish) |
| `real_yield_z_60d` | `(DFII10 − DFII10.rolling(60).mean()) / DFII10.rolling(60).std()` | standardized level vs recent |
| `real_yield_pct_252d` | `DFII10.rolling(252).rank(pct=True)` | 1y percentile rank (regime) |
| `real_yield_above_2pct` | `(DFII10 > 2.0).astype(int)` | binary regime flag (headwind for gold) |
| `breakeven_infl_10y` | `DGS10 − DFII10` (FRED `T10YIE`) | inflation expectations — gold-bullish when rising |

**Regime interpretation table (prior):**
| `real_yield_pct_252d` | `real_yield_dir_5d` | Gold directional prior |
|----------------------|--------------------|-----------------------|
| High (>0.75) & falling | −1 | **Strong bullish** (yields rolling over from high) |
| High & rising | +1 | Bearish (yields still climbing) |
| Low (<0.25) & falling | −1 | Mild bullish (decoupled — use sparingly) |
| Low & rising | +1 | Cautious (real-yield channel weak) |

---

## 3. VIX (CBOE Volatility Index) — VIXCLS / ^VIX

### 3.1 Data sources
- **FRED `VIXCLS`** — daily close, source CBOE. Confirmed live: 2026-06-24 = **18.63**. URL: https://fred.stlouisfed.org/series/VIXCLS
- **yfinance `^VIX`** — daily (intraday VIX via yfinance is unreliable/limited; use daily).
- **CBOE direct** — historical VIX CSV archives: https://www.cboe.com/us/indices/market_statistics/historical_data/ (free, daily, long history back to 1990).
- **Bonus (gold's own vol):** FRED **`GVZCLS`** = CBOE Gold ETF Volatility Index (GLD implied vol). Stronger, more direct gold-risk feature than VIX. Also **`OVXCLS`** = crude oil ETF vol.

### 3.2 Regime signal — risk-on / risk-off
VIX–gold is **episodic and non-linear**, not a stable linear correlation. The edge is in **regime gating**, not direction:
- **VIX < 15** → complacency / risk-on → gold rangebound, lower vol regime. Reduce size, favor mean-reversion.
- **15 ≤ VIX ≤ 20** → normal → neutral, no strong gate.
- **20 < VIX ≤ 30** → elevated stress → mild gold tailwind (safe-haven bid begins).
- **VIX > 30** → fear / crisis / "flight to safety" → **historically bullish gold on average**, BUT with a critical caveat: in acute *dollar-liquidity squeezes* (e.g. March 2020), gold initially **sold off** alongside equities because of forced USD demand. The safe-haven bid arrives *after* the liquidity phase. → use VIX>30 as a *size-regime / stand-aside* flag, not a naive buy signal.

### 3.3 Features
| Feature name | Formula | Use |
|--------------|---------|-----|
| `vix_level` | `VIXCLS` (shift−1, ffill) | raw level |
| `vix_pct_252d` | `VIXCLS.rolling(252).rank(pct=True)` | 1y percentile (regime) |
| `vix_regime` | `cut: <15=0, 15-20=1, 20-30=2, >30=3` | categorical gate |
| `vix_spike` | `(VIXCLS > 1.5 * VIXCLS.rolling(20).mean()).astype(int)` | acute-stress flag → stand-aside |
| `vix_term_slope` | `VIX9D − VIX` (or `VXV − VIX`) | **optional, advanced** — inverted term structure = near-term stress |
| `gvz_level` | `GVZCLS` (gold's own implied vol) | better gold-risk proxy than VIX if available |

**Thresholds that matter for gold:** `vix_regime==3` (>30) and `vix_spike==1` are the actionable ones — use them to **stand aside or cut size**, not to chase direction.

---

## 4. WTI Crude Oil — DCOILWTICO / CL=F

### 4.1 Data sources
- **FRED `DCOILWTICO`** — WTI spot, Cushing OK, daily, $/barrel, source EIA. Confirmed live: 2026-06-22 = **$78.94**. URL: https://fred.stlouisfed.org/series/DCOILWTICO
- **yfinance `CL=F`** — continuous WTI futures, intraday (1h up to 730d, 1d max history). Better for intraday co-movement.
- **EIA direct** — https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm (free daily).

### 4.2 Gold–oil relationship
- **Positive but unstable** correlation (~0.1–0.4 daily; higher in commodity-supercycle regimes, near-zero or negative in rate-shock regimes). Both share an inflation-hedge / USD-denomination factor.
- The **gold/oil ratio** (XAUUSD price ÷ WTI price) is a famous macro barometer; long-run average ~15–25 barrels per ounce. Extremes (>30 or <10) signal regime stress and mean-revert.
- Edge is **contextual**: oil rising *with* inflation expectations rising = gold-supportive; oil rising *with* dollar spiking = gold-headwind. Net standalone directional edge is **low** — keep WTI as a secondary inflation-regime feature.

### 4.3 Features
| Feature name | Formula |
|--------------|---------|
| `wti_ret_1d` | `log(CL=F close).diff(1)` |
| `wti_ret_5d` | `log(close).diff(5)` |
| `wti_z_20d` | `(ret − ret.rolling(20).mean())/ret.rolling(20).std()` |
| `gold_oil_ratio` | `XAUUSD_close / WTI_close` |
| `gold_oil_ratio_z_252d` | `(ratio − ratio.rolling(252).mean())/ratio.rolling(252).std()` |
| `oil_vol_flag` | `OVXCLS > OVXCLS.rolling(60).quantile(0.9)` (optional, uses OVX) |

---

## 5. Implementation specifics

### 5.1 Python libraries
```python
# requirements
# yfinance>=0.2.40      # DXY 1H, VIX daily, WTI CL=F intraday
# fredapi>=0.5.2        # DFII10, DTWEXBGS, VIXCLS, DCOILWTICO, GVZCLS, T10YIE
# pandas>=2.0
# pyarrow>=15.0         # parquet
# pandas_datareader     # fallback if no FRED key
```
Get a **free FRED API key**: https://fred.stlouisfed.org/docs/api/api_key.html (store in env `FRED_API_KEY`, never commit — project uses `runtime/secret_provider.py`).

### 5.2 Fetch — DXY (intraday 1H → resample 4H)
```python
import yfinance as yf, pandas as pd

dxy = yf.download("DX-Y.NYB", period="730d", interval="60m", auto_adjust=False)
dxy = dxy.rename(columns=str.lower)["close"].to_frame("dxy_close")
dxy.index = dxy.index.tz_convert("UTC")          # yfinance returns NY tz for US idx
dxy = dxy.shift(1)                                # lookahead guard: use prior completed H1 bar
dxy_4h = dxy.resample("4H").last()                # 4H close = last 1H close in window
```

### 5.3 Fetch — FRED daily macro (real yield, VIX, WTI, breakeven)
```python
import os
from fredapi import Fred
fred = Fred(api_key=os.environ["FRED_API_KEY"])

real_yield = fred.get_series("DFII10").rename("real_yield")     # 10Y TIPS, %
dgs10      = fred.get_series("DGS10").rename("dgs10")           # nominal 10Y
vix        = fred.get_series("VIXCLS").rename("vix")
wti        = fred.get_series("DCOILWTICO").rename("wti")        # $/bbl
gvz        = fred.get_series("GVZCLS").rename("gvz")            # gold implied vol (optional)
breakeven  = (dgs10 - real_yield).rename("breakeven_10y")       # = T10YIE
```

### 5.4 Timezone alignment — daily macro into M15 bars (the critical part)
Daily macro (DFII10/VIX/WTI) is **date-indexed**; XAUUSD is **M15 tz-aware UTC** (convert from MT5 server EET first). The safe pattern:

```python
def align_daily_to_m15(daily: pd.Series, m15_index: pd.DatetimeIndex, shift_days: int = 1) -> pd.Series:
    """Forward-fill daily macro into M15 bars with NO lookahead.
    shift_days=1 => a bar on day D uses day D-1's CONFIRMED daily value.
    (Daily value for D is published end-of-D; using it intraday on D is lookahead.)"""
    d = daily.copy()
    if d.index.tz is None:
        d.index = d.index.tz_localize("UTC")          # treat daily stamp as UTC midnight
    d = d.shift(shift_days)                            # confirmed-yesterday rule
    # reindex onto intraday grid; ffill carries last confirmed value forward
    return d.reindex(m15_index, method="ffill")

gold_m15_idx = gold_m15.index                           # already tz-aware UTC
feat_real_yield = align_daily_to_m15(real_yield, gold_m15_idx)
feat_vix        = align_daily_to_m15(vix,        gold_m15_idx)
feat_wti        = align_daily_to_m15(wti,        gold_m15_idx)
```
**Why shift_days=1 (fail-closed):** FRED real-yield value for date D is finalized at/after D's close. Any M15 bar *during* D using "D's value" leaks future info. Using D-1's confirmed value is always safe. This costs ~1 day of latency but guarantees the project's `CONSTITUTION.md` no-lookahead invariant. **Do not optimize this away.**

### 5.5 Forward-fill caveats
- `method="ffill"` carries the last value across weekends/holidays — correct and intended (the macro regime persists).
- **Weekend gold gap:** gold trades ~23h/day Sun–Fri; macro is weekday-only. Saturday gold bars (if any broker) inherit Friday's value — fine.
- **NaN at series start:** first `shift_days` rows are NaN → drop, never impute forward from a value that didn't exist yet.

### 5.6 Storage format — parquet, one file per asset
Aligns with project's existing parquet migration (`reports/PARQUET_MIGRATION_PLAN.md`, `scripts/convert_to_parquet.py`).
```python
import os, pandas as pd

OUT = "data/cross_asset"                     # create under quant_os/data/
os.makedirs(OUT, exist_ok=True)

# raw, canonical, tz-aware UTC, one file per asset (long clean history)
dxy.to_parquet(f"{OUT}/dxy_1h.parquet")       # ICE DXY, 1H
dxy_4h.to_parquet(f"{OUT}/dxy_4h.parquet")
real_yield.to_frame().to_parquet(f"{OUT}/real_yield_10y_daily.parquet")
vix.to_frame().to_parquet(f"{OUT}/vix_daily.parquet")
wti.to_frame().to_parquet(f"{OUT}/wti_daily.parquet")

# final aligned feature frame joined onto gold M15 (the model input)
features = pd.concat([feat_real_yield, feat_vix, feat_wti], axis=1)
features.to_parquet(f"{OUT}/cross_asset_features_m15.parquet")
```
**Manifest + hash:** write a `data/cross_asset/manifest.json` with source, ticker/FRED id, TF, fetched_at, row count, and SHA256 (project convention — see `scripts/hash_data_manifests.py`). Required for dataset protocol / `validation/dataset_protocol.py` compliance.

### 5.7 End-to-end feature pipeline (sketch)
```python
def build_cross_asset_features(gold_m15: pd.DataFrame) -> pd.DataFrame:
    idx = gold_m15.index
    out = pd.DataFrame(index=idx)
    # real yield regime
    ry = align_daily_to_m15(real_yield, idx)
    out["real_yield_level"]      = ry
    out["real_yield_dir_5d"]     = align_daily_to_m15(np.sign(real_yield.diff(5)), idx)
    out["real_yield_z_60d"]      = align_daily_to_m15(
        (real_yield - real_yield.rolling(60).mean())/real_yield.rolling(60).std(), idx)
    out["real_yield_pct_252d"]   = align_daily_to_m15(real_yield.rolling(252).rank(pct=True), idx)
    out["real_yield_above_2pct"] = (ry > 2.0).astype(int)
    # DXY intraday
    dxy1 = yf.download("DX-Y.NYB", period="730d", interval="60m", auto_adjust=False)["Close"]
    dxy1.index = dxy1.index.tz_convert("UTC"); dxy1 = dxy1.shift(1)
    dxy_m15 = dxy1.reindex(idx, method="ffill")
    out["dxy_ret_1h"]   = np.log(dxy_m15).diff(1)
    out["dxy_rsi_14"]   = rsi(dxy_m15, 14)               # Wilder RSI helper
    out["dxy_zscore_20"]= (out["dxy_ret_1h"] - out["dxy_ret_1h"].rolling(20).mean())/out["dxy_ret_1h"].rolling(20).std()
    # VIX regime
    vx = align_daily_to_m15(vix, idx)
    out["vix_level"]     = vx
    out["vix_pct_252d"]  = align_daily_to_m15(vix.rolling(252).rank(pct=True), idx)
    out["vix_regime"]    = pd.cut(vx, [-1,15,20,30,1e9], labels=[0,1,2,3]).astype("Int8")
    out["vix_spike"]     = (vx > 1.5*vx.rolling(20).mean()).astype(int)
    # WTI context
    wti_m15 = align_daily_to_m15(wti, idx)
    out["wti_ret_1d"]   = np.log(wti_m15).diff(1)
    out["gold_oil_ratio"]      = gold_m15["close"] / wti_m15
    out["gold_oil_ratio_z_252d"] = (
        out["gold_oil_ratio"] - out["gold_oil_ratio"].rolling(252).mean()
    ) / out["gold_oil_ratio"].rolling(252).std()
    return out.dropna(how="all")
```

---

## 6. Expected edge & how to validate it (per project discipline)

1. **Don't trust the literature numbers as your edge.** Compute *your own* rolling correlations on the exact XAUUSD M15 series + these features over the **locked** dataset, per `validation/dataset_protocol.py`.
2. **Pre-register** the feature set and the expected sign of each feature's relationship with forward gold returns before measuring IC — matches `Meta/pre_register_b2.md` discipline.
3. **Block-bootstrap / walk-forward** the feature IC (Spearman rank IC with 1H/4H forward gold return) — do not use a single in-sample correlation. (`tests/test_phase_5_bootstrap.py`, `core/bootstrap`.)
4. **Lookahead gate:** re-run `tests/test_lookahead_regression.py` and `tests/test_mtf_leak.py` after adding features — must stay green.
5. **Multicollinearity check:** compute VIF across `[real_yield_level, dxy_ret_1h, vix_level, wti_ret_1d]`; if VIF>5 for real_yield vs dxy, keep real_yield as regime and use DXY *return* (orthogonal to level) rather than DXY level.
6. **Feature stability:** `core/stability.py` / `validation/parameter_stability.py` — feature IC must be stable across walk-forward folds, not concentrated in 1-2 regimes.
7. **Deflated Sharpe / PBO:** per `validation/deflated_sharpe.py` and `validation/probability_overfitting.py` — adding 4 features inflates multiple-testing; report deflated metric, not raw.

---

## 7. Honest limitations
- **Real-yield correlation is regime-varying** (Baur & Glover): in very-low-rate regimes the relationship decouples. A static coefficient will mislead.
- **DXY↔real-yield↔VIX share Fed-policy factor** → redundancy risk in linear models; prefer tree-based models or explicit orthogonalization, OR use real_yield as regime gate and DXY as intraday momentum.
- **VIX>30 ≠ automatic gold buy:** liquidity-squeeze episodes (Mar 2020) saw gold fall first. Gate, don't chase.
- **WTI edge is weak and unstable** — lowest priority; include only if a stability test justifies it, else drop.
- **Daily→M15 forward-fill** smooths macro into intraday — fine for regime, but it adds no *intraday* signal. Only DXY provides true intraday cross-asset co-movement.
- **yfinance reliability:** rate-limited and occasionally yanks intraday history; for production, mirror to a broker/bulk provider (Dukascopy/Stooq) and treat yfinance as dev-only. Per `CONSTITUTION.md`, never present backtest/demo results as live-profit proof.

---

## 8. Source index (verified live 2026-06-26)
- FRED `DFII10` — 10Y TIPS real yield, daily, Fed H.15: https://fred.stlouisfed.org/series/DFII10 (live: 2.23%)
- FRED `DTWEXBGS` — Nominal Broad Dollar, daily, Fed H.10: https://fred.stlouisfed.org/series/DTWEXBGS (live: 120.40)
- FRED `VIXCLS` — VIX, daily close, CBOE: https://fred.stlouisfed.org/series/VIXCLS (live: 18.63)
- FRED `DCOILWTICO` — WTI spot, daily, EIA: https://fred.stlouisfed.org/series/DCOILWTICO (live: $78.94)
- FRED `GVZCLS` — CBOE Gold ETF Volatility: https://fred.stlouisfed.org/series/GVZCLS
- FRED `T10YIE` — 10Y breakeven inflation: https://fred.stlouisfed.org/series/T10YIE
- CBOE historical VIX archives: https://www.cboe.com/us/indices/market_statistics/historical_data/
- EIA WTI spot: https://www.eia.gov/dnav/pet/pet_pri_spt_s1_d.htm
- yfinance DXY ticker: `DX-Y.NYB`; WTI: `CL=F`; VIX: `^VIX`
- FRED API key (free): https://fred.stlouisfed.org/docs/api/api_key.html
- Erb, C. & Harvey, C. (2013). *The Golden Dilemma*. Financial Analysts Journal. (gold–real-yield negative relationship)
- Baur, D. & Glover, K. (2014/2015). time-varying gold–real-yield relationship.
- World Gold Council — *Gold Investor* / market commentary (real yields as primary gold driver).

*All FRED series pages fetched and confirmed live on 2026-06-26 by researcher agent. Correlation magnitudes are documented literature ranges, not freshly computed on this dataset — compute your own on the locked series per §6 before relying on them.*
