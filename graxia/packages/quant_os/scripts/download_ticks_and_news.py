"""
download_ticks_and_news.py — Download tick data + news/macro events

Ticks: from MT5 (last 24h for 6 major symbols)
News: from ForexFactory calendar via cloudscraper
Macro: from Investing.com economic calendar via cloudscraper
"""
import logging
from datetime import datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
TICK_DIR = ROOT / "data" / "ticks"
NEWS_DIR = ROOT / "data" / "news"
TICK_DIR.mkdir(parents=True, exist_ok=True)
NEWS_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)


def download_ticks():
    import MetaTrader5 as mt5
    import pandas as pd

    symbols = ["XAUUSD", "EURUSD", "US30", "BTCUSD", "GBPUSD", "USDJPY"]
    log.info("Initializing MT5 for tick download...")
    if not mt5.initialize():
        log.error(f"MT5 init failed: {mt5.last_error()}")
        return {}

    results = {}
    for sym in symbols:
        try:
            if not mt5.symbol_select(sym, True):
                log.warning(f"{sym}: cannot select")
                continue
            from_time = datetime.now() - timedelta(hours=24)
            ticks = mt5.copy_ticks_from(sym, from_time, 1_000_000, mt5.COPY_TICKS_ALL)
            if ticks is None or len(ticks) == 0:
                log.warning(f"{sym}: no ticks ({mt5.last_error()})")
                results[sym] = 0
                continue
            df = pd.DataFrame(ticks)
            df["time"] = pd.to_datetime(df["time"], unit="s")
            path = TICK_DIR / f"{sym}_ticks_24h.parquet"
            df.to_parquet(path, index=False)
            log.info(f"{sym}: {len(df):,} ticks -> {path.name}")
            results[sym] = len(df)
        except Exception as e:
            log.error(f"{sym}: {e}")
            results[sym] = -1

    mt5.shutdown()
    return results


def download_news():
    import cloudscraper
    from bs4 import BeautifulSoup
    import json

    results = {}
    scraper = cloudscraper.create_scraper()

    # ForexFactory
    try:
        log.info("Fetching ForexFactory calendar via cloudscraper...")
        r = scraper.get("https://www.forexfactory.com/calendar", timeout=20)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            items = soup.select("tr.calendar__row")
            events = []
            for item in items[:100]:
                ev = {
                    "time": item.get("data-date", ""),
                    "currency": item.get("data-currency", ""),
                    "event": item.get("data-event", ""),
                    "impact": item.get("data-impact", ""),
                }
                tds = item.find_all("td")
                if tds:
                    ev["time_text"] = tds[0].get_text(strip=True) if tds else ""
                    ev["currency_text"] = tds[1].get_text(strip=True) if len(tds) > 1 else ""
                    ev["event_text"] = tds[2].get_text(strip=True) if len(tds) > 2 else ""
                events.append(ev)
            path = NEWS_DIR / "forexfactory_calendar.json"
            path.write_text(json.dumps(events, indent=2, ensure_ascii=False))
            log.info(f"ForexFactory: {len(events)} events -> {path.name}")
            results["forexfactory"] = len(events)
        else:
            log.warning(f"ForexFactory: HTTP {r.status_code}")
            results["forexfactory"] = -1
    except Exception as e:
        log.warning(f"ForexFactory: {e}")
        results["forexfactory"] = -1

    # Investing.com
    try:
        log.info("Fetching Investing.com calendar via cloudscraper...")
        r = scraper.get("https://www.investing.com/economic-calendar/", timeout=20)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, "html.parser")
            tables = soup.find_all("table")
            events = []
            if tables:
                rows = tables[0].find_all("tr")
                for row in rows[1:]:
                    tds = row.find_all("td")
                    if len(tds) == 1:
                        continue
                    if len(tds) >= 8:
                        ev = {
                            "time": tds[0].get_text(strip=True),
                            "currency": tds[2].get_text(strip=True),
                            "event": tds[3].get_text(strip=True),
                            "importance": tds[4].get_text(strip=True) if tds[4].get_text(strip=True) else "",
                            "actual": tds[5].get_text(strip=True),
                            "forecast": tds[6].get_text(strip=True),
                            "previous": tds[7].get_text(strip=True),
                        }
                        events.append(ev)
            path = NEWS_DIR / "investing_calendar.json"
            path.write_text(json.dumps(events, indent=2, ensure_ascii=False))
            log.info(f"Investing.com: {len(events)} events -> {path.name}")
            results["investing"] = len(events)
        else:
            log.warning(f"Investing.com: HTTP {r.status_code}")
            results["investing"] = -1
    except Exception as e:
        log.warning(f"Investing.com: {e}")
        results["investing"] = -1

    return results


def main():
    from datetime import datetime
    log.info("═══ TICK & NEWS DOWNLOAD ═══")
    t0 = datetime.now()

    ticks = download_ticks()
    total_ticks = sum(v for v in ticks.values() if v > 0)
    tick_syms = sum(1 for v in ticks.values() if v > 0)
    log.info(f"Ticks: {total_ticks:,} total from {tick_syms} symbols")

    news = download_news()
    log.info(f"News sources: {news}")

    elapsed = (datetime.now() - t0).total_seconds()
    log.info(f"Done in {elapsed:.0f}s")
    log.info(f"Ticks in: {TICK_DIR}")
    log.info(f"News in: {NEWS_DIR}")

    return {"ticks": ticks, "news": news, "elapsed_seconds": elapsed}


if __name__ == "__main__":
    main()
