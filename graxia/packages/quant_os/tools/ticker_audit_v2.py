import json
import os
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

OLLAMA = r"C:\Users\menum\AppData\Local\Programs\Ollama\ollama.exe"

# Test headlines: (headline, expected_ticker_or_None, category)
TESTS = [
    # Clear single-ticker (10)
    ("Apple reported record iPhone sales", "AAPL", "clear"),
    ("Tesla stock drops after delivery miss", "TSLA", "clear"),
    ("NVIDIA shares surge on AI chip demand", "NVDA", "clear"),
    ("Bitcoin drops below 60000 support level", "BTC-USD", "clear"),
    ("Microsoft Azure revenue beats estimates", "MSFT", "clear"),
    ("Amazon Web Services grows 20 percent year over year", "AMZN", "clear"),
    ("Meta Platforms reports declining ad revenue", "META", "clear"),
    ("AMD launches new AI chip to challenge NVIDIA", "AMD", "clear"),
    ("JPMorgan Chase raises interest rate outlook", "JPM", "clear"),
    ("Gold reaches all-time high amid inflation fears", "GC=F", "clear"),
    # No-ticker / general commentary (5)
    ("Markets react to unexpected inflation data", None, "none"),
    ("Consumer confidence index falls to 12-month low", None, "none"),
    ("Economic growth slows in third quarter", None, "none"),
    ("Housing market shows signs of cooling", None, "none"),
    ("Manufacturing sector contracts for second month", None, "none"),
    # Ambiguous (3)
    ("Amazon delivery drivers strike affects holiday shipping", "AMZN", "ambiguous"),
    ("Apple suppliers in Asia face production challenges", "AAPL", "ambiguous"),
    ("Chinese EV makers challenge Tesla dominance", "TSLA", "ambiguous"),
    # Foreign / no US ticker (2)
    ("Toyota Motor reports record quarterly profit", None, "foreign"),
    ("Samsung Electronics warns on chip demand", None, "foreign"),
]


def run_llm(headlines):
    prompt = "Extract the primary ticker from each headline.\n"
    prompt += 'Return JSON array: [{"s":"headline","k":"TICKER"}]\n'
    prompt += "If no specific ticker, use k=null.\n"
    prompt += "Standard tickers: AAPL, MSFT, NVDA, TSLA, AMZN, META, GOOGL, BTC-USD, ETH-USD, CL=F, GC=F, ^GSPC, ^DJI, ^IXIC.\n\n"
    prompt += "Headlines:\n"
    for i, h in enumerate(headlines, 1):
        prompt += f"{i}. {h}\n"

    try:
        result = subprocess.run(
            [OLLAMA, "run", "qwen3.5:9b", "--verbose", "false"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=180,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def parse_output(raw):
    import re

    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        data = json.loads(clean)
        if isinstance(data, list):
            return [(item.get("s", ""), item.get("k")) for item in data]
    except Exception:
        pass

    results = []
    for m in re.finditer(r'"s"\s*:\s*"([^"]+)"\s*,\s*"k"\s*:\s*"?([^",}]+)"?', raw, re.I):
        s, k = m.group(1), m.group(2)
        if k.lower() in ("null", "none"):
            k = None
        results.append((s, k))
    return results


def normalize(t):
    if t is None:
        return None
    return t.upper().replace("^", "").replace("=X", "").replace("-USD", "").replace("=F", "")


def classify(extracted, expected):
    if expected is None and extracted is None:
        return "correct_none"
    if expected is not None and extracted is None:
        return "no_ticker"
    if expected is None and extracted is not None:
        return "false_positive"
    if normalize(extracted) == normalize(expected):
        return "valid"
    return "wrong_ticker"


def main():
    log = []
    log.append("TICKER EXTRACTION AUDIT (20 headlines)")
    log.append("=" * 60)

    all_results = []

    # Run in 4 batches of 5
    for i in range(0, len(TESTS), 5):
        batch = TESTS[i : i + 5]
        headlines = [h[0] for h in batch]
        batch_num = i // 5 + 1
        log.append(f"\nBatch {batch_num}/4...")

        raw = run_llm(headlines)
        log.append(f"Raw: {raw[:300]}")

        parsed = parse_output(raw)
        log.append(f"Parsed count: {len(parsed)}")

        for j, (headline, expected, cat) in enumerate(batch):
            ext = None
            if j < len(parsed):
                ext = parsed[j][1]
            mode = classify(ext, expected)
            all_results.append(
                {
                    "headline": headline[:60],
                    "expected": expected,
                    "extracted": ext,
                    "category": cat,
                    "mode": mode,
                }
            )

        time.sleep(3)

    # Summary
    log.append("\n" + "=" * 60)
    log.append("RESULTS")
    log.append("=" * 60)

    total = len(all_results)
    counts = {}
    for r in all_results:
        counts[r["mode"]] = counts.get(r["mode"], 0) + 1

    for mode in ["valid", "correct_none", "no_ticker", "wrong_ticker", "false_positive"]:
        c = counts.get(mode, 0)
        log.append(f"  {mode:20s}: {c:2d} / {total} ({c/total*100:.0f}%)")

    # By category
    log.append("\nBy category:")
    for cat in ["clear", "none", "ambiguous", "foreign"]:
        items = [r for r in all_results if r["category"] == cat]
        good = sum(1 for r in items if r["mode"] in ("valid", "correct_none"))
        log.append(f"  {cat:12s}: {good}/{len(items)} correct")

    # Failures
    log.append("\nFailures:")
    for r in all_results:
        if r["mode"] not in ("valid", "correct_none"):
            log.append(f"  [{r['mode']}] expected={r['expected']} got={r['extracted']}")
            log.append(f"    \"{r['headline']}\"")

    # Write to file
    out_path = os.path.join(os.path.dirname(__file__), "..", "state", "ticker_audit_results.txt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(log))

    # Also print
    for line in log:
        print(line)

    # Save JSON
    json_path = os.path.join(os.path.dirname(__file__), "..", "state", "ticker_audit_results.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    main()
