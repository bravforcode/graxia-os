"""
notebooklm_add_sources.py — Direct Playwright: dismiss overlay, add ALL sources
Uses MCP server's persistent browser context (already authenticated)
"""

import asyncio
import os
from pathlib import Path
from playwright.async_api import async_playwright

VAULT = Path(os.environ["USERPROFILE"]) / "Documents" / "ObsidianVault" / "Second Brain"
NB_URL = "https://notebooklm.google.com/notebook/f6b81dd1-a298-4709-a018-c4aec5269e5c?authuser=1"
CHROME_PROFILE = (
    Path(os.environ["USERPROFILE"]) / "AppData/Local/notebooklm-mcp/Data/chrome_profile"
)


def read_file(p):
    try:
        return p.read_text(encoding="utf-8")
    except:
        return ""


def get_all_sources():
    srcs = []
    for sub in [
        ("Strategy", VAULT / "skills/trading/strategies"),
        ("Backtest", VAULT / "03-resources/trading/backtest"),
        ("Macro", VAULT / "03-resources/trading/macro"),
        ("Model", VAULT / "03-resources/trading/models"),
        ("Trade", VAULT / "07-Daily/trades"),
        ("Risk", VAULT / "03-resources/trading/risk"),
        ("Regime", VAULT / "03-resources/trading/regime"),
        ("Signals", VAULT / "03-resources/trading/signals"),
        ("Attribution", VAULT / "03-resources/trading/attribution"),
        ("Ensemble", VAULT / "03-resources/trading/ensemble"),
    ]:
        prefix, d = sub
        if not d.exists():
            continue
        for f in sorted(d.glob("*.md")):
            if f.name == "Index.md":
                continue
            txt = read_file(f)
            if len(txt.strip()) > 50:
                srcs.append((f"{prefix}: {f.stem}", txt[:500000]))
    return srcs


async def dismiss_overlay(page):
    """Try to dismiss any overlay/modal blocking the page"""
    # Try Escape key
    await page.keyboard.press("Escape")
    await asyncio.sleep(1)

    # Try clicking outside any modal
    await page.mouse.click(10, 10)
    await asyncio.sleep(0.5)

    # Try clicking any close/dismiss buttons
    for sel in [
        'button[aria-label="Close"]',
        'button[aria-label="Dismiss"]',
        'button[aria-label="Got it"]',
        'button[aria-label="OK"]',
        'button[aria-label="Close dialog"]',
        ".cdk-overlay-backdrop",
    ]:
        try:
            el = page.locator(sel).first
            if await el.is_visible(timeout=500):
                await el.click(timeout=2000)
                await asyncio.sleep(0.5)
        except:
            pass


async def add_text_source(page, title, content, nb_url):
    """Add a single text source via the NotebookLM UI"""
    # Navigate to notebook
    await page.goto(nb_url, wait_until="networkidle", timeout=30000)
    await asyncio.sleep(2)

    # Dismiss overlay
    await dismiss_overlay(page)
    await asyncio.sleep(1)

    # Click "Add source" button
    add_btn = page.locator(
        'button.add-source-button, button[aria-label*="เพิ่มแหล่งข้อมูล"], button[aria-label*="Add source"]'
    ).first
    try:
        await add_btn.click(timeout=10000)
        await asyncio.sleep(1)
    except:
        # Try force click
        await add_btn.click(force=True, timeout=5000)
        await asyncio.sleep(1)

    # Select "Copied text" / text source option
    text_opt = page.locator(
        'button:has-text("Copied text"), button:has-text("คัดลอก"), [data-source-type="text"]'
    ).first
    try:
        await text_opt.click(timeout=5000)
        await asyncio.sleep(1)
    except:
        # Try menu item
        text_opt2 = page.locator("text=Copied text, text=คัดลอก").first
        try:
            await text_opt2.click(timeout=3000)
            await asyncio.sleep(1)
        except:
            pass

    # Fill title
    title_input = page.locator(
        'input[placeholder*="title"], input[placeholder*="ชื่อ"], input[aria-label*="title"]'
    ).first
    try:
        await title_input.fill(title, timeout=3000)
    except:
        pass

    # Fill content
    textarea = page.locator('textarea, [contenteditable="true"]').first
    try:
        await textarea.fill(content, timeout=5000)
    except:
        # Try typing
        await textarea.type(content[:10000], delay=0)

    # Click Submit/Paste button
    submit = page.locator(
        'button[type="submit"], button:has-text("Insert"), button:has-text("เพิ่ม"), button:has-text("Paste")'
    ).first
    try:
        await submit.click(timeout=5000)
        await asyncio.sleep(2)
        return True
    except:
        return False


async def main():
    print("=" * 60)
    print("  ADDING ALL SOURCES VIA PLAYWRIGHT")
    print("=" * 60)

    all_sources = get_all_sources()
    print(f"  Sources: {len(all_sources)}")
    total = sum(len(t) for _, t in all_sources)
    print(f"  Total size: {total/1000:.0f} KB")

    async with async_playwright() as p:
        # Use MCP server's Chrome profile for auth
        browser = await p.chromium.launch_persistent_context(
            str(CHROME_PROFILE),
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
            user_data_dir=str(CHROME_PROFILE),
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        # Navigate to notebook
        print("\nNavigating to notebook...")
        await page.goto(NB_URL, wait_until="networkidle", timeout=30000)
        await asyncio.sleep(3)

        # Check if authenticated
        if "accounts.google.com" in page.url:
            print("  NOT AUTHENTICATED - please login manually")
            input("  Press Enter after login...")

        print(f"  Page title: {await page.title()}")

        # Dismiss any overlays
        await dismiss_overlay(page)
        await asyncio.sleep(2)

        # Take screenshot to see state
        screenshot_path = Path(__file__).parent / "notebooklm_state.png"
        await page.screenshot(path=str(screenshot_path))
        print(f"  Screenshot: {screenshot_path}")

        # Add sources one by one
        ok = 0
        fail = 0
        for i, (name, content) in enumerate(all_sources, 1):
            print(f"  [{i:2d}/{len(all_sources)}] {name}...", end=" ", flush=True)
            try:
                result = await add_text_source(page, name, content, NB_URL)
                if result:
                    ok += 1
                    print("OK")
                else:
                    fail += 1
                    print("FAIL")
            except Exception as e:
                fail += 1
                print(f"ERROR: {str(e)[:50]}")

            # Brief pause between sources
            await asyncio.sleep(1)

        await browser.close()

    print(f"\n{'='*60}")
    print(f"  RESULT: {ok} added, {fail} failed, {len(all_sources)} total")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
