#!/usr/bin/env python3
"""Import all Notion content reachable by one or more tokens into Graxia.

Security and correctness contract:

* Tokens are accepted only through process environment variables or stdin.
  They are never written to disk, included in manifests, or logged.
* The Notion API is read-only.  Exported pages are written to a dedicated
  namespace and are safe to re-run.
* Discovery and content retrieval are paginated.  Incomplete pages, unknown
  blocks, rate-limit failures, and inaccessible content remain visible in the
  manifest; the importer never calls a partial export complete.
* Graxia indexing uses the existing vault/index_markdown_content path.  The
  broken generic document endpoint is intentionally not used.

Examples (PowerShell):

  # Inventory only; paste one token per line, then Ctrl+Z/Enter on Windows.
  Get-Content .\tokens.txt | python scripts\notion_to_graxia.py \
      --token-stdin --dry-run

  # Full export to the configured Obsidian vault, then index only that
  # namespace into Graxia.  --allow-remote-db is required for Supabase.
  Get-Content .\tokens.txt | python scripts\notion_to_graxia.py \
      --token-stdin --output-dir "C:\\...\\Second Brain\\knowledge\\Notion" \
      --include-archived --index --vault-root "C:\\...\\Second Brain" \
      --allow-remote-db

The token file is only an example; do not save tokens in the repository.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import sys
import tempfile
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


API_BASE = "https://api.notion.com/v1"
DEFAULT_API_VERSION = "2026-03-11"
DEFAULT_PAGE_SIZE = 100
DEFAULT_TIMEOUT_SECONDS = 45.0
MAX_RETRIES = 6
RETRY_STATUSES = {429, 500, 502, 503, 504, 529}
TOKEN_ENV_NAMES = ("NOTION_TOKEN_1", "NOTION_TOKEN_2")


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def scrub(value: Any, secrets: Iterable[str] = ()) -> Any:
    """Remove tokens from arbitrary error/manifest values recursively."""

    secret_values = [secret for secret in secrets if secret]
    if isinstance(value, str):
        output = value
        for secret in secret_values:
            output = output.replace(secret, "<redacted-token>")
        return output
    if isinstance(value, list):
        return [scrub(item, secret_values) for item in value]
    if isinstance(value, dict):
        return {str(key): scrub(item, secret_values) for key, item in value.items()}
    return value


class NotionAPIError(RuntimeError):
    """Structured Notion API failure with no token material."""

    def __init__(self, status: int, code: str, message: str, *, path: str):
        self.status = status
        self.code = code
        self.message = message
        self.path = path
        super().__init__(f"Notion API {status} {code} at {path}: {message}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "code": self.code,
            "message": self.message,
            "path": self.path,
        }


@dataclass
class SourceRuntime:
    label: str
    client: "NotionClient"
    me: dict[str, Any] = field(default_factory=dict)
    discovery_errors: list[dict[str, Any]] = field(default_factory=list)
    incomplete_queries: list[str] = field(default_factory=list)
    discovered_pages: int = 0
    discovered_data_sources: int = 0


@dataclass
class MergedPage:
    page: dict[str, Any]
    sources: set[str] = field(default_factory=set)
    data_sources: set[str] = field(default_factory=set)


@dataclass
class MergedDataSource:
    data_source: dict[str, Any]
    sources: set[str] = field(default_factory=set)


def _retry_after(headers: Mapping[str, str]) -> float | None:
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if not raw:
        return None
    try:
        return max(0.0, min(float(raw), 60.0))
    except ValueError:
        return None


class NotionClient:
    """Small dependency-free Notion REST client with bounded retries."""

    def __init__(
        self,
        token: str,
        *,
        api_version: str = DEFAULT_API_VERSION,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        sleep_fn: Callable[[float], None] = time.sleep,
        min_interval: float = 0.34,
    ) -> None:
        if not token or not token.strip():
            raise ValueError("Notion token must not be empty")
        self._token = token.strip()
        self.api_version = api_version
        self.timeout = timeout
        self._sleep = sleep_fn
        self.min_interval = min_interval
        self._last_request_at = 0.0
        self.incomplete_queries: list[str] = []

    @property
    def token_fingerprint(self) -> str:
        """Non-secret diagnostic identifier; token itself never leaves client."""

        return hashlib.sha256(self._token.encode("utf-8")).hexdigest()[:12]

    def _wait_before_request(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval:
            self._sleep(self.min_interval - elapsed)

    def request_json(
        self,
        method: str,
        path: str,
        *,
        body: dict[str, Any] | None = None,
        query: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        query_pairs: list[tuple[str, str]] = []
        for key, value in (query or {}).items():
            if value is None:
                continue
            if isinstance(value, list):
                query_pairs.extend((key, str(item)) for item in value)
            else:
                query_pairs.append((key, str(value).lower() if isinstance(value, bool) else str(value)))
        url = f"{API_BASE}{path}"
        if query_pairs:
            url = f"{url}?{urllib.parse.urlencode(query_pairs)}"

        encoded_body = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Notion-Version": self.api_version,
            "Accept": "application/json",
            "User-Agent": "GraxiaNotionImporter/1.0",
        }
        if encoded_body is not None:
            headers["Content-Type"] = "application/json"

        for attempt in range(MAX_RETRIES + 1):
            self._wait_before_request()
            request = urllib.request.Request(url, data=encoded_body, headers=headers, method=method)
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    self._last_request_at = time.monotonic()
                    raw = response.read()
                    if not raw:
                        return {}
                    parsed = json.loads(raw.decode("utf-8"))
                    if not isinstance(parsed, dict):
                        raise NotionAPIError(502, "invalid_response", "Notion response was not an object", path=path)
                    return parsed
            except urllib.error.HTTPError as exc:
                self._last_request_at = time.monotonic()
                raw = exc.read()
                try:
                    payload = json.loads(raw.decode("utf-8")) if raw else {}
                except (UnicodeDecodeError, json.JSONDecodeError):
                    payload = {}
                if exc.code in RETRY_STATUSES and attempt < MAX_RETRIES:
                    retry_after = _retry_after(exc.headers) or min(2.0**attempt, 20.0)
                    self._sleep(retry_after)
                    continue
                code = str(payload.get("code") or f"http_{exc.code}")
                message = str(payload.get("message") or exc.reason or "request failed")
                raise NotionAPIError(exc.code, code, message, path=path) from None
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                self._last_request_at = time.monotonic()
                if attempt < MAX_RETRIES:
                    self._sleep(min(2.0**attempt, 20.0))
                    continue
                raise NotionAPIError(599, "transport_error", str(exc), path=path) from exc

    def get_me(self) -> dict[str, Any]:
        return self.request_json("GET", "/users/me")

    def _paginate_post(
        self,
        path: str,
        body: dict[str, Any],
        *,
        query: Mapping[str, Any] | None = None,
        label: str,
    ) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        while True:
            request_body = dict(body)
            request_body["page_size"] = min(int(request_body.get("page_size", DEFAULT_PAGE_SIZE)), 100)
            if cursor:
                request_body["start_cursor"] = cursor
            response = self.request_json("POST", path, body=request_body, query=query)
            page_results = response.get("results") or []
            if not isinstance(page_results, list):
                raise NotionAPIError(502, "invalid_response", "results was not a list", path=path)
            results.extend(item for item in page_results if isinstance(item, dict))
            request_status = response.get("request_status") or {}
            if request_status.get("type") == "incomplete":
                reason = str(request_status.get("incomplete_reason") or "unknown")
                self.incomplete_queries.append(f"{label}:{reason}")
            if not response.get("has_more"):
                break
            next_cursor = response.get("next_cursor")
            if not next_cursor or next_cursor == cursor:
                self.incomplete_queries.append(f"{label}:cursor_stalled")
                break
            cursor = str(next_cursor)
        return results

    def search(self, object_type: str, *, include_archived: bool) -> list[dict[str, Any]]:
        """Search live content and, when requested, a second trash partition."""

        partitions = [False, True] if include_archived else [False]
        merged: dict[str, dict[str, Any]] = {}
        for in_trash in partitions:
            filter_body: dict[str, Any] = {"property": "object", "value": object_type}
            if in_trash:
                filter_body["in_trash"] = True
            results = self._paginate_post(
                "/search",
                {"page_size": DEFAULT_PAGE_SIZE, "filter": filter_body},
                label=f"search:{object_type}:trash={in_trash}",
            )
            for item in results:
                item_id = str(item.get("id") or _json_text(item))
                merged[item_id] = item
        return list(merged.values())

    def query_data_source(self, data_source_id: str, *, include_archived: bool) -> list[dict[str, Any]]:
        partitions = [False, True] if include_archived else [False]
        merged: dict[str, dict[str, Any]] = {}
        for in_trash in partitions:
            query = {"in_trash": True} if in_trash else None
            path = f"/data_sources/{urllib.parse.quote(data_source_id, safe='')}/query"
            try:
                results = self._paginate_post(
                    path,
                    {"page_size": DEFAULT_PAGE_SIZE, "result_type": "page"},
                    query=query,
                    label=f"data_source:{data_source_id}:trash={in_trash}",
                )
            except NotionAPIError as exc:
                # Some current API deployments reject the documented query
                # parameter.  Try the body form once, then expose the gap.
                if not in_trash or exc.status != 400 or exc.code != "validation_error":
                    raise
                try:
                    results = self._paginate_post(
                        path,
                        {"page_size": DEFAULT_PAGE_SIZE, "result_type": "page", "in_trash": True},
                        label=f"data_source:{data_source_id}:trash=true-body",
                    )
                except NotionAPIError:
                    self.incomplete_queries.append(f"data_source:{data_source_id}:archived_rows_unavailable")
                    continue
            for item in results:
                item_id = str(item.get("id") or _json_text(item))
                merged[item_id] = item
        return list(merged.values())

    def get_data_source(self, data_source_id: str) -> dict[str, Any]:
        return self.request_json("GET", f"/data_sources/{urllib.parse.quote(data_source_id, safe='')}")

    def get_page(self, page_id: str) -> dict[str, Any]:
        return self.request_json("GET", f"/pages/{urllib.parse.quote(page_id, safe='')}")

    def get_page_markdown(self, page_id: str) -> dict[str, Any]:
        return self.request_json("GET", f"/pages/{urllib.parse.quote(page_id, safe='')}/markdown")

    def list_block_children(self, block_id: str) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        cursor: str | None = None
        path = f"/blocks/{urllib.parse.quote(block_id, safe='')}/children"
        while True:
            query: dict[str, Any] = {"page_size": DEFAULT_PAGE_SIZE}
            if cursor:
                query["start_cursor"] = cursor
            response = self.request_json("GET", path, query=query)
            page_results = response.get("results") or []
            if isinstance(page_results, list):
                results.extend(item for item in page_results if isinstance(item, dict))
            if not response.get("has_more"):
                break
            next_cursor = response.get("next_cursor")
            if not next_cursor or next_cursor == cursor:
                self.incomplete_queries.append(f"blocks:{block_id}:cursor_stalled")
                break
            cursor = str(next_cursor)
        return results


def rich_text_to_text(items: Any) -> str:
    if not isinstance(items, list):
        return ""
    parts: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        text = str(item.get("plain_text") or "")
        if not text:
            item_type = str(item.get("type") or "")
            payload = item.get(item_type) or {}
            if isinstance(payload, dict):
                text = str(payload.get("content") or payload.get("text", {}).get("content") or "")
        href = item.get("href")
        if text and href:
            text = f"[{text}]({href})"
        parts.append(text)
    return "".join(parts)


def property_to_text(value: Any) -> str:
    if not isinstance(value, dict):
        return str(value) if value is not None else ""
    kind = str(value.get("type") or "")
    payload = value.get(kind)
    if kind in {"title", "rich_text", "caption"}:
        return rich_text_to_text(payload)
    if kind in {"select", "status"}:
        return str((payload or {}).get("name") or "") if isinstance(payload, dict) else ""
    if kind == "multi_select":
        return ", ".join(str(item.get("name") or "") for item in (payload or []) if isinstance(item, dict))
    if kind in {"number", "checkbox", "url", "email", "phone_number"}:
        return "" if payload is None else str(payload)
    if kind == "date" and isinstance(payload, dict):
        start = payload.get("start") or ""
        end = payload.get("end") or ""
        return f"{start}..{end}" if end else str(start)
    if kind in {"created_time", "last_edited_time"}:
        return str(payload or "")
    if kind == "formula" and isinstance(payload, dict):
        return property_to_text(payload)
    if kind in {"people", "relation"} and isinstance(payload, list):
        return ", ".join(str(item.get("id") or "") for item in payload if isinstance(item, dict))
    return _json_text(payload) if payload is not None else ""


def page_title(page: Mapping[str, Any]) -> str:
    properties = page.get("properties") or {}
    if isinstance(properties, dict):
        for name, value in properties.items():
            if isinstance(value, dict) and value.get("type") == "title":
                title = property_to_text(value).strip()
                if title:
                    return title
        # Some API responses use a title field on data source objects.
    title_value = page.get("title")
    title = rich_text_to_text(title_value).strip() if isinstance(title_value, list) else str(title_value or "").strip()
    return title or "Untitled Notion page"


def parent_identifier(parent: Any) -> str:
    if not isinstance(parent, dict):
        return ""
    for key in ("page_id", "data_source_id", "database_id", "block_id"):
        value = parent.get(key)
        if value:
            return str(value)
    if parent.get("type") == "workspace":
        return "workspace"
    return ""


def safe_slug(value: str, *, fallback: str = "untitled") -> str:
    normalized = unicodedata.normalize("NFKC", value).strip()
    normalized = re.sub(r"[<>:\"/\\|?*\x00-\x1f]", "-", normalized)
    normalized = re.sub(r"\s+", " ", normalized)
    normalized = re.sub(r"-+", "-", normalized)
    normalized = normalized.strip(" .-") or fallback
    return normalized[:120]


def short_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value)[-12:] or "no-id"


def page_path(root: Path, source_label: str, page: Mapping[str, Any]) -> Path:
    return root / safe_slug(source_label) / "pages" / f"{safe_slug(page_title(page))}--{short_id(str(page.get('id') or ''))}.md"


def data_source_path(root: Path, source_label: str, data_source: Mapping[str, Any]) -> Path:
    return root / safe_slug(source_label) / "data-sources" / f"{safe_slug(page_title(data_source))}--{short_id(str(data_source.get('id') or ''))}.md"


def render_frontmatter(metadata: Mapping[str, Any]) -> str:
    lines = ["---"]
    for key, value in metadata.items():
        if isinstance(value, bool):
            rendered = "true" if value else "false"
        elif value is None:
            rendered = "null"
        elif isinstance(value, (dict, list)):
            rendered = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        else:
            rendered = json.dumps(str(value), ensure_ascii=False)
        lines.append(f"{key}: {rendered}")
    lines.extend(["---", ""])
    return "\n".join(lines)


def render_page_document(page: Mapping[str, Any], markdown: str, *, sources: Iterable[str], complete: bool) -> str:
    metadata = {
        "graxia_source": "notion",
        "notion_id": str(page.get("id") or ""),
        "notion_url": str(page.get("url") or page.get("public_url") or ""),
        "notion_parent_id": parent_identifier(page.get("parent")),
        "notion_created_time": str(page.get("created_time") or ""),
        "notion_last_edited_time": str(page.get("last_edited_time") or ""),
        "notion_in_trash": bool(page.get("in_trash", False)),
        "notion_content_complete": complete,
        "notion_sources": sorted(set(sources)),
    }
    body = markdown.strip("\n")
    heading = f"# {page_title(page)}"
    return f"{render_frontmatter(metadata)}{heading}\n\n{body}\n"


def render_data_source_document(data_source: Mapping[str, Any], *, sources: Iterable[str]) -> str:
    metadata = {
        "graxia_source": "notion",
        "notion_object": "data_source",
        "notion_id": str(data_source.get("id") or ""),
        "notion_parent_id": parent_identifier(data_source.get("parent")),
        "notion_sources": sorted(set(sources)),
    }
    schema = json.dumps(data_source, ensure_ascii=False, indent=2, sort_keys=True)
    return f"{render_frontmatter(metadata)}# {page_title(data_source)}\n\n```json\n{schema}\n```\n"


def _block_text(payload: Mapping[str, Any]) -> str:
    for key in ("rich_text", "title", "caption"):
        if key in payload:
            return rich_text_to_text(payload.get(key))
    return ""


def _render_blocks(blocks: list[dict[str, Any]], children: Mapping[str, str], unsupported: list[str], depth: int = 0) -> str:
    lines: list[str] = []
    indent = "  " * min(depth, 20)
    for block in blocks:
        block_type = str(block.get("type") or "unsupported")
        payload = block.get(block_type) if isinstance(block.get(block_type), dict) else {}
        text = _block_text(payload)
        if block_type == "paragraph":
            if text:
                lines.append(f"{indent}{text}")
        elif block_type.startswith("heading_"):
            level = min(6, max(1, int(block_type.rsplit("_", 1)[-1])))
            lines.append(f"{indent}{'#' * level} {text}".rstrip())
        elif block_type == "bulleted_list_item":
            lines.append(f"{indent}- {text}".rstrip())
        elif block_type == "numbered_list_item":
            lines.append(f"{indent}1. {text}".rstrip())
        elif block_type == "to_do":
            mark = "x" if payload.get("checked") else " "
            lines.append(f"{indent}- [{mark}] {text}".rstrip())
        elif block_type == "toggle":
            lines.append(f"{indent}> {text}".rstrip())
        elif block_type == "quote":
            lines.append(f"{indent}> {text}".rstrip())
        elif block_type == "callout":
            lines.append(f"{indent}> {text}".rstrip())
        elif block_type == "code":
            language = str(payload.get("language") or "plain text")
            lines.extend([f"{indent}```{language}", f"{indent}{text}", f"{indent}```"])
        elif block_type == "divider":
            lines.append(f"{indent}---")
        elif block_type in {"equation", "bookmark", "embed", "link_preview", "image", "video", "file", "audio"}:
            url = str(payload.get("url") or payload.get("external", {}).get("url") or "")
            lines.append(f"{indent}<!-- notion:{block_type} {url} -->".rstrip())
            if text:
                lines.append(f"{indent}{text}")
        elif block_type in {"child_page", "child_database", "link_to_page"}:
            title = str(payload.get("title") or payload.get("type") or block_type)
            lines.append(f"{indent}- {title}")
        elif block_type == "table_row":
            cells = payload.get("cells") or []
            lines.append(f"{indent}| " + " | ".join(rich_text_to_text(cell) for cell in cells) + " |")
        elif block_type in {"column_list", "column", "table", "synced_block", "template", "breadcrumb", "table_of_contents", "tab"}:
            if text:
                lines.append(f"{indent}{text}")
        else:
            unsupported.append(str(block.get("id") or block_type))
            raw = json.dumps(block, ensure_ascii=False, sort_keys=True)
            lines.append(f"{indent}<!-- unsupported Notion block {block_type}; raw saved in sidecar -->")
            lines.append(f"{indent}```json\n{raw}\n```" )
        child = children.get(str(block.get("id") or ""))
        if child:
            lines.append(child)
    return "\n\n".join(lines)


def _write_atomic(path: Path, content: str, *, encoding: str = "utf-8") -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    old = path.read_text(encoding=encoding) if path.exists() else None
    if old == content:
        return False
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="\n") as handle:
            handle.write(content)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)
    return True


def _write_json_atomic(path: Path, payload: Any) -> bool:
    return _write_atomic(path, json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _api_error_record(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, NotionAPIError):
        return exc.as_dict()
    return {"status": 599, "code": "local_error", "message": str(exc)}


def _safe_local_error(exc: Exception) -> dict[str, str]:
    message = str(exc)
    message = re.sub(r"(postgres(?:ql)?(?:\+\w+)?://)[^@\s]+@", r"\1<redacted>@", message, flags=re.IGNORECASE)
    return {"error_type": type(exc).__name__, "message": message}


class NotionImporter:
    def __init__(
        self,
        sources: list[SourceRuntime],
        *,
        output_dir: Path,
        include_archived: bool = False,
        dry_run: bool = False,
        refresh: bool = False,
        max_pages: int | None = None,
    ) -> None:
        self.sources = sources
        self.output_dir = output_dir
        self.include_archived = include_archived
        self.dry_run = dry_run
        self.refresh = refresh
        self.max_pages = max_pages
        self.pages: dict[str, MergedPage] = {}
        self.data_sources: dict[str, MergedDataSource] = {}
        self.errors: list[dict[str, Any]] = []
        self.content_errors: list[dict[str, Any]] = []
        self.incomplete = False

    def _merge_page(self, page: dict[str, Any], source: SourceRuntime, data_source_id: str = "") -> None:
        page_id = str(page.get("id") or "")
        if not page_id:
            return
        current = self.pages.get(page_id)
        if current is None:
            current = MergedPage(page=dict(page))
            self.pages[page_id] = current
        else:
            # Keep the richest/latest object without discarding the original parent.
            if len(_json_text(page)) >= len(_json_text(current.page)):
                current.page = dict(page)
        current.sources.add(source.label)
        if data_source_id:
            current.data_sources.add(data_source_id)

    def discover(self) -> None:
        for source in self.sources:
            try:
                source.me = source.client.get_me()
            except Exception as exc:
                source.discovery_errors.append(_api_error_record(exc))
                self.errors.append({"kind": "source_auth", "source": source.label, **_api_error_record(exc)})
                continue
            try:
                pages = source.client.search("page", include_archived=self.include_archived)
                source.discovered_pages = len(pages)
                for page in pages:
                    self._merge_page(page, source)
            except Exception as exc:
                source.discovery_errors.append(_api_error_record(exc))
                self.errors.append({"kind": "page_discovery", "source": source.label, **_api_error_record(exc)})
            try:
                data_source_hits = source.client.search("data_source", include_archived=self.include_archived)
                source.discovered_data_sources = len(data_source_hits)
                for hit in data_source_hits:
                    data_source_id = str(hit.get("id") or "")
                    if not data_source_id:
                        continue
                    data_source = dict(hit)
                    try:
                        data_source = source.client.get_data_source(data_source_id)
                    except Exception as exc:
                        self.errors.append(
                            {"kind": "data_source_metadata", "source": source.label, "id": data_source_id, **_api_error_record(exc)}
                        )
                    current = self.data_sources.get(data_source_id)
                    if current is None:
                        current = MergedDataSource(data_source=data_source)
                        self.data_sources[data_source_id] = current
                    else:
                        current.data_source = data_source
                    current.sources.add(source.label)
                    try:
                        rows = source.client.query_data_source(data_source_id, include_archived=self.include_archived)
                        for page in rows:
                            self._merge_page(page, source, data_source_id)
                    except Exception as exc:
                        self.errors.append(
                            {"kind": "data_source_query", "source": source.label, "id": data_source_id, **_api_error_record(exc)}
                        )
            except Exception as exc:
                source.discovery_errors.append(_api_error_record(exc))
                self.errors.append({"kind": "data_source_discovery", "source": source.label, **_api_error_record(exc)})
            if source.client.incomplete_queries:
                source.incomplete_queries.extend(source.client.incomplete_queries)
                self.incomplete = True

        ordered_ids = sorted(self.pages)
        if self.max_pages is not None:
            self.pages = {page_id: self.pages[page_id] for page_id in ordered_ids[: self.max_pages]}

    def _load_state(self) -> dict[str, Any]:
        path = self.output_dir / ".notion-import-state.json"
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            return payload if isinstance(payload, dict) else {}
        except (OSError, json.JSONDecodeError):
            self.errors.append({"kind": "state_read", "path": str(path)})
            return {}

    def _candidate_sources(self, merged: MergedPage) -> list[SourceRuntime]:
        source_map = {source.label: source for source in self.sources}
        return [source_map[label] for label in sorted(merged.sources) if label in source_map]

    def _fetch_page_content(self, merged: MergedPage) -> tuple[str, dict[str, Any], list[dict[str, Any]], bool]:
        page = merged.page
        page_id = str(page.get("id") or "")
        last_errors: list[dict[str, Any]] = []
        for source in self._candidate_sources(merged):
            try:
                response = source.client.get_page_markdown(page_id)
                markdown = str(response.get("markdown") or "")
                unknown_ids = [str(item) for item in (response.get("unknown_block_ids") or [])]
                extra: list[str] = []
                unresolved: list[str] = []
                for unknown_id in unknown_ids:
                    try:
                        nested = source.client.get_page_markdown(unknown_id)
                        nested_markdown = str(nested.get("markdown") or "")
                        if nested_markdown:
                            extra.append(f"\n\n## Imported nested block {unknown_id}\n\n{nested_markdown}")
                        unresolved.extend(str(item) for item in (nested.get("unknown_block_ids") or []))
                    except NotionAPIError as exc:
                        unresolved.append(unknown_id)
                        last_errors.append({"kind": "unknown_block", "source": source.label, "page_id": page_id, "block_id": unknown_id, **exc.as_dict()})
                content = markdown + "".join(extra)
                complete = not bool(response.get("truncated")) and not unresolved
                raw = {"mode": "page_markdown", "response": response, "resolved_unknown_blocks": unknown_ids, "unresolved_unknown_blocks": unresolved}
                return content, raw, last_errors, complete
            except NotionAPIError as exc:
                last_errors.append({"kind": "page_markdown", "source": source.label, "page_id": page_id, **exc.as_dict()})
                try:
                    blocks = source.client.list_block_children(page_id)
                    children: dict[str, str] = {}
                    unsupported: list[str] = []
                    for block in blocks:
                        block_id = str(block.get("id") or "")
                        if block.get("has_children") and block_id:
                            nested_blocks = source.client.list_block_children(block_id)
                            children[block_id] = _render_blocks(nested_blocks, {}, unsupported, 1)
                    fallback = _render_blocks(blocks, children, unsupported)
                    raw = {"mode": "block_fallback", "block_count": len(blocks), "unsupported_blocks": unsupported}
                    return fallback, raw, last_errors, not unsupported and not source.client.incomplete_queries
                except Exception as fallback_exc:
                    last_errors.append({"kind": "block_fallback", "source": source.label, "page_id": page_id, **_api_error_record(fallback_exc)})
        raise RuntimeError(_json_text(last_errors))

    def export(self) -> dict[str, Any]:
        if self.dry_run:
            return self._manifest(imported=False)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        state = self._load_state()
        old_pages = state.get("pages") if isinstance(state.get("pages"), dict) else {}
        new_state: dict[str, Any] = {"schema_version": 1, "updated_at": utc_now(), "pages": {}}
        counts = {"created": 0, "updated": 0, "unchanged": 0, "failed": 0}

        for page_id in sorted(self.pages):
            merged = self.pages[page_id]
            page = merged.page
            target = page_path(self.output_dir, sorted(merged.sources)[0], page)
            previous = old_pages.get(page_id) if isinstance(old_pages, dict) else None
            can_reuse = (
                not self.refresh
                and isinstance(previous, dict)
                and previous.get("last_edited_time") == page.get("last_edited_time")
                and target.exists()
            )
            if can_reuse:
                counts["unchanged"] += 1
                new_state["pages"][page_id] = {**previous, "sources": sorted(merged.sources), "path": str(target)}
                continue
            try:
                content, raw_content, fetch_errors, complete = self._fetch_page_content(merged)
                document = render_page_document(page, content, sources=merged.sources, complete=complete)
                changed = _write_atomic(target, document)
                sidecar = {
                    "page": page,
                    "content": raw_content,
                    "content_sha256": sha256_text(content),
                    "exported_at": utc_now(),
                    "sources": sorted(merged.sources),
                    "data_sources": sorted(merged.data_sources),
                    "complete": complete,
                }
                _write_json_atomic(target.with_suffix(".page.json"), sidecar)
                if fetch_errors:
                    self.content_errors.extend(fetch_errors)
                counts["updated" if target.exists() and not changed else "created"] += 1
                new_state["pages"][page_id] = {
                    "last_edited_time": page.get("last_edited_time"),
                    "content_sha256": sha256_text(content),
                    "path": str(target),
                    "complete": complete,
                    "sources": sorted(merged.sources),
                }
                if not complete:
                    self.incomplete = True
            except Exception as exc:
                counts["failed"] += 1
                self.content_errors.append({"kind": "page_export", "page_id": page_id, **_api_error_record(exc)})

        data_source_count = 0
        for data_source_id in sorted(self.data_sources):
            merged = self.data_sources[data_source_id]
            target = data_source_path(self.output_dir, sorted(merged.sources)[0], merged.data_source)
            try:
                _write_atomic(target, render_data_source_document(merged.data_source, sources=merged.sources))
                _write_json_atomic(target.with_suffix(".json"), {"data_source": merged.data_source, "sources": sorted(merged.sources), "exported_at": utc_now()})
                data_source_count += 1
            except OSError as exc:
                self.errors.append({"kind": "data_source_export", "id": data_source_id, "message": str(exc)})

        index_lines = ["# Notion import index", "", f"Exported: {utc_now()}", ""]
        for page_id in sorted(self.pages):
            merged = self.pages[page_id]
            target = page_path(self.output_dir, sorted(merged.sources)[0], merged.page)
            index_lines.append(f"- [{page_title(merged.page)}]({target.relative_to(self.output_dir).as_posix()}) — `{page_id}`")
        _write_atomic(self.output_dir / "INDEX.md", "\n".join(index_lines) + "\n")
        new_state["data_sources"] = sorted(self.data_sources)
        _write_json_atomic(self.output_dir / ".notion-import-state.json", new_state)
        manifest = self._manifest(imported=True)
        manifest["counts"] = {**counts, "data_sources_exported": data_source_count}
        _write_json_atomic(self.output_dir / "import-manifest.json", manifest)
        return manifest

    def _manifest(self, *, imported: bool) -> dict[str, Any]:
        sources = []
        for source in self.sources:
            me = source.me or {}
            bot = me.get("bot") if isinstance(me.get("bot"), dict) else {}
            sources.append(
                {
                    "label": source.label,
                    "token_fingerprint": source.client.token_fingerprint,
                    "api_version": source.client.api_version,
                    "bot_id": bot.get("id") or me.get("id"),
                    "bot_name": bot.get("name") or me.get("name"),
                    "discovered_pages": source.discovered_pages,
                    "discovered_data_sources": source.discovered_data_sources,
                    "incomplete_queries": sorted(set(source.incomplete_queries)),
                    "discovery_errors": source.discovery_errors,
                }
            )
        all_errors = [*self.errors, *self.content_errors]
        return scrub(
            {
                "schema_version": 1,
                "generated_at": utc_now(),
                "api_version": self.sources[0].client.api_version if self.sources else DEFAULT_API_VERSION,
                "imported": imported,
                "dry_run": self.dry_run,
                "include_archived": self.include_archived,
                "output_dir": str(self.output_dir),
                "sources": sources,
                "pages_discovered_unique": len(self.pages),
                "data_sources_discovered_unique": len(self.data_sources),
                "duplicate_page_hits_collapsed": sum(max(0, len(page.sources) - 1) for page in self.pages.values()),
                "incomplete": bool(self.incomplete),
                "complete": not self.incomplete and not all_errors,
                "errors": all_errors,
            },
            [source.client._token for source in self.sources],
        )


async def index_with_graxia(markdown_root: Path, vault_root: Path, *, allow_remote_db: bool) -> dict[str, Any]:
    """Index only imported Markdown files through Graxia's existing vault path."""

    backend_root = Path(__file__).resolve().parents[1] / "backend"
    if not backend_root.exists():
        raise RuntimeError(f"Graxia backend not found: {backend_root}")
    sys.path.insert(0, str(backend_root))
    from app.config import settings  # type: ignore[import-not-found]

    db_url = str(settings.DATABASE_URL or "")
    if not db_url:
        raise RuntimeError("Graxia DATABASE_URL is empty")
    parsed = urllib.parse.urlsplit(db_url)
    is_remote = parsed.hostname not in {None, "", "localhost", "127.0.0.1", "::1"}
    if is_remote and not allow_remote_db:
        raise RuntimeError("Refusing remote Graxia DB; pass --allow-remote-db explicitly")

    from app.database import AsyncSessionLocal  # type: ignore[import-not-found]
    from app.services.knowledge_service import get_knowledge_service  # type: ignore[import-not-found]

    files = sorted(markdown_root.rglob("*.md"))
    indexed_files = 0
    unchanged_files = 0
    failed_files: list[dict[str, Any]] = []
    total_chunks = 0
    async with AsyncSessionLocal() as db:
        service = await get_knowledge_service()
        for file_path in files:
            try:
                content = file_path.read_text(encoding="utf-8")
                source_path = file_path.relative_to(vault_root).as_posix()
                count = await service.index_markdown_content(
                    db=db,
                    title=file_path.stem,
                    content=content,
                    source_path=source_path,
                    metadata={"category": "research", "tags": ["notion", "graxia-import"]},
                )
                await db.commit()
                if count:
                    indexed_files += 1
                    total_chunks += count
                else:
                    unchanged_files += 1
            except Exception as exc:
                await db.rollback()
                failed_files.append({"path": str(file_path), "message": str(exc)})
    return {
        "vault_root": str(vault_root),
        "markdown_root": str(markdown_root),
        "database_host": parsed.hostname,
        "remote_database": is_remote,
        "files_seen": len(files),
        "indexed_files": indexed_files,
        "unchanged_files": unchanged_files,
        "chunks_indexed": total_chunks,
        "failed_files": failed_files,
        "complete": not failed_files,
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token-stdin", action="store_true", help="Read one or more tokens from stdin, one per line")
    parser.add_argument("--token-count", type=int, help="Read exactly this many stdin token lines; useful for interactive pipes")
    parser.add_argument("--output-dir", type=Path, default=Path("data/imports/notion"))
    parser.add_argument("--vault-root", type=Path, help="Vault root used to calculate Graxia source_path")
    parser.add_argument("--api-version", default=DEFAULT_API_VERSION)
    parser.add_argument("--include-archived", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Discover/count only; write nothing")
    parser.add_argument("--validate-only", action="store_true", help="Call /users/me only; write nothing")
    parser.add_argument("--refresh", action="store_true", help="Refetch unchanged pages")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--index", action="store_true", help="Index exported Markdown into Graxia")
    parser.add_argument("--index-only", action="store_true", help="Skip Notion API; index an existing export directory")
    parser.add_argument("--allow-remote-db", action="store_true", help="Required before indexing a non-local Graxia DB")
    parser.add_argument("--source-label", action="append", help="Stable label; repeat once per token")
    return parser.parse_args(argv)


def read_tokens(args: argparse.Namespace) -> list[str]:
    tokens: list[str] = []
    if args.token_stdin:
        if args.token_count is not None:
            if args.token_count < 1:
                raise SystemExit("--token-count must be positive")
            tokens.extend(line.strip() for _ in range(args.token_count) if (line := sys.stdin.readline()).strip())
        else:
            tokens.extend(line.strip() for line in sys.stdin.read().splitlines() if line.strip())
    else:
        tokens.extend(os.environ.get(name, "").strip() for name in TOKEN_ENV_NAMES if os.environ.get(name, "").strip())
    if not tokens:
        raise SystemExit("No Notion tokens supplied. Use --token-stdin or NOTION_TOKEN_1/2 process env.")
    labels = args.source_label or []
    if labels and len(labels) != len(tokens):
        raise SystemExit("Pass exactly one --source-label per token, or omit labels.")
    if not labels:
        labels = [f"workspace-{index:02d}" for index in range(1, len(tokens) + 1)]
    return list(zip(tokens, labels, strict=True))


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args(argv)
    if args.index_only:
        if args.dry_run:
            raise SystemExit("--index-only cannot be combined with --dry-run")
        markdown_root = args.output_dir.resolve()
        vault_root = args.vault_root.resolve() if args.vault_root else markdown_root.parent.parent.resolve()
        try:
            result = asyncio.run(index_with_graxia(markdown_root, vault_root, allow_remote_db=args.allow_remote_db))
        except Exception as exc:
            result = {
                "complete": False,
                "markdown_root": str(markdown_root),
                "vault_root": str(vault_root),
                "error": _safe_local_error(exc),
            }
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if result.get("complete") else 2
    token_pairs = read_tokens(args)
    sources = [SourceRuntime(label=label, client=NotionClient(token, api_version=args.api_version)) for token, label in token_pairs]
    if args.validate_only:
        report: list[dict[str, Any]] = []
        failed = False
        for source in sources:
            try:
                me = source.client.get_me()
                bot = me.get("bot") if isinstance(me.get("bot"), dict) else {}
                report.append({
                    "label": source.label,
                    "token_fingerprint": source.client.token_fingerprint,
                    "api_version": source.client.api_version,
                    "status": "valid",
                    "bot_id": bot.get("id") or me.get("id"),
                    "bot_name": bot.get("name") or me.get("name"),
                })
            except Exception as exc:
                failed = True
                report.append({"label": source.label, "token_fingerprint": source.client.token_fingerprint, "status": "invalid", "error": _api_error_record(exc)})
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return 2 if failed else 0
    importer = NotionImporter(
        sources,
        output_dir=args.output_dir.resolve(),
        include_archived=args.include_archived,
        dry_run=args.dry_run,
        refresh=args.refresh,
        max_pages=args.max_pages,
    )
    importer.discover()
    manifest = importer.export()
    if args.index and not args.dry_run:
        vault_root = args.vault_root.resolve() if args.vault_root else importer.output_dir.parent.parent.resolve()
        try:
            index_result = asyncio.run(index_with_graxia(importer.output_dir, vault_root, allow_remote_db=args.allow_remote_db))
        except Exception as exc:
            index_result = {"complete": False, "error": _safe_local_error(exc)}
        manifest["graxia_index"] = index_result
        _write_json_atomic(importer.output_dir / "import-manifest.json", manifest)
    print(json.dumps(scrub(manifest, [token for token, _ in token_pairs]), ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if manifest.get("complete") and ("graxia_index" not in manifest or manifest["graxia_index"].get("complete")) else 2


if __name__ == "__main__":
    raise SystemExit(main())
