"""Commitment of Traders (COT) integration for XAUUSD macro features."""

from pathlib import Path

import numpy as np
import pandas as pd

from cot_reports import cot_year

XAUUSD_CFTC_CODE = "088691"
COT_CACHE_DIR = Path("data/cot")


def _parse_numeric(val: str) -> float:
    val = str(val).replace(",", "").strip()
    if val in ("", ".", "-", "nan", "NaN"):
        return np.nan
    try:
        return float(val)
    except ValueError:
        return np.nan


def _extract_gold_records(df_raw: pd.DataFrame) -> pd.DataFrame:
    if "CFTC_Contract_Market_Code" in df_raw.columns:
        mask = df_raw["CFTC_Contract_Market_Code"].astype(str).str.strip() == XAUUSD_CFTC_CODE
        return df_raw[mask].copy()
    if "Market_and_Exchange_Names" in df_raw.columns:
        mask = df_raw["Market_and_Exchange_Names"].astype(str).str.contains("GOLD", case=False, na=False)
        return df_raw[mask].copy()
    return df_raw.copy()


def _parse_date_col(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["Report_Date_as_YYYY-MM-DD", "As_of_Date_In_Form_YYMMDD", "Date", "Report_Date"]:
        if col in df.columns:
            df["date"] = pd.to_datetime(df[col], errors="coerce")
            break
    if "date" not in df.columns:
        raise KeyError(f"Cannot find date column. Available: {list(df.columns)}")
    return df.dropna(subset=["date"])


def _compute_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True)

    for col, target in [
        ("MM_Positions_Long_All", "mm_long"),
        ("MM_Positions_Short_All", "mm_short"),
        ("MM_Money_Positions_Long_All", "mm_long"),
        ("MM_Money_Positions_Short_All", "mm_short"),
        ("M_Money_Positions_Long_All", "mm_long"),
        ("M_Money_Positions_Short_All", "mm_short"),
        ("Prod_Merc_Positions_Long_All", "prod_long"),
        ("Prod_Merc_Positions_Short_All", "prod_short"),
    ]:
        if col in df.columns:
            df[target] = df[col].apply(_parse_numeric)

    if "mm_long" in df.columns and "mm_short" in df.columns:
        df["mm_net_long"] = df["mm_long"] - df["mm_short"]

    if "prod_long" in df.columns and "prod_short" in df.columns:
        df["prod_net_short"] = df["prod_short"] - df["prod_long"]

    for oi_col in ["Open_Interest_All", "OI_All", "Tot_Reportable_Positions_All", "Open_Interest"]:
        if oi_col in df.columns:
            df["open_interest"] = df[oi_col].apply(_parse_numeric)
            break

    if "mm_net_long" in df.columns and "open_interest" in df.columns:
        df["mm_net_long_pct"] = df["mm_net_long"] / df["open_interest"].replace(0, np.nan)

    if "mm_net_long" in df.columns:
        df["cot_index_52w"] = (
            df["mm_net_long"].rolling(52, min_periods=13).apply(
                lambda x: pd.Series(x).rank(pct=True).iloc[-1] if len(x) >= 13 else np.nan,
                raw=False,
            )
        )
        df["mm_trend_3w"] = df["mm_net_long"].diff(3)

    if "prod_net_short" in df.columns:
        df["producer_net_short_pct"] = df["prod_net_short"] / df["open_interest"].replace(0, np.nan)

    return df


def fetch_cot_gold(
    year: int,
    report_type: str = "disaggregated_fut",
    force: bool = False,
) -> pd.DataFrame:
    COT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache_path = COT_CACHE_DIR / f"cot_xauusd_{report_type}_{year}.parquet"

    if not force and cache_path.exists():
        df = pd.read_parquet(cache_path)
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
        return df

    df_raw = cot_year(year=year, cot_report_type=report_type, store_txt=False, verbose=False)

    if df_raw is None or (hasattr(df_raw, "empty") and df_raw.empty):
        return pd.DataFrame()

    df_raw = pd.DataFrame(df_raw)
    df = _extract_gold_records(df_raw)
    if df.empty:
        return df

    df = _parse_date_col(df)
    df = _compute_features(df)
    df.to_parquet(cache_path, index=False)
    return df


def fetch_cot_gold_range(
    start_year: int,
    end_year: int,
    report_type: str = "disaggregated_fut",
    force: bool = False,
) -> pd.DataFrame:
    frames = []
    for y in range(start_year, end_year + 1):
        df = fetch_cot_gold(y, report_type=report_type, force=force)
        if not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.sort_values("date").drop_duplicates(subset=["date"]).reset_index(drop=True)
    return combined
