"""Macro feature engineering for M15 alignment with publication lag handling."""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from .fred_client import FredClient
from .point_in_time_store import PointInTimeStore

PUBLICATION_LAG_DAYS = {
    "real_yield_pct": 1,
    "real_yield_1m_change": 1,
    "real_yield_3m_change": 1,
    "vix_percentile": 1,
    "vix_regime": 1,
    "dxy_return_5d": 1,
    "dxy_return_20d": 1,
    "oil_return_5d": 1,
    "gold_vol_percentile": 1,
    "breakeven_inflation": 1,
    "real_rate_zscore": 1,
    "cot_net_long_pct": 2,
    "cot_net_long_3w_change": 2,
}


def _shift_series(series: pd.Series, lag_days: int) -> pd.Series:
    if lag_days <= 0:
        return series
    shifted = series.shift(lag_days)
    shifted.index = series.index
    return shifted


def _rolling_percentile(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window, min_periods=int(window * 0.5)).apply(
        lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) >= 5 else np.nan,
        raw=False,
    )


def _rolling_zscore(series: pd.Series, window: int) -> pd.Series:
    rolling_mean = series.rolling(window, min_periods=int(window * 0.5)).mean()
    rolling_std = series.rolling(window, min_periods=int(window * 0.5)).std()
    z = (series - rolling_mean) / rolling_std.replace(0, np.nan)
    return z


def build_macro_features(
    m15_index: pd.DatetimeIndex,
    fred_client: FredClient,
    cot_df: Optional[pd.DataFrame] = None,
    start_date: str = "2015-01-01",
    end_date: Optional[str] = None,
    pit_store: Optional[PointInTimeStore] = None,
) -> pd.DataFrame:
    if end_date is None:
        end_date = m15_index.max().strftime("%Y-%m-%d")

    fetch_start = pd.Timestamp(start_date) - pd.Timedelta(days=365)
    fetch_start_str = fetch_start.strftime("%Y-%m-%d")

    ALL_MACRO_SERIES = [
        "DFII10", "VIXCLS", "DCOILWTICO", "GVZCLS", "T10YIE", "DGS10",
        "DTWEXBGS", "UNRATE", "FEDFUNDS",
    ]

    df_all = fred_client.fetch_multiple(
        series_ids=ALL_MACRO_SERIES,
        start_date=fetch_start_str,
        end_date=end_date,
        silent=True,
    )

    frame = pd.DataFrame(index=m15_index)
    frame.index.name = "timestamp"
    frame["date"] = frame.index.normalize()

    def _reindex(series: pd.Series) -> pd.Series:
        if series.empty:
            return pd.Series(np.nan, index=m15_index, name=series.name)
        day_map = series.groupby(series.index.normalize()).last()
        result = pd.Series(np.nan, index=m15_index)
        day_vals = frame["date"].map(day_map)
        day_vals.index = m15_index
        result = day_vals
        result.name = series.name
        return result

    feat = {}

    if "DFII10" in df_all.columns:
        real_yield = _reindex(df_all["DFII10"])
        feat["real_yield_pct"] = _shift_series(real_yield, 1)
        feat["real_yield_1m_change"] = _shift_series(real_yield.diff(30), 1)
        feat["real_yield_3m_change"] = _shift_series(real_yield.diff(90), 1)
        feat["real_rate_zscore"] = _shift_series(_rolling_zscore(real_yield, 252), 1)

    if "VIXCLS" in df_all.columns:
        vix = _reindex(df_all["VIXCLS"])
        feat["vix_percentile"] = _shift_series(_rolling_percentile(vix, 252), 1)
        vix_shifted = _shift_series(vix, 1)
        regime_vals = pd.cut(
            vix_shifted,
            bins=[-np.inf, 20, 30, np.inf],
            labels=["low", "mid", "high"],
        )
        feat["vix_regime"] = regime_vals

    if "DTWEXBGS" in df_all.columns:
        dxy = _reindex(df_all["DTWEXBGS"])
        feat["dxy_return_5d"] = _shift_series(dxy.pct_change(5), 1)
        feat["dxy_return_20d"] = _shift_series(dxy.pct_change(20), 1)

    if "DCOILWTICO" in df_all.columns:
        oil = _reindex(df_all["DCOILWTICO"])
        feat["oil_return_5d"] = _shift_series(oil.pct_change(5), 1)

    if "GVZCLS" in df_all.columns:
        gvz = _reindex(df_all["GVZCLS"])
        feat["gold_vol_percentile"] = _shift_series(_rolling_percentile(gvz, 252), 1)

    if "T10YIE" in df_all.columns:
        breakeven = _reindex(df_all["T10YIE"])
        feat["breakeven_inflation"] = _shift_series(breakeven, 1)

    if "DGS10" in df_all.columns:
        dgs10 = _reindex(df_all["DGS10"])
        feat["nominal_yield_10y"] = _shift_series(dgs10, 1)

    if "UNRATE" in df_all.columns:
        unrate = _reindex(df_all["UNRATE"])
        feat["unemployment_rate"] = _shift_series(unrate, 1)

    if "FEDFUNDS" in df_all.columns:
        fedfunds = _reindex(df_all["FEDFUNDS"])
        feat["fed_funds_rate"] = _shift_series(fedfunds, 1)

    if cot_df is not None and not cot_df.empty and "date" in cot_df.columns:
        cot = cot_df.set_index("date").sort_index()

        if "mm_net_long_pct" in cot.columns:
            cot_day_map = cot["mm_net_long_pct"]
            mapped = frame["date"].map(
                pd.Series(cot_day_map.values, index=cot_day_map.index)
            )
            mapped.index = m15_index
            feat["cot_net_long_pct"] = _shift_series(mapped, 2)

        if "mm_trend_3w" in cot.columns:
            cot_trend_map = cot["mm_trend_3w"]
            mapped = frame["date"].map(
                pd.Series(cot_trend_map.values, index=cot_trend_map.index)
            )
            mapped.index = m15_index
            feat["cot_net_long_3w_change"] = _shift_series(mapped, 2)

    result = pd.DataFrame(feat, index=m15_index)
    result.index.name = "timestamp"

    if pit_store is not None:
        pit_df = pit_store.get_latest()
        if not pit_df.empty:
            for _, row in pit_df.iterrows():
                col = row["series"]
                val = row["value"]
                val_date = row["value_date"]
                mask_later = result.index >= val_date
                result.loc[mask_later, col] = val

    return result
