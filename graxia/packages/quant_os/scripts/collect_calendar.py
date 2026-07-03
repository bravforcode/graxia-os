#!/usr/bin/env python3
"""
Economic Calendar Collector — Runs daily to collect calendar data.
Saves to data/news/economic_calendar.json
"""
import json
import urllib.request
from pathlib import Path

BASE = Path(__file__).parent.parent
OUTPUT = BASE / "data" / "news" / "economic_calendar.json"

def fetch_calendar():
    """Fetch current week's calendar from FairEconomy."""
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        print("Failed to fetch: %s" % str(e))
        return []

def merge_events(existing, new):
    """Merge new events into existing, avoiding duplicates."""
    seen = set()
    for e in existing:
        key = "%s_%s_%s" % (e.get("title", ""), e.get("date", ""), e.get("currency", ""))
        seen.add(key)
    
    merged = list(existing)
    added = 0
    for e in new:
        key = "%s_%s_%s" % (e.get("title", ""), e.get("date", ""), e.get("currency", ""))
        if key not in seen:
            merged.append(e)
            seen.add(key)
            added += 1
    
    return merged, added

def main():
    print("Collecting economic calendar data...")
    
    # Load existing
    existing = []
    if OUTPUT.exists():
        with open(OUTPUT) as f:
            existing = json.load(f)
        print("Existing events: %d" % len(existing))
    
    # Fetch new
    new_events = fetch_calendar()
    if not new_events:
        print("No new events fetched")
        return
    
    print("Fetched events: %d" % len(new_events))
    
    # Merge
    merged, added = merge_events(existing, new_events)
    print("Merged: %d total, %d new" % (len(merged), added))
    
    # Save
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT, "w") as f:
        json.dump(merged, f, indent=2)
    
    print("Saved to: %s" % OUTPUT)
    
    # Stats
    high = sum(1 for e in merged if e.get("impact") == "High")
    medium = sum(1 for e in merged if e.get("impact") == "Medium")
    low = sum(1 for e in merged if e.get("impact") == "Low")
    print("By impact: High=%d, Medium=%d, Low=%d" % (high, medium, low))

if __name__ == "__main__":
    main()
