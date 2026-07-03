"""Research ALL alternative data sources for XAUUSD gold trading.

Tests each source, downloads available data, saves results to JSON.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

RESULTS = {}

def record(source: str, status: str, detail: str, rows: int = 0, date_range: str = "", data: dict | None = None):
    RESULTS[source] = {
        "status": status,
        "detail": detail,
        "rows": rows,
        "date_range": date_range,
        "tested_at": datetime.now().isoformat(),
    }
    if data:
        RESULTS[source]["sample"] = data
    tag = {"ok": "✓", "warn": "△", "fail": "✗", "skip": "○"}.get(status, "?")
    print(f"  [{tag}] {source}: {detail}")


# ── 1. COT Reports ──────────────────────────────────────────────────────
def test_cot_reports():
    print("\n=== 1. COT Reports (cot_reports library) ===")
    try:
        from cot_reports import cot_year
        print("  cot_reports library imported OK")

        # Test 2025 disaggregated gold futures
        df = cot_year(year=2025, cot_report_type="disaggregated_fut", store_txt=False, verbose=False)
        if df is not None and len(df) > 0:
            df = df[df["CFTC_Contract_Market_Code"].astype(str).str.strip() == "088691"]
            cols_of_interest = [c for c in df.columns if any(k in c.lower() for k in
                ["date", "long", "short", "position", "money", "merc", "asset_mgr", "lever"])]
            sample = {}
            if not df.empty:
                for c in cols_of_interest[:10]:
                    sample[c] = str(df[c].iloc[0])
            record("cot_reports", "ok", f"Gold COT 2025: {len(df)} rows, {len(df.columns)} cols",
                   rows=len(df), data=sample)
        else:
            record("cot_reports", "warn", "cot_year returned empty for 2025")

        # Test cached data
        cache_dir = Path("data/cot")
        if cache_dir.exists():
            cached = list(cache_dir.glob("*.parquet"))
            record("cot_reports_cached", "ok", f"{len(cached)} cached parquet files", rows=len(cached),
                   data={f.name: str(f.stat().st_size) + " bytes" for f in cached})
        else:
            record("cot_reports_cached", "warn", "No cot cache directory")

        # Test existing COT module
        from core.data.cot_reports import fetch_cot_gold_range
        df_range = fetch_cot_gold_range(2024, 2025)
        if not df_range.empty:
            key_cols = [c for c in ["date", "mm_net_long", "mm_net_long_pct", "cot_index_52w",
                                     "prod_net_short", "open_interest"] if c in df_range.columns]
            sample = {}
            if key_cols:
                last = df_range[key_cols].iloc[-1]
                for c in key_cols:
                    sample[c] = str(last[c])
            record("cot_module", "ok", f"fetch_cot_gold_range(2024-2025): {len(df_range)} rows",
                   rows=len(df_range), date_range=f"{df_range['date'].min().date()} → {df_range['date'].max().date()}",
                   data=sample)
        else:
            record("cot_module", "warn", "fetch_cot_gold_range returned empty")

    except Exception as e:
        record("cot_reports", "fail", f"Error: {e}")


# ── 2. MT5 Historical Data ─────────────────────────────────────────────
def test_mt5():
    print("\n=== 2. MT5 Historical Data (Pepperstone) ===")
    try:
        import MetaTrader5 as mt5
        print("  MetaTrader5 module imported OK")

        if not mt5.initialize():
            err = mt5.last_error()
            record("mt5_connection", "warn",
                   f"MT5 terminal not running. Error: {err}. "
                   "To use: open Pepperstone MT5 → allow algo trading → re-run script.")
            return

        info = mt5.terminal_info()
        ver = mt5.version()
        record("mt5_terminal", "ok", f"Terminal: {info.name}, Build: {ver[0]}, Build date: {ver[2]}")

        # Check XAUUSD symbol
        symbol_info = mt5.symbol_info("XAUUSD")
        if symbol_info is None:
            record("mt5_xauusd", "fail", "XAUUSD symbol not found")
            mt5.shutdown()
            return

        record("mt5_xauusd", "ok", f"XAUUSD found: {symbol_info.name}, digits={symbol_info.digits}")

        import pandas as pd
        from time import mktime

        # Scan all timeframes for max available history
        tf_map = {
            "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, "M30": mt5.TIMEFRAME_M30,
            "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4, "D1": mt5.TIMEFRAME_D1,
            "W1": mt5.TIMEFRAME_W1, "MN1": mt5.TIMEFRAME_MN1,
        }
        tf_summary = {}
        for tf_name, tf_code in tf_map.items():
            best = None
            best_label = None
            for days, label in [(3650, "10yr"), (2555, "7yr"), (1825, "5yr"), (1095, "3yr"), (730, "2yr"), (365, "1yr")]:
                end_ts = int(mktime(datetime.now().timetuple()))
                start_ts = int(mktime((datetime.now() - timedelta(days=days)).timetuple()))
                rates = mt5.copy_rates_range("XAUUSD", tf_code, start_ts, end_ts)
                if rates is not None and len(rates) > 0:
                    best = rates
                    best_label = label
                    break
            if best is not None:
                df = pd.DataFrame(best)
                df["time"] = pd.to_datetime(df["time"], unit="s")
                tf_summary[tf_name] = {"bars": len(best), "max_range": best_label,
                                       "start": str(df["time"].iloc[0].date()),
                                       "end": str(df["time"].iloc[-1].date())}
            else:
                tf_summary[tf_name] = {"bars": 0, "max_range": "N/A"}

        avail = [f"{k}={v['max_range']}" for k, v in tf_summary.items() if v["bars"] > 0]
        record("mt5_timeframes", "ok", f"MT5 XAUUSD: {', '.join(avail)}", data=tf_summary)

        # Save the best available high-res data (H1 = 10yr, good for backtest)
        h1_rates = mt5.copy_rates_range("XAUUSD", mt5.TIMEFRAME_H1,
                                         int(mktime((datetime.now()-timedelta(days=3650)).timetuple())),
                                         int(mktime(datetime.now().timetuple())))
        if h1_rates is not None and len(h1_rates) > 0:
            df_h1 = pd.DataFrame(h1_rates)
            df_h1["time"] = pd.to_datetime(df_h1["time"], unit="s")
            out_path = Path("data/mt5_xauusd_h1_10yr.parquet")
            df_h1.to_parquet(out_path, index=False)
            record("mt5_h1_10yr_save", "ok", f"Saved H1 10yr to {out_path}: {len(df_h1)} bars",
                   rows=len(df_h1))

        mt5.shutdown()

    except ImportError:
        record("mt5", "fail", "MetaTrader5 module not installed")
    except Exception as e:
        record("mt5", "fail", f"Error: {e}")


# ── 3. Yahoo Finance (yfinance) ─────────────────────────────────────────
def test_yfinance():
    print("\n=== 3. Yahoo Finance (yfinance) ===")
    try:
        import yfinance as yf

        # Gold futures (GC=F)
        gold = yf.Ticker("GC=F")
        hist = gold.history(period="max")
        if not hist.empty:
            record("yf_gold_futures", "ok", f"GC=F max history: {len(hist)} rows",
                   rows=len(hist),
                   date_range=f"{hist.index[0].date()} → {hist.index[-1].date()}")
        else:
            record("yf_gold_futures", "fail", "GC=F returned empty")

        # GLD ETF
        gld = yf.Ticker("GLD")
        gld_hist = gld.history(period="max")
        if not gld_hist.empty:
            record("yf_gld_etf", "ok", f"GLD ETF: {len(gld_hist)} rows",
                   rows=len(gld_hist),
                   date_range=f"{gld_hist.index[0].date()} → {gld_hist.index[-1].date()}")
        else:
            record("yf_gld_etf", "fail", "GLD returned empty")

        # IAU ETF
        iau = yf.Ticker("IAU")
        iau_hist = iau.history(period="max")
        if not iau_hist.empty:
            record("yf_iau_etf", "ok", f"IAU ETF: {len(iau_hist)} rows",
                   rows=len(iau_hist),
                   date_range=f"{iau_hist.index[0].date()} → {iau_hist.index[-1].date()}")
        else:
            record("yf_iau_etf", "fail", "IAU returned empty")

        # GVZ - CBOE Gold Volatility Index
        gvz = yf.Ticker("^GVZ")
        gvz_hist = gvz.history(period="max")
        if not gvz_hist.empty:
            record("yf_gvz_volatility", "ok", f"^GVZ: {len(gvz_hist)} rows",
                   rows=len(gvz_hist),
                   date_range=f"{gvz_hist.index[0].date()} → {gvz_hist.index[-1].date()}")
        else:
            record("yf_gvz_volatility", "warn", "^GVZ returned empty (may be delisted)")

        # GDX - Gold Miners ETF
        gdx = yf.Ticker("GDX")
        gdx_hist = gdx.history(period="max")
        if not gdx_hist.empty:
            record("yf_gdx_miners", "ok", f"GDX: {len(gdx_hist)} rows",
                   rows=len(gdx_hist),
                   date_range=f"{gdx_hist.index[0].date()} → {gdx_hist.index[-1].date()}")
        else:
            record("yf_gdx_miners", "warn", "GDX returned empty")

        # Gold spot via XAU/USD=X
        xau = yf.Ticker("XAUUSD=X")
        xau_hist = xau.history(period="max")
        if not xau_hist.empty:
            record("yf_xauusd_spot", "ok", f"XAUUSD=X: {len(xau_hist)} rows",
                   rows=len(xau_hist),
                   date_range=f"{xau_hist.index[0].date()} → {xau_hist.index[-1].date()}")
        else:
            record("yf_xauusd_spot", "warn", "XAUUSD=X may not have full history")

    except Exception as e:
        record("yfinance", "fail", f"Error: {e}")


# ── 4. Quandl / NASDAQ Data Link ────────────────────────────────────────
def test_quandl():
    print("\n=== 4. Quandl / NASDAQ Data Link (via API) ===")
    try:
        import requests

        # LBMA Gold Price - free dataset (no API key needed for some)
        # Try free endpoint
        url = "https://data.nasdaq.com/api/v3/datasets/LBMA/GPM.json"
        params = {"limit": 5}
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            cols = data.get("dataset", {}).get("column_names", [])
            rows = data.get("dataset", {}).get("data", [])
            record("quandl_lbma_gold", "ok",
                   f"LBMA/GPM (Gold PM Price): {len(rows)} sample rows, cols={cols[:5]}",
                   data={"columns": cols, "sample": rows[:2]})
        else:
            record("quandl_lbma_gold", "warn", f"HTTP {resp.status_code}: {resp.text[:200]}")

        # Try LBMA/GOLD
        url2 = "https://data.nasdaq.com/api/v3/datasets/LBMA/GOLD.json"
        resp2 = requests.get(url2, params={"limit": 5}, timeout=15)
        if resp2.status_code == 200:
            data2 = resp2.json()
            cols2 = data2.get("dataset", {}).get("column_names", [])
            rows2 = data2.get("dataset", {}).get("data", [])
            record("quandl_lbma_gold2", "ok",
                   f"LBMA/GOLD: {len(rows2)} sample rows, cols={cols2[:5]}",
                   data={"columns": cols2, "sample": rows2[:2]})
        else:
            record("quandl_lbma_gold2", "warn", f"HTTP {resp2.status_code}")

        # Try GLD holdings (SPDR Gold Shares)
        url3 = "https://data.nasdaq.com/api/v3/datasets/COM/GLD_HOLDINGS.json"
        resp3 = requests.get(url3, params={"limit": 5}, timeout=15)
        if resp3.status_code == 200:
            data3 = resp3.json()
            cols3 = data3.get("dataset", {}).get("column_names", [])
            rows3 = data3.get("dataset", {}).get("data", [])
            record("quandl_gld_holdings", "ok",
                   f"COM/GLD_HOLDINGS: {len(rows3)} rows, cols={cols3[:5]}",
                   data={"columns": cols3, "sample": rows3[:2]})
        else:
            record("quandl_gld_holdings", "warn", f"HTTP {resp3.status_code}")

    except Exception as e:
        record("quandl", "fail", f"Error: {e}")


# ── 5. World Gold Council ───────────────────────────────────────────────
def test_world_gold_council():
    print("\n=== 5. World Gold Council Data ===")
    try:
        import requests

        # WGC doesn't have a public API; test if we can scrape demand data
        # Try their market data page
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

        # Check if their gold demand trends page is accessible
        url = "https://www.gold.org/goldhub/data/gold-demand-trends"
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            record("wgc_demand_page", "ok", f"Gold demand trends page accessible (HTTP {resp.status_code})")
        else:
            record("wgc_demand_page", "warn", f"HTTP {resp.status_code}")

        # Try their gold price data (often mirrors LBMA)
        url2 = "https://www.gold.org/goldhub/data/gold-prices"
        resp2 = requests.get(url2, headers=headers, timeout=10)
        if resp2.status_code == 200:
            record("wgc_gold_prices", "ok", "Gold prices page accessible")
        else:
            record("wgc_gold_prices", "warn", f"HTTP {resp2.status_code}")

        # Try their data API (JSON endpoints they use internally)
        url3 = "https://www.gold.org/goldhub/api/gold-prices"
        resp3 = requests.get(url3, headers=headers, timeout=10)
        if resp3.status_code == 200:
            try:
                d = resp3.json()
                record("wgc_api", "ok", f"WGC API returned {len(str(d))} bytes", data={"sample": str(d)[:300]})
            except Exception:
                record("wgc_api", "warn", "WGC API returned non-JSON content")
        else:
            record("wgc_api", "warn", f"WGC API HTTP {resp3.status_code}")

        # Suggest alternatives
        record("wgc_note", "skip",
               "WGC offers PDF/Excel reports (no public API). "
               "Best alternative: use yfinance GLD/IAU holdings + LBMA prices from Quandl.")

    except Exception as e:
        record("world_gold_council", "fail", f"Error: {e}")


# ── 6. ETF Flows (GLD, IAU) ────────────────────────────────────────────
def test_etf_flows():
    print("\n=== 6. ETF Flows (GLD, IAU holdings proxy) ===")
    try:
        import yfinance as yf

        # GLD shares outstanding
        gld = yf.Ticker("GLD")
        try:
            shares = gld.get_shares_full(start="2004-01-01")
            if shares is not None and not shares.empty:
                record("etf_gld_shares", "ok", f"GLD shares outstanding: {len(shares)} rows",
                       rows=len(shares),
                       date_range=f"{shares.index[0].date()} → {shares.index[-1].date()}")
            else:
                record("etf_gld_shares", "warn", "GLD shares data unavailable via yfinance")
        except Exception as e:
            record("etf_gld_shares", "warn", f"GLD shares error: {e}")

        # IAU shares outstanding
        iau = yf.Ticker("IAU")
        try:
            shares_iau = iau.get_shares_full(start="2005-01-01")
            if shares_iau is not None and not shares_iau.empty:
                record("etf_iau_shares", "ok", f"IAU shares outstanding: {len(shares_iau)} rows",
                       rows=len(shares_iau),
                       date_range=f"{shares_iau.index[0].date()} → {shares_iau.index[-1].date()}")
            else:
                record("etf_iau_shares", "warn", "IAU shares data unavailable")
        except Exception as e:
            record("etf_iau_shares", "warn", f"IAU shares error: {e}")

        # GDX (Gold Miners) as proxy for gold equity sentiment
        gdx = yf.Ticker("GDX")
        try:
            gdx_h = gdx.history(period="5y")
            if not gdx_h.empty:
                # Compute rolling correlation with GLD
                gld_h = yf.Ticker("GLD").history(period="5y")
                if not gld_h.empty and len(gld_h) == len(gdx_h):
                    import pandas as pd
                    combined = pd.DataFrame({
                        "gld": gld_h["Close"].values,
                        "gdx": gdx_h["Close"].values
                    })
                    corr = combined["gld"].pct_change().rolling(20).corr(combined["gdx"].pct_change())
                    latest_corr = corr.iloc[-1]
                    record("etf_gdx_correlation", "ok",
                           f"GLD-GDX 20d rolling corr: {latest_corr:.4f}",
                           data={"latest_corr": float(latest_corr)})
                else:
                    record("etf_gdx_correlation", "warn", "GLD/GDX length mismatch")
            else:
                record("etf_gdx_correlation", "warn", "GDX history empty")
        except Exception as e:
            record("etf_gdx_correlation", "warn", f"Error: {e}")

    except Exception as e:
        record("etf_flows", "fail", f"Error: {e}")


# ── 7. Investing.com API (investingpy) ──────────────────────────────────
def test_investing():
    print("\n=== 7. Investing.com (investingpy) ===")
    try:
        import investingpy
        record("investingpy", "ok", "investingpy available")
    except ImportError:
        record("investingpy", "skip",
               "investingpy not installed. "
               "Install via: pip install investingpy. "
               "Alternative: use yfinance GC=F for gold futures data.")


# ── 8. Free API alternatives ────────────────────────────────────────────
def test_free_apis():
    print("\n=== 8. Free API Alternatives ===")
    try:
        import requests

        # 8a. Open Exchange Rates (free tier)
        url = "https://openexchangerates.org/api/latest.json"
        params = {"app_id": "demo"}
        try:
            resp = requests.get(url, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                rates = data.get("rates", {})
                xau = rates.get("XAU")
                record("api_openexchange", "ok",
                       f"Open Exchange Rates: XAU={xau}",
                       data={"xau_rate": xau, "sample_currencies": list(rates.keys())[:10]})
            else:
                record("api_openexchange", "warn", f"HTTP {resp.status_code}")
        except Exception as e:
            record("api_openexchange", "warn", f"Error: {e}")

        # 8b. Alpha Vantage (free key required)
        record("api_alphavantage", "skip",
               "Alpha Vantage: free key at https://www.alphavantage.co/support/#api-key. "
               "Provides: FX_DAILY, CURRENCY_EXCHANGE_RATE for XAU/USD.")

        # 8c. Twelve Data (free tier)
        record("api_twelvedata", "skip",
               "Twelve Data: free tier at https://twelvedata.com/. "
               "Provides XAU/USD real-time and historical.")

        # 8d. CoinGecko (for gold-pegged tokens if relevant)
        try:
            resp_cg = requests.get("https://api.coingecko.com/api/v3/coins/markets",
                                    params={"vs_currency": "usd", "ids": "pax-gold,tether-gold"},
                                    timeout=10)
            if resp_cg.status_code == 200:
                cg_data = resp_cg.json()
                names = [d["name"] for d in cg_data]
                record("api_coingecko_gold_tokens", "ok",
                       f"Gold-backed tokens: {names}",
                       data={d["name"]: d.get("current_price") for d in cg_data})
            else:
                record("api_coingecko_gold_tokens", "warn", f"HTTP {resp_cg.status_code}")
        except Exception as e:
            record("api_coingecko_gold_tokens", "warn", f"Error: {e}")

    except Exception as e:
        record("free_apis", "fail", f"Error: {e}")


# ── 9. Existing FRED data ───────────────────────────────────────────────
def test_existing_fred():
    print("\n=== 9. Existing FRED/Macro Data (in repo) ===")
    try:
        macro_dir = Path("data/macro")
        if macro_dir.exists():
            files = list(macro_dir.glob("*.parquet"))
            import pandas as pd
            summary = {}
            for f in files:
                df = pd.read_parquet(f)
                summary[f.name] = {
                    "rows": len(df),
                    "cols": list(df.columns)[:5],
                    "date_range": f"{df.index.min()} → {df.index.max()}" if hasattr(df.index, 'min') else "N/A",
                }
            record("existing_fred_data", "ok", f"{len(files)} macro parquet files in data/macro/",
                   rows=sum(v["rows"] for v in summary.values()),
                   data=summary)
        else:
            record("existing_fred_data", "warn", "data/macro/ directory not found")
    except Exception as e:
        record("existing_fred_data", "fail", f"Error: {e}")


# ── Main ─────────────────────────────────────────────────────────────────
def main():
    print("=" * 70)
    print("  XAUUSD ALTERNATIVE DATA SOURCES RESEARCH")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)

    test_cot_reports()
    test_mt5()
    test_yfinance()
    test_quandl()
    test_world_gold_council()
    test_etf_flows()
    test_investing()
    test_free_apis()
    test_existing_fred()

    # Save results
    output_path = Path("reports/alternative_data_research.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(RESULTS, f, indent=2, default=str)

    print(f"\n{'=' * 70}")
    print("  SUMMARY")
    print(f"{'=' * 70}")
    ok = sum(1 for v in RESULTS.values() if v["status"] == "ok")
    warn = sum(1 for v in RESULTS.values() if v["status"] == "warn")
    fail = sum(1 for v in RESULTS.values() if v["status"] == "fail")
    skip = sum(1 for v in RESULTS.values() if v["status"] == "skip")
    print(f"  ✓ OK: {ok}  |  △ Warn: {warn}  |  ✗ Fail: {fail}  |  ○ Skip: {skip}")
    print(f"\n  Results saved to: {output_path}")
    print(f"{'=' * 70}")


if __name__ == "__main__":
    main()
