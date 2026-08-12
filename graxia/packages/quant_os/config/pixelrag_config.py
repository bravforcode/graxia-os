"""
PixelRAG Visual Search Configuration.

Environment-driven settings for PixelRAG visual search service connection
and default parameters.
"""

from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# PixelRAG Service
# ---------------------------------------------------------------------------

PIXELRAG_URL: str = os.getenv("PIXELRAG_URL", "http://localhost:30002")
PIXELRAG_HOST: str = os.getenv("PIXELRAG_HOST", "127.0.0.1")

# ---------------------------------------------------------------------------
# Directories
# ---------------------------------------------------------------------------

PIXELRAG_INDEX_DIR: Path = Path(os.getenv("PIXELRAG_INDEX_DIR", "data/visual_index"))
PIXELRAG_TILES_DIR: Path = Path(os.getenv("PIXELRAG_TILES_DIR", "data/visual_tiles"))

# ---------------------------------------------------------------------------
# Search Defaults
# ---------------------------------------------------------------------------

PIXELRAG_DEFAULT_N_DOCS: int = int(os.getenv("PIXELRAG_DEFAULT_N_DOCS", "5"))

# ---------------------------------------------------------------------------
# HTTP Client
# ---------------------------------------------------------------------------

PIXELRAG_REQUEST_TIMEOUT: float = float(os.getenv("PIXELRAG_REQUEST_TIMEOUT", "30.0"))
PIXELRAG_MAX_RETRIES: int = int(os.getenv("PIXELRAG_MAX_RETRIES", "3"))
PIXELRAG_RETRY_BACKOFF: float = float(os.getenv("PIXELRAG_RETRY_BACKOFF", "1.0"))

# ---------------------------------------------------------------------------
# CLI Timeouts (seconds)
# ---------------------------------------------------------------------------

PIXELSHOT_TIMEOUT: int = int(os.getenv("PIXELSHOT_TIMEOUT", "120"))
PIXELRAG_INDEX_TIMEOUT: int = int(os.getenv("PIXELRAG_INDEX_TIMEOUT", "300"))
PIXELRAG_SERVE_TIMEOUT: int = int(os.getenv("PIXELRAG_SERVE_TIMEOUT", "300"))
