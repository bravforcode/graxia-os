"""Build cross-asset macro features and join to the main feature dataframe.

Fetches FRED data (DFII10, VIXCLS, DTWEXBGS, GVZCLS) with yfinance fallback,
fetches COT gold data, aligns to M15 index with publication lag, and saves.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SRC))

from core.data.fred_client import FredClient
from core.data.cot_reports import fetch_cot_gold_range
from core.data.macro_features import _shift_series, _rolling_percentile


FEATURES_PATH = SRC / "artifacts/features_v2/features_v2_XAUUSD_15min.parquet"
OUTPUT_PATH = SRC / "artifacts/features_v2/features_v2_XAUUSD_15min_macro.parquet"
MACRO_CACHE = SRC / "data/macro"
MACRO_CACHE.mkdir(parents=True, exist_ok=True)
COT_CACHE = SRC / "data/cot"
COT_CACHE.mkdir(parents=True, exist_ok=True)


def fetch_via_yfinance(ticker_map: dict) -> dict[str, pd.Series]:
    """Fallback: fetch daily series via yfinance."""
    import yfinance as yf
    result = {}
    for yahoo_ticker, name in ticker_map.items():
        cache_path = MACRO_CACHE / f"yf_{name}.parquet"
        if cache_path.exists():
            df = pd.read_parquet(cache_path)
            result[name] = df.set_index("date")["value"].rename(name)
            continue
        try:
            data = yf.download(yahoo_ticker, period="5y", progress=False)
            if data.empty:
                print(f"  yfinance {yahoo_ticker}: no data")
                continue
            close = data["Close"]
            if hasattr(close, "columns"):
                close = close.iloc[:, 0]
            s = close.copy()
            s.name = name
            s.index = pd.to_datetime(s.index)
            s = s.groupby(s.index.normalize()).last().sort_index()
            pd.DataFrame({"date": s.index, "value": s.values}).to_parquet(cache_path, index=False)
            result[name] = s
            print(f"  yfinance {yahoo_ticker}: {len(s)} rows ({s.index[0].date()} to {s.index[-1].date()})")
        except Exception as e:
            print(f"  yfinance {yahoo_ticker}: error - {e}")
    return result


def reindex_daily(series: pd.Series, m15_index: pd.DatetimeIndex) -> pd.Series:
    """Map daily series to M15 index (last value of each day)."""
    if series.empty:
        return pd.Series(np.nan, index=m15_index, name=series.name)
    date_map = series.groupby(series.index.normalize()).last()
    result = pd.Series(np.nan, index=m15_index)
    days = pd.Series(m15_index.date, index=m15_index)
    mapped = days.map(date_map)
    mapped.index = m15_index
    mapped.name = series.name
    return mapped


def main():
    print("=" * 60)
    print("build_macro_features.py — Cross-asset feature builder")
    print("=" * 60)

    # 1. Load existing features
    print(f"\n[1] Loading features from {FEATURES_PATH}")
    feature_df = pd.read_parquet(FEATURES_PATH)
    m15_idx = feature_df.index
    print(f"    Shape: {feature_df.shape}")
    print(f"    Index: {m15_idx[0]} to {m15_idx[-1]}")

    start_date = m15_idx.min().strftime("%Y-%m-%d")
    end_date = m15_idx.max().strftime("%Y-%m-%d")
    fetch_start = (pd.Timestamp(start_date) - pd.Timedelta(days=365)).strftime("%Y-%m-%d")

    # 2. FRED data
    print(f"\n[2] Fetching FRED data ({fetch_start} to {end_date})")
    fred_data = {}
    try:
        fred = FredClient()
        fred_series = fred.fetch_multiple(
            ["DFII10", "VIXCLS", "DTWEXBGS", "GVZCLS"],
            start_date=fetch_start,
            end_date=end_date,
            silent=True,
        )
        if not fred_series.empty:
            for col in fred_series.columns:
                fred_data[col] = fred_series[col]
                print(f"    FRED {col}: {len(fred_series[col])} rows")
    except Exception as e:
        print(f"    FRED client failed: {e}")
        print("    Will use yfinance fallback for available series.")

    # 3. yfinance fallback for data FRED couldn't provide
    print("\n[3] Fetching yfinance fallbacks")
    yf_needed = {}
    fred_has = set(fred_data.keys())
    if "VIXCLS" not in fred_has:
        yf_needed["^VIX"] = "VIXCLS"
    if "DTWEXBGS" not in fred_has:
        yf_needed["DX-Y.NYB"] = "DTWEXBGS"
    if "GVZCLS" not in fred_has:
        yf_needed["^GVZ"] = "GVZCLS"
    if "DFII10" not in fred_has:
        print("    NOTE: DFII10 (real yield) requires FRED_API_KEY — will remain NaN")

    yf_data = fetch_via_yfinance(yf_needed) if yf_needed else {}

    # 4. COT data
    print("\n[4] Fetching COT gold data")
    cot_year_start = max(2024, pd.Timestamp(fetch_start).year)
    cot_year_end = pd.Timestamp(end_date).year
    cot_df = fetch_cot_gold_range(cot_year_start, cot_year_end, force=False)
    if cot_df.empty:
        print("    No COT data — skipping COT features")
    else:
        print(f"    COT: {len(cot_df)} rows ({cot_df.date.min().date()} to {cot_df.date.max().date()})")
        print(f"    COT columns: {list(cot_df.columns)}")

    # 5. Build macro feature columns
    print("\n[5] Building feature columns (aligning to M15)")

    frame = pd.DataFrame(index=m15_idx)
    frame.index.name = "timestamp"

    feat = {}

    # --- Real Yield (DFII10) — requires FRED_API_KEY ---
    ry_series = fred_data.get("DFII10")
    if ry_series is not None and not ry_series.dropna().empty:
        ry = reindex_daily(ry_series, m15_idx)
        feat["real_yield_pct"] = _shift_series(ry, 1)
        feat["real_yield_1m_change"] = _shift_series(ry.diff(30), 1)
        feat["real_yield_3m_change"] = _shift_series(ry.diff(90), 1)
        print(f"    real_yield_pct: {ry.dropna().iloc[0]:.2f}% to {ry.dropna().iloc[-1]:.2f}%")
    else:
        print("    WARNING: no DFII10 data — real yield features will be NaN")

    # --- VIX ---
    vix_series = fred_data.get("VIXCLS") or yf_data.get("VIXCLS")
    if vix_series is not None and not vix_series.dropna().empty:
        vix = reindex_daily(vix_series, m15_idx)
        feat["vix_cls"] = _shift_series(vix, 1)
        feat["vix_percentile_252"] = _shift_series(_rolling_percentile(vix, 252), 1)
        vix_shifted = _shift_series(vix, 1)
        regime_vals = pd.cut(vix_shifted, bins=[-np.inf, 20, 30, np.inf], labels=["low", "mid", "high"])
        feat["vix_regime"] = regime_vals
        print(f"    vix_cls: {vix.dropna().iloc[0]:.1f} to {vix.dropna().iloc[-1]:.1f}")
    else:
        print("    WARNING: no VIX data — VIX features will be NaN")

    # --- DXY ---
    dxy_series = fred_data.get("DTWEXBGS") or yf_data.get("DTWEXBGS")
    if dxy_series is not None and not dxy_series.dropna().empty:
        # Compute returns on daily series BEFORE reindexing to M15
        dxy_daily = dxy_series.groupby(dxy_series.index.normalize()).last().sort_index()
        dxy_daily_ret_5d = dxy_daily.pct_change(5, fill_method=None)
        dxy_daily_ret_20d = dxy_daily.pct_change(20, fill_method=None)
        dxy = reindex_daily(dxy_series, m15_idx)
        feat["dxy_level"] = _shift_series(dxy, 1)
        feat["dxy_return_5d"] = _shift_series(reindex_daily(dxy_daily_ret_5d, m15_idx), 1)
        feat["dxy_return_20d"] = _shift_series(reindex_daily(dxy_daily_ret_20d, m15_idx), 1)
        print(f"    dxy_level: {dxy.dropna().iloc[0]:.1f} to {dxy.dropna().iloc[-1]:.1f}")
    else:
        print("    WARNING: no DXY data — DXY features will be NaN")

    # --- Gold Vol (GVZ) ---
    gvz_series = fred_data.get("GVZCLS") or yf_data.get("GVZCLS")
    if gvz_series is not None and not gvz_series.dropna().empty:
        gvz = reindex_daily(gvz_series, m15_idx)
        feat["gold_vol_index"] = _shift_series(gvz, 1)
        print(f"    gold_vol_index: {gvz.dropna().iloc[0]:.1f} to {gvz.dropna().iloc[-1]:.1f}")
    else:
        print("    WARNING: no GVZ data — gold_vol_index will be NaN")

    # --- COT features (weekly, published ~2 days after Tuesday) ---
    if cot_df is not None and not cot_df.empty and "date" in cot_df.columns:
        cot_daily = cot_df.set_index("date").sort_index()

        for src_col, feat_name, lag in [
            ("mm_net_long_pct", "cot_mm_net_long_pct", 2),
            ("mm_trend_3w", "cot_mm_3w_change", 2),
        ]:
            if src_col in cot_daily.columns:
                vals = cot_daily[src_col].dropna()
                tz = m15_idx.tz
                shifted_idx = vals.index + pd.Timedelta(days=lag)
                if tz:
                    shifted_idx = shifted_idx.tz_localize(tz)
                shifted = pd.Series(vals.values, index=shifted_idx, name=src_col)
                all_dates = pd.Series(m15_idx.date, index=m15_idx).drop_duplicates()
                aligned = all_dates.to_frame("date").join(
                    shifted.to_frame("val"), how="left"
                )["val"]
                result_s = aligned.reindex(m15_idx, method="ffill")
                result_s.index = m15_idx
                result_s.name = feat_name
                feat[feat_name] = result_s

        if "cot_mm_net_long_pct" in feat:
            valid = feat["cot_mm_net_long_pct"].dropna()
            if not valid.empty:
                print(f"    cot_mm_net_long_pct: {valid.iloc[0]:.3f} to {valid.iloc[-1]:.3f}")

        if "cot_mm_3w_change" in feat:
            valid = feat["cot_mm_3w_change"].dropna()
            if not valid.empty:
                print(f"    cot_mm_3w_change: {valid.iloc[0]:.3f} to {valid.iloc[-1]:.3f}")

    # 6. Build macro DataFrame and join to features
    print("\n[6] Joining macro features to main feature set")
    macro_df = pd.DataFrame(feat, index=m15_idx)
    macro_df.index.name = "timestamp"
    print(f"    Macro features shape: {macro_df.shape}")
    print(f"    Macro columns: {list(macro_df.columns)}")
    print("    NaN counts:")
    for col in macro_df.columns:
        nan_pct = macro_df[col].isna().mean() * 100
        print(f"      {col}: {nan_pct:.1f}% NaN")

    # Join
    result = feature_df.join(macro_df)
    print(f"    Joined shape: {result.shape}")

    # 7. Validate
    print("\n[7] Validation checks")

    # 7a. NaN check
    for col in macro_df.columns:
        nan_pct = result[col].isna().mean() * 100
        if nan_pct > 10:
            print(f"    WARNING: {col} has {nan_pct:.1f}% NaN (>10%)")

    # 7b. Lookahead check — latest value should be from yesterday at most
    today = pd.Timestamp.now(tz=result.index.tz).normalize() if result.index.tz else pd.Timestamp.now().normalize()
    for col in macro_df.columns:
        valid = result[col].dropna()
        if not valid.empty:
            col_max_date = valid.index.max()
            if col_max_date.tz is None and today.tz is not None:
                col_max_date = col_max_date.tz_localize(today.tz)
            elif col_max_date.tz is not None and today.tz is None:
                col_max_date = col_max_date.tz_localize(None)
            days_diff = (today - col_max_date).days
            if days_diff < 0:
                print(f"    LOOKAHEAD: {col} has future data ({col_max_date.date()})")

    # 7c. Correlation with target_return (numeric columns only)
    if "target_return" in result.columns:
        tar = result["target_return"]
        print("\n    Correlation with target_return:")
        corrs = []
        for col in macro_df.columns:
            if result[col].dtype.kind not in ("i", "f"):
                continue
            both = pd.concat([result[col], tar], axis=1).dropna()
            if len(both) > 100:
                r = both[col].corr(both["target_return"])
                corrs.append((col, r))
        corrs.sort(key=lambda x: -abs(x[1]))
        for col, r in corrs:
            print(f"      {col}: {r:+.5f}")

    # 8. Save
    print(f"\n[8] Saving to {OUTPUT_PATH}")
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(OUTPUT_PATH, index=True)
    print(f"    Saved! {result.shape[0]} rows × {result.shape[1]} columns")
    print(f"\n    New columns added: {list(macro_df.columns)}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"  New columns added: {list(macro_df.columns)}")
    print(f"  Output file: {OUTPUT_PATH.relative_to(SRC)}")
    print(f"  Total columns in output: {result.shape[1]}")
    return result


if __name__ == "__main__":
    result = main()
