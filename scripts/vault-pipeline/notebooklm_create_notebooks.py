"""
notebooklm_create_notebooks.py — Create real notebooks on NotebookLM via Playwright
Uses the same Chrome profile as notebooklm-mcp (already authenticated)
"""

import asyncio
import json
import os
import re
from pathlib import Path
from playwright.async_api import async_playwright

# Chrome profile used by notebooklm-mcp
CHROME_PROFILE = (
    Path(os.environ["USERPROFILE"]) / "AppData/Local/notebooklm-mcp/Data/chrome_profile"
)
OUTPUT_FILE = Path(__file__).parent / "notebooklm_real_notebooks.json"

# Notebook definitions — create the most important ones first
NOTEBOOKS_TO_CREATE = [
    # Strategies (13)
    (
        "Strategy: BOS/CHOCH",
        "Break of Structure and Change of Character strategy analysis, entries, exits, backtest results for XAUUSD and other pairs",
    ),
    (
        "Strategy: EMA Cross",
        "EMA crossover trend following strategy, multi-timeframe analysis, parameter optimization",
    ),
    (
        "Strategy: Fair Value Gap",
        "Fair Value Gap imbalances, institutional order flow, entry criteria and risk management",
    ),
    (
        "Strategy: Fibonacci",
        "Fibonacci retracement and extension strategy, confluence zones, key levels",
    ),
    (
        "Strategy: Liquidity Sweep",
        "Liquidity sweep and stop hunt detection, institutional manipulation patterns",
    ),
    (
        "Strategy: London Breakout",
        "London session breakout strategy, volatility expansion, first-hour range",
    ),
    (
        "Strategy: Multi-TF Alignment",
        "Multi-timeframe alignment, confluence across HTF/LTF, entry confirmation",
    ),
    (
        "Strategy: News Fade",
        "News fade strategy, trading against impulse moves after high-impact releases",
    ),
    (
        "Strategy: Opening Range",
        "Opening range breakout, first 15min/1hour range expansion patterns",
    ),
    (
        "Strategy: Order Block",
        "Order block strategy, institutional supply/demand zones, mitigation entries",
    ),
    (
        "Strategy: RSI Divergence",
        "RSI divergence strategy, hidden and regular divergences, momentum shifts",
    ),
    (
        "Strategy: Supply/Demand",
        "Supply and demand zones, fresh vs tested zones, rally-base-rally patterns",
    ),
    (
        "Strategy: VWAP Rejection",
        "VWAP rejection and mean reversion, intraday VWAP levels and bands",
    ),
    # Backtest (5)
    (
        "Backtest: XAUUSD",
        "XAUUSD gold backtest results across all strategies, timeframes, and market conditions",
    ),
    (
        "Backtest: Multi-Symbol",
        "Complete backtest suite: XAUUSD, EURUSD, GBPUSD, USDJPY, US30, NAS100, BTCUSD",
    ),
    (
        "Backtest: Strategy Comparison",
        "Strategy performance comparison, win rate, profit factor, Sharpe ratio across all symbols",
    ),
    (
        "Backtest: MTM/MRB/MLB",
        "Mean Trend Momentum, Mean Reversion Bias, Mean Linear Bias strategy variants",
    ),
    (
        "Backtest: Cost Analysis",
        "Transaction cost impact, spread and commission effects on strategy returns",
    ),
    # Macro (6)
    (
        "Macro: Dashboard",
        "Daily macro overview: VIX, GVZ, DXY, yields, regime detection, key events calendar",
    ),
    (
        "Macro: Yield Curve",
        "US yield curve analysis, real yields, inflation expectations, term premium",
    ),
    (
        "Macro: Credit Markets",
        "Credit spreads, HY OAS, financial stress indicators, corporate bonds",
    ),
    (
        "Macro: Liquidity",
        "Market liquidity: Fed balance sheet, RRP, TGA, net reserves, plumbing",
    ),
    (
        "Macro: Cross-Market",
        "Cross-market correlations: equities, bonds, FX, commodities, volatility",
    ),
    (
        "Macro: Weekly Review",
        "Weekly macro summary, key themes, regime shifts, outlook",
    ),
    # ML (4)
    (
        "ML: Model Registry",
        "All ML models: XGBoost, LightGBM, training metrics, feature importance",
    ),
    (
        "ML: Training Results",
        "Model training history, hyperparameters, validation scores, overfitting",
    ),
    (
        "ML: Feature Importance",
        "Feature importance rankings, SHAP values, feature engineering",
    ),
    (
        "ML: Live Performance",
        "Live model predictions, accuracy tracking, drift detection",
    ),
    # Trading Ops (6)
    (
        "Trade Journal",
        "Live trade journal: entries, exits, P&L, lessons learned, emotional notes",
    ),
    (
        "Risk Management",
        "Risk dashboard: drawdown, circuit breaker, kill switch, position sizing",
    ),
    (
        "Regime Analysis",
        "Market regime detection: trending, ranging, volatile, regime transitions",
    ),
    (
        "Signal Quality",
        "Signal quality metrics: hit rate, false positive analysis, signal decay",
    ),
    (
        "P&L Attribution",
        "P&L attribution by strategy, symbol, timeframe, session, condition",
    ),
    (
        "Ensemble Optimizer",
        "Ensemble weight optimization: MTM, MRB, MLB dynamic rebalancing",
    ),
    # System (4)
    (
        "System Architecture",
        "Trading system architecture: components, data flow, execution pipeline",
    ),
    (
        "XAUUSD Playbook",
        "Complete XAUUSD trading playbook: strategies, macro context, regime notes",
    ),
    (
        "Multi-Asset Overview",
        "Cross-asset analysis: correlations, relative strength, sector rotation",
    ),
    (
        "Daily Briefing",
        "Daily pre-market briefing: overnight moves, key levels, risk events",
    ),
]


async def create_notebooks():
    """Create notebooks on NotebookLM and return their URLs"""

    results = {"notebooks": [], "errors": []}

    async with async_playwright() as p:
        # Launch browser with the same profile as notebooklm-mcp
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=str(CHROME_PROFILE),
            headless=False,  # Need to see the browser for auth
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
            ],
            viewport={"width": 1280, "height": 800},
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        # Navigate to NotebookLM
        print("Navigating to NotebookLM...")
        await page.goto(
            "https://notebooklm.google.com/", wait_until="networkidle", timeout=30000
        )
        await asyncio.sleep(3)

        # Check if we're logged in
        current_url = page.url
        print(f"Current URL: {current_url}")

        if "accounts.google.com" in current_url:
            print("ERROR: Not logged in. Please log in manually.")
            print("The browser window should be open. Log in to your Google account.")
            print("Press Enter after logging in...")
            await asyncio.get_event_loop().run_in_executor(None, input)
            await page.goto(
                "https://notebooklm.google.com/",
                wait_until="networkidle",
                timeout=30000,
            )
            await asyncio.sleep(3)

        print(f"Logged in. URL: {page.url}")

        # Create notebooks
        for nb_name, nb_desc in NOTEBOOKS_TO_CREATE:
            try:
                print(f"\nCreating: {nb_name}")

                # Click "New Notebook" button (look for the + or Create button)
                # NotebookLM UI: there's usually a "Create new" or "+" button
                create_btn = page.locator(
                    "button:has-text('Create'), button:has-text('New'), [aria-label*='Create'], [aria-label*='New notebook']"
                ).first

                if await create_btn.count() > 0:
                    await create_btn.click()
                    await asyncio.sleep(2)
                else:
                    # Try finding by other selectors
                    print("  Looking for create button...")
                    # The UI might have a specific class or data attribute
                    all_buttons = await page.locator("button").all()
                    for btn in all_buttons:
                        text = await btn.text_content()
                        if text and (
                            "create" in text.lower()
                            or "new" in text.lower()
                            or "+" in text
                        ):
                            await btn.click()
                            await asyncio.sleep(2)
                            break

                # After clicking create, a new notebook should open
                # The URL will change to include the notebook ID
                await asyncio.sleep(3)
                new_url = page.url

                if "/notebook/" in new_url:
                    # Extract notebook ID from URL
                    match = re.search(r"/notebook/([a-zA-Z0-9_-]+)", new_url)
                    if match:
                        nb_id = match.group(1)
                        nb_url = f"https://notebooklm.google.com/notebook/{nb_id}"

                        # Set the title
                        title_input = page.locator(
                            "input[type='text'], [contenteditable='true'], h1"
                        ).first
                        if await title_input.count() > 0:
                            await title_input.fill("")
                            await title_input.fill(nb_name)
                            await asyncio.sleep(1)

                        results["notebooks"].append(
                            {
                                "name": nb_name,
                                "desc": nb_desc,
                                "url": nb_url,
                                "id": nb_id,
                            }
                        )
                        print(f"  OK: {nb_url}")
                    else:
                        print(f"  FAIL: Could not extract notebook ID from {new_url}")
                        results["errors"].append(f"{nb_name}: no ID in URL {new_url}")
                else:
                    print(f"  FAIL: URL doesn't contain /notebook/: {new_url}")
                    results["errors"].append(f"{nb_name}: unexpected URL {new_url}")

                # Go back to home for next notebook
                await page.goto(
                    "https://notebooklm.google.com/",
                    wait_until="networkidle",
                    timeout=15000,
                )
                await asyncio.sleep(2)

            except Exception as e:
                print(f"  ERROR: {e}")
                results["errors"].append(f"{nb_name}: {e}")
                # Try to recover
                try:
                    await page.goto(
                        "https://notebooklm.google.com/",
                        wait_until="networkidle",
                        timeout=15000,
                    )
                    await asyncio.sleep(2)
                except:
                    pass

        await browser.close()

    return results


def main():
    print("=" * 60)
    print("  NotebookLM Notebook Creator (Playwright)")
    print(f"  Creating {len(NOTEBOOKS_TO_CREATE)} notebooks")
    print("=" * 60)

    results = asyncio.run(create_notebooks())

    print("\n" + "=" * 60)
    print(f"  Created: {len(results['notebooks'])}")
    print(f"  Errors:  {len(results['errors'])}")

    if results["errors"]:
        print("\n  Errors:")
        for e in results["errors"]:
            print(f"    - {e}")

    # Save results
    OUTPUT_FILE.write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    print(f"\n  Saved: {OUTPUT_FILE}")

    return results


if __name__ == "__main__":
    main()
