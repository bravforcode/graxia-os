"""
notebooklm_interactive.py — Run in terminal directly (not via MCP tool)
Opens browser, creates notebooks, adds sources, tests ask_question
"""

import asyncio
import json
import os
from pathlib import Path

# MUST run in interactive terminal: python notebooklm_interactive.py

VAULT = Path(os.environ["USERPROFILE"]) / "Documents" / "ObsidianVault" / "Second Brain"
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


def get_sources():
    srcs = {}
    for f in STRATEGIES.glob("*.md"):
        if f.name == "Index.md":
            continue
        srcs[f"Strategy: {f.stem}"] = read_file(f)
    for f in BACKTEST.glob("*.md"):
        srcs[f"Backtest: {f.stem}"] = read_file(f)
    for f in MACRO.glob("*.md"):
        srcs[f"Macro: {f.stem}"] = read_file(f)
    return srcs


async def main():
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(command="npx", args=["-y", "notebooklm-mcp@latest"])

    print("=" * 60)
    print("  NOTEBOOKLM INTERACTIVE SETUP")
    print("=" * 60)

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # Step 1: Auth
            print("\n[1] Opening browser for Google login...")
            try:
                result = await asyncio.wait_for(
                    s.call_tool("setup_auth", {}), timeout=5
                )
            except asyncio.TimeoutError:
                print("  Browser opened. Log in, then come back here.")
            except Exception as e:
                print(f"  {e}")

            # Step 2: Enter URLs
            print("\n[2] Enter notebook URLs (empty line to finish):")
            notebooks = []
            while True:
                url = input("  URL: ").strip()
                if not url:
                    break
                name = input("  Name: ").strip()
                notebooks.append({"url": url, "name": name})

            if not notebooks:
                print("  No notebooks. Done.")
                return

            # Step 3: Register + add sources
            print(f"\n[3] Registering {len(notebooks)} notebooks...")
            all_sources = get_sources()

            for nb in notebooks:
                nb_id = (
                    nb["name"]
                    .lower()
                    .replace(" ", "-")
                    .replace(":", "")
                    .replace("/", "-")
                )
                print(f"\n  --- {nb['name']} ---")

                try:
                    await s.call_tool(
                        "update_notebook", {"id": nb_id, "url": nb["url"]}
                    )
                    print("  Registered")
                except:
                    try:
                        await s.call_tool(
                            "add_notebook",
                            {
                                "name": nb["name"],
                                "description": nb["name"],
                                "url": nb["url"],
                            },
                        )
                        print("  Added")
                    except Exception as e:
                        print(f"  Fail: {e}")
                        continue

                try:
                    await s.call_tool("select_notebook", {"notebook_id": nb_id})
                except:
                    pass

                for src_name, src_text in all_sources.items():
                    if not src_text or len(src_text.strip()) < 20:
                        continue
                    if any(
                        w in nb["name"].lower() for w in src_name.lower().split()[:2]
                    ):
                        try:
                            await s.call_tool(
                                "add_source",
                                {
                                    "type": "text",
                                    "content": src_text[:30000],
                                    "title": src_name,
                                    "notebook_url": nb["url"],
                                },
                            )
                            print(f"  Source: {src_name}")
                        except Exception as e:
                            print(f"  Source fail: {str(e)[:60]}")
                        break

            # Step 4: Test
            print("\n[4] Testing ask_question...")
            for nb in notebooks[:3]:
                try:
                    result = await s.call_tool(
                        "ask_question",
                        {
                            "question": "Summarize in 2 sentences.",
                            "notebook_url": nb["url"],
                        },
                    )
                    for c in result.content:
                        if hasattr(c, "text"):
                            d = json.loads(c.text)
                            if d.get("success"):
                                print(f"  {nb['name']}: OK")
                            else:
                                print(
                                    f"  {nb['name']}: {d.get('error', 'unknown')[:60]}"
                                )
                except Exception as e:
                    print(f"  {nb['name']}: {str(e)[:60]}")

    print("\n" + "=" * 60)
    print("  DONE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
