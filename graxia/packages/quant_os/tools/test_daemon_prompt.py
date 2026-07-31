"""Test the exact daemon prompt with Shell headline."""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"

prompt = """Analyze this financial headline. Return ONLY a JSON object.

bloomberg_markets: Shell Profit Surges to $9.8 Billion on Oil Trading and Refining

Return exactly this format:
{"s":"positive","i":"high","k":"NVDA","c":"one sentence summary"}

Fields: s=sentiment(positive/negative/neutral), i=impact(high/medium/low), k=ticker or empty string, c=summary
Ticker mapping: Apple->AAPL, Nvidia->NVDA, Tesla->TSLA, Microsoft->MSFT, Meta->META, Amazon->AMZN, Google->GOOGL, JPMorgan->JPM, Goldman->GS, Shell->SHEL
If no company or index is mentioned, use "k": ""."""

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
print("RAW:")
print(repr(resp))
print()
print("VISIBLE:")
print(resp)
