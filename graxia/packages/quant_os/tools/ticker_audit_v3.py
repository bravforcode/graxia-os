"""
Full 20-headline audit with the fixed single-headline daemon prompt.
Tests the exact prompt the daemon will use.
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import contextlib
import json
import time

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"

# 20 test headlines covering all failure modes
HEADLINES = [
    # clear_ticker (10)
    ("Reuters", "Nvidia beats quarterly revenue estimates on strong AI chip demand", "NVDA"),
    ("CNBC", "Apple launches new iPhone with AI features", "AAPL"),
    ("FT", "Tesla cuts prices in China amid competition", "TSLA"),
    ("WSJ", "JPMorgan Chase reports record quarterly profit", "JPM"),
    ("Bloomberg", "Shell Profit Surges to $9.8 Billion on Oil Trading", "SHEL"),
    ("Reuters", "BP to cut 700 jobs as it warns on oil oversupply", "BP"),
    ("Bloomberg", "Goldman Sachs beats earnings estimates on strong trading revenue", "GS"),
    ("CNBC", "Microsoft Azure revenue grows 29% as AI demand accelerates", "MSFT"),
    ("Reuters", "Toyota recalls 1.4 million vehicles over airbag defect", "TM"),
    ("Bloomberg", "Blackstone Said to Buy $25 Billion HSBC Australia Home Loan Portfolio", "BX"),
    # none (5)
    ("Reuters", "Markets rally on strong jobs data", ""),
    ("CNBC", "Consumer confidence rises to 8-month high", ""),
    ("Bloomberg", "Housing starts fall 3.2% in December", ""),
    ("FT", "Manufacturing sector contracts for third straight month", ""),
    ("Reuters", "Economic growth slows to 1.8% annualized pace", ""),
    # ambiguous (3)
    ("Reuters", "Apple, Amazon and Meta all move higher in morning trading", "AAPL"),
    ("CNBC", "Bitcoin jumps above $100,000 for first time", "BTC-USD"),
    ("Bloomberg", "Chinese EV makers gain ground in European markets", ""),
    # foreign_name (2)
    ("Reuters", "Toyota Motor posts record annual profit amid weak yen", "TM"),
    ("FT", "Samsung Electronics warns of chip demand slowdown", "005930.KS"),
]

PROMPT = """Analyze this financial headline. Return ONLY a JSON object.

{source}: {title}

Return: {{"s":"positive/negative/neutral", "i":"high/medium/low", "k":"ticker or empty", "c":"one sentence summary"}}

k: stock ticker. Use general knowledge for well-known companies. If unsure, leave empty.
Common: Shell->SHEL, BP->BP, Apple->AAPL, Nvidia->NVDA, Tesla->TSLA, Microsoft->MSFT, Meta->META, Amazon->AMZN, Google->GOOGL, JPMorgan->JPM, Goldman->GS, Blackstone->BX, Bitcoin->BTC-USD, Gold->GC=F, Oil->CL=F, S&P500->SPX"""

results = {"valid": 0, "correct_none": 0, "no_ticker": 0, "wrong_ticker": 0, "false_positive": 0}
details = []

for i, (source, title, expected) in enumerate(HEADLINES):
    prompt = PROMPT.format(source=source, title=title)
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.05, "num_predict": 150, "num_ctx": 1024},
    }
    try:
        r = requests.post(OLLAMA_URL, json=body, timeout=120)
        d = r.json()
        resp = d.get("message", {}).get("content", "")
        start = resp.find("{")
        end = resp.rfind("}") + 1
        parsed = None
        if start >= 0 and end > start:
            with contextlib.suppress(BaseException):
                parsed = json.loads(resp[start:end])
        ticker = parsed.get("k", "") if parsed else ""
        sentiment = parsed.get("s", "?") if parsed else "?"

        # Classify
        if expected and ticker:
            if expected.upper() in ticker.upper() or ticker.upper() in expected.upper():
                cat = "valid"
            else:
                cat = "wrong_ticker"
        elif expected and not ticker:
            cat = "no_ticker"
        elif not expected and not ticker:
            cat = "correct_none"
        elif not expected and ticker:
            cat = "false_positive"
        else:
            cat = "unknown"

        results[cat] = results.get(cat, 0) + 1
        sym = {"valid": "V", "correct_none": "N", "no_ticker": "X", "wrong_ticker": "W", "false_positive": "F"}.get(
            cat, "?"
        )
        print(f"  [{sym}] {source:10} k={ticker:8} exp={expected:6} | {title[:45]}")
        details.append({"source": source, "title": title, "expected": expected, "got": ticker, "category": cat})
    except Exception as e:
        print(f"  [E] ERROR: {e}")
        results["no_ticker"] = results.get("no_ticker", 0) + 1
    time.sleep(0.5)

# Results
print(f"\n{'='*60}")
print("RESULTS:")
for k, v in results.items():
    print(f"  {k:15}: {v}")
total_with_ticker = sum(1 for d in details if d["expected"])
correct_with_ticker = sum(1 for d in details if d["expected"] and d["category"] == "valid")
if total_with_ticker:
    print(
        f"\nExtraction rate: {correct_with_ticker}/{total_with_ticker} = {100*correct_with_ticker/total_with_ticker:.0f}%"
    )

# Save
with open(r"C:\Users\menum\graxia os\graxia\packages\quant_os\state\ticker_audit_v3.json", "w") as f:
    json.dump(
        {"results": results, "details": details, "extraction_rate": f"{correct_with_ticker}/{total_with_ticker}"},
        f,
        indent=2,
    )
