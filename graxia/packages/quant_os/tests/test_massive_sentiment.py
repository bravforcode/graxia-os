"""
MASSIVE SENTIMENT INTEGRATION TEST
===================================
Tests ALL 6 LLM providers with real financial news headlines.
Sends 12 headlines across 6 providers → 72 parallel API calls.

Providers:
  1. Groq (Llama 3.3 70B) — 1000 req/day
  2. Google AI (Gemini 2.5 Flash) — 20 req/day
  3. Cerebras (Llama 3.1 8B) — 14400 req/day
  4. OpenRouter (Llama 3.3 70B) — 50 req/day
  5. Cohere (Command R+) — 1000 req/month
  6. Cloudflare (Llama 3.3 70B) — 10000 neurons/day

Run:
  cd graxia/packages
  python -m pytest quant_os/tests/test_massive_sentiment.py -v -s
"""

import asyncio
import os
import sys
import time
import json
from dataclasses import dataclass
from pathlib import Path

import pytest

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))


# ═══════════════════════════════════════════════════════════════════
# NEWS HEADLINES — 12 real financial headlines
# ═══════════════════════════════════════════════════════════════════

HEADLINES = [
    # BULLISH
    "Fed signals rate cut in September, markets rally to all-time highs",
    "US GDP growth beats expectations at 3.2%, unemployment drops to 3.4%",
    "NVIDIA reports record earnings, stock surges 12% after hours",
    # BEARISH
    "Federal Reserve raises interest rates by 75 basis points, inflation still hot",
    "China Evergrande defaults on $300 billion debt, global markets plunge",
    "US unemployment jumps to 4.2%, recession fears intensify",
    # CRISIS
    "Breaking: Russia launches military operation against Ukraine, oil spikes 15%",
    "Major cyberattack disables SWIFT banking system, financial markets frozen",
    "US-China tensions escalate, Taiwan Strait blockade announced",
    # MIXED/UNCERTAIN
    "ECB maintains rates amid mixed economic signals from eurozone",
    "Bitcoin crashes 20% in 24 hours amid regulatory crackdown fears",
    "Gold hits $3200 as safe-haven demand surges on geopolitical tensions",
]


# ═══════════════════════════════════════════════════════════════════
# PROVIDER CONFIGS
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ProviderCfg:
    name: str
    env_key: str
    base_url: str
    model: str
    api_type: str  # "openai", "google", "cohere", "cloudflare"


PROVIDERS = [
    ProviderCfg(
        name="groq",
        env_key="GROQ_API_KEY",
        base_url="https://api.groq.com/openai/v1/chat/completions",
        model="llama-3.3-70b-versatile",
        api_type="openai",
    ),
    ProviderCfg(
        name="google",
        env_key="GOOGLE_AI_KEY",
        base_url="https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent",
        model="gemini-2.5-flash",
        api_type="google",
    ),
    ProviderCfg(
        name="cerebras",
        env_key="CEREBRAS_API_KEY",
        base_url="https://api.cerebras.ai/v1/chat/completions",
        model="gpt-oss-120b",
        api_type="openai",
    ),
    ProviderCfg(
        name="openrouter",
        env_key="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1/chat/completions",
        model="meta-llama/llama-3.3-70b-instruct:free",
        api_type="openai",
    ),
    ProviderCfg(
        name="cohere",
        env_key="COHERE_API_KEY",
        base_url="https://api.cohere.com/v2/chat",
        model="command-r-plus-08-2024",
        api_type="cohere",
    ),
    ProviderCfg(
        name="cloudflare",
        env_key="CF_API_TOKEN",
        base_url="https://api.cloudflare.com/client/v4",
        model="@cf/meta/llama-3.3-70b-instruct-fp8",
        api_type="cloudflare",
    ),
]


# ═══════════════════════════════════════════════════════════════════
# PROMPT
# ═══════════════════════════════════════════════════════════════════

PROMPT_TEMPLATE = """You are a financial sentiment analyzer for a trading system.

Analyze the following news headline and return a JSON object with:
- sentiment_score: float from -1.0 (extremely bearish) to 1.0 (extremely bullish)
- confidence: float from 0.0 to 1.0 (how confident you are in the sentiment)
- regime_override: string, one of ["NORMAL", "HIGH_UNCERTAINTY", "CRISIS"]
- position_multiplier: float from 0.0 to 1.0 (risk scalar: 1.0 = full size, 0.5 = half size, 0.0 = no trade)
- reasoning: string, brief explanation

Rules:
- Fed hawkish = bearish, dovish = bullish
- Geopolitical tension = HIGH_UNCERTAINTY, position_multiplier <= 0.5
- War/crisis = CRISIS, position_multiplier = 0.0
- Positive earnings/GDP = bullish
- Negative earnings/GDP = bearish
- Unclear/ambiguous = low confidence, position_multiplier = 0.75

Headline: {headline}

Return ONLY valid JSON, no other text."""


# ═══════════════════════════════════════════════════════════════════
# API CALLERS
# ═══════════════════════════════════════════════════════════════════

async def call_openai_compatible(
    client, cfg: ProviderCfg, api_key: str, headline: str, max_retries: int = 3
) -> dict | None:
    """Call OpenAI-compatible APIs (Groq, Cerebras, OpenRouter) with retry."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    if cfg.name == "openrouter":
        headers["HTTP-Referer"] = "https://graxia.dev"
        headers["X-Title"] = "Graxia Quant OS"

    payload = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": PROMPT_TEMPLATE.format(headline=headline)}],
        "temperature": 0.1,
        "max_tokens": 500,
    }

    for attempt in range(max_retries):
        try:
            resp = await client.post(cfg.base_url, headers=headers, json=payload)
            if resp.status_code == 429:
                # Rate limited - wait and retry
                wait = 2 ** attempt  # 1s, 2s, 4s
                await asyncio.sleep(wait)
                continue
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}", "body": resp.text[:200]}
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return parse_json_response(content)
        except Exception as e:
            if attempt == max_retries - 1:
                return {"error": str(e)}
            await asyncio.sleep(1)
    return {"error": "Max retries exceeded"}


async def call_google(
    client, cfg: ProviderCfg, api_key: str, headline: str, max_retries: int = 3
) -> dict | None:
    """Call Google AI Studio (Gemini) with retry."""
    url = f"{cfg.base_url}?key={api_key}"
    payload = {
        "contents": [{"parts": [{"text": PROMPT_TEMPLATE.format(headline=headline)}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 500},
    }

    for attempt in range(max_retries):
        try:
            resp = await client.post(url, json=payload)
            if resp.status_code == 429:
                wait = 2 ** attempt
                await asyncio.sleep(wait)
                continue
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}", "body": resp.text[:200]}
            data = resp.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            return parse_json_response(content)
        except Exception as e:
            if attempt == max_retries - 1:
                return {"error": str(e)}
            await asyncio.sleep(1)
    return {"error": "Max retries exceeded"}


async def call_cohere(
    client, cfg: ProviderCfg, api_key: str, headline: str, max_retries: int = 3
) -> dict | None:
    """Call Cohere API with retry."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": PROMPT_TEMPLATE.format(headline=headline)}],
        "temperature": 0.1,
        "max_tokens": 500,
    }

    for attempt in range(max_retries):
        try:
            resp = await client.post(cfg.base_url, headers=headers, json=payload)
            if resp.status_code == 429:
                wait = 2 ** attempt
                await asyncio.sleep(wait)
                continue
            if resp.status_code != 200:
                return {"error": f"HTTP {resp.status_code}", "body": resp.text[:200]}
            data = resp.json()
            content = data["message"]["content"][0]["text"]
            return parse_json_response(content)
        except Exception as e:
            if attempt == max_retries - 1:
                return {"error": str(e)}
            await asyncio.sleep(1)
    return {"error": "Max retries exceeded"}


async def call_cloudflare(
    client, cfg: ProviderCfg, api_key: str, headline: str
) -> dict | None:
    """Call Cloudflare Workers AI."""
    account_id = os.getenv("CF_ACCOUNT_ID", "")
    if not account_id:
        return {"error": "CF_ACCOUNT_ID not set"}
    url = f"{cfg.base_url}/accounts/{account_id}/ai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": PROMPT_TEMPLATE.format(headline=headline)}],
        "max_tokens": 500,
        "temperature": 0.1,
    }

    try:
        resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            return {"error": f"HTTP {resp.status_code}", "body": resp.text[:200]}
        data = resp.json()
        content = data["result"]["response"]["content"]
        return parse_json_response(content)
    except Exception as e:
        return {"error": str(e)}


def parse_json_response(content: str) -> dict | None:
    """Extract JSON from LLM response, handling markdown code blocks."""
    try:
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        return json.loads(content.strip())
    except (json.JSONDecodeError, ValueError):
        return {"error": "JSON parse failed", "raw": content[:300]}


async def _delayed_call(delay: float, coro):
    """Add delay before executing a coroutine (for rate limiting)."""
    if delay > 0:
        await asyncio.sleep(delay)
    return await coro


# ═══════════════════════════════════════════════════════════════════
# MAIN TEST
# ═══════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_massive_sentiment_all_providers():
    """
    Send 12 headlines × 6 providers = 72 parallel API calls.
    Tests Groq, Google, Cerebras, OpenRouter, Cohere, Cloudflare.
    """
    import httpx

    # Load env
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())

    # Filter available providers
    available = []
    for cfg in PROVIDERS:
        key = os.environ.get(cfg.env_key, "")
        if key:
            available.append((cfg, key))
            print(f"\n  [OK] {cfg.name}: key={key[:8]}...")
        else:
            print(f"\n  [--] {cfg.name}: no key ({cfg.env_key})")

    assert len(available) >= 1, "No providers configured!"

    print(f"\n{'='*70}")
    print(f"  MASSIVE SENTIMENT TEST: {len(available)} providers × {len(HEADLINES)} headlines")
    print(f"  Total API calls: {len(available) * len(HEADLINES)}")
    print(f"{'='*70}\n")

    # Call each provider with ALL headlines in parallel (staggered)
    async with httpx.AsyncClient(timeout=30.0) as client:
        all_results = {}
        tasks = []

        for cfg, api_key in available:
            for idx, headline in enumerate(HEADLINES):
                # Stagger requests: 0.5s between each for rate-limited providers
                delay = idx * 0.5 if cfg.name in ("openrouter", "google", "cerebras") else 0
                if cfg.api_type == "openai":
                    tasks.append((cfg.name, headline, _delayed_call(delay, call_openai_compatible(client, cfg, api_key, headline))))
                elif cfg.api_type == "google":
                    tasks.append((cfg.name, headline, _delayed_call(delay, call_google(client, cfg, api_key, headline))))
                elif cfg.api_type == "cohere":
                    tasks.append((cfg.name, headline, _delayed_call(delay, call_cohere(client, cfg, api_key, headline))))
                elif cfg.api_type == "cloudflare":
                    tasks.append((cfg.name, headline, _delayed_call(delay, call_cloudflare(client, cfg, api_key, headline))))

        # Run ALL in parallel
        start = time.time()
        results = await asyncio.gather(*[t[2] for t in tasks], return_exceptions=True)
        elapsed = time.time() - start

        # Collect results
        for i, ((provider_name, headline, _), result) in enumerate(zip(tasks, results)):
            if provider_name not in all_results:
                all_results[provider_name] = []
            all_results[provider_name].append({
                "headline": headline[:60],
                "result": result,
            })

    # ═══════════════════════════════════════════════════════════════
    # RESULTS
    # ═══════════════════════════════════════════════════════════════

    total_success = 0
    total_error = 0

    print(f"\n{'='*70}")
    print(f"  RESULTS — {elapsed:.1f}s total")
    print(f"{'='*70}")

    for provider_name, results_list in all_results.items():
        success = sum(1 for r in results_list if r["result"] and "error" not in r["result"])
        error = len(results_list) - success
        total_success += success
        total_error += error

        print(f"\n  [{provider_name.upper()}] {success}/{len(results_list)} success")
        for r in results_list:
            res = r["result"]
            if res and "error" not in res:
                score = res.get("sentiment_score", "?")
                conf = res.get("confidence", "?")
                regime = res.get("regime_override", "?")
                mult = res.get("position_multiplier", "?")
                print(f"    [OK] {r['headline']}")
                print(f"         score={score}  conf={conf}  regime={regime}  mult={mult}")
            else:
                err = res.get("error", str(res)) if res else "None"
                print(f"    [ERR] {r['headline']}")
                print(f"          {err[:100]}")

    # ═══════════════════════════════════════════════════════════════
    # AGGREGATION TEST
    # ═══════════════════════════════════════════════════════════════

    print(f"\n{'='*70}")
    print("  AGGREGATION")
    print(f"{'='*70}")

    all_scores = []
    for provider_name, results_list in all_results.items():
        for r in results_list:
            res = r["result"]
            if res and "error" not in res and "sentiment_score" in res:
                all_scores.append(res["sentiment_score"])

    if all_scores:
        avg = sum(all_scores) / len(all_scores)
        print(f"  Total valid scores: {len(all_scores)}")
        print(f"  Average sentiment: {avg:.4f}")
        print(f"  Min: {min(all_scores):.4f}  Max: {max(all_scores):.4f}")

    print(f"\n{'='*70}")
    print(f"  SUMMARY: {total_success} success / {total_error} error / {total_success+total_error} total")
    print(f"  Time: {elapsed:.1f}s")
    print(f"{'='*70}\n")

    # Assert at least 1 provider worked
    assert total_success >= 1, f"No providers succeeded! Errors: {total_error}"


if __name__ == "__main__":
    asyncio.run(test_massive_sentiment_all_providers())
