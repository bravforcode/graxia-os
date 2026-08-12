"""
notebooklm_max_sources.py — Pack ALL vault data into ONE NotebookLM notebook
"""

import asyncio
import json
import os
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

VAULT = Path(os.environ["USERPROFILE"]) / "Documents" / "ObsidianVault" / "Second Brain"
NB_URL = "https://notebooklm.google.com/notebook/f6b81dd1-a298-4709-a018-c4aec5269e5c?authuser=1&addSource=true"


def read_file(p):
    try:
        return p.read_text(encoding="utf-8")
    except:
        return ""


def get_all_sources():
    srcs = []

    # Strategies (13)
    d = VAULT / "skills" / "trading" / "strategies"
    for f in sorted(d.glob("*.md")):
        if f.name == "Index.md":
            continue
        txt = read_file(f)
        if len(txt.strip()) > 50:
            srcs.append((f"Strategy: {f.stem}", txt))

    # Backtest (35+)
    d = VAULT / "03-resources" / "trading" / "backtest"
    for f in sorted(d.glob("*.md")):
        txt = read_file(f)
        if len(txt.strip()) > 50:
            srcs.append((f"Backtest: {f.stem}", txt))

    # Macro (6)
    d = VAULT / "03-resources" / "trading" / "macro"
    for f in sorted(d.glob("*.md")):
        txt = read_file(f)
        if len(txt.strip()) > 50:
            srcs.append((f"Macro: {f.stem}", txt))

    # Models (26)
    d = VAULT / "03-resources" / "trading" / "models"
    for f in sorted(d.glob("*.md")):
        if f.name == "Index.md":
            continue
        txt = read_file(f)
        if len(txt.strip()) > 50:
            srcs.append((f"Model: {f.stem}", txt))

    # Trades
    d = VAULT / "07-Daily" / "trades"
    for f in sorted(d.glob("*.md")):
        txt = read_file(f)
        if len(txt.strip()) > 50:
            srcs.append((f"Trade: {f.stem}", txt))

    # Risk, Regime, Signals, Attribution, Ensemble
    for sub in ["risk", "regime", "signals", "attribution", "ensemble"]:
        d = VAULT / "03-resources" / "trading" / sub
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md")):
            txt = read_file(f)
            if len(txt.strip()) > 50:
                srcs.append((f"{sub}: {f.stem}", txt))

    return srcs


async def main():
    params = StdioServerParameters(command="npx", args=["-y", "notebooklm-mcp@latest"])

    print("=" * 60)
    print("  PACKING ALL VAULT DATA INTO ONE NOTEBOOK")
    print("=" * 60)
    print(f"  Notebook: {NB_URL}")

    all_sources = get_all_sources()
    print(f"  Sources found: {len(all_sources)}")

    # Check total size
    total_size = sum(len(t) for _, t in all_sources)
    print(f"  Total content: {total_size:,} chars ({total_size/1000:.0f} KB)")
    print()

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # Register notebook
            print("[1] Registering notebook...")
            try:
                await s.call_tool(
                    "update_notebook", {"id": "master-trading", "url": NB_URL}
                )
                print("  OK: Updated")
            except:
                try:
                    await s.call_tool(
                        "add_notebook",
                        {
                            "name": "Master Trading Intelligence",
                            "description": "All trading data: strategies, backtests, macro, ML models, trades, risk",
                            "url": NB_URL,
                        },
                    )
                    print("  OK: Added")
                except Exception as e:
                    print(f"  FAIL: {e}")
                    return

            try:
                await s.call_tool("select_notebook", {"notebook_id": "master-trading"})
                print("  Selected")
            except:
                pass

            # Add ALL sources
            print(f"\n[2] Adding {len(all_sources)} sources...")
            ok = 0
            fail = 0

            for i, (name, content) in enumerate(all_sources, 1):
                # Truncate if too long (NotebookLM limit ~500K chars per source)
                truncated = content[:500000]

                try:
                    result = await asyncio.wait_for(
                        s.call_tool(
                            "add_source",
                            {
                                "type": "text",
                                "content": truncated,
                                "title": name,
                                "notebook_url": NB_URL,
                            },
                        ),
                        timeout=60,
                    )

                    # Check result
                    success = False
                    for c in result.content:
                        if hasattr(c, "text"):
                            try:
                                d = json.loads(c.text)
                                success = d.get("success", False)
                            except:
                                pass

                    if success:
                        ok += 1
                        print(
                            f"  [{i:2d}/{len(all_sources)}] OK: {name} ({len(content):,} chars)"
                        )
                    else:
                        fail += 1
                        print(f"  [{i:2d}/{len(all_sources)}] FAIL: {name}")
                except asyncio.TimeoutError:
                    fail += 1
                    print(f"  [{i:2d}/{len(all_sources)}] TIMEOUT: {name}")
                except Exception as e:
                    fail += 1
                    print(f"  [{i:2d}/{len(all_sources)}] ERROR: {name}: {str(e)[:50]}")

                # Small delay to avoid rate limiting
                await asyncio.sleep(0.5)

            # Test
            print("\n[3] Testing ask_question...")
            try:
                result = await asyncio.wait_for(
                    s.call_tool(
                        "ask_question",
                        {
                            "question": "List all trading strategies and their key characteristics in a table.",
                            "notebook_url": NB_URL,
                        },
                    ),
                    timeout=30,
                )
                for c in result.content:
                    if hasattr(c, "text"):
                        d = json.loads(c.text)
                        if d.get("success"):
                            answer = d.get("answer", "")[:500]
                            print(f"  Answer: {answer}")
                        else:
                            print(f"  Error: {d.get('error')}")
            except Exception as e:
                print(f"  Test fail: {e}")

    print(f"\n{'='*60}")
    print(f"  RESULT: {ok} added, {fail} failed, {len(all_sources)} total")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
