"""
notebooklm_create_all.py — Create notebooks on NotebookLM via Playwright, register via MCP, add sources
"""

import asyncio
import json
import os
import re
from pathlib import Path
from playwright.async_api import async_playwright
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

CHROME_PROFILE = (
    Path(os.environ["USERPROFILE"]) / "AppData/Local/notebooklm-mcp/Data/chrome_profile"
)
VAULT = Path(os.environ["USERPROFILE"]) / "Documents" / "ObsidianVault" / "Second Brain"
QUANT = (
    Path(os.environ["USERPROFILE"]) / "graxia os" / "graxia" / "packages" / "quant_os"
)
STRATEGIES = VAULT / "skills" / "trading" / "strategies"
MACRO = VAULT / "03-resources" / "trading" / "macro"
BACKTEST = VAULT / "03-resources" / "trading" / "backtest"
MODELS = VAULT / "03-resources" / "trading" / "models"
TRADES = VAULT / "07-Daily" / "trades"

NOTEBOOKS = [
    ("Strategy: BOS/CHOCH", "bos_choch.md"),
    ("Strategy: EMA Cross", "ema_cross.md"),
    ("Strategy: Fair Value Gap", "fair_value_gap.md"),
    ("Strategy: Fibonacci", "fibonacci.md"),
    ("Strategy: Liquidity Sweep", "liquidity_sweep.md"),
    ("Strategy: London Breakout", "london_breakout.md"),
    ("Strategy: Multi-TF Alignment", "multi_tf_align.md"),
    ("Strategy: News Fade", "news_fade.md"),
    ("Strategy: Opening Range", "opening_range.md"),
    ("Strategy: Order Block", "order_block.md"),
    ("Strategy: RSI Divergence", "rsi_divergence.md"),
    ("Strategy: Supply/Demand", "supply_demand.md"),
    ("Strategy: VWAP Rejection", "vwap_rejection.md"),
    ("Backtest: XAUUSD", None),
    ("Backtest: Multi-Symbol", None),
    ("Backtest: Strategy Comparison", None),
    ("Backtest: MTM/MRB/MLB", None),
    ("Backtest: Cost Analysis", None),
    ("Macro: Dashboard", None),
    ("Macro: Yield Curve", None),
    ("Macro: Credit Markets", None),
    ("Macro: Liquidity", None),
    ("Macro: Cross-Market", None),
    ("Macro: Weekly Review", None),
    ("ML: Model Registry", None),
    ("ML: Training Results", None),
    ("Trade Journal", None),
    ("Risk Management", None),
    ("Regime Analysis", None),
    ("Signal Quality", None),
    ("P&L Attribution", None),
    ("Ensemble Optimizer", None),
    ("System Architecture", None),
    ("XAUUSD Playbook", None),
    ("Multi-Asset Overview", None),
    ("Daily Briefing", None),
]


def read_file(p):
    try:
        return p.read_text(encoding="utf-8")
    except:
        return ""


def get_source_content(nb_name):
    """Get source content for a notebook"""
    content = ""

    if "BOS/CHOCH" in nb_name:
        content = read_file(STRATEGIES / "bos_choch.md")
    elif "EMA Cross" in nb_name:
        content = read_file(STRATEGIES / "ema_cross.md")
    elif "Fair Value Gap" in nb_name:
        content = read_file(STRATEGIES / "fair_value_gap.md")
    elif "Fibonacci" in nb_name:
        content = read_file(STRATEGIES / "fibonacci.md")
    elif "Liquidity Sweep" in nb_name:
        content = read_file(STRATEGIES / "liquidity_sweep.md")
    elif "London Breakout" in nb_name:
        content = read_file(STRATEGIES / "london_breakout.md")
    elif "Multi-TF" in nb_name:
        content = read_file(STRATEGIES / "multi_tf_align.md")
    elif "News Fade" in nb_name:
        content = read_file(STRATEGIES / "news_fade.md")
    elif "Opening Range" in nb_name:
        content = read_file(STRATEGIES / "opening_range.md")
    elif "Order Block" in nb_name:
        content = read_file(STRATEGIES / "order_block.md")
    elif "RSI Divergence" in nb_name:
        content = read_file(STRATEGIES / "rsi_divergence.md")
    elif "Supply/Demand" in nb_name:
        content = read_file(STRATEGIES / "supply_demand.md")
    elif "VWAP Rejection" in nb_name:
        content = read_file(STRATEGIES / "vwap_rejection.md")
    elif "XAUUSD" in nb_name and "Backtest" in nb_name:
        for f in BACKTEST.glob("*XAUUSD*"):
            content += read_file(f) + "\n\n"
    elif "Multi-Symbol" in nb_name:
        for f in BACKTEST.glob("*.md"):
            content += read_file(f) + "\n\n"
        content = content[:30000]
    elif "Strategy Comparison" in nb_name:
        for f in BACKTEST.glob("*.md"):
            content += read_file(f) + "\n\n"
        content = content[:30000]
    elif "MTM" in nb_name or "MRB" in nb_name or "MLB" in nb_name:
        for f in BACKTEST.glob("*MTM*"):
            content += read_file(f) + "\n"
        for f in BACKTEST.glob("*MRB*"):
            content += read_file(f) + "\n"
        for f in BACKTEST.glob("*MLB*"):
            content += read_file(f) + "\n"
    elif "Cost" in nb_name:
        for f in (QUANT / "results").glob("backtest_*.json"):
            content += read_file(f)[:10000] + "\n\n"
    elif "Macro: Dashboard" in nb_name:
        for f in MACRO.glob("*.md"):
            if (
                "yield" not in f.name
                and "credit" not in f.name
                and "liquid" not in f.name
                and "cross" not in f.name
                and "weekly" not in f.name
            ):
                content += read_file(f) + "\n\n"
    elif "Yield" in nb_name:
        for f in MACRO.glob("*yield*"):
            content += read_file(f) + "\n\n"
    elif "Credit" in nb_name:
        for f in MACRO.glob("*credit*"):
            content += read_file(f) + "\n\n"
    elif "Liquidity" in nb_name:
        for f in MACRO.glob("*liquid*"):
            content += read_file(f) + "\n\n"
    elif "Cross-Market" in nb_name:
        for f in MACRO.glob("*cross*"):
            content += read_file(f) + "\n\n"
    elif "Weekly" in nb_name:
        for f in MACRO.glob("*weekly*"):
            content += read_file(f) + "\n\n"
    elif "Model Registry" in nb_name:
        for f in MODELS.glob("*.md"):
            content += read_file(f) + "\n\n"
        content = content[:30000]
    elif "Training Results" in nb_name:
        content = read_file(QUANT / "results" / "ml_training_results.json")[:30000]
    elif "Trade Journal" in nb_name:
        for f in TRADES.glob("*.md"):
            content += read_file(f) + "\n\n"
    elif "Risk" in nb_name:
        for f in (VAULT / "03-resources/trading/risk").glob("*.md"):
            content += read_file(f) + "\n\n"
    elif "Regime" in nb_name:
        for f in (VAULT / "03-resources/trading/regime").glob("*.md"):
            content += read_file(f) + "\n\n"
    elif "Signal" in nb_name:
        for f in (VAULT / "03-resources/trading/signals").glob("*.md"):
            content += read_file(f) + "\n\n"
    elif "Attribution" in nb_name:
        for f in (VAULT / "03-resources/trading/attribution").glob("*.md"):
            content += read_file(f) + "\n\n"
    elif "Ensemble" in nb_name:
        for f in (VAULT / "03-resources/trading/ensemble").glob("*.md"):
            content += read_file(f) + "\n\n"
    elif "Architecture" in nb_name:
        for f in (QUANT / "Meta").glob("*.md"):
            content += read_file(f) + "\n\n"
        content = content[:30000]
    elif "XAUUSD Playbook" in nb_name:
        for f in BACKTEST.glob("*XAUUSD*"):
            content += read_file(f) + "\n\n"
    elif "Multi-Asset" in nb_name:
        for f in STRATEGIES.glob("*.md"):
            if f.name != "Index.md":
                content += read_file(f) + "\n\n"
    elif "Daily Briefing" in nb_name:
        for f in MACRO.glob("*.md"):
            content += read_file(f) + "\n\n"
        for f in (VAULT / "03-resources/trading/regime").glob("*.md"):
            content += read_file(f) + "\n\n"

    return content[:30000] if content else ""


async def create_notebook_on_website(page, nb_name):
    """Create a notebook on NotebookLM and return its URL"""
    try:
        # Click the create button (Thai: สร้างใหม่)
        create_btn = page.locator(
            "[aria-label*='สร้าง Notebook ใหม่'], [aria-label*='Create new notebook'], button:has-text('สร้างใหม่'), button:has-text('Create')"
        ).first

        if await create_btn.count() > 0:
            await create_btn.click()
            await asyncio.sleep(4)
        else:
            print("    [WARN] Create button not found, trying grid click")
            # Try clicking on empty area or specific UI element
            await page.keyboard.press("Control+n")
            await asyncio.sleep(4)

        new_url = page.url
        if "/notebook/" in new_url:
            match = re.search(r"/notebook/([a-zA-Z0-9_-]+)", new_url)
            if match:
                nb_id = match.group(1)
                nb_url = f"https://notebooklm.google.com/notebook/{nb_id}"

                # Try to set the title
                try:
                    title_el = page.locator(
                        "[contenteditable='true'], input[type='text'], h1"
                    ).first
                    if await title_el.count() > 0:
                        await title_el.click()
                        await title_el.fill("")
                        await title_el.type(nb_name, delay=30)
                        await asyncio.sleep(1)
                except:
                    pass

                return nb_url

        return None
    except Exception as e:
        print(f"    [ERROR] {e}")
        return None


async def main():
    print("=" * 60)
    print("  NOTEBOOKLM FULL SETUP")
    print(f"  Notebooks: {len(NOTEBOOKS)}")
    print("=" * 60)

    all_results = {"notebooks": {}, "errors": []}

    # STEP 1: Create notebooks on NotebookLM website
    print("\n--- STEP 1: Create notebooks on website ---")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_PROFILE),
            headless=False,
            channel="chrome",
            args=["--disable-blink-features=AutomationControlled"],
            viewport={"width": 1280, "height": 800},
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        print("  Navigating to NotebookLM...")
        await page.goto(
            "https://notebooklm.google.com/", wait_until="networkidle", timeout=30000
        )
        await asyncio.sleep(3)

        if "accounts.google.com" in page.url:
            print("  NOT LOGGED IN. Waiting for manual login...")
            # Wait up to 120 seconds for login
            for i in range(24):
                await asyncio.sleep(5)
                if "notebooklm.google.com" in page.url:
                    print("  Logged in!")
                    break
                print(f"  Waiting for login... ({i*5}s)")

        print(f"  URL: {page.url}")

        # Create notebooks one by one
        created_urls = []

        for nb_name, _ in NOTEBOOKS:
            print(f"\n  Creating: {nb_name}")

            # Go back to home
            await page.goto(
                "https://notebooklm.google.com/",
                wait_until="networkidle",
                timeout=15000,
            )
            await asyncio.sleep(2)

            nb_url = await create_notebook_on_website(page, nb_name)

            if nb_url:
                created_urls.append({"name": nb_name, "url": nb_url})
                all_results["notebooks"][nb_name] = nb_url
                print(f"    OK: {nb_url}")
            else:
                all_results["errors"].append(f"create {nb_name}")
                print("    FAIL")

            await asyncio.sleep(1)

        await browser.close()

    print(f"\n  Created: {len(created_urls)} notebooks on website")

    # STEP 2: Register URLs in MCP library
    print("\n--- STEP 2: Register in MCP library ---")

    params = StdioServerParameters(command="npx", args=["-y", "notebooklm-mcp@latest"])

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            for nb_info in created_urls:
                nb_name = nb_info["name"]
                nb_url = nb_info["url"]
                nb_id = (
                    nb_name.lower().replace(" ", "-").replace(":", "").replace("/", "-")
                )

                print(f"  Registering: {nb_name}")
                try:
                    # Try update first
                    await s.call_tool("update_notebook", {"id": nb_id, "url": nb_url})
                    print("    OK: Updated")
                except:
                    try:
                        # Try add with URL
                        await s.call_tool(
                            "add_notebook",
                            {"name": nb_name, "description": nb_name, "url": nb_url},
                        )
                        print("    OK: Added")
                    except Exception as e:
                        print(f"    FAIL: {e}")
                        all_results["errors"].append(f"register {nb_name}: {e}")

            # STEP 3: Add sources
            print("\n--- STEP 3: Add sources ---")

            for nb_info in created_urls:
                nb_name = nb_info["name"]
                nb_url = nb_info["url"]

                content = get_source_content(nb_name)
                if not content:
                    print(f"  {nb_name}: no content, skipping")
                    continue

                print(f"  Adding source to: {nb_name}")
                try:
                    result = await s.call_tool(
                        "add_source",
                        {
                            "type": "text",
                            "content": content,
                            "title": nb_name,
                            "notebook_url": nb_url,
                        },
                    )
                    for c in result.content:
                        if hasattr(c, "text"):
                            print(f"    OK: {c.text[:100]}")
                except Exception as e:
                    print(f"    FAIL: {e}")
                    all_results["errors"].append(f"source {nb_name}: {e}")

    # Save results
    out = Path(__file__).parent / "notebooklm_setup_results.json"
    out.write_text(
        json.dumps(all_results, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print("\n" + "=" * 60)
    print(f"  NOTEBOOKS: {len(created_urls)}")
    print(f"  ERRORS: {len(all_results['errors'])}")
    print(f"  RESULTS: {out}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
