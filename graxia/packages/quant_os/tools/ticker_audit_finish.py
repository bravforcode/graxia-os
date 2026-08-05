"""Finish last 3 headlines from the audit."""

import json
import os
import re
import subprocess
import sys
import time

sys.stdout.reconfigure(encoding="utf-8")

OLLAMA = r"C:\Users\menum\AppData\Local\Programs\Ollama\ollama.exe"
STATE = os.path.join(os.path.dirname(__file__), "..", "state")

REMAINING = [
    ("Apple suppliers in Asia face production challenges", "AAPL", "ambiguous"),
    ("Chinese EV makers challenge Tesla dominance", "TSLA", "ambiguous"),
    ("Toyota Motor reports record quarterly profit", None, "foreign"),
    ("Samsung Electronics warns on chip demand", None, "foreign"),
]


def run_single(headline):
    prompt = f'Extract the ticker from this headline: "{headline}"\nReturn ONLY a JSON object: {{"k":"TICKER"}} or {{"k":null}}'
    try:
        result = subprocess.run(
            [OLLAMA, "run", "qwen3.5:9b", "--verbose", "false"],
            input=prompt,
            capture_output=True,
            text=True,
            timeout=120,
            encoding="utf-8",
            errors="replace",
        )
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


def extract_ticker(raw):
    try:
        m = re.search(r'\{\s*"k"\s*:\s*"?([^",}]+)"?\s*\}', raw, re.I)
        if m:
            k = m.group(1).strip('"').strip("'")
            if k.lower() in ("null", "none", ""):
                return None
            return k
    except Exception:
        pass
    return None


def normalize(t):
    if t is None:
        return None
    return t.upper().replace("^", "").replace("=X", "").replace("-USD", "").replace("=F", "")


def classify(ext, exp):
    if exp is None and ext is None:
        return "correct_none"
    if exp is not None and ext is None:
        return "no_ticker"
    if exp is None and ext is not None:
        return "false_positive"
    if normalize(ext) == normalize(exp):
        return "valid"
    return "wrong_ticker"


def main():
    # Load existing results
    json_path = os.path.join(STATE, "ticker_audit_results.json")
    if os.path.exists(json_path):
        with open(json_path, encoding="utf-8") as f:
            results = json.load(f)
    else:
        results = []

    # Also load the text log
    txt_path = os.path.join(STATE, "ticker_audit_results.txt")
    with open(txt_path, "a", encoding="utf-8") as f:
        for i, (headline, expected, cat) in enumerate(REMAINING):
            idx = len(results) + 1
            f.write(f"[{idx}/20] {headline[:50]}...\n")
            f.flush()

            raw = run_single(headline)
            ticker = extract_ticker(raw)
            mode = classify(ticker, expected)

            results.append(
                {
                    "headline": headline,
                    "expected": expected,
                    "extracted": ticker,
                    "category": cat,
                    "mode": mode,
                }
            )

            f.write(f"  Expected: {expected}, Got: {ticker}, Mode: {mode}\n")
            f.flush()

            time.sleep(2)

        # Final summary
        f.write("\n" + "=" * 60 + "\n")
        f.write("FINAL RESULTS (20 headlines)\n")
        f.write("=" * 60 + "\n\n")

        total = len(results)
        counts = {}
        for r in results:
            counts[r["mode"]] = counts.get(r["mode"], 0) + 1

        for mode in ["valid", "correct_none", "no_ticker", "wrong_ticker", "false_positive"]:
            c = counts.get(mode, 0)
            f.write(f"  {mode:20s}: {c:2d} / {total} ({c/total*100:.0f}%)\n")

        # Extraction rate for headlines that SHOULD have tickers
        should_have = [r for r in results if r["expected"] is not None]
        did_extract = sum(1 for r in should_have if r["mode"] == "valid")
        f.write(
            f"\nExtraction rate (should have ticker): {did_extract}/{len(should_have)} ({did_extract/len(should_have)*100:.0f}%)\n"
        )

        f.write("\nBy category:\n")
        for cat in ["clear", "none", "ambiguous", "foreign"]:
            items = [r for r in results if r["category"] == cat]
            good = sum(1 for r in items if r["mode"] in ("valid", "correct_none"))
            f.write(f"  {cat:12s}: {good}/{len(items)} correct\n")

        f.write("\nFailure modes for should-have-ticker headlines:\n")
        for r in should_have:
            if r["mode"] != "valid":
                f.write(f"  [{r['mode']}] expected={r['expected']} got={r['extracted']}\n")
                f.write(f"    \"{r['headline'][:60]}\"\n")

    # Save JSON
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Done. Results at {txt_path}")


if __name__ == "__main__":
    main()
