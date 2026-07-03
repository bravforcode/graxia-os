"""
Research ALL FRED series relevant to XAUUSD gold trading.
Downloads metadata, tests availability, and saves 5yr daily data for working series.
"""

import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from fredapi import Fred

# ─── Configuration ───────────────────────────────────────────────────
FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
if not FRED_API_KEY:
    print("ERROR: Set FRED_API_KEY env var before running (get one at https://fred.stlouisfed.org/docs/api/api_key.html)")
    sys.exit(1)
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "fred"
REPORT_PATH = OUTPUT_DIR / "fred_series_report.json"
DAILY_DIR = OUTPUT_DIR / "daily"

YEARS_BACK = 5
END_DATE = datetime.now()
START_DATE = END_DATE - timedelta(days=YEARS_BACK * 365)

# ─── Series Registry ────────────────────────────────────────────────
SERIES = {
    # --- Interest Rates ---
    "DFII10":   {"category": "interest_rate", "desc": "10-Year TIPS Yield"},
    "T10YIE":   {"category": "interest_rate", "desc": "10-Year Breakeven Inflation Rate"},
    "DGS10":    {"category": "interest_rate", "desc": "10-Year Treasury Nominal Yield"},
    "DGS2":     {"category": "interest_rate", "desc": "2-Year Treasury Nominal Yield"},
    "T10Y2Y":   {"category": "interest_rate", "desc": "10Y-2Y Term Spread"},
    "DGS30":    {"category": "interest_rate", "desc": "30-Year Treasury Nominal Yield"},
    "DGS5":     {"category": "interest_rate", "desc": "5-Year Treasury Nominal Yield"},
    "DGS7":     {"category": "interest_rate", "desc": "7-Year Treasury Nominal Yield"},
    "DGS1":     {"category": "interest_rate", "desc": "1-Year Treasury Nominal Yield"},
    "DGS3MO":   {"category": "interest_rate", "desc": "3-Month Treasury Nominal Yield"},
    "DGS6MO":   {"category": "interest_rate", "desc": "6-Month Treasury Nominal Yield"},
    "T5YIE":    {"category": "interest_rate", "desc": "5-Year Breakeven Inflation Rate"},
    "T5YIFR":   {"category": "interest_rate", "desc": "5-Year, 5-Year Forward Inflation Expectation Rate"},
    "DFF":      {"category": "interest_rate", "desc": "Federal Funds Effective Rate"},

    # --- Gold / Volatility ---
    "GVZCLS":              {"category": "gold_vol", "desc": "Gold VIX (CBOE Gold ETF Volatility Index)"},
    "GOLDAMGBD228NLBM":    {"category": "gold",     "desc": "Gold Spot AM Fix (USD/oz)"},
    "GOLDPMGBD228NLBM":    {"category": "gold",     "desc": "Gold Spot PM Fix (USD/oz)"},
    "GBDPMAMTLGNZD":       {"category": "gold",     "desc": "Gold Fixing Price (London PM, EUR)"},
    "GOLDPMGBD228NLBM_D":  {"category": "gold",     "desc": "Gold PM Fix (daily derived)"},

    # --- Oil ---
    "DCOILWTICO":   {"category": "oil", "desc": "WTI Crude Oil Spot Price"},
    "DCOILBRENTEU":  {"category": "oil", "desc": "Brent Crude Oil Spot Price (EUR)"},
    "DCOILBRENTEU":  {"category": "oil", "desc": "Brent Crude Oil Spot Price"},
    "DHHGSWP":       {"category": "oil", "desc": "Henry Hub Natural Gas Spot Price"},

    # --- Dollar / FX ---
    "DTWEXBGS":  {"category": "dollar", "desc": "Trade Weighted USD Index (Broad)"},
    "DTWEXM":    {"category": "dollar", "desc": "Trade Weighted USD Index (Major Currencies)"},
    "DTWEXB":    {"category": "dollar", "desc": "Trade Weighted USD Index (Broad, alt)"},
    "DEXUSEU":   {"category": "fx",     "desc": "EUR/USD Exchange Rate"},
    "DEXJPUS":   {"category": "fx",     "desc": "USD/JPY Exchange Rate"},
    "DEXGBUS":   {"category": "fx",     "desc": "GBP/USD Exchange Rate"},
    "DEXCHUS":   {"category": "fx",     "desc": "USD/CNY Exchange Rate"},

    # --- Economic ---
    "UNRATE":    {"category": "economic", "desc": "Unemployment Rate"},
    "CPIAUCSL":  {"category": "economic", "desc": "CPI for All Urban Consumers"},
    "CPILFESL":  {"category": "economic", "desc": "Core CPI (Less Food & Energy)"},
    "FEDFUNDS":  {"category": "economic", "desc": "Federal Funds Target Rate"},
    "A191RL1Q225SBEA": {"category": "economic", "desc": "Real GDP Growth (Quarterly, Annualized)"},
    "INDPRO":    {"category": "economic", "desc": "Industrial Production Index"},
    "UMCSENT":   {"category": "economic", "desc": "U. of Michigan Consumer Sentiment"},
    "T10YIE":    {"category": "economic", "desc": "10-Year Breakeven Inflation Rate"},

    # --- Credit ---
    "BAMLH0A0HYM2":  {"category": "credit", "desc": "ICE BofA US High Yield OAS (HY Credit Spread)"},
    "BAMLH0A0HYM2EY": {"category": "credit", "desc": "High Yield OAS Excess Yield"},
    "TEDRATE":        {"category": "credit", "desc": "TED Spread (3M T-Bill vs 3M LIBOR)"},
    "BAA10Y":         {"category": "credit", "desc": "Moody's BAA Corporate Bond Yield vs 10Y Treasury"},
    "T10Y2Y":         {"category": "credit", "desc": "10Y-2Y Treasury Spread (recession proxy)"},
    "BAMLH0A1HYBB":   {"category": "credit", "desc": "US HY OAS - BB Rated"},

    # --- Liquidity / Fed Balance Sheet ---
    "WALCL":       {"category": "liquidity", "desc": "Fed Total Assets (Liabilities) Weekly"},
    "BOGMBASEW":   {"category": "liquidity", "desc": "Monetary Base (Weekly)"},
    "BOGMBASE":    {"category": "liquidity", "desc": "Monetary Base (Monthly)"},
    "WTREGEN":     {"category": "liquidity", "desc": "Treasury General Account Balance"},
    "RRPONTSYD":   {"category": "liquidity", "desc": "ON RRP Facility (Daily)"},
    "USESLB":      {"category": "liquidity", "desc": "Federal Reserve Bank Reserve Balances"},

    # --- VIX / Equities (correlated with gold) ---
    "VIXCLS":     {"category": "vix",      "desc": "CBOE Volatility Index (VIX)"},
    "SP500":      {"category": "equities", "desc": "S&P 500 Index"},
    "DJI":        {"category": "equities", "desc": "Dow Jones Industrial Average"},

    # --- Additional Gold-Adjacent ---
    "SLVPRUSD":   {"category": "metals", "desc": "Silver Spot Price (USD/oz)"},
    "PCOPPMMUSD": {"category": "metals", "desc": "Copper Price (USD/lb)"},
}


def classify_frequency(series_id: str, df: pd.DataFrame) -> str:
    if len(df) < 2:
        return "unknown"
    inferred = pd.infer_freq(df.index)
    if inferred:
        return inferred
    median_days = pd.Series(df.index).diff().dt.days.median()
    if median_days <= 1.5:
        return "daily"
    elif median_days <= 8:
        return "business_daily"
    elif median_days <= 35:
        return "weekly"
    elif median_days <= 40:
        return "monthly"
    else:
        return f"~{int(median_days)}d"


def research_all_series():
    fred = Fred(api_key=FRED_API_KEY)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DAILY_DIR.mkdir(parents=True, exist_ok=True)

    report = {
        "generated": datetime.now().isoformat(),
        "date_range": f"{START_DATE.date()} to {END_DATE.date()}",
        "years_back": YEARS_BACK,
        "series_tested": len(SERIES),
        "working": [],
        "failed": [],
        "summary": {},
    }

    for sid, meta in sorted(SERIES.items()):
        print(f"\n{'='*60}")
        print(f"  Testing: {sid} — {meta['desc']}")
        print(f"  Category: {meta['category']}")
        print(f"{'='*60}")

        entry = {
            "series_id": sid,
            "description": meta["desc"],
            "category": meta["category"],
        }

        try:
            df = fred.get_series(
                sid,
                observation_start=START_DATE.strftime("%Y-%m-%d"),
                observation_end=END_DATE.strftime("%Y-%m-%d"),
            )

            if df is None or df.empty:
                raise ValueError("Empty series returned")

            df = df.dropna()
            freq = classify_frequency(sid, df)
            row_count = len(df)

            entry.update({
                "status": "OK",
                "first_date": str(df.index.min().date()),
                "last_date": str(df.index.max().date()),
                "rows": row_count,
                "frequency": freq,
                "mean": round(float(df.mean()), 6),
                "std": round(float(df.std()), 6),
                "min": round(float(df.min()), 6),
                "max": round(float(df.max()), 6),
            })

            csv_path = DAILY_DIR / f"{sid}.csv"
            df.to_csv(csv_path, header=[sid])
            entry["csv"] = str(csv_path.relative_to(OUTPUT_DIR))

            print(f"  ✓ OK — {row_count} rows, freq={freq}")
            print(f"  Range: {entry['first_date']} to {entry['last_date']}")
            print(f"  Stats: mean={entry['mean']}, std={entry['std']}")
            print(f"  Saved: {csv_path.name}")

            report["working"].append(entry)

        except Exception as e:
            err_msg = str(e)[:200]
            entry["status"] = "FAILED"
            entry["error"] = err_msg
            report["failed"].append(entry)
            print(f"  ✗ FAILED — {err_msg}")

    # ─── Summary ─────────────────────────────────────────────────────
    categories = {}
    for w in report["working"]:
        cat = w["category"]
        categories.setdefault(cat, []).append(w["series_id"])

    report["summary"] = {
        "total_tested": report["series_tested"],
        "working_count": len(report["working"]),
        "failed_count": len(report["failed"]),
        "by_category": {k: len(v) for k, v in categories.items()},
        "working_by_category": categories,
    }

    with open(REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*60}")
    print(f"  REPORT: {report['summary']['working_count']}/{report['summary']['total_tested']} series working")
    print(f"  Saved: {REPORT_PATH}")
    print(f"{'='*60}")

    if report["failed"]:
        print("\n  FAILED SERIES:")
        for f_entry in report["failed"]:
            print(f"    {f_entry['series_id']}: {f_entry.get('error', '?')[:80]}")

    if categories:
        print("\n  WORKING BY CATEGORY:")
        for cat, ids in sorted(categories.items()):
            print(f"    {cat}: {', '.join(ids)}")

    return report


if __name__ == "__main__":
    research_all_series()
