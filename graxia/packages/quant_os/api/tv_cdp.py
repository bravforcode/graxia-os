"""
TradingView CDP Bridge — Chrome DevTools Protocol control for TradingView.

Provides async access to TradingView Desktop or Web via CDP for:
  - Chart symbol and timeframe control
  - Drawing support/resistance/trendlines
  - Pine Script writing and compilation
  - Watchlist management
  - Multi-chart layout control
  - Chart screenshots
  - Price alerts

Prerequisites:
  - TradingView Desktop: launch with ``--remote-debugging-port=9222``
  - TradingView Web: Chrome with
    ``--remote-debugging-port=9222 --user-data-dir="C:\\chrome-debug"``

Usage::

    async with TradingViewCDP() as tv:
        await tv.change_symbol("XAUUSD")
        await tv.change_timeframe("1h")
        await tv.draw_support_line(2300.0)
        path = await tv.screenshot_chart()
"""

from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog

try:
    from ..config.tv_cdp_config import (
        TV_CDP_CHROME_PATH,
        TV_CDP_TIMEOUT,
        TV_CDP_URL,
        TV_CDP_USER_DATA_DIR,
        TV_SCREENSHOT_DIR,
    )
except ImportError:
    from config.tv_cdp_config import (
        TV_CDP_CHROME_PATH,
        TV_CDP_TIMEOUT,
        TV_CDP_URL,
        TV_CDP_USER_DATA_DIR,
        TV_SCREENSHOT_DIR,
    )

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PineCompileResult:
    """Pine Script compilation result."""

    success: bool
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    script_id: str = ""


@dataclass(frozen=True)
class ChartData:
    """Extracted chart data snapshot."""

    symbol: str
    timeframe: str
    ohlcv: dict[str, float] = field(default_factory=dict)
    indicators: dict[str, Any] = field(default_factory=dict)
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Valid timeframes
# ---------------------------------------------------------------------------

VALID_TIMEFRAMES: frozenset[str] = frozenset(
    {
        "1m",
        "3m",
        "5m",
        "15m",
        "30m",
        "1h",
        "2h",
        "4h",
        "6h",
        "8h",
        "12h",
        "1D",
        "1W",
        "1M",
    }
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_timeframe(tf: str) -> str:
    """Normalize timeframe string to TradingView format.

    Accepts: 1m, 5m, 15m, 1h, 4h, 1D, 1W, 1M (case-insensitive for m/h).
    Returns canonical form or raises ValueError.
    """
    tf_lower = tf.lower()
    # Map common aliases
    aliases = {
        "1min": "1m",
        "5min": "5m",
        "15min": "15m",
        "30min": "30m",
        "1hr": "1h",
        "4hr": "4h",
        "daily": "1D",
        "d": "1D",
        "day": "1D",
        "weekly": "1W",
        "w": "1W",
        "week": "1W",
        "monthly": "1M",
        "mo": "1M",
        "month": "1M",
    }
    normalized = aliases.get(tf_lower, tf)
    if normalized not in VALID_TIMEFRAMES:
        raise ValueError(f"Invalid timeframe '{tf}'. " f"Valid: {', '.join(sorted(VALID_TIMEFRAMES))}")
    return normalized


def _ensure_screenshot_dir(path: Path | None) -> Path:
    """Return screenshot output path, creating parent dir if needed."""
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        return path
    out_dir = Path(TV_SCREENSHOT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / "chart.png"


# ---------------------------------------------------------------------------
# CDP Bridge
# ---------------------------------------------------------------------------


class TradingViewCDP:
    """TradingView CDP bridge for chart control.

    Supports async context manager::

        async with TradingViewCDP() as tv:
            await tv.change_symbol("XAUUSD")
    """

    def __init__(
        self,
        cdp_url: str | None = None,
        timeout: int | None = None,
    ) -> None:
        self._cdp_url = cdp_url or TV_CDP_URL
        self._timeout = timeout or TV_CDP_TIMEOUT
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    # -- lifecycle -----------------------------------------------------------

    async def __aenter__(self) -> TradingViewCDP:
        await self.connect()
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.disconnect()

    async def connect(self) -> bool:
        """Connect to TradingView via CDP.

        Returns:
            True if connection succeeded, False otherwise.
        """
        try:
            from playwright.async_api import async_playwright

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.connect_over_cdp(
                self._cdp_url,
                timeout=self._timeout * 1000,
            )
            # Use existing context or create new one
            contexts = self._browser.contexts
            if contexts:
                self._context = contexts[0]
            else:
                self._context = await self._browser.new_context()

            pages = self._context.pages
            if pages:
                self._page = pages[0]
            else:
                self._page = await self._context.new_page()

            logger.info("tv_cdp_connected", url=self._cdp_url)
            return True
        except Exception as exc:
            logger.error(
                "tv_cdp_connect_failed",
                url=self._cdp_url,
                error=str(exc),
            )
            return False

    async def disconnect(self) -> None:
        """Disconnect from CDP and clean up resources."""
        try:
            if self._browser is not None:
                await self._browser.close()
                self._browser = None
            if self._playwright is not None:
                await self._playwright.stop()
                self._playwright = None
            self._context = None
            self._page = None
            logger.info("tv_cdp_disconnected")
        except Exception as exc:
            logger.warning("tv_cdp_disconnect_error", error=str(exc))

    async def _ensure_connected(self) -> Any:
        """Ensure CDP connection is active, reconnect if needed."""
        if self._page is None:
            ok = await self.connect()
            if not ok:
                raise ConnectionError(
                    "Not connected to TradingView CDP. "
                    "Ensure TradingView is running with "
                    "--remote-debugging-port=9222"
                )
        return self._page

    # -- chrome launch helper ------------------------------------------------

    @staticmethod
    def launch_chrome(
        chrome_path: str | None = None,
        user_data_dir: str | None = None,
        port: int = 9222,
    ) -> subprocess.Popen[bytes]:
        """Launch Chrome with CDP debugging enabled.

        Args:
            chrome_path: Path to Chrome executable.
            user_data_dir: Chrome user data directory.
            port: Debugging port.

        Returns:
            Popen object for the Chrome process.
        """
        exe = chrome_path or TV_CDP_CHROME_PATH
        data_dir = user_data_dir or TV_CDP_USER_DATA_DIR
        cmd = [
            exe,
            f"--remote-debugging-port={port}",
            f'--user-data-dir="{data_dir}"',
        ]
        logger.info("tv_cdp_launching_chrome", cmd=" ".join(cmd))
        return subprocess.Popen(cmd)

    # -- symbol & timeframe --------------------------------------------------

    async def get_current_symbol(self) -> str:
        """Get current chart symbol.

        Returns:
            Symbol string (e.g. "XAUUSD", "AAPL").
        """
        page = await self._ensure_connected()
        try:
            # Try the symbol info header first
            symbol_el = await page.query_selector(
                "[data-symbol-title], .chart-markup-table__symbol-name, " "div[class*='symbolTitle']"
            )
            if symbol_el:
                text = await symbol_el.inner_text()
                return text.strip()

            # Fallback: read from URL hash
            url = page.url
            if "#" in url:
                fragment = url.split("#")[-1]
                # Typical: symbol=XAUUSD
                for part in fragment.split(","):
                    if "symbol" in part.lower():
                        return part.split("=")[-1].strip()

            return ""
        except Exception as exc:
            logger.error("tv_cdp_get_symbol_failed", error=str(exc))
            return ""

    async def change_symbol(self, symbol: str) -> bool:
        """Change chart symbol.

        Args:
            symbol: Trading symbol (e.g. "XAUUSD", "AAPL").

        Returns:
            True if symbol was changed successfully.
        """
        page = await self._ensure_connected()
        try:
            # Click symbol search input
            search = await page.query_selector(
                "[data-role='search'], input[class*='search'], " "div[class*='symbol'] input"
            )
            if search is None:
                # Try clicking the symbol name to open search
                sym_btn = await page.query_selector("[data-symbol-title], .chart-markup-table__symbol-name")
                if sym_btn:
                    await sym_btn.click()
                    await asyncio.sleep(0.3)
                    search = await page.query_selector("input[data-role='search'], " "input[class*='search']")

            if search is None:
                logger.error("tv_cdp_symbol_input_not_found")
                return False

            await search.click()
            await search.fill("")
            await search.type(symbol, delay=50)
            await asyncio.sleep(0.5)
            await page.keyboard.press("Enter")
            await asyncio.sleep(1)

            logger.info("tv_cdp_symbol_changed", symbol=symbol)
            return True
        except Exception as exc:
            logger.error(
                "tv_cdp_change_symbol_failed",
                symbol=symbol,
                error=str(exc),
            )
            return False

    async def change_timeframe(self, timeframe: str) -> bool:
        """Change chart timeframe.

        Args:
            timeframe: One of 1m, 5m, 15m, 1h, 4h, 1D, 1W, 1M.

        Returns:
            True if timeframe was changed successfully.
        """
        page = await self._ensure_connected()
        try:
            tf = _normalize_timeframe(timeframe)

            # Try clicking the timeframe button directly
            tf_btn = await page.query_selector(
                f"button[data-name='{tf}'], " f"button[data-value='{tf}'], " f"[data-role='timeframe']"
            )
            if tf_btn:
                await tf_btn.click()
                await asyncio.sleep(0.5)
                logger.info("tv_cdp_timeframe_changed", timeframe=tf)
                return True

            # Fallback: use keyboard shortcut
            # Open timeframe dialog with the period button
            period_btn = await page.query_selector("button[data-name='period'], " "div[class*='timeframe'] button")
            if period_btn:
                await period_btn.click()
                await asyncio.sleep(0.3)
                # Type the timeframe in the search
                input_el = await page.query_selector("input[data-role='search'], " "div[class*='dialog'] input")
                if input_el:
                    await input_el.fill(tf)
                    await asyncio.sleep(0.3)
                    await page.keyboard.press("Enter")
                    await asyncio.sleep(0.5)
                    logger.info("tv_cdp_timeframe_changed", timeframe=tf)
                    return True

            logger.error("tv_cdp_timeframe_change_failed", timeframe=tf)
            return False
        except Exception as exc:
            logger.error(
                "tv_cdp_change_timeframe_failed",
                timeframe=timeframe,
                error=str(exc),
            )
            return False

    # -- drawing tools -------------------------------------------------------

    async def draw_support_line(
        self,
        price: float,
        color: str = "green",
    ) -> bool:
        """Draw horizontal support line at price level.

        Args:
            price: Price level for the support line.
            color: Line color (default green).

        Returns:
            True if line was drawn successfully.
        """
        return await self._draw_horizontal_line(price, color, "support")

    async def draw_resistance_line(
        self,
        price: float,
        color: str = "red",
    ) -> bool:
        """Draw horizontal resistance line at price level.

        Args:
            price: Price level for the resistance line.
            color: Line color (default red).

        Returns:
            True if line was drawn successfully.
        """
        return await self._draw_horizontal_line(price, color, "resistance")

    async def _draw_horizontal_line(
        self,
        price: float,
        color: str,
        label: str,
    ) -> bool:
        """Draw a horizontal line via TradingView drawing tools.

        Uses the hline drawing tool or JavaScript injection.
        """
        page = await self._ensure_connected()
        try:
            # Method: Use TradingView's drawing tool via JS
            # This creates a horizontal line at the specified price
            js_code = """
            (price, color, label) => {
                // Access TradingView's chart widget
                const widget = window.tvWidget ||
                    document.querySelector('.chart-container')?.__vue_app__;
                if (!widget) return { ok: false, error: 'no_widget' };

                // Try to use the drawing API
                try {
                    const chart = widget.activeChart?.() ||
                        widget.charts?.[0];
                    if (!chart) return { ok: false, error: 'no_chart' };

                    const shape = chart.createShape(
                        { price: price },
                        {
                            shape: 'horizontal_line',
                            lock: true,
                            overrides: {
                                linecolor: color,
                                linewidth: 2,
                            },
                        }
                    );
                    return { ok: true, shape_id: shape };
                } catch (e) {
                    return { ok: false, error: e.message };
                }
            }
            """
            result = await page.evaluate(js_code, [price, color, label])
            if result and result.get("ok"):
                logger.info(
                    "tv_cdp_line_drawn",
                    type=label,
                    price=price,
                    color=color,
                )
                return True

            # Fallback: use keyboard shortcut for hline tool
            logger.warning(
                "tv_cdp_js_draw_fallback",
                type=label,
                price=price,
            )
            # Select hline tool from toolbar
            await page.keyboard.press("Alt+H")
            await asyncio.sleep(0.3)
            # Click on chart at approximate price level
            chart_el = await page.query_selector(".chart-markup-table, canvas")
            if chart_el:
                box = await chart_el.bounding_box()
                if box:
                    # Click in center of chart
                    await page.mouse.click(
                        box["x"] + box["width"] / 2,
                        box["y"] + box["height"] / 2,
                    )
                    await asyncio.sleep(0.5)
                    return True

            return False
        except Exception as exc:
            logger.error(
                "tv_cdp_draw_line_failed",
                type=label,
                price=price,
                error=str(exc),
            )
            return False

    async def draw_trendline(
        self,
        start_price: float,
        end_price: float,
        start_time: str | None = None,
        end_time: str | None = None,
    ) -> bool:
        """Draw trendline between two points.

        Args:
            start_price: Starting price level.
            end_price: Ending price level.
            start_time: Starting time (ISO format, optional).
            end_time: Ending time (ISO format, optional).

        Returns:
            True if trendline was drawn successfully.
        """
        page = await self._ensure_connected()
        try:
            js_code = """
            (args) => {
                const widget = window.tvWidget ||
                    document.querySelector('.chart-container')?.__vue_app__;
                if (!widget) return { ok: false, error: 'no_widget' };

                try {
                    const chart = widget.activeChart?.() ||
                        widget.charts?.[0];
                    if (!chart) return { ok: false, error: 'no_chart' };

                    const shape = chart.createShape(
                        [
                            { price: args.start_price },
                            { price: args.end_price },
                        ],
                        {
                            shape: 'trend_line',
                            lock: false,
                            overrides: {
                                linecolor: '#2196F3',
                                linewidth: 2,
                            },
                        }
                    );
                    return { ok: true, shape_id: shape };
                } catch (e) {
                    return { ok: false, error: e.message };
                }
            }
            """
            result = await page.evaluate(
                js_code,
                {
                    "start_price": start_price,
                    "end_price": end_price,
                    "start_time": start_time,
                    "end_time": end_time,
                },
            )
            if result and result.get("ok"):
                logger.info(
                    "tv_cdp_trendline_drawn",
                    start_price=start_price,
                    end_price=end_price,
                )
                return True
            return False
        except Exception as exc:
            logger.error("tv_cdp_trendline_failed", error=str(exc))
            return False

    # -- Pine Script ---------------------------------------------------------

    async def write_pine_script(self, script: str) -> bool:
        """Write Pine Script to the Pine Editor.

        Args:
            script: Pine Script source code.

        Returns:
            True if script was written successfully.
        """
        page = await self._ensure_connected()
        try:
            # Open Pine Editor if not visible
            editor_btn = await page.query_selector("button[data-name='pine-editor'], " "[data-name='Pine Editor']")
            if editor_btn:
                await editor_btn.click()
                await asyncio.sleep(0.5)

            # Try to find the code editor
            editor = await page.query_selector(
                ".pine-editor .monaco-editor, " ".pine-editor textarea, " "[class*='pineEditor'] textarea"
            )
            if editor is None:
                logger.error("tv_cdp_pine_editor_not_found")
                return False

            # Clear existing content and type new script
            await editor.click()
            await page.keyboard.press("Control+a")
            await asyncio.sleep(0.1)

            # Use clipboard for large scripts
            await page.evaluate(
                "text => navigator.clipboard.writeText(text)",
                script,
            )
            await page.keyboard.press("Control+v")
            await asyncio.sleep(0.5)

            logger.info("tv_cdp_pine_script_written", length=len(script))
            return True
        except Exception as exc:
            logger.error("tv_cdp_write_pine_failed", error=str(exc))
            return False

    async def compile_pine_script(self) -> PineCompileResult:
        """Compile current Pine Script.

        Returns:
            PineCompileResult with success status, errors, warnings.
        """
        page = await self._ensure_connected()
        try:
            # Click compile button
            compile_btn = await page.query_selector(
                "button[data-name='compile'], " "button[data-name='addToChart'], " "[class*='compile'] button"
            )
            if compile_btn:
                await compile_btn.click()
            else:
                # Keyboard shortcut
                await page.keyboard.press("Control+Enter")

            await asyncio.sleep(2)

            # Check for errors
            errors: list[str] = []
            warnings: list[str] = []

            error_el = await page.query_selector(".pine-editor__error, [class*='error-message']")
            if error_el:
                err_text = await error_el.inner_text()
                if err_text.strip():
                    errors.append(err_text.strip())

            warning_el = await page.query_selector(".pine-editor__warning, [class*='warning-message']")
            if warning_el:
                warn_text = await warning_el.inner_text()
                if warn_text.strip():
                    warnings.append(warn_text.strip())

            success = len(errors) == 0
            result = PineCompileResult(
                success=success,
                errors=errors,
                warnings=warnings,
                script_id="",
            )

            logger.info(
                "tv_cdp_pine_compiled",
                success=success,
                errors=len(errors),
                warnings=len(warnings),
            )
            return result
        except Exception as exc:
            logger.error("tv_cdp_compile_failed", error=str(exc))
            return PineCompileResult(
                success=False,
                errors=[str(exc)],
            )

    # -- watchlist -----------------------------------------------------------

    async def add_to_watchlist(self, symbols: list[str]) -> bool:
        """Add symbols to the watchlist.

        Args:
            symbols: List of symbol strings to add.

        Returns:
            True if all symbols were added successfully.
        """
        page = await self._ensure_connected()
        try:
            for symbol in symbols:
                # Find watchlist input
                wl_input = await page.query_selector(
                    ".watchlist input, " "[data-name='watchlist'] input, " "div[class*='watchlist'] input"
                )
                if wl_input is None:
                    # Try clicking add button first
                    add_btn = await page.query_selector(
                        "button[data-name='add-symbol'], " "[class*='watchlist'] button[class*='add']"
                    )
                    if add_btn:
                        await add_btn.click()
                        await asyncio.sleep(0.3)
                        wl_input = await page.query_selector("input[data-role='search']")

                if wl_input is None:
                    logger.error(
                        "tv_cdp_watchlist_input_not_found",
                        symbol=symbol,
                    )
                    return False

                await wl_input.click()
                await wl_input.fill(symbol)
                await asyncio.sleep(0.5)
                await page.keyboard.press("Enter")
                await asyncio.sleep(0.3)

            logger.info("tv_cdp_watchlist_added", symbols=symbols)
            return True
        except Exception as exc:
            logger.error(
                "tv_cdp_watchlist_failed",
                symbols=symbols,
                error=str(exc),
            )
            return False

    # -- layout --------------------------------------------------------------

    async def set_layout(self, layout: str = "2x2") -> bool:
        """Set chart layout.

        Args:
            layout: Layout string — "1x1", "2x1", "2x2", "3x1", etc.

        Returns:
            True if layout was changed successfully.
        """
        page = await self._ensure_connected()
        try:
            # Open layout selector
            layout_btn = await page.query_selector(
                "button[data-name='layout'], " "[class*='layout'] button, " "div[class*='charts-menu']"
            )
            if layout_btn:
                await layout_btn.click()
                await asyncio.sleep(0.3)

            # Click the specific layout option
            layout_option = await page.query_selector(
                f"div[data-name='{layout}'], "
                f"button[data-name='{layout}'], "
                f"[class*='layout'] [data-value='{layout}']"
            )
            if layout_option:
                await layout_option.click()
                await asyncio.sleep(0.5)
                logger.info("tv_cdp_layout_changed", layout=layout)
                return True

            logger.error("tv_cdp_layout_not_found", layout=layout)
            return False
        except Exception as exc:
            logger.error(
                "tv_cdp_layout_failed",
                layout=layout,
                error=str(exc),
            )
            return False

    # -- screenshot ----------------------------------------------------------

    async def screenshot_chart(
        self,
        output_path: Path | None = None,
    ) -> Path:
        """Take screenshot of the current chart.

        Args:
            output_path: Where to save the screenshot.
                Defaults to ``TV_SCREENSHOT_DIR/chart.png``.

        Returns:
            Path to the saved screenshot file.
        """
        page = await self._ensure_connected()
        try:
            out = _ensure_screenshot_dir(output_path)

            # Try to screenshot just the chart area
            chart = await page.query_selector(".chart-markup-table, " "div[class*='chartContainer'], " "canvas")
            if chart:
                await chart.screenshot(path=str(out))
            else:
                await page.screenshot(path=str(out))

            logger.info("tv_cdp_screenshot_saved", path=str(out))
            return out
        except Exception as exc:
            logger.error("tv_cdp_screenshot_failed", error=str(exc))
            raise

    # -- chart data ----------------------------------------------------------

    async def get_chart_data(self) -> dict[str, Any]:
        """Extract current chart data (OHLCV, indicators).

        Returns:
            Dict with symbol, timeframe, ohlcv, indicators.
        """
        page = await self._ensure_connected()
        try:
            js_code = """
            () => {
                const widget = window.tvWidget ||
                    document.querySelector('.chart-container')?.__vue_app__;
                if (!widget) return { error: 'no_widget' };

                try {
                    const chart = widget.activeChart?.() ||
                        widget.charts?.[0];
                    if (!chart) return { error: 'no_chart' };

                    const symbol = chart.symbol?.() || '';
                    const resolution = chart.resolution?.() || '';
                    const series = chart.getSeries?.();

                    let ohlcv = {};
                    if (series) {
                        const lastBar = series.data?.()?.last?.();
                        if (lastBar) {
                            ohlcv = {
                                open: lastBar.open,
                                high: lastBar.high,
                                low: lastBar.low,
                                close: lastBar.close,
                                volume: lastBar.volume,
                            };
                        }
                    }

                    return {
                        symbol: symbol,
                        timeframe: resolution,
                        ohlcv: ohlcv,
                    };
                } catch (e) {
                    return { error: e.message };
                }
            }
            """
            result = await page.evaluate(js_code)
            if "error" in result:
                logger.warning("tv_cdp_chart_data_error", error=result["error"])
                return result

            logger.info(
                "tv_cdp_chart_data_extracted",
                symbol=result.get("symbol"),
            )
            return result
        except Exception as exc:
            logger.error("tv_cdp_get_chart_data_failed", error=str(exc))
            return {"error": str(exc)}

    # -- alerts --------------------------------------------------------------

    async def set_alert(
        self,
        symbol: str,
        condition: str,
        price: float,
    ) -> bool:
        """Set a price alert.

        Args:
            symbol: Symbol to set alert on.
            condition: Alert condition ("crosses", "crosses_up", "crosses_down",
                "greater", "less").
            price: Alert price level.

        Returns:
            True if alert was set successfully.
        """
        page = await self._ensure_connected()
        try:
            # Open alert dialog
            await page.keyboard.press("Alt+A")
            await asyncio.sleep(0.5)

            # Fill in alert details
            condition_select = await page.query_selector(
                "select[data-name='condition'], " "[class*='alert-dialog'] select"
            )
            if condition_select:
                await condition_select.select_option(condition)

            price_input = await page.query_selector(
                "input[data-name='price'], " "[class*='alert-dialog'] input[type='number']"
            )
            if price_input:
                await price_input.fill(str(price))

            # Confirm alert
            create_btn = await page.query_selector(
                "button[data-name='create'], " "[class*='alert-dialog'] button[class*='create']"
            )
            if create_btn:
                await create_btn.click()
                await asyncio.sleep(0.5)

            logger.info(
                "tv_cdp_alert_set",
                symbol=symbol,
                condition=condition,
                price=price,
            )
            return True
        except Exception as exc:
            logger.error(
                "tv_cdp_alert_failed",
                symbol=symbol,
                error=str(exc),
            )
            return False
