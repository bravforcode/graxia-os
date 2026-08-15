"""Split sacred holdout from RYDC data."""
import csv
from datetime import date, datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = PROJECT_ROOT / "data" / "rydc" / "rydc_daily.csv"
HOLDOUT_FILE = PROJECT_ROOT / "data" / "sacred_holdout" / "holdout.csv"
RESEARCH_FILE = PROJECT_ROOT / "data" / "rydc" / "rydc_research.csv"

with open(DATA_FILE) as f:
    reader = csv.DictReader(f)
    rows = list(reader)

print(f"Total rows: {len(rows)}")
print(f"First date: {rows[0]['date']}")
print(f"Last date: {rows[-1]['date']}")

# Sacred holdout: last 12 months (2025-07-01 to 2026-07-01)
last_date = datetime.strptime(rows[-1]["date"], "%Y-%m-%d").date()
holdout_start = date(last_date.year - 1, last_date.month, 1)

holdout = [r for r in rows if datetime.strptime(r["date"], "%Y-%m-%d").date() >= holdout_start]
research = [r for r in rows if datetime.strptime(r["date"], "%Y-%m-%d").date() < holdout_start]

print(f"\nHoldout period: {holdout_start} to {last_date}")
print(f"Research rows: {len(research)} ({research[0]['date']} to {research[-1]['date']})")
print(f"Holdout rows: {len(holdout)} ({holdout[0]['date']} to {holdout[-1]['date']})")

# Write research file (replace original)
with open(RESEARCH_FILE, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["date", "xau_close", "xau_high", "xau_low", "dxy_close", "dfii10"])
    for r in research:
        writer.writerow([r["date"], r["xau_close"], r["xau_high"], r["xau_low"], r["dxy_close"], r["dfii10"]])

# Write holdout to separate directory
HOLDOUT_FILE.parent.mkdir(parents=True, exist_ok=True)
with open(HOLDOUT_FILE, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["date", "xau_close", "xau_high", "xau_low", "dxy_close", "dfii10"])
    for r in holdout:
        writer.writerow([r["date"], r["xau_close"], r["xau_high"], r["xau_low"], r["dxy_close"], r["dfii10"]])

print(f"\nResearch data: {RESEARCH_FILE}")
print(f"Sacred holdout: {HOLDOUT_FILE}")
print("\n!!! DO NOT TOUCH HOLDOUT FILE UNTIL PHASE 4.5 !!!")
