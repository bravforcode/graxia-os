"""
Ticker Extraction Audit
=======================
Measure actual extraction rate on a sample of real headlines.
Separate failure modes:
  - no_ticker: model returned empty or no ticker found
  - wrong_ticker: extracted ticker doesn't match the entity
  - ambiguous: multiple valid candidates, unclear which is correct
  - valid: correct ticker extracted

Run: python tools/ticker_extraction_audit.py
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.stdout.reconfigure(encoding="utf-8")

# Real headlines from our feeds - diverse sources, topics, ambiguity levels
AUDIT_HEADLINES = [
    # Clear single-ticker headlines (should extract correctly)
    ("Apple reported record iPhone sales", "AAPL", "clear"),
    ("Tesla stock drops after delivery miss", "TSLA", "clear"),
    ("Microsoft Azure revenue beats estimates", "MSFT", "clear"),
    ("NVIDIA shares surge on AI chip demand", "NVDA", "clear"),
    ("Amazon Web Services grows 20% year over year", "AMZN", "clear"),
    ("Meta Platforms reports declining ad revenue", "META", "clear"),
    ("Google parent Alphabet faces antitrust ruling", "GOOGL", "clear"),
    ("Boeing delivers 50 aircraft in November", "BA", "clear"),
    ("JPMorgan Chase raises interest rate outlook", "JPM", "clear"),
    ("Goldman Sachs cuts Apple price target", "GS", "clear"),
    ("Bitcoin drops below 60000 support level", "BTC-USD", "clear"),
    ("Ethereum network activity hits new highs", "ETH-USD", "clear"),
    ("Rivian Automotive shares fall on production cut", "RIVN", "clear"),
    ("Palantir Technologies wins defense contract", "PLTR", "clear"),
    ("CrowdStrike reports cybersecurity revenue growth", "CRWD", "clear"),
    ("AMD launches new AI chip to challenge NVIDIA", "AMD", "clear"),
    ("Intel foundry business shows signs of recovery", "INTC", "clear"),
    ("Salesforce completes Slack integration", "CRM", "clear"),
    ("Adobe releases new AI creative tools", "ADBE", "clear"),
    ("Netflix subscriber growth exceeds forecasts", "NFLX", "clear"),
    # Multi-ticker headlines (should pick the primary subject)
    ("Oil prices rise as OPEC meets, boosting Chevron and Exxon", "CL=F", "clear"),
    ("Fed rate decision impacts both banks and tech stocks", "SPX", "clear"),
    ("S&P 500 reaches new all-time high", "^GSPC", "clear"),
    ("Dow Jones Industrial Average closes above 40000", "^DJI", "clear"),
    ("NASDAQ composite hits record on tech rally", "^IXIC", "clear"),
    ("Oil prices surge on Middle East tensions", "CL=F", "clear"),
    ("Gold reaches all-time high amid inflation fears", "GC=F", "clear"),
    ("Copper prices drop on China demand concerns", "HG=F", "clear"),
    ("EUR/USD falls on ECB policy shift", "EURUSD=X", "clear"),
    ("USD/JPY rises on Bank of Japan intervention", "USDJPY=X", "clear"),
    ("Treasury yields surge on inflation data", "^TNX", "clear"),
    ("Apple and Microsoft lead tech rally", "AAPL", "clear"),
    ("Tesla and Rivian move on EV news", "TSLA", "clear"),
    ("NVIDIA and AMD gain on AI momentum", "NVDA", "clear"),
    ("Oil and gas stocks rally on crude surge", "XLE", "clear"),
    # No-ticker headlines (general market commentary)
    ("Markets react to unexpected inflation data", None, "none"),
    ("Investors remain cautious amid global uncertainty", None, "none"),
    ("Economic growth slows in third quarter", None, "none"),
    ("Consumer confidence index falls to 12-month low", None, "none"),
    ("Housing market shows signs of cooling", None, "none"),
    ("Trade deficit widens on strong dollar", None, "none"),
    ("Manufacturing sector contracts for second month", None, "none"),
    ("Retail sales disappoint during holiday season", None, "none"),
    ("Unemployment claims rise unexpectedly", None, "none"),
    ("GDP growth revised down to 1.8 percent", None, "none"),
    ("Inflation expectations increase among consumers", None, "none"),
    ("Business investment declines in equipment", None, "none"),
    ("Government shutdown threatens economic recovery", None, "none"),
    ("Central bank signals pause in rate hikes", None, "none"),
    ("Credit conditions tighten for small businesses", None, "none"),
    ("Supply chain bottlenecks persist across industries", None, "none"),
    ("Consumer spending slows amid rising costs", None, "none"),
    ("Labor market shows mixed signals", None, "none"),
    ("Global recession fears intensify", None, "none"),
    ("Markets digest latest policy announcements", None, "none"),
    # Ambiguous headlines (multiple valid interpretations)
    ("Amazon delivery drivers strike affects holiday shipping", "AMZN", "ambiguous"),
    ("Apple suppliers in Asia face production challenges", "AAPL", "ambiguous"),
    ("Microsoft cloud competitors gain market share", "MSFT", "ambiguous"),
    ("Chinese EV makers challenge Tesla dominance", "TSLA", "ambiguous"),
    ("Google AI division faces regulatory scrutiny", "GOOGL", "ambiguous"),
    ("Oil producers cut output as demand weakens", "CL=F", "ambiguous"),
    ("Bank of Japan policy change impacts global markets", "^N225", "ambiguous"),
    ("European auto stocks fall on emission rules", "^STOXX50E", "ambiguous"),
    ("Tech giants face new antitrust legislation", "QQQ", "ambiguous"),
    ("Semiconductor shortage eases for automakers", "SOXX", "ambiguous"),
    # Foreign company headlines (no US ticker)
    ("Toyota Motor reports record quarterly profit", None, "foreign"),
    ("Samsung Electronics warns on chip demand", None, "foreign"),
    ("Nestle raises prices to offset cost pressures", None, "foreign"),
    ("HSBC profits beat expectations on interest income", None, "foreign"),
    ("Toyota shares jump on hybrid demand surge", None, "foreign"),
    ("TSMC expands production capacity in Arizona", None, "foreign"),
    ("Nestle sells Russian business at loss", None, "foreign"),
    ("Samsung unveils new foldable phone lineup", None, "foreign"),
    ("HSBC pivots to Asia strategy", None, "foreign"),
    ("Toyota leads EV transition in Japan", None, "foreign"),
]


def extract_tickers_with_llm(headlines_batch):
    """Use LLM to extract tickers from headlines. Returns list of (headline, ticker_result, confidence)."""
    import subprocess

    # Build prompt
    prompt_lines = [
        "Extract the primary stock/crypto/commodity ticker symbol from each headline.",
        'Return JSON array: [{"s":"headline","k":"TICKER"}]',
        "If no specific ticker, use k=null.",
        "Use standard US tickers: AAPL, MSFT, NVDA, TSLA, AMZN, META, GOOGL, BTC-USD, ETH-USD, CL=F, GC=F, ^GSPC, ^DJI, ^IXIC.",
        "",
        "Headlines:",
    ]
    for i, h in enumerate(headlines_batch):
        prompt_lines.append(f"{i+1}. {h}")

    prompt = "\n".join(prompt_lines)

    try:
        result = subprocess.run(
            [
                "C:\\Users\\menum\\AppData\\Local\\Programs\\Ollama\\ollama.exe",
                "run",
                "qwen3.5:9b",
                "--verbose",
                "false",
            ],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=300,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        print("  [TIMEOUT on batch]")
        return "[]"
    except Exception as e:
        print(f"  [ERROR: {e}]")
        return "[]"


def parse_extraction_result(llm_output):
    """Parse LLM output into list of (headline, extracted_ticker)."""
    import re

    # Try JSON parse
    try:
        clean = llm_output.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        data = json.loads(clean)
        if isinstance(data, list):
            results = []
            for item in data:
                s = item.get("s", "")
                k = item.get("k", None)
                # Clean ticker
                if k and k.lower() in ("null", "none", ""):
                    k = None
                results.append((s, k))
            return results
    except (json.JSONDecodeError, KeyError):
        pass

    # Fallback: regex extraction
    results = []
    pattern = r'"s"\s*:\s*"([^"]+)"\s*,\s*"k"\s*:\s*"?([^",}]+)"?'
    matches = re.findall(pattern, llm_output, re.IGNORECASE)
    for s, k in matches:
        if k.lower() in ("null", "none"):
            k = None
        results.append((s, k))

    return results


def classify_result(extracted_ticker, expected_ticker, headline):
    """Classify extraction result into failure mode."""
    # If no ticker expected and none found
    if expected_ticker is None and extracted_ticker is None:
        return "correct_none"

    # If ticker expected but none found
    if expected_ticker is not None and extracted_ticker is None:
        return "no_ticker"

    # If no ticker expected but one found
    if expected_ticker is None and extracted_ticker is not None:
        return "false_positive"

    # Normalize tickers for comparison
    def normalize(t):
        return t.upper().replace("^", "").replace("=X", "").replace("-USD", "").replace("=F", "")

    # If ticker matches
    if normalize(extracted_ticker) == normalize(expected_ticker):
        return "valid"

    # Check if it's a plausible alternative (e.g., GOOGL vs GOOG)
    # For now, just mark as wrong
    return "wrong_ticker"


def main():
    print("=" * 60)
    print("TICKER EXTRACTION AUDIT")
    print("=" * 60)
    print(f"Headlines to test: {len(AUDIT_HEADLINES)}")
    print()

    # Run in batches of 5
    all_results = []
    batch_size = 5

    for i in range(0, len(AUDIT_HEADLINES), batch_size):
        batch = AUDIT_HEADLINES[i : i + batch_size]
        headlines = [h[0] for h in batch]

        print(f"Batch {i // batch_size + 1}/{(len(AUDIT_HEADLINES) + batch_size - 1) // batch_size}...")
        llm_output = extract_tickers_with_llm(headlines)

        # Parse results
        parsed = parse_extraction_result(llm_output)

        # Classify each result
        for j, (headline, expected_ticker, category) in enumerate(batch):
            extracted_ticker = None
            if j < len(parsed):
                _, extracted_ticker = parsed[j]

            failure_mode = classify_result(extracted_ticker, expected_ticker, headline)

            all_results.append(
                {
                    "headline": headline,
                    "expected": expected_ticker,
                    "extracted": extracted_ticker,
                    "category": category,
                    "failure_mode": failure_mode,
                }
            )

        # Small delay between batches
        time.sleep(2)

    # Print results
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print()

    # Overall stats
    total = len(all_results)
    valid = sum(1 for r in all_results if r["failure_mode"] == "valid")
    no_ticker = sum(1 for r in all_results if r["failure_mode"] == "no_ticker")
    wrong_ticker = sum(1 for r in all_results if r["failure_mode"] == "wrong_ticker")
    false_positive = sum(1 for r in all_results if r["failure_mode"] == "false_positive")
    correct_none = sum(1 for r in all_results if r["failure_mode"] == "correct_none")

    print(f"TOTAL HEADLINES: {total}")
    print()
    print("FAILURE MODE BREAKDOWN:")
    print(f"  valid (correct ticker):     {valid:3d} ({valid/total*100:.1f}%)")
    print(f"  no_ticker (expected but missing): {no_ticker:3d} ({no_ticker/total*100:.1f}%)")
    print(f"  wrong_ticker (extracted but wrong): {wrong_ticker:3d} ({wrong_ticker/total*100:.1f}%)")
    print(f"  false_positive (found when none expected): {false_positive:3d} ({false_positive/total*100:.1f}%)")
    print(f"  correct_none (correctly no ticker): {correct_none:3d} ({correct_none/total*100:.1f}%)")
    print()

    # By category
    for cat in ["clear", "none", "ambiguous", "foreign"]:
        cat_results = [r for r in all_results if r["category"] == cat]
        cat_valid = sum(1 for r in cat_results if r["failure_mode"] in ("valid", "correct_none"))
        cat_total = len(cat_results)
        if cat_total > 0:
            print(f"  {cat:12s}: {cat_valid}/{cat_total} correct ({cat_valid/cat_total*100:.1f}%)")

    print()
    print("=" * 60)
    print("DETAILED RESULTS")
    print("=" * 60)
    print()

    # Show failures
    print("FAILURES:")
    for r in all_results:
        if r["failure_mode"] not in ("valid", "correct_none"):
            print(f"  [{r['failure_mode']}]")
            print(f"    Headline: {r['headline'][:70]}...")
            print(f"    Expected: {r['expected']}")
            print(f"    Got:      {r['extracted']}")
            print()

    # Save full results
    output_path = os.path.join(os.path.dirname(__file__), "..", "state", "ticker_audit_results.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    print(f"Full results saved to: {output_path}")


if __name__ == "__main__":
    main()
