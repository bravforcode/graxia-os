"""
TradingView MCP Client Configuration.

Environment-driven settings for TradingView MCP server connection and defaults.
"""

from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

TV_MCP_URL: str = os.getenv("TV_MCP_URL", "http://localhost:30001")

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

TV_DEFAULT_TIMEFRAME: str = os.getenv("TV_DEFAULT_TIMEFRAME", "1D")
TV_SCREEN_EXCHANGE: str = os.getenv("TV_SCREEN_EXCHANGE", "NASDAQ")

# ---------------------------------------------------------------------------
# HTTP Client
# ---------------------------------------------------------------------------

TV_REQUEST_TIMEOUT: float = float(os.getenv("TV_REQUEST_TIMEOUT", "30.0"))
TV_MAX_RETRIES: int = int(os.getenv("TV_MAX_RETRIES", "3"))
TV_RETRY_BACKOFF: float = float(os.getenv("TV_RETRY_BACKOFF", "1.0"))
