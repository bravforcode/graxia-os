"""Test exact daemon prompt with Microsoft headline."""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import json

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"

prompt = """Analyze this financial headline. Return ONLY a JSON object.

bloomberg_markets: Microsoft Eyes History With $490 Billion Pop in Market Value

Return: {{"s":"positive/negative/neutral", "i":"high/medium/low", "k":"ticker or empty", "c":"one sentence summary"}}

k: stock ticker. Use general knowledge for well-known companies. If unsure, leave empty.
Common: Shell->SHEL, BP->BP, Apple->AAPL, Nvidia->NVDA, Tesla->TSLA, Microsoft->MSFT, Meta->META, Amazon->AMZN, Google->GOOGL, JPMorgan->JPM, Goldman->GS, Blackstone->BX, Bitcoin->BTC-USD, Gold->GC=F, Oil->CL=F, S&P500->SPX"""

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
# Parse
start = resp.find("{")
end = resp.rfind("}") + 1
if start >= 0 and end > start:
    try:
        parsed = json.loads(resp[start:end])
        print(f"PARSED: {json.dumps(parsed, indent=2)}")
    except json.JSONDecodeError as e:
        print(f"PARSE ERROR: {e}")
