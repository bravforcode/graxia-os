"""
notebooklm_test_5q.py — Test 5 questions on the master notebook
"""

import asyncio
import json
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

NB_URL = "https://notebooklm.google.com/notebook/f6b81dd1-a298-4709-a018-c4aec5269e5c?authuser=1"
OUT = Path(__file__).parent / "notebooklm_test_5q.txt"


async def main():
    params = StdioServerParameters(command="npx", args=["-y", "notebooklm-mcp@latest"])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            questions = [
                "Based on all sources, what is the current outlook for XAUUSD gold? Give price targets and key levels.",
                "Which trading strategy from the vault should be used for EURUSD right now? Explain why.",
                "What is the current macro regime? Risk-on or risk-off? Which assets benefit?",
                "Based on ML models and backtests, what is the optimal strategy allocation for this week?",
                "What are the biggest risks to watch this week? Give specific levels and events.",
            ]

            results = []
            for i, q in enumerate(questions, 1):
                print(f"Q{i}: {q[:60]}...", flush=True)
                try:
                    result = await asyncio.wait_for(
                        s.call_tool(
                            "ask_question", {"question": q, "notebook_url": NB_URL}
                        ),
                        timeout=90,
                    )
                    for c in result.content:
                        if hasattr(c, "text"):
                            d = json.loads(c.text)
                            ans = d.get("data", {}).get("answer", "no answer")
                            results.append(f"Q{i}: {q}\nA: {ans}\n")
                            print(f"  -> {len(ans)} chars", flush=True)
                except Exception as e:
                    results.append(f"Q{i}: {q}\nA: ERROR: {str(e)[:100]}\n")
                    print(f"  -> ERROR: {str(e)[:60]}", flush=True)

            OUT.write_text("\n---\n".join(results), encoding="utf-8")
            print(f"\nSaved: {OUT}")


asyncio.run(main())
