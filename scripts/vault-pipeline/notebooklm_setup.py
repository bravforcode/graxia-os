"""
notebooklm_setup.py — One-click setup: creates notebooks via MCP browser, registers, adds sources
Flow: setup_auth -> create notebooks -> register -> add sources -> test ask_question
"""

import asyncio
import json
import os
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

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
    for f in MODELS.glob("*.md"):
        srcs[f"Model: {f.stem}"] = read_file(f)
    for f in TRADES.glob("*.md"):
        srcs[f"Trade: {f.stem}"] = read_file(f)
    for d in ["risk", "regime", "signals", "attribution", "ensemble"]:
        p = VAULT / "03-resources/trading" / d
        if p.exists():
            for f in p.glob("*.md"):
                srcs[f"{d}: {f.stem}"] = read_file(f)
    return srcs


async def main():
    params = StdioServerParameters(command="npx", args=["-y", "notebooklm-mcp@latest"])

    print("=" * 60)
    print("  NOTEBOOKLM FULL SETUP")
    print("=" * 60)

    # Step 1: Open browser for auth
    print("\n[1/4] Opening browser for Google login...")
    print("  A browser window will open. Log in to your Google account.")
    print("  After logging in, create a notebook on NotebookLM.")
    print(
        "  Copy the notebook URL (format: https://notebooklm.google.com/notebook/<uuid>)"
    )
    print()

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # setup_auth
            try:
                result = await asyncio.wait_for(
                    s.call_tool("setup_auth", {}), timeout=5
                )
                for c in result.content:
                    if hasattr(c, "text"):
                        print(f"  {c.text[:200]}")
            except asyncio.TimeoutError:
                print("  Browser opened (timeout expected)")
            except Exception as e:
                print(f"  Error: {e}")

            # Step 2: Get notebook URLs from user
            print("\n[2/4] Enter notebook URLs (empty line to finish):")
            print("  Create notebooks at https://notebooklm.google.com/")
            print("  Then paste their URLs below.")
            print()

            notebooks = []
            loop = asyncio.get_event_loop()

            while True:
                url = await loop.run_in_executor(
                    None, lambda: input("  Notebook URL (or Enter to finish): ")
                )
                url = url.strip()
                if not url:
                    break
                name = await loop.run_in_executor(
                    None, lambda: input("  Notebook name: ")
                )
                notebooks.append({"url": url, "name": name.strip()})
                print(f"  Added: {name.strip()}")

            if not notebooks:
                print("\n  No notebooks provided. Creating one test notebook...")
                notebooks = [{"url": "", "name": "Test Notebook"}]

            # Step 3: Register notebooks and add sources
            print(
                f"\n[3/4] Registering {len(notebooks)} notebooks and adding sources..."
            )

            all_sources = get_sources()
            results = {"registered": 0, "sources_added": 0, "errors": []}

            for nb in notebooks:
                nb_name = nb["name"]
                nb_url = nb["url"]
                nb_id = (
                    nb_name.lower().replace(" ", "-").replace(":", "").replace("/", "-")
                )

                print(f"\n  --- {nb_name} ---")

                # Register
                if nb_url:
                    try:
                        await s.call_tool(
                            "update_notebook", {"id": nb_id, "url": nb_url}
                        )
                        print("  Registered with URL")
                        results["registered"] += 1
                    except:
                        try:
                            await s.call_tool(
                                "add_notebook",
                                {
                                    "name": nb_name,
                                    "description": nb_name,
                                    "url": nb_url,
                                },
                            )
                            print("  Added with URL")
                            results["registered"] += 1
                        except Exception as e:
                            print(f"  Register fail: {e}")
                            results["errors"].append(f"register {nb_name}: {e}")
                            continue

                # Select
                try:
                    await s.call_tool("select_notebook", {"notebook_id": nb_id})
                except:
                    pass

                # Add matching source
                for src_name, src_text in all_sources.items():
                    if not src_text or len(src_text.strip()) < 20:
                        continue
                    if any(w in nb_name.lower() for w in src_name.lower().split()[:2]):
                        try:
                            await s.call_tool(
                                "add_source",
                                {
                                    "type": "text",
                                    "content": src_text[:30000],
                                    "title": src_name,
                                    "notebook_url": nb_url,
                                },
                            )
                            results["sources_added"] += 1
                            print(f"    Source: {src_name}")
                        except Exception as e:
                            print(f"    Source fail: {src_name}: {str(e)[:60]}")
                        break

            # Step 4: Test ask_question
            print("\n[4/4] Testing ask_question...")

            for nb in notebooks[:3]:  # Test first 3
                if not nb["url"]:
                    continue
                try:
                    await s.call_tool(
                        "select_notebook",
                        {
                            "notebook_id": nb["name"]
                            .lower()
                            .replace(" ", "-")
                            .replace(":", "")
                            .replace("/", "-")
                        },
                    )
                    result = await s.call_tool(
                        "ask_question",
                        {
                            "question": "Summarize this notebook in 2 sentences.",
                            "notebook_url": nb["url"],
                        },
                    )
                    for c in result.content:
                        if hasattr(c, "text"):
                            text = c.text[:200]
                            if "success" in text and "true" in text:
                                print(f"  {nb['name']}: OK")
                            else:
                                print(f"  {nb['name']}: {text[:100]}")
                except Exception as e:
                    print(f"  {nb['name']}: {str(e)[:60]}")

    # Summary
    print("\n" + "=" * 60)
    print(f"  Registered: {results['registered']}")
    print(f"  Sources: {results['sources_added']}")
    print(f"  Errors: {len(results['errors'])}")
    print("=" * 60)

    # Save
    out = Path(__file__).parent / "notebooklm_setup_results.json"
    out.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"  Saved: {out}")


if __name__ == "__main__":
    asyncio.run(main())
