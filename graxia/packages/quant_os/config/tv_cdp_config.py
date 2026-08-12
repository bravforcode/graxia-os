"""
TradingView CDP Bridge Configuration.

Environment-driven settings for TradingView Chrome DevTools Protocol connection.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# CDP Connection
# ---------------------------------------------------------------------------

TV_CDP_URL: str = os.getenv("TV_CDP_URL", "http://localhost:9222")
TV_CDP_TIMEOUT: int = int(os.getenv("TV_CDP_TIMEOUT", "30"))

# ---------------------------------------------------------------------------
# Chrome Launch
# ---------------------------------------------------------------------------

TV_CDP_CHROME_PATH: str = os.getenv(
    "TV_CDP_CHROME_PATH",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
)
TV_CDP_USER_DATA_DIR: str = os.getenv(
    "TV_CDP_USER_DATA_DIR",
    r"C:\chrome-debug",
)

# ---------------------------------------------------------------------------
# TradingView Selectors (CSS)
# ---------------------------------------------------------------------------

# Symbol input
TV_SELECTOR_SYMBOL_INPUT: str = os.getenv(
    "TV_SELECTOR_SYMBOL_INPUT",
    "input[data-role='search'][class*='search']",
)

# Timeframe button
TV_SELECTOR_TIMEFRAME_BTN: str = os.getenv(
    "TV_SELECTOR_TIMEFRAME_BTN",
    "button[data-role='timeframe']",
)

# Pine Editor
TV_SELECTOR_PINE_EDITOR: str = os.getenv(
    "TV_SELECTOR_PINE_EDITOR",
    ".pine-editor",
)

# Pine Editor code textarea
TV_SELECTOR_PINE_CODE: str = os.getenv(
    "TV_SELECTOR_PINE_CODE",
    ".pine-editor .view-lines",
)

# Pine compile button
TV_SELECTOR_COMPILE_BTN: str = os.getenv(
    "TV_SELECTOR_COMPILE_BTN",
    "button[data-name='compile']",
)

# Watchlist panel
TV_SELECTOR_WATCHLIST: str = os.getenv(
    "TV_SELECTOR_WATCHLIST",
    ".watchlist",
)

# Screenshot output directory
TV_SCREENSHOT_DIR: str = os.getenv(
    "TV_SCREENSHOT_DIR",
    r"C:\Users\menum\graxia os\graxia\packages\quant_os\artifacts\screenshots",
)
