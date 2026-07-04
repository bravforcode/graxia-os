"""
notebooklm_register_url.py — Register NotebookLM notebooks by URL
No browser automation. User creates notebooks on website, then runs this script.

Usage:
  python notebooklm_register_url.py
  python notebooklm_register_url.py --url "https://notebooklm.google.com/notebook/xxx" --name "My Notebook"
  python notebooklm_register_url.py --file urls.txt   (format: url|name per line)
"""

import asyncio
import json
import os
import argparse
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


def get_all_sources():
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


def match_source(nb_name, sources):
    """Find best matching source for a notebook by name keywords"""
    name_lower = nb_name.lower()
    best_match = None
    best_score = 0
    for src_name in sources:
        words = src_name.lower().split()
        score = sum(1 for w in words if w in name_lower)
        if score > best_score:
            best_score = score
            best_match = src_name
    return best_match if best_score > 0 else None


async def register_notebook(session, url, name, sources, auto_source=True):
    """Register a single notebook and optionally add matching source"""
    nb_id = (
        name.lower()
        .replace(" ", "-")
        .replace(":", "")
        .replace("/", "-")
        .replace("(", "")
        .replace(")", "")
    )

    # Try update first, then add
    try:
        await session.call_tool("update_notebook", {"id": nb_id, "url": url})
        print(f"  [OK] Updated: {name}")
    except:
        try:
            await session.call_tool(
                "add_notebook",
                {"name": name, "description": f"Trading notebook: {name}", "url": url},
            )
            print(f"  [OK] Added: {name}")
        except Exception as e:
            print(f"  [FAIL] {name}: {e}")
            return False

    # Select
    try:
        await session.call_tool("select_notebook", {"notebook_id": nb_id})
    except:
        pass

    # Add source if matched
    if auto_source:
        src_name = match_source(name, sources)
        if src_name and sources[src_name]:
            try:
                await session.call_tool(
                    "add_source",
                    {
                        "type": "text",
                        "content": sources[src_name][:30000],
                        "title": src_name,
                        "notebook_url": url,
                    },
                )
                print(f"    Source: {src_name}")
                return True
            except Exception as e:
                print(f"    Source fail: {str(e)[:60]}")

    return True


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", help="Single notebook URL")
    parser.add_argument("--name", help="Notebook name")
    parser.add_argument("--file", help="File with url|name lines")
    parser.add_argument("--no-source", action="store_true", help="Skip source addition")
    args = parser.parse_args()

    # Collect notebooks
    notebooks = []
    if args.url and args.name:
        notebooks = [{"url": args.url, "name": args.name}]
    elif args.file:
        for line in Path(args.file).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("|")
            if len(parts) >= 2:
                notebooks.append({"url": parts[0].strip(), "name": parts[1].strip()})
    else:
        print("Enter notebook URLs (empty line to finish):")
        print("Format: paste URL from NotebookLM, then enter name")
        print()
        while True:
            url = input("  URL: ").strip()
            if not url:
                break
            name = input("  Name: ").strip()
            if not name:
                name = url.split("/")[-1][:20]
            notebooks.append({"url": url, "name": name})

    if not notebooks:
        print("No notebooks. Exit.")
        return

    print(f"\nRegistering {len(notebooks)} notebooks...")

    params = StdioServerParameters(command="npx", args=["-y", "notebooklm-mcp@latest"])
    sources = {} if args.no_source else get_all_sources()

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as session:
            await session.initialize()

            ok = 0
            for nb in notebooks:
                if await register_notebook(
                    session, nb["url"], nb["name"], sources, not args.no_source
                ):
                    ok += 1

            # List all
            print("\nAll registered notebooks:")
            result = await session.call_tool("list_notebooks", {})
            for c in result.content:
                if hasattr(c, "text"):
                    try:
                        nbs = json.loads(c.text)
                        if isinstance(nbs, list):
                            for nb in nbs:
                                has_url = "✓" if nb.get("url") else "✗"
                                print(f"  [{has_url}] {nb.get('name', 'unknown')}")
                    except:
                        pass

    print(f"\nDone: {ok}/{len(notebooks)} registered")


if __name__ == "__main__":
    asyncio.run(main())
