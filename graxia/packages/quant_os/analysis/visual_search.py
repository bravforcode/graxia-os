"""
PixelRAG Visual Search — Visual RAG for trading charts and reports.

Provides semantic search over chart images, PDF reports, and HTML backtest
outputs using PixelRAG's visual FAISS index.  Supports both text queries
("show me head and shoulders pattern") and image-similarity queries.

Standalone module — no quant_os domain imports required.

Usage:
    from analysis.visual_search import VisualChartSearch

    search = VisualChartSearch()
    await search.index_directory(Path("reports/"))
    results = await search.search_by_text("double top pattern")
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from config.pixelrag_config import (
    PIXELRAG_DEFAULT_N_DOCS,
    PIXELRAG_INDEX_DIR,
    PIXELRAG_INDEX_TIMEOUT,
    PIXELRAG_MAX_RETRIES,
    PIXELRAG_REQUEST_TIMEOUT,
    PIXELRAG_TILES_DIR,
    PIXELRAG_URL,
    PIXELSHOT_TIMEOUT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Supported file patterns
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".svg", ".webp"}
PDF_EXTENSIONS: set[str] = {".pdf"}
HTML_EXTENSIONS: set[str] = {".html", ".htm"}
REPORT_EXTENSIONS: set[str] = PDF_EXTENSIONS | HTML_EXTENSIONS
ALL_EXTENSIONS: set[str] = IMAGE_EXTENSIONS | REPORT_EXTENSIONS

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class SearchResult:
    """Visual search result."""

    id: str
    score: float
    image_path: Path
    metadata: dict[str, Any]
    snippet: str = ""  # Text description if available

    def __post_init__(self) -> None:
        self.image_path = Path(self.image_path)


@dataclass
class IndexStats:
    """Index statistics."""

    total_documents: int
    index_size_mb: float
    last_updated: datetime
    source_types: dict[str, int] = field(default_factory=dict)
    # e.g. {"chart": 50, "report": 20, "url": 10}

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_documents": self.total_documents,
            "index_size_mb": round(self.index_size_mb, 2),
            "last_updated": self.last_updated.isoformat(),
            "source_types": self.source_types,
        }


# ---------------------------------------------------------------------------
# Main class
# ---------------------------------------------------------------------------


class VisualChartSearch:
    """Visual search for trading charts using PixelRAG.

    Lifecycle:
        1. ``index_*`` methods produce screenshot tiles in *tiles_dir*.
        2. ``build_index`` compiles tiles into a FAISS index.
        3. ``serve_index`` starts the PixelRAG HTTP search service.
        4. ``search_by_text`` / ``search_by_image`` query the service.

    All public async methods are safe to call from an async event loop.
    CLI operations (pixelshot, pixelrag index build) run in a thread pool
    so they do not block the loop.
    """

    def __init__(
        self,
        serve_url: str | None = None,
        tiles_dir: Path | None = None,
        index_dir: Path | None = None,
        request_timeout: float = PIXELRAG_REQUEST_TIMEOUT,
        max_retries: int = PIXELRAG_MAX_RETRIES,
    ) -> None:
        self.serve_url: str = serve_url or PIXELRAG_URL
        self.tiles_dir: Path = tiles_dir or PIXELRAG_TILES_DIR
        self.index_dir: Path = index_dir or PIXELRAG_INDEX_DIR
        self._request_timeout = request_timeout
        self._max_retries = max_retries
        self._client: httpx.AsyncClient | None = None
        self._meta_path: Path = self.index_dir / "quant_meta.json"
        self._metadata: dict[str, dict[str, Any]] = {}
        self._source_counts: dict[str, int] = {}

    # -- lifecycle helpers --------------------------------------------------

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init HTTP client with retry transport."""
        if self._client is None or self._client.is_closed:
            transport = httpx.AsyncHTTPTransport(retries=self._max_retries)
            self._client = httpx.AsyncClient(
                transport=transport,
                timeout=httpx.Timeout(self._request_timeout),
            )
        return self._client

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> VisualChartSearch:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    # -- metadata persistence -----------------------------------------------

    def _load_metadata(self) -> None:
        """Load persisted metadata from index directory."""
        if self._meta_path.exists():
            try:
                data = json.loads(self._meta_path.read_text(encoding="utf-8"))
                self._metadata = data.get("documents", {})
                self._source_counts = data.get("source_counts", {})
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load metadata: %s", exc)

    def _save_metadata(self) -> None:
        """Persist metadata to index directory."""
        self.index_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "documents": self._metadata,
            "source_counts": self._source_counts,
            "updated_at": datetime.now(UTC).isoformat(),
        }
        self._meta_path.write_text(
            json.dumps(payload, indent=2, default=str),
            encoding="utf-8",
        )

    # -- CLI wrappers (run in executor) -------------------------------------

    @staticmethod
    async def _run_cli(
        cmd: list[str],
        timeout: int = 120,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """Run a CLI command in the thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(cwd) if cwd else None,
            ),
        )

    # -- indexing methods ---------------------------------------------------

    async def index_chart(
        self,
        chart_path: Path,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        """Index a single chart image.

        Copies the image into the tiles directory so ``build_index`` picks it
        up on the next run.

        Args:
            chart_path: Path to chart image (png, jpg, svg, webp).
            metadata: Optional metadata dict to attach to this document.

        Returns:
            True if the chart was indexed successfully.
        """
        chart_path = Path(chart_path)
        if not chart_path.exists():
            logger.error("Chart file not found: %s", chart_path)
            return False

        if chart_path.suffix.lower() not in IMAGE_EXTENSIONS:
            logger.error("Unsupported image format: %s", chart_path.suffix)
            return False

        self.tiles_dir.mkdir(parents=True, exist_ok=True)
        dest = self.tiles_dir / chart_path.name

        # Avoid duplicates — add numeric suffix
        counter = 0
        while dest.exists():
            counter += 1
            dest = self.tiles_dir / f"{chart_path.stem}_{counter}{chart_path.suffix}"

        # Copy file
        import shutil

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, shutil.copy2, chart_path, dest)

        # Track metadata
        doc_id = dest.stem
        self._metadata[doc_id] = {
            "source_type": "chart",
            "original_path": str(chart_path),
            "tile_path": str(dest),
            "indexed_at": datetime.now(UTC).isoformat(),
            **(metadata or {}),
        }
        self._source_counts["chart"] = self._source_counts.get("chart", 0) + 1
        self._save_metadata()

        logger.info("Indexed chart: %s -> %s", chart_path, dest)
        return True

    async def index_report(self, report_path: Path) -> bool:
        """Index a PDF or HTML report.

        For HTML files, uses ``pixelshot`` to render them to screenshot tiles.
        For PDFs, copies them to the tiles directory for later processing.

        Args:
            report_path: Path to PDF or HTML report.

        Returns:
            True if the report was indexed successfully.
        """
        report_path = Path(report_path)
        if not report_path.exists():
            logger.error("Report file not found: %s", report_path)
            return False

        suffix = report_path.suffix.lower()
        if suffix not in REPORT_EXTENSIONS:
            logger.error("Unsupported report format: %s", suffix)
            return False

        self.tiles_dir.mkdir(parents=True, exist_ok=True)

        if suffix in HTML_EXTENSIONS:
            # Use pixelshot to render HTML to screenshot tiles
            out_dir = self.tiles_dir / report_path.stem
            out_dir.mkdir(parents=True, exist_ok=True)
            try:
                result = await self._run_cli(
                    ["pixelshot", str(report_path.resolve()), "-o", str(out_dir)],
                    timeout=PIXELSHOT_TIMEOUT,
                )
                if result.returncode != 0:
                    logger.error("pixelshot failed: %s", result.stderr)
                    return False
            except FileNotFoundError:
                logger.error("pixelshot not found — install with: pip install 'pixelrag[serve]'")
                return False
            except subprocess.TimeoutExpired:
                logger.error("pixelshot timed out for %s", report_path)
                return False
        else:
            # PDF — copy to tiles dir
            import shutil

            loop = asyncio.get_running_loop()
            dest = self.tiles_dir / report_path.name
            await loop.run_in_executor(None, shutil.copy2, report_path, dest)

        # Track metadata
        doc_id = report_path.stem
        self._metadata[doc_id] = {
            "source_type": "report",
            "format": suffix.lstrip("."),
            "original_path": str(report_path),
            "indexed_at": datetime.now(UTC).isoformat(),
        }
        self._source_counts["report"] = self._source_counts.get("report", 0) + 1
        self._save_metadata()

        logger.info("Indexed report: %s", report_path)
        return True

    async def index_url(self, url: str) -> bool:
        """Index a web page by URL using pixelshot.

        Args:
            url: Fully-qualified URL to render and index.

        Returns:
            True if the page was indexed successfully.
        """
        if not url.startswith(("http://", "https://")):
            logger.error("Invalid URL: %s", url)
            return False

        self.tiles_dir.mkdir(parents=True, exist_ok=True)

        # Derive a directory name from the URL
        slug = url.replace("https://", "").replace("http://", "").replace("/", "_").replace("?", "_")[:80]
        out_dir = self.tiles_dir / slug
        out_dir.mkdir(parents=True, exist_ok=True)

        try:
            result = await self._run_cli(
                ["pixelshot", url, "-o", str(out_dir)],
                timeout=PIXELSHOT_TIMEOUT,
            )
            if result.returncode != 0:
                logger.error("pixelshot failed for %s: %s", url, result.stderr)
                return False
        except FileNotFoundError:
            logger.error("pixelshot not found — install with: pip install 'pixelrag[serve]'")
            return False
        except subprocess.TimeoutExpired:
            logger.error("pixelshot timed out for %s", url)
            return False

        # Track metadata
        doc_id = slug
        self._metadata[doc_id] = {
            "source_type": "url",
            "url": url,
            "indexed_at": datetime.now(UTC).isoformat(),
        }
        self._source_counts["url"] = self._source_counts.get("url", 0) + 1
        self._save_metadata()

        logger.info("Indexed URL: %s -> %s", url, out_dir)
        return True

    async def index_directory(
        self,
        dir_path: Path,
        patterns: list[str] | None = None,
    ) -> int:
        """Index all matching files in a directory.

        Walks *dir_path* recursively and indexes each file that matches
        the given glob patterns (default: all supported extensions).

        Args:
            dir_path: Root directory to scan.
            patterns: Glob patterns to match (default: ``["**/*.png", …]``).

        Returns:
            Number of files successfully indexed.
        """
        dir_path = Path(dir_path)
        if not dir_path.is_dir():
            logger.error("Not a directory: %s", dir_path)
            return 0

        if patterns is None:
            patterns = [f"**/*{ext}" for ext in ALL_EXTENSIONS]

        files: list[Path] = []
        for pat in patterns:
            files.extend(dir_path.glob(pat))

        # Deduplicate
        files = sorted(set(files))

        if not files:
            logger.info("No matching files in %s", dir_path)
            return 0

        count = 0
        for f in files:
            suffix = f.suffix.lower()
            if suffix in IMAGE_EXTENSIONS:
                ok = await self.index_chart(f)
            elif suffix in REPORT_EXTENSIONS:
                ok = await self.index_report(f)
            else:
                continue
            if ok:
                count += 1

        logger.info("Indexed %d/%d files from %s", count, len(files), dir_path)
        return count

    # -- index build --------------------------------------------------------

    async def build_index(
        self,
        tiles_dir: Path | None = None,
        output_dir: Path | None = None,
    ) -> bool:
        """Build FAISS index from tiles.

        Runs ``pixelrag index build`` on the tiles directory.

        Args:
            tiles_dir: Directory containing screenshot tiles (default: self.tiles_dir).
            output_dir: Output directory for the FAISS index (default: self.index_dir).

        Returns:
            True if the index was built successfully.
        """
        tiles = tiles_dir or self.tiles_dir
        output = output_dir or self.index_dir

        if not tiles.exists() or not any(tiles.iterdir()):
            logger.error("Tiles directory is empty or missing: %s", tiles)
            return False

        output.mkdir(parents=True, exist_ok=True)

        try:
            result = await self._run_cli(
                [
                    "pixelrag",
                    "index",
                    "build",
                    "--input-dir",
                    str(tiles),
                    "--output-dir",
                    str(output),
                ],
                timeout=PIXELRAG_INDEX_TIMEOUT,
            )
            if result.returncode != 0:
                logger.error("pixelrag index build failed: %s", result.stderr)
                return False
        except FileNotFoundError:
            logger.error("pixelrag not found — install with: pip install 'pixelrag[serve]'")
            return False
        except subprocess.TimeoutExpired:
            logger.error("pixelrag index build timed out")
            return False

        logger.info("Built FAISS index: %s", output)
        return True

    # -- serve --------------------------------------------------------------

    async def serve_index(
        self,
        index_dir: Path | None = None,
        port: int = 30001,
    ) -> bool:
        """Start serving the PixelRAG index.

        Launches ``pixelrag serve`` as a background process.

        Args:
            index_dir: Directory containing the FAISS index (default: self.index_dir).
            port: Port to serve on.

        Returns:
            True if the server started successfully (health check passed).
        """
        index = index_dir or self.index_dir

        if not index.exists():
            logger.error("Index directory not found: %s", index)
            return False

        try:
            # Start serve in background
            proc = subprocess.Popen(
                [
                    "pixelrag",
                    "serve",
                    "--index-dir",
                    str(index),
                    "--port",
                    str(port),
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.error("pixelrag not found — install with: pip install 'pixelrag[serve]'")
            return False

        # Update serve URL
        self.serve_url = f"http://localhost:{port}"

        # Wait for server to be ready (health check)
        client = await self._get_client()
        for attempt in range(10):
            await asyncio.sleep(1.0)
            try:
                resp = await client.get(f"{self.serve_url}/health")
                if resp.status_code == 200:
                    logger.info("PixelRAG serve started on port %d (pid=%d)", port, proc.pid)
                    return True
            except httpx.HTTPError:
                continue

        # If we get here, server didn't start
        proc.terminate()
        logger.error("PixelRAG serve failed to start within 10s")
        return False

    # -- search methods -----------------------------------------------------

    async def search_by_text(
        self,
        query: str,
        n_docs: int = PIXELRAG_DEFAULT_N_DOCS,
    ) -> list[SearchResult]:
        """Search by text query.

        Args:
            query: Natural language query (e.g. "head and shoulders pattern").
            n_docs: Number of results to return.

        Returns:
            List of SearchResult ordered by relevance.
        """
        payload = {
            "queries": [{"text": query}],
            "n_docs": n_docs,
        }
        return await self._search(payload)

    async def search_by_image(
        self,
        image_path: Path,
        n_docs: int = PIXELRAG_DEFAULT_N_DOCS,
    ) -> list[SearchResult]:
        """Search by image similarity.

        Args:
            image_path: Path to query image.
            n_docs: Number of results to return.

        Returns:
            List of SearchResult ordered by visual similarity.
        """
        image_path = Path(image_path)
        if not image_path.exists():
            logger.error("Query image not found: %s", image_path)
            return []

        payload = {
            "queries": [{"image": str(image_path.resolve())}],
            "n_docs": n_docs,
        }
        return await self._search(payload)

    async def _search(self, payload: dict[str, Any]) -> list[SearchResult]:
        """Execute a search request against the PixelRAG serve API."""
        client = await self._get_client()

        try:
            resp = await client.post(
                f"{self.serve_url}/search",
                json=payload,
            )
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            logger.error("Search API error %d: %s", exc.response.status_code, exc.response.text)
            return []
        except httpx.HTTPError as exc:
            logger.error("Search request failed: %s", exc)
            return []

        data = resp.json()
        results: list[SearchResult] = []

        for item in data.get("results", []):
            doc_id = item.get("id", "")
            # Enrich with our metadata if available
            meta = self._metadata.get(doc_id, {})
            meta.update(item.get("metadata", {}))

            results.append(
                SearchResult(
                    id=doc_id,
                    score=float(item.get("score", 0.0)),
                    image_path=Path(item.get("image_path", "")),
                    metadata=meta,
                    snippet=item.get("snippet", ""),
                )
            )

        return results

    # -- stats --------------------------------------------------------------

    def get_index_stats(self) -> IndexStats:
        """Get current index statistics.

        Returns:
            IndexStats with document counts and index size.
        """
        self._load_metadata()

        total = len(self._metadata)
        size_mb = 0.0

        # Calculate index size on disk
        if self.index_dir.exists():
            for f in self.index_dir.rglob("*"):
                if f.is_file():
                    size_mb += f.stat().st_size
            size_mb /= 1024 * 1024  # Convert to MB

        # Determine last update
        last_updated = datetime.min.replace(tzinfo=UTC)
        for doc in self._metadata.values():
            ts_str = doc.get("indexed_at")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str)
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=UTC)
                    if ts > last_updated:
                        last_updated = ts
                except ValueError:
                    pass

        return IndexStats(
            total_documents=total,
            index_size_mb=round(size_mb, 2),
            last_updated=last_updated,
            source_types=dict(self._source_counts),
        )
