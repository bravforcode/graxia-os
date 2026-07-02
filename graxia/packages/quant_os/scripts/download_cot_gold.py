"""Download COT (Commitment of Traders) data for gold and silver."""

from pathlib import Path

import pandas as pd
import cot_reports


DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "market_data" / "cot"


def load_disaggregated() -> pd.DataFrame:
    df = cot_reports.cot_all(
        cot_report_type="disaggregated_fut", store_txt=False, verbose=True
    )
    df["Report_Date_as_YYYY-MM-DD"] = pd.to_datetime(
        df["Report_Date_as_YYYY-MM-DD"]
    )
    return df


def filter_commodity(df: pd.DataFrame, name: str) -> pd.DataFrame:
    mask = df["Market_and_Exchange_Names"].str.contains(name, case=False, na=False)
    return df[mask].copy()


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive key positioning metrics from raw disaggregated COT columns."""
    out = pd.DataFrame()
    out["report_date"] = df["Report_Date_as_YYYY-MM-DD"]
    out["market"] = df["Market_and_Exchange_Names"]
    out["open_interest"] = df["Open_Interest_All"]

    # Commercials (Producer/Merchant) net long %
    prod_long = df["Prod_Merc_Positions_Long_All"]
    prod_short = df["Prod_Merc_Positions_Short_All"]
    out["commercials_long"] = prod_long
    out["commercials_short"] = prod_short
    out["commercials_net"] = prod_long - prod_short
    oi = df["Open_Interest_All"].replace(0, pd.NA)
    out["commercials_net_pct"] = ((prod_long - prod_short) / oi * 100).round(2)

    # Managed Money positioning
    mm_long = df["M_Money_Positions_Long_All"]
    mm_short = df["M_Money_Positions_Short_All"]
    out["managed_money_long"] = mm_long
    out["managed_money_short"] = mm_short
    out["managed_money_net"] = mm_long - mm_short
    out["managed_money_net_pct"] = ((mm_long - mm_short) / oi * 100).round(2)
    out["managed_money_long_pct"] = df["Pct_of_OI_M_Money_Long_All"]
    out["managed_money_short_pct"] = df["Pct_of_OI_M_Money_Short_All"]
    out["managed_money_spread_pct"] = df["Pct_of_OI_M_Money_Spread_All"]

    # Large Speculators (Other Reportable)
    other_long = df["Other_Rept_Positions_Long_All"]
    other_short = df["Other_Rept_Positions_Short_All"]
    out["large_spec_long"] = other_long
    out["large_spec_short"] = other_short
    out["large_spec_net"] = other_long - other_short
    out["large_spec_net_pct"] = ((other_long - other_short) / oi * 100).round(2)

    # Weekly change columns
    out["oi_change"] = df["Change_in_Open_Interest_All"]
    out["mm_long_change"] = df["Change_in_M_Money_Long_All"]
    out["mm_short_change"] = df["Change_in_M_Money_Short_All"]

    # Non-reportable (retail)
    out["non_reportable_long"] = df["NonRept_Positions_Long_All"]
    out["non_reportable_short"] = df["NonRept_Positions_Short_All"]
    out["non_reportable_net"] = (
        df["NonRept_Positions_Long_All"] - df["NonRept_Positions_Short_All"]
    )

    return out.sort_values("report_date").reset_index(drop=True)


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("Downloading COT disaggregated futures data from CFTC...")
    print("=" * 60)
    raw = load_disaggregated()
    print(f"Total rows: {len(raw)}")

    for commodity, label, filename in [
        ("GOLD", "Gold", "gold_cot_weekly.parquet"),
        ("SILVER", "Silver", "silver_cot_weekly.parquet"),
    ]:
        subset = filter_commodity(raw, commodity)
        # Keep only the primary COMEX contract (exclude micro / coinbase)
        if commodity == "GOLD":
            subset = subset[
                subset["Market_and_Exchange_Names"] == "GOLD - COMMODITY EXCHANGE INC."
            ]
        elif commodity == "SILVER":
            subset = subset[
                subset["Market_and_Exchange_Names"] == "SILVER - COMMODITY EXCHANGE INC."
            ]

        featured = build_features(subset)
        out_path = DATA_DIR / filename
        featured.to_parquet(out_path, index=False)
        print(f"\n{label}: {len(featured)} rows saved to {out_path}")
        if len(featured) > 0:
            print(f"  Date range: {featured['report_date'].min().date()} to {featured['report_date'].max().date()}")
            print("  Latest row:")
            latest = featured.iloc[-1]
            print(f"    OI: {latest['open_interest']:,.0f}")
            print(f"    Commercials net: {latest['commercials_net']:,.0f} ({latest['commercials_net_pct']}%)")
            print(f"    Managed Money net: {latest['managed_money_net']:,.0f} ({latest['managed_money_net_pct']}%)")
            print(f"    Large Specs net: {latest['large_spec_net']:,.0f} ({latest['large_spec_net_pct']}%)")
        else:
            print("  WARNING: No data found for this commodity.")

    print("\nDone.")


if __name__ == "__main__":
    main()
