"""Test: does the model know tickers WITHOUT a mapping list?"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import contextlib
import json

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"

test_headlines = [
    ("bloomberg", "Shell Profit Surges to $9.8 Billion on Oil Trading"),
    ("reuters", "Japan's yen jumps 3% as speculation over intervention swirls"),
    ("ft", "BP to cut 700 jobs as it warns on oil oversupply"),
    ("cnbc", "Apple launches new iPhone with AI features"),
    ("wsj", "JPMorgan Chase reports record quarterly profit"),
    ("bloomberg", "Blackstone Said to Buy $25 Billion HSBC Australia Home Loan Portfolio"),
    ("reuters", "Coal Falls Below 50% Of China's Power Mix For First Time"),
]

# Minimal prompt - no mapping, let model use general knowledge
prompt_template = """Analyze this financial headline. Return ONLY a JSON object.

{source}: {title}

Return: {{"s":"positive/negative/neutral", "i":"high/medium/low", "k":"ticker symbol or empty"}}

k: company stock ticker (e.g. Shell->SHEL, BP->BP, Apple->AAPL). Empty if no company/index mentioned."""

for source, title in test_headlines:
    prompt = prompt_template.format(source=source, title=title)
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.05, "num_predict": 100, "num_ctx": 1024},
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
        ticker = parsed.get("k", "?") if parsed else "?"
        print(f"  {source:10} | k={ticker:8} | {title[:50]}")
    except Exception as e:
        print(f"  ERROR: {e}")
    import time

    time.sleep(1)
