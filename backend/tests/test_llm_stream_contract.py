import pytest
from app.core.llm import LLMClient


async def collect_stream(stream):
    chunks = []
    async for chunk in stream:
        chunks.append(chunk)
    return chunks


def test_openai_stream_payload_parser_extracts_delta_content():
    payload = {"choices": [{"delta": {"content": "partial"}}]}

    assert LLMClient._extract_openai_stream_text(payload) == "partial"


def test_gemini_stream_payload_parser_extracts_candidate_text():
    payload = {"candidates": [{"content": {"parts": [{"text": "partial"}]}}]}

    assert LLMClient._extract_gemini_stream_text(payload) == "partial"


@pytest.mark.asyncio
async def test_sse_json_iterator_ignores_comments_and_stops_on_done():
    client = LLMClient()

    class FakeResponse:
        async def aiter_lines(self):
            for line in [
                ": keepalive",
                "",
                'data: {"chunk": 1}',
                "not-an-sse-line",
                "data: [DONE]",
                'data: {"chunk": 2}',
            ]:
                yield line

    payloads = [payload async for payload in client._iter_sse_json(FakeResponse())]

    assert payloads == [{"chunk": 1}]


@pytest.mark.asyncio
async def test_generate_stream_uses_openclaw_streaming_provider(monkeypatch):
    client = LLMClient()
    client.openclaw_key = "real-openclaw-key"
    client.api_key = ""

    cache_writes = []
    log_writes = []

    async def fake_openclaw_stream(*args, **kwargs):
        yield "Hel"
        yield "lo"

    async def fake_set_cache(key, value):
        cache_writes.append((key, value))

    async def fake_log_call(*args, **kwargs):
        log_writes.append(kwargs)

    async def allow_request():
        return True

    async def cache_miss(key):
        return None

    monkeypatch.setattr(client, "_track_request", allow_request)
    monkeypatch.setattr(client, "_get_cache", cache_miss)
    monkeypatch.setattr(client, "_set_cache", fake_set_cache)
    monkeypatch.setattr(client, "_log_call", fake_log_call)
    monkeypatch.setattr(client, "_call_openclaw_stream", fake_openclaw_stream)

    chunks = await collect_stream(
        client.generate_stream(
            system="You are concise.",
            user="Say hello.",
            model="openclaw-test",
            max_tokens=20,
        )
    )

    assert chunks == ["Hel", "lo"]
    assert cache_writes and cache_writes[0][1] == "Hello"
    assert log_writes and log_writes[0]["was_fallback"] is False


@pytest.mark.asyncio
async def test_generate_stream_falls_back_to_gemini_stream_when_openclaw_fails(monkeypatch):
    client = LLMClient()
    client.openclaw_key = "real-openclaw-key"
    client.api_key = "real-gemini-key"

    async def broken_openclaw_stream(*args, **kwargs):
        raise RuntimeError("gateway closed stream")
        yield ""

    async def fake_gemini_stream(*args, **kwargs):
        yield "safe "
        yield "fallback"

    async def allow_request():
        return True

    async def cache_miss(key):
        return None

    async def noop_async(*args, **kwargs):
        return None

    monkeypatch.setattr(client, "_track_request", allow_request)
    monkeypatch.setattr(client, "_get_cache", cache_miss)
    monkeypatch.setattr(client, "_set_cache", noop_async)
    monkeypatch.setattr(client, "_log_call", noop_async)
    monkeypatch.setattr(client, "_call_openclaw_stream", broken_openclaw_stream)
    monkeypatch.setattr(client, "_call_gemini_stream", fake_gemini_stream)

    chunks = await collect_stream(
        client.generate_stream(system="system", user="user", model="openclaw-test")
    )

    assert chunks == ["safe ", "fallback"]


@pytest.mark.asyncio
async def test_generate_stream_falls_back_to_complete_when_streaming_provider_fails(monkeypatch):
    client = LLMClient()
    client.openclaw_key = "real-openclaw-key"
    client.api_key = ""

    async def broken_openclaw_stream(*args, **kwargs):
        raise RuntimeError("streaming unsupported")
        yield ""

    async def fake_complete(*args, **kwargs):
        return "non-stream response"

    async def allow_request():
        return True

    async def cache_miss(key):
        return None

    async def noop_async(*args, **kwargs):
        return None

    monkeypatch.setattr(client, "_track_request", allow_request)
    monkeypatch.setattr(client, "_get_cache", cache_miss)
    monkeypatch.setattr(client, "_set_cache", noop_async)
    monkeypatch.setattr(client, "_log_call", noop_async)
    monkeypatch.setattr(client, "_call_openclaw_stream", broken_openclaw_stream)
    monkeypatch.setattr(client, "complete", fake_complete)

    chunks = await collect_stream(client.generate_stream(system="system", user="user"))

    assert chunks == ["non-stream response"]
