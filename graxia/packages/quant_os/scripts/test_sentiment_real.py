"""
Real Integration Test — Send news to all 6 LLM providers.

Run: python scripts/test_sentiment_real.py
"""

import asyncio
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")


async def test_all_providers():
    """Test all 6 providers with real news headlines."""
    from core.agents.sentiment_agent import SentimentAgent

    agent = SentimentAgent()

    # Real news headlines to test
    headlines = [
        "Federal Reserve raises interest rates by 50 basis points, signals more hikes ahead",
        "US-China trade war escalates as new tariffs imposed on $200 billion in goods",
        "Gold prices surge to all-time high above $2500 amid geopolitical tensions",
        "Bitcoin crashes 15% in 24 hours as major exchange files for bankruptcy",
        "US GDP grows 3.2% in Q1 2026, beating expectations of 2.8%",
        "OPEC announces surprise production cut of 1 million barrels per day",
        "European Central Bank holds rates steady, adopts dovish tone",
        "Japan intervenes in currency markets to strengthen yen after sharp decline",
    ]

    # Add all headlines to agent
    for headline in headlines:
        agent._pending_headlines.append({
            "headline": headline,
            "source": "test",
            "timestamp": "2026-06-27T10:00:00Z",
        })

    print("=" * 80)
    print("MULTI-PROVIDER SENTIMENT TEST")
    print("=" * 80)
    print(f"\nHeadlines: {len(headlines)}")
    print("Providers: Groq, Google, Cerebras, OpenRouter, Cohere, Cloudflare")
    print("\nAnalyzing...")

    result = await agent.act()

    if result:
        print("\n" + "=" * 80)
        print("RESULT")
        print("=" * 80)
        print(f"Sentiment Score:    {result['sentiment_score']:+.4f}")
        print(f"Confidence:        {result['confidence']:.4f}")
        print(f"Regime Override:   {result['regime_override']}")
        print(f"Position Multiplier: {result['position_multiplier']:.4f}")
        print(f"Headline Count:    {result['headline_count']}")
        print(f"Provider Count:    {result['provider_count']}")
        print(f"Provider Breakdown: {result['provider_breakdown']}")
        print("\nHeadlines Analyzed:")
        for h in result.get('headlines', []):
            print(f"  - {h}")
        print("\nReasoning:")
        for r in result.get('reasoning', '').split(' | '):
            print(f"  - {r}")
    else:
        print("\nNo result returned. Check API keys in .env")

    await agent.shutdown()
    return result


if __name__ == "__main__":
    result = asyncio.run(test_all_providers())
