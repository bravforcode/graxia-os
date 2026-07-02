#!/usr/bin/env python3
"""Test all yfinance tickers relevant to XAUUSD gold trading."""

import json
from datetime import datetime

import yfinance as yf

TICKERS = {
    "Gold": {
        "GC=F": "Gold Futures",
        "GLD": "Gold ETF",
        "IAU": "iShares Gold ETF",
    },
    "Silver": {
        "SI=F": "Silver Futures",
        "SLV": "iShares Silver ETF",
    },
    "Oil & Gas": {
        "CL=F": "Crude Oil Futures",
        "BZ=F": "Brent Crude Futures",
        "NG=F": "Natural Gas Futures",
    },
    "DXY": {
        "DX-Y.NYB": "US Dollar Index",
    },
    "VIX": {
        "^VIX": "CBOE Volatility Index",
        "VIXY": "VIX Short-Term Futures ETF",
        "VXX": "iPath VIX Short-Term Futures ETN",
    },
    "Bonds & Yields": {
        "^TNX": "10-Year Treasury Yield",
        "^FVX": "5-Year Treasury Yield",
        "^TYX": "30-Year Treasury Yield",
        "TLT": "iShares 20+ Year Bond ETF",
        "IEF": "iShares 7-10 Year Bond ETF",
        "SHY": "iShares 1-3 Year Bond ETF",
    },
    "Equities": {
        "^GSPC": "S&P 500",
        "^DJI": "Dow Jones",
        "^IXIC": "Nasdaq",
        "^RUT": "Russell 2000",
    },
    "FX & Spot": {
        "XAUUSD=X": "Gold Spot",
        "EURUSD=X": "EUR/USD",
        "GBPUSD=X": "GBP/USD",
        "USDJPY=X": "USD/JPY",
    },
    "Crypto": {
        "BTC-USD": "Bitcoin",
        "ETH-USD": "Ethereum",
    },
    "Other Commodities & USD": {
        "DBA": "Invesco Agriculture ETF",
        "UUP": "Invesco DB USD Bull ETF",
        "UDN": "Invesco DB USD Bear ETF",
    },
}

def test_ticker(symbol: str) -> dict:
    """Test a single ticker and return metadata."""
    try:
        t = yf.Ticker(symbol)
        hist = t.history(period="max")
        if hist.empty:
            return {"status": "empty", "rows": 0, "start": None, "end": None}
        return {
            "status": "ok",
            "rows": len(hist),
            "start": str(hist.index.min().date()),
            "end": str(hist.index.max().date()),
        }
    except Exception as e:
        return {"status": "error", "error": str(e)[:120], "rows": 0, "start": None, "end": None}

def main():
    results = {}
    total = sum(len(v) for v in TICKERS.values())
    idx = 0
    for category, tickers in TICKERS.items():
        results[category] = {}
        for symbol, name in tickers.items():
            idx += 1
            print(f"[{idx}/{total}] {symbol} ({name})...", end=" ", flush=True)
            info = test_ticker(symbol)
            info["name"] = name
            results[category][symbol] = info
            if info["status"] == "ok":
                print(f"OK  {info['rows']} rows  {info['start']} -> {info['end']}")
            else:
                print(f"{info['status'].upper()}  {info.get('error', '')}")

    # Summary
    ok = sum(1 for cat in results.values() for v in cat.values() if v["status"] == "ok")
    empty = sum(1 for cat in results.values() for v in cat.values() if v["status"] == "empty")
    err = sum(1 for cat in results.values() for v in cat.values() if v["status"] == "error")
    print(f"\n{'='*60}")
    print(f"RESULTS: {ok} working / {empty} empty / {err} errors  (total {total})")
    print(f"{'='*60}")

    out = {"tested_at": datetime.utcnow().isoformat() + "Z", "summary": {"ok": ok, "empty": empty, "errors": err, "total": total}, "results": results}
    out_path = "reports/yfinance_ticker_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to {out_path}")

if __name__ == "__main__":
    main()
