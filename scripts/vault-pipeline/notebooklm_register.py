"""
notebooklm_register.py — Register a real NotebookLM notebook URL and add sources
Usage: python notebooklm_register.py <notebook_url> <notebook_name>

Example:
  python notebooklm_register.py https://notebooklm.google.com/notebook/abc123 "Strategy: BOS/CHOCH"
"""

import asyncio
import os
import sys
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

VAULT = Path(os.environ["USERPROFILE"]) / "Documents" / "ObsidianVault" / "Second Brain"
QUANT = (
    Path(os.environ["USERPROFILE"]) / "graxia os" / "graxia" / "packages" / "quant_os"
)
STRATEGIES = VAULT / "skills" / "trading" / "strategies"
MACRO = VAULT / "03-resources" / "trading" / "macro"
BACKTEST = VAULT / "03-resources" / "trading" / "backtest"
MODELS = VAULT / "03-resources" / "trading" / "models"
TRADES = VAULT / "07-Daily" / "trades"


def read_file(p):
    try:
        return p.read_text(encoding="utf-8")
    except:
        return ""


def get_source_content(nb_name):
    name = nb_name.lower()
    content = ""

    for f in STRATEGIES.glob("*.md"):
        if f.name == "Index.md":
            continue
        key = f.stem.lower().replace("_", " ")
        if key in name or any(w in name for w in key.split()):
            content = read_file(f)
            break

    if not content:
        for f in BACKTEST.glob("*.md"):
            if any(w in name for w in f.stem.lower().split("_")):
                content += read_file(f) + "\n"
        content = content[:30000]

    if not content:
        for f in MACRO.glob("*.md"):
            if any(w in name for w in f.stem.lower().split("-")):
                content += read_file(f) + "\n"
        content = content[:30000]

    if not content and "model" in name:
        for f in MODELS.glob("*.md"):
            content += read_file(f) + "\n"
        content = content[:30000]

    if not content and "trade" in name:
        for f in TRADES.glob("*.md"):
            content += read_file(f) + "\n"

    if not content and "risk" in name:
        for f in (VAULT / "03-resources/trading/risk").glob("*.md"):
            content += read_file(f) + "\n"

    if not content and "regime" in name:
        for f in (VAULT / "03-resources/trading/regime").glob("*.md"):
            content += read_file(f) + "\n"

    if not content and "signal" in name:
        for f in (VAULT / "03-resources/trading/signals").glob("*.md"):
            content += read_file(f) + "\n"

    if not content and "attribution" in name:
        for f in (VAULT / "03-resources/trading/attribution").glob("*.md"):
            content += read_file(f) + "\n"

    if not content and "ensemble" in name:
        for f in (VAULT / "03-resources/trading/ensemble").glob("*.md"):
            content += read_file(f) + "\n"

    if not content and "architecture" in name:
        for f in (QUANT / "Meta").glob("*.md"):
            content += read_file(f) + "\n"
        content = content[:30000]

    return content[:30000] if content else ""


async def register_and_populate(url, name):
    params = StdioServerParameters(command="npx", args=["-y", "notebooklm-mcp@latest"])
    nb_id = name.lower().replace(" ", "-").replace(":", "").replace("/", "-")

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # Register notebook with URL
            print(f"Registering: {name}")
            try:
                await s.call_tool("update_notebook", {"id": nb_id, "url": url})
                print("  OK: Updated existing entry")
            except:
                try:
                    await s.call_tool(
                        "add_notebook", {"name": name, "description": name, "url": url}
                    )
                    print("  OK: Added new entry")
                except Exception as e:
                    print(f"  FAIL: {e}")
                    return

            # Select notebook
            try:
                await s.call_tool("select_notebook", {"notebook_id": nb_id})
            except:
                pass

            # Add source
            content = get_source_content(name)
            if content:
                print(f"Adding source ({len(content)} chars)...")
                try:
                    result = await s.call_tool(
                        "add_source",
                        {
                            "type": "text",
                            "content": content,
                            "title": name,
                            "notebook_url": url,
                        },
                    )
                    for c in result.content:
                        if hasattr(c, "text"):
                            print(f"  OK: {c.text[:100]}")
                except Exception as e:
                    print(f"  FAIL: {e}")
            else:
                print("  No matching content found")

            # Test ask_question
            print("Testing ask_question...")
            try:
                result = await s.call_tool(
                    "ask_question",
                    {
                        "question": "Summarize what this notebook covers in 2 sentences.",
                        "notebook_url": url,
                    },
                )
                for c in result.content:
                    if hasattr(c, "text"):
                        print(f"  ANSWER: {c.text[:300]}")
            except Exception as e:
                print(f"  FAIL: {e}")


def main():
    if len(sys.argv) < 3:
        print("Usage: python notebooklm_register.py <notebook_url> <notebook_name>")
        print()
        print("Example:")
        print(
            '  python notebooklm_register.py https://notebooklm.google.com/notebook/abc123 "Strategy: BOS/CHOCH"'
        )
        print()
        print("Available notebooks to register:")
        notebooks = [
            "Strategy: BOS/CHOCH",
            "Strategy: EMA Cross",
            "Strategy: Fair Value Gap",
            "Strategy: Fibonacci",
            "Strategy: Liquidity Sweep",
            "Strategy: London Breakout",
            "Strategy: Multi-TF Alignment",
            "Strategy: News Fade",
            "Strategy: Opening Range",
            "Strategy: Order Block",
            "Strategy: RSI Divergence",
            "Strategy: Supply/Demand",
            "Strategy: VWAP Rejection",
            "Backtest: XAUUSD",
            "Backtest: Multi-Symbol",
            "Backtest: Strategy Comparison",
            "Backtest: MTM/MRB/MLB",
            "Backtest: Cost Analysis",
            "Macro: Dashboard",
            "Macro: Yield Curve",
            "Macro: Credit Markets",
            "Macro: Liquidity",
            "Macro: Cross-Market",
            "Macro: Weekly Review",
            "ML: Model Registry",
            "ML: Training Results",
            "Trade Journal",
            "Risk Management",
            "Regime Analysis",
            "Signal Quality",
            "P&L Attribution",
            "Ensemble Optimizer",
            "System Architecture",
            "XAUUSD Playbook",
            "Multi-Asset Overview",
            "Daily Briefing",
        ]
        for nb in notebooks:
            print(f"  - {nb}")
        return

    url = sys.argv[1]
    name = sys.argv[2]

    asyncio.run(register_and_populate(url, name))


if __name__ == "__main__":
    main()
