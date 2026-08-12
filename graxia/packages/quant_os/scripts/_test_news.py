import cloudscraper
from bs4 import BeautifulSoup
from pathlib import Path

scraper = cloudscraper.create_scraper()
r = scraper.get("https://www.investing.com/economic-calendar/", timeout=20)
soup = BeautifulSoup(r.text, "html.parser")
tables = soup.find_all("table")
print(f"Tables found: {len(tables)}")
for i, t in enumerate(tables[:5]):
    rows = t.find_all("tr")
    print(f"  Table {i}: {len(rows)} rows, id={t.get('id')}, class={t.get('class')}")

# Look for common calendar selectors
for sel in [".js-event-item", ".eventItem", "tr.event", "[data-event-id]", ".ec-calendar"]:
    els = soup.select(sel)
    print(f"  Selector '{sel}': {len(els)}")

Path("data/news/investing_debug.html").write_text(r.text[:100000], encoding="utf-8")
print("Saved debug snippet")
