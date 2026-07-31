"""Test what model actually returns for 5 headlines from the DB."""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import contextlib
import json
import time

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"

test = [
    ("reuters", "Japan's yen jumps 3% as speculation over intervention swirls"),
    ("bloomberg", "Blackstone Said to Buy $25 Billion HSBC Australia Home Loan Portfolio"),
    ("bloomberg", "Shell Profit Surges to $9.8 Billion on Oil Trading and Refining"),
    ("ft", "BP to cut 700 jobs as it warns on oil oversupply"),
    ("cnbc", "Top US science journals more likely to reject paper by Chinese researchers"),
]

PROMPT = """Analyze this financial headline. Return ONLY a JSON object.

{source}: {title}

Return: {{"s":"positive/negative/neutral", "i":"high/medium/low", "k":"ticker or empty", "c":"one sentence summary"}}

k: company stock ticker symbol (e.g. Shell->SHEL, Nvidia->NVDA, Apple->AAPL). Empty if no company/index mentioned."""

for source, title in test:
    prompt = PROMPT.format(source=source, title=title)
    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {"temperature": 0.05, "num_predict": 150, "num_ctx": 1024},
    }
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
    print(f"k={ticker!r:12} | {title[:55]}")
    time.sleep(1)
