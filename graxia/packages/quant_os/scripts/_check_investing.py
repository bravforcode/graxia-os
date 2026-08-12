import cloudscraper
from bs4 import BeautifulSoup

scraper = cloudscraper.create_scraper()
r = scraper.get("https://www.investing.com/economic-calendar/", timeout=20)
soup = BeautifulSoup(r.text, "html.parser")

tables = soup.find_all("table")
table = tables[0]
rows = table.find_all("tr")
print(f"Rows: {len(rows)}")

# Print first row (header)
print(f"Header: {[th.get_text(strip=True) for th in rows[0].find_all('th')]}")

# Print first data row
cols = rows[1].find_all("td")
for i, c in enumerate(cols):
    print(f"  Col {i}: class={c.get('class')}, text='{c.get_text(strip=True)[:80]}'")

# Check for data attributes
print(f"  Data attrs: { {k:v for k,v in cols[0].attrs.items() if k.startswith('data-')} }")
