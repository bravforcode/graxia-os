from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.notion_to_graxia import (
    NotionClient,
    NotionImporter,
    SourceRuntime,
    NotionAPIError,
    page_title,
    property_to_text,
    render_page_document,
    safe_slug,
)


def test_property_and_title_rendering_preserves_rich_text_links() -> None:
    page = {
        "id": "page-123",
        "properties": {
            "Name": {
                "type": "title",
                "title": [{"plain_text": "Build docs", "href": "https://example.test/docs"}],
            }
        },
    }
    assert page_title(page) == "[Build docs](https://example.test/docs)"
    assert property_to_text({"type": "status", "status": {"name": "Done"}}) == "Done"


def test_slug_removes_windows_path_characters_and_is_bounded() -> None:
    value = safe_slug('A<>:"/\\|?*' + "x" * 200)
    assert all(character not in value for character in '<>:"/\\|?*')
    assert len(value) <= 120


def test_render_page_document_contains_source_contract() -> None:
    page = {"id": "page-1", "url": "https://notion.test/page-1", "properties": {"Title": {"type": "title", "title": [{"plain_text": "Title"}]}}}
    output = render_page_document(page, "body", sources=["workspace-01"], complete=True)
    assert "notion_id: \"page-1\"" in output
    assert "notion_content_complete: true" in output
    assert "# Title" in output
    assert "body" in output


def test_api_client_retries_rate_limit_without_logging_token(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[object] = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout):
        calls.append(request)
        if len(calls) == 1:
            error = __import__("urllib.error", fromlist=["HTTPError"]).HTTPError(
                request.full_url, 429, "rate limited", {"Retry-After": "0"}, None
            )
            raise error
        return Response()

    sleeps: list[float] = []
    monkeypatch.setattr("scripts.notion_to_graxia.urllib.request.urlopen", fake_urlopen)
    client = NotionClient("ntn_secret_must_not_escape", sleep_fn=sleeps.append, min_interval=0)
    assert client.request_json("GET", "/users/me") == {"ok": True}
    assert len(calls) == 2
    assert client.token_fingerprint not in json.dumps({"ok": True})


def test_importer_merges_duplicate_page_ids_without_duplicate_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    page = {"id": "page-1", "last_edited_time": "2026-01-01T00:00:00Z", "properties": {"Title": {"type": "title", "title": [{"plain_text": "Same"}]}}}

    class FakeClient:
        api_version = "2026-03-11"
        _token = "secret"
        incomplete_queries: list[str] = []

        @property
        def token_fingerprint(self):
            return "fingerprint"

        def get_page_markdown(self, _page_id):
            return {"markdown": "same", "truncated": False, "unknown_block_ids": []}

    source_a = SourceRuntime("workspace-01", FakeClient())
    source_b = SourceRuntime("workspace-02", FakeClient())
    importer = NotionImporter([source_a, source_b], output_dir=tmp_path)
    importer._merge_page(page, source_a)
    importer._merge_page(page, source_b)
    manifest = importer.export()
    assert manifest["pages_discovered_unique"] == 1
    assert manifest["duplicate_page_hits_collapsed"] == 1
    assert len(list(tmp_path.rglob("*.md"))) == 2  # page + INDEX.md

    second = NotionImporter([SourceRuntime("workspace-01", FakeClient())], output_dir=tmp_path)
    second._merge_page(page, second.sources[0])
    rerun = second.export()
    assert rerun["counts"]["unchanged"] == 1
    assert rerun["counts"]["created"] == 0


def test_api_error_is_structured() -> None:
    error = NotionAPIError(403, "restricted_resource", "no access", path="/pages/id")
    assert error.as_dict() == {"status": 403, "code": "restricted_resource", "message": "no access", "path": "/pages/id"}
