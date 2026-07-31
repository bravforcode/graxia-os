"""Compile full audit results from text log."""

import json
import os

STATE = os.path.join(os.path.dirname(__file__), "..", "state")

# Manually compile from text log (all 20 results)
results = [
    # Clear (10)
    {
        "headline": "Apple reported record iPhone sales",
        "expected": "AAPL",
        "extracted": None,
        "category": "clear",
        "mode": "no_ticker",
    },
    {
        "headline": "Tesla stock drops after delivery miss",
        "expected": "TSLA",
        "extracted": "TICKER",
        "category": "clear",
        "mode": "wrong_ticker",
    },
    {
        "headline": "NVIDIA shares surge on AI chip demand",
        "expected": "NVDA",
        "extracted": "NVDA",
        "category": "clear",
        "mode": "valid",
    },
    {
        "headline": "Bitcoin drops below 60000 support level",
        "expected": "BTC-USD",
        "extracted": None,
        "category": "clear",
        "mode": "no_ticker",
    },
    {
        "headline": "Microsoft Azure revenue beats estimates",
        "expected": "MSFT",
        "extracted": "MSFT",
        "category": "clear",
        "mode": "valid",
    },
    {
        "headline": "Amazon Web Services grows 20 percent year over year",
        "expected": "AMZN",
        "extracted": None,
        "category": "clear",
        "mode": "no_ticker",
    },
    {
        "headline": "Meta Platforms reports declining ad revenue",
        "expected": "META",
        "extracted": None,
        "category": "clear",
        "mode": "no_ticker",
    },
    {
        "headline": "AMD launches new AI chip to challenge NVIDIA",
        "expected": "AMD",
        "extracted": None,
        "category": "clear",
        "mode": "no_ticker",
    },
    {
        "headline": "JPMorgan Chase raises interest rate outlook",
        "expected": "JPM",
        "extracted": None,
        "category": "clear",
        "mode": "no_ticker",
    },
    {
        "headline": "Gold reaches all-time high amid inflation fears",
        "expected": "GC=F",
        "extracted": None,
        "category": "clear",
        "mode": "no_ticker",
    },
    # None (5)
    {
        "headline": "Markets react to unexpected inflation data",
        "expected": None,
        "extracted": None,
        "category": "none",
        "mode": "correct_none",
    },
    {
        "headline": "Consumer confidence index falls to 12-month low",
        "expected": None,
        "extracted": None,
        "category": "none",
        "mode": "correct_none",
    },
    {
        "headline": "Economic growth slows in third quarter",
        "expected": None,
        "extracted": None,
        "category": "none",
        "mode": "correct_none",
    },
    {
        "headline": "Housing market shows signs of cooling",
        "expected": None,
        "extracted": None,
        "category": "none",
        "mode": "correct_none",
    },
    {
        "headline": "Manufacturing sector contracts for second month",
        "expected": None,
        "extracted": None,
        "category": "none",
        "mode": "correct_none",
    },
    # Ambiguous (3)
    {
        "headline": "Amazon delivery drivers strike affects holiday shipping",
        "expected": "AMZN",
        "extracted": "AMZN",
        "category": "ambiguous",
        "mode": "valid",
    },
    {
        "headline": "Apple suppliers in Asia face production challenges",
        "expected": "AAPL",
        "extracted": "AAPL",
        "category": "ambiguous",
        "mode": "valid",
    },
    {
        "headline": "Chinese EV makers challenge Tesla dominance",
        "expected": "TSLA",
        "extracted": None,
        "category": "ambiguous",
        "mode": "no_ticker",
    },
    # Foreign (2)
    {
        "headline": "Toyota Motor reports record quarterly profit",
        "expected": None,
        "extracted": None,
        "category": "foreign",
        "mode": "correct_none",
    },
    {
        "headline": "Samsung Electronics warns on chip demand",
        "expected": None,
        "extracted": None,
        "category": "foreign",
        "mode": "correct_none",
    },
]

# Save JSON
json_path = os.path.join(STATE, "ticker_audit_results.json")
with open(json_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, ensure_ascii=False)

# Compute stats
total = len(results)
counts = {}
for r in results:
    counts[r["mode"]] = counts.get(r["mode"], 0) + 1

should_have = [r for r in results if r["expected"] is not None]
did_extract = sum(1 for r in should_have if r["mode"] == "valid")

print("=" * 60)
print("TICKER EXTRACTION AUDIT - FINAL RESULTS (20 headlines)")
print("=" * 60)
print()
print("FAILURE MODE BREAKDOWN:")
for mode in ["valid", "correct_none", "no_ticker", "wrong_ticker", "false_positive"]:
    c = counts.get(mode, 0)
    print(f"  {mode:20s}: {c:2d} / {total} ({c/total*100:.0f}%)")

print()
print("EXTRACTION RATE (headlines that SHOULD have tickers):")
print(f"  {did_extract}/{len(should_have)} ({did_extract/len(should_have)*100:.0f}%)")

print()
print("BY CATEGORY:")
for cat in ["clear", "none", "ambiguous", "foreign"]:
    items = [r for r in results if r["category"] == cat]
    good = sum(1 for r in items if r["mode"] in ("valid", "correct_none"))
    print(f"  {cat:12s}: {good}/{len(items)} correct")

print()
print("FAILURE MODE ANALYSIS:")
print("  no_ticker (8 cases): LLM returns thinking but no parseable JSON ticker")
print("  wrong_ticker (1 case): Tesla → returned literal 'TICKER' from prompt template")
print()
print("ROOT CAUSE: Model's thinking output overwhelms the JSON response.")
print("The model correctly identifies the company but the JSON extraction")
print("from its verbose thinking output fails.")
