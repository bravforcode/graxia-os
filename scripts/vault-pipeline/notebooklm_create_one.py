"""
notebooklm_create_one.py — Create ONE notebook on NotebookLM, register it, add source, test ask_question
"""

import asyncio
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


async def main():
    print("=" * 50)
    print("  STEP 1: Create notebook on NotebookLM via Playwright")
    print("=" * 50)

    nb_url = None

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

        print(f"  URL: {page.url}")

        if "accounts.google.com" in page.url:
            print("  NOT LOGGED IN. Please log in manually in the browser.")
            print("  Press Enter after logging in...")
            await asyncio.get_event_loop().run_in_executor(None, input)
            await page.goto(
                "https://notebooklm.google.com/",
                wait_until="networkidle",
                timeout=30000,
            )
            await asyncio.sleep(3)

        # Take a screenshot to see the UI
        await page.screenshot(
            path=str(Path(__file__).parent / "notebooklm_screenshot.png")
        )
        print("  Screenshot saved to notebooklm_screenshot.png")

        # Try to find and click the "New Notebook" or "Create" button
        print("  Looking for create/new notebook button...")

        # Try multiple selectors
        selectors = [
            "button:has-text('Create new')",
            "button:has-text('New notebook')",
            "button:has-text('Create')",
            "[aria-label*='Create']",
            "[aria-label*='New']",
            "button:has-text('+')",
            ".create-button",
            "[data-test-id='create-notebook']",
        ]

        clicked = False
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if await btn.count() > 0:
                    print(f"  Found button: {sel}")
                    await btn.click()
                    clicked = True
                    await asyncio.sleep(3)
                    break
            except:
                continue

        if not clicked:
            # List all buttons for debugging
            buttons = await page.locator("button").all()
            print(f"  Found {len(buttons)} buttons:")
            for i, btn in enumerate(buttons[:10]):
                text = await btn.text_content()
                label = await btn.get_attribute("aria-label")
                print(f"    [{i}] text='{text}' aria-label='{label}'")

            print("  Could not find create button. Trying keyboard shortcut...")
            await page.keyboard.press("Control+n")
            await asyncio.sleep(3)

        # Check if a new notebook was created
        new_url = page.url
        print(f"  After create: {new_url}")

        if "/notebook/" in new_url:
            match = re.search(r"/notebook/([a-zA-Z0-9_-]+)", new_url)
            if match:
                nb_id = match.group(1)
                nb_url = f"https://notebooklm.google.com/notebook/{nb_id}"
                print(f"  CREATED: {nb_url}")

        await browser.close()

    if not nb_url:
        print("\n  FAILED: Could not create notebook")
        print("  Please create a notebook manually at https://notebooklm.google.com/")
        print(
            "  and paste the URL (format: https://notebooklm.google.com/notebook/<uuid>)"
        )
        nb_url = input("  Notebook URL: ").strip()
        if not nb_url:
            print("  No URL provided. Exiting.")
            return

    print(f"\n  Notebook URL: {nb_url}")

    # STEP 2: Register in MCP library and add source
    print("\n" + "=" * 50)
    print("  STEP 2: Register in MCP library")
    print("=" * 50)

    params = StdioServerParameters(command="npx", args=["-y", "notebooklm-mcp@latest"])

    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # Update existing notebook with real URL
            print("  Registering URL for strategy-bos-choch...")
            try:
                result = await s.call_tool(
                    "update_notebook", {"id": "strategy-bos-choch", "url": nb_url}
                )
                print("  OK: Notebook registered")
            except Exception as e:
                print(f"  FAIL: {e}")
                # Try adding as new notebook with URL
                try:
                    result = await s.call_tool(
                        "add_notebook",
                        {
                            "name": "Strategy: BOS/CHOCH",
                            "description": "Break of Structure / Change of Character strategy",
                            "url": nb_url,
                        },
                    )
                    print("  OK: Added as new notebook with URL")
                except Exception as e2:
                    print(f"  FAIL: {e2}")

            # Select the notebook
            print("  Selecting notebook...")
            try:
                await s.call_tool(
                    "select_notebook", {"notebook_id": "strategy-bos-choch"}
                )
                print("  OK: Selected")
            except Exception as e:
                print(f"  WARN: {e}")

            # Add a source
            print("  Adding source: BOS/CHOCH strategy...")
            bos_file = VAULT / "skills/trading/strategies/bos_choch.md"
            if bos_file.exists():
                source_text = bos_file.read_text(encoding="utf-8")
                try:
                    result = await s.call_tool(
                        "add_source",
                        {
                            "type": "text",
                            "content": source_text[:30000],
                            "title": "Strategy: BOS/CHOCH",
                            "notebook_url": nb_url,
                        },
                    )
                    for c in result.content:
                        if hasattr(c, "text"):
                            print(f"  OK: Source added - {c.text[:200]}")
                except Exception as e:
                    print(f"  FAIL: {e}")
            else:
                print("  WARN: bos_choch.md not found")

            # Test ask_question
            print("\n  Testing ask_question...")
            try:
                result = await s.call_tool(
                    "ask_question",
                    {
                        "question": "What is the BOS/CHOCH strategy? Summarize in 3 sentences.",
                        "notebook_url": nb_url,
                    },
                )
                for c in result.content:
                    if hasattr(c, "text"):
                        print(f"  ANSWER: {c.text[:500]}")
            except Exception as e:
                print(f"  FAIL: {e}")

    print("\n" + "=" * 50)
    print("  DONE")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
