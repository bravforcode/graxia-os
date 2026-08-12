"""
Visual Search API Routes — PixelRAG integration for chart image search.

Provides endpoints for indexing chart images, PDF reports, and HTML pages,
and searching by text query or image similarity using PixelRAG's FAISS index.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, File, HTTPException, Query, UploadFile

from ..analysis.visual_search import VisualChartSearch

logger = structlog.get_logger(__name__)

visual_router = APIRouter(prefix="/visual", tags=["visual-search"])

# Singleton instance — lazily initialized
_search: VisualChartSearch | None = None


def _get_search() -> VisualChartSearch:
    """Get or create the VisualChartSearch singleton."""
    global _search
    if _search is None:
        _search = VisualChartSearch()
    return _search


# ---------------------------------------------------------------------------
# Indexing endpoints
# ---------------------------------------------------------------------------


@visual_router.post("/index/chart")
async def index_chart(
    file: UploadFile = File(...),
    metadata: str | None = None,
) -> dict[str, Any]:
    """Index a chart image.

    Uploads a chart image (png, jpg, svg, webp) and adds it to the
    visual search index for later retrieval.

    Args:
        file: Chart image file upload.
        metadata: Optional JSON string of metadata to attach.

    Returns:
        Dict with indexing status and document ID.
    """
    import json

    search = _get_search()

    # Parse metadata if provided
    meta_dict: dict[str, Any] | None = None
    if metadata:
        try:
            meta_dict = json.loads(metadata)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid JSON in metadata parameter")

    # Save upload to temp file, then index
    suffix = Path(file.filename or "chart.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        ok = await search.index_chart(tmp_path, metadata=meta_dict)
        if not ok:
            raise HTTPException(status_code=422, detail="Failed to index chart image")
        return {"status": "indexed", "filename": file.filename, "size_bytes": len(content)}
    finally:
        tmp_path.unlink(missing_ok=True)


@visual_router.post("/index/url")
async def index_url(url: str = Query(...)) -> dict[str, Any]:
    """Index a web page by URL.

    Renders the page using pixelshot and indexes the screenshot tiles.

    Args:
        url: Fully-qualified URL to render and index.

    Returns:
        Dict with indexing status.
    """
    search = _get_search()
    ok = await search.index_url(url)
    if not ok:
        raise HTTPException(status_code=422, detail=f"Failed to index URL: {url}")
    return {"status": "indexed", "url": url}


@visual_router.post("/index/directory")
async def index_directory(
    dir_path: str = Query(...),
    patterns: list[str] | None = None,
) -> dict[str, Any]:
    """Index all matching files in a directory.

    Walks the directory recursively and indexes each file matching
    the supported extensions (images, PDFs, HTML).

    Args:
        dir_path: Root directory to scan.
        patterns: Optional glob patterns to match (default: all supported).

    Returns:
        Dict with count of indexed files.
    """
    search = _get_search()
    path = Path(dir_path)
    if not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Not a directory: {dir_path}")

    count = await search.index_directory(path, patterns=patterns)
    return {"status": "indexed", "directory": dir_path, "files_indexed": count}


# ---------------------------------------------------------------------------
# Search endpoints
# ---------------------------------------------------------------------------


@visual_router.post("/search/text")
async def search_by_text(
    query: str = Query(...),
    n_docs: int = Query(5, ge=1, le=50),
) -> dict[str, Any]:
    """Search by text query.

    Performs semantic search over indexed chart images and reports
    using a natural language description.

    Args:
        query: Natural language search query.
        n_docs: Maximum number of results to return.

    Returns:
        Dict with list of search results.
    """
    search = _get_search()
    results = await search.search_by_text(query, n_docs=n_docs)
    return {
        "query": query,
        "count": len(results),
        "results": [
            {
                "id": r.id,
                "score": round(r.score, 4),
                "image_path": str(r.image_path),
                "metadata": r.metadata,
                "snippet": r.snippet,
            }
            for r in results
        ],
    }


@visual_router.post("/search/image")
async def search_by_image(
    file: UploadFile = File(...),
    n_docs: int = Query(5, ge=1, le=50),
) -> dict[str, Any]:
    """Search by image similarity.

    Uploads a query image and finds visually similar indexed charts.

    Args:
        file: Query image file upload.
        n_docs: Maximum number of results to return.

    Returns:
        Dict with list of similar images.
    """
    search = _get_search()

    # Save upload to temp file
    suffix = Path(file.filename or "query.png").suffix or ".png"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)

    try:
        results = await search.search_by_image(tmp_path, n_docs=n_docs)
        return {
            "query_image": file.filename,
            "count": len(results),
            "results": [
                {
                    "id": r.id,
                    "score": round(r.score, 4),
                    "image_path": str(r.image_path),
                    "metadata": r.metadata,
                    "snippet": r.snippet,
                }
                for r in results
            ],
        }
    finally:
        tmp_path.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# Index management endpoints
# ---------------------------------------------------------------------------


@visual_router.get("/index/stats")
async def get_index_stats() -> dict[str, Any]:
    """Get current index statistics.

    Returns:
        Dict with total documents, index size, last updated, and source types.
    """
    search = _get_search()
    stats = search.get_index_stats()
    return stats.to_dict()


@visual_router.post("/index/build")
async def build_index() -> dict[str, Any]:
    """Build FAISS index from tiles.

    Compiles all screenshot tiles in the tiles directory into a
    searchable FAISS index.

    Returns:
        Dict with build status.
    """
    search = _get_search()
    ok = await search.build_index()
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to build FAISS index")
    return {"status": "built", "index_dir": str(search.index_dir)}


@visual_router.post("/serve")
async def serve_index(
    port: int = Query(30002, ge=1024, le=65535),
) -> dict[str, Any]:
    """Start serving the PixelRAG index.

    Launches the PixelRAG HTTP search service on the specified port.
    Note: First startup may take 1-5 minutes while the Qwen model downloads.

    Args:
        port: Port to serve on (default: 30002).

    Returns:
        Dict with serve status and URL.
    """
    search = _get_search()
    ok = await search.serve_index(port=port)
    if not ok:
        raise HTTPException(status_code=500, detail=f"Failed to start PixelRAG serve on port {port}")
    return {"status": "serving", "port": port, "url": f"http://localhost:{port}"}
