"""Test exact daemon prompt with these headlines."""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import json

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"

headlines = [
    ("economic_times", "Five months in, the US-Iran war keeps spreading"),
    ("oilprice", "Russia Extends Diesel and Gasoline Export Bans Into 2027"),
]

PROMPT = """Analyze this financial headline. Return ONLY a JSON object.

{source}: {title}

Return: {{"s":"positive/negative/neutral", "i":"high/medium/low", "k":"ticker or empty", "c":"one sentence summary"}}

k: company stock ticker symbol (e.g. Shell->SHEL, Nvidia->NVDA, Apple->AAPL). Empty if no company/index mentioned."""

for source, title in headlines:
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
    print(f"--- {source}: {title[:50]} ---")
    print(f"RAW: {repr(resp)}")
    # Parse
    start = resp.find("{")
    end = resp.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            parsed = json.loads(resp[start:end])
            print(f"PARSED: k={parsed.get('k','?')}")
        except json.JSONDecodeError as e:
            print(f"PARSE ERROR: {e}")
    print()
    import time

    time.sleep(1)
