"""
Probe v2: test different prompt styles for ticker extraction.
"""

import sys

sys.stdout.reconfigure(encoding="utf-8")
import contextlib
import json
import time

import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3.5:9b"

test_headlines = [
    ("Reuters", "Nvidia beats quarterly revenue estimates on strong AI chip demand"),
    ("CNBC", "Apple launches new iPhone with AI features"),
    ("Bloomberg", "Markets rally on strong jobs data"),
    ("FT", "Tesla cuts prices in China amid competition"),
    ("WSJ", "JPMorgan Chase reports record quarterly profit"),
]

# Prompt style A: explicit field names
prompt_a = """Analyze this financial headline. Return ONLY a JSON object.

{source}: {title}

Return exactly this format:
{{"sentiment": "positive", "impact": "high", "ticker": "NVDA"}}

If no company ticker applies, use empty string: "ticker": ""
Indices: S&P500=SPX, Nasdaq=IXIC, Dow=DJI
Commodities: Gold=GC=F, Oil=CL=F, Bitcoin=BTC-USD"""

# Prompt style B: just say what to extract
prompt_b = """Extract sentiment, impact level, and stock ticker from this headline.

Headline: {source}: {title}

Return JSON: {{"sentiment": "...", "impact": "...", "ticker": "..."}}

Company->Ticker: Apple->AAPL, Nvidia->NVDA, Tesla->TSLA, Microsoft->MSFT, Meta->META, Amazon->AMZN
Indices: S&P500=SPX, Nasdaq=IXIC, Dow=DJI"""

# Prompt style C: minimal
prompt_c = """Classify this headline:

{source}: {title}

Return JSON: {{"sentiment": "positive/negative/none", "impact": "high/med/low", "ticker": "SYMBOL or none"}}"""

for source, title in test_headlines:
    print(f"\n{'='*60}")
    print(f"HEADLINE: {source}: {title}")

    for style, prompt_template in [("A-explicit", prompt_a), ("B-dict", prompt_b), ("C-minimal", prompt_c)]:
        prompt = prompt_template.format(source=source, title=title)
        body = {
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "think": False,
            "options": {
                "temperature": 0.05,
                "num_predict": 150,
                "num_ctx": 1024,
            },
        }

        try:
            r = requests.post(OLLAMA_URL, json=body, timeout=120)
            d = r.json()
            resp = d.get("message", {}).get("content", "")
            tokens = d.get("eval_count", 0)
            # Extract JSON
            start = resp.find("{")
            end = resp.rfind("}") + 1
            parsed = None
            if start >= 0 and end > start:
                with contextlib.suppress(BaseException):
                    parsed = json.loads(resp[start:end])
            print(f"  {style}: {tokens} tok | {parsed or resp[:80]}")
        except Exception as e:
            print(f"  {style}: ERROR {e}")
        time.sleep(1)
