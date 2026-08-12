import cloudscraper
from bs4 import BeautifulSoup
from pathlib import Path
import json

scraper = cloudscraper.create_scraper()
r = scraper.get("https://www.investing.com/economic-calendar/", timeout=20)
soup = BeautifulSoup(r.text, "html.parser")

tables = soup.find_all("table")
table = tables[0]
rows = table.find_all("tr")

# Print all data rows with their TD count
data_rows = []
for i, row in enumerate(rows):
    tds = row.find_all("td")
    data_rows.append((i, tds))
    if i > 0 and i < 6:
        print(f"Row {i}: {len(tds)} tds")
        for j, td in enumerate(tds):
            txt = td.get_text(strip=True)[:50]
            print(f"  TD {j}: '{txt}'")

# Now try to extract properly
events = []
for row in rows[1:]:
    tds = row.find_all("td")
    if len(tds) == 1:
        # Date separator
        continue
    if len(tds) >= 7:
        ev = {
            "time": tds[0].get_text(strip=True),
            "currency": tds[1].get_text(strip=True),
            "event": tds[2].get_text(strip=True),
            "importance": tds[3].get_text(strip=True) if tds[3].get_text(strip=True) else "",
            "actual": tds[4].get_text(strip=True),
            "forecast": tds[5].get_text(strip=True),
            "previous": tds[6].get_text(strip=True),
        }
        events.append(ev)

path = Path("data/news/investing_calendar.json")
path.write_text(json.dumps(events, indent=2, ensure_ascii=False))
print(f"\nExtracted {len(events)} events -> {path.name}")
for ev in events[:5]:
    print(f"  {ev['time']} | {ev['currency']} | {ev['event']} | {ev['importance']}")
