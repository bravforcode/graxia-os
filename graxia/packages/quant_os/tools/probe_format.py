"""
Quick probe: what does the model return with think=false?
Tests 3 headlines to see actual output format.
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import time

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"

test_headlines = [
    ("Reuters", "Nvidia beats quarterly revenue estimates on strong AI chip demand"),
    ("CNBC", "Apple launches new iPhone with AI features"),
    ("Bloomberg", "Markets rally on strong jobs data"),
]

for source, title in test_headlines:
    prompt = f'Headline: {source}: {title}\n\nReturn JSON: {{"s":"positive/negative/neutral","i":"high/medium/low","k":"ticker or empty string"}}'

    body = {
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "options": {
            "temperature": 0.05,
            "num_predict": 300,
            "num_ctx": 1024,
        },
    }

    print(f"\n--- {source}: {title[:50]} ---")
    try:
        r = requests.post(OLLAMA_URL, json=body, timeout=120)
        d = r.json()
        resp = d.get("message", {}).get("content", "")
        tokens = d.get("eval_count", 0)
        print(f"Tokens: {tokens}")
        print(f"Full response:\n{resp[:800]}")
        print(f"Response length: {len(resp)} chars")
    except Exception as e:
        print(f"Error: {e}")
    time.sleep(2)
