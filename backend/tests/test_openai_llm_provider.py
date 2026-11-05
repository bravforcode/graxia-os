import json
from decimal import Decimal
from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import Settings
from app.core.llm import LLMClient


def openai_settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "testing",
        "LLM_PROVIDER": "openai",
        "OPENAI_API_KEY": "unit-test-key",
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "OPENAI_CHAT_MODEL": "account-model-test",
        "OPENAI_INPUT_PRICE_USD_PER_1M": 2.0,
        "OPENAI_OUTPUT_PRICE_USD_PER_1M": 4.0,
    }
    values.update(overrides)
    return Settings(**values)


def openclaw_settings(**overrides) -> Settings:
    values = {
        "APP_ENV": "testing",
        "LLM_PROVIDER": "openclaw",
        "OPENCLAW_API_KEY": "unit-test-openclaw-key",
        "OPENCLAW_DEFAULT_MODEL": "openclaw-test",
        "OPENCLAW_FAST_MODEL": "openclaw-fast-test",
        "CHEAP_MODEL": "gemini-test",
        "MID_MODEL": "gemini-test",
        "HIGH_QUALITY_MODEL": "gemini-test",
        "CHEAP_MODEL_INPUT_COST_PER_1M": 1.0,
        "CHEAP_MODEL_OUTPUT_COST_PER_1M": 1.0,
        "MID_MODEL_INPUT_COST_PER_1M": 1.0,
        "MID_MODEL_OUTPUT_COST_PER_1M": 1.0,
        "HIGH_QUALITY_MODEL_INPUT_COST_PER_1M": 1.0,
        "HIGH_QUALITY_MODEL_OUTPUT_COST_PER_1M": 1.0,
    }
    values.update(overrides)
    return Settings(**values)


class FakeResponse:
    status_code = 200
    headers = {"content-type": "application/json"}

    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "response contains unit-test-key",
                request=httpx.Request("POST", "https://api.openai.com/v1/chat/completions"),
                response=httpx.Response(self.status_code),
            )

    def json(self):
        return self.payload


class FakeStreamResponse(FakeResponse):
    def __init__(self, lines):
        super().__init__({})
        self.lines = lines

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def aiter_lines(self):
        for line in self.lines:
            yield line


class FakeAsyncClient:
    instances = []
    post_response = None
    stream_response = None

    def __init__(self, *args, **kwargs):
        self.options = kwargs
        self.calls = []
        self.instances.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return None

    async def post(self, url, *, json, headers):
        self.calls.append((url, json, headers))
        return self.post_response

    def stream(self, method, url, *, json, headers):
        self.calls.append((method, url, json, headers))
        return self.stream_response


@pytest.fixture(autouse=True)
def reset_fake_client():
    FakeAsyncClient.instances = []
    FakeAsyncClient.post_response = None
    FakeAsyncClient.stream_response = None


@pytest.mark.asyncio
async def test_nonstream_openai_uses_official_chat_completions_and_tracks_actual_usage(monkeypatch):
    client = LLMClient(openai_settings())
    client._validate_openai_target = AsyncMock(return_value=None)
    tracked = AsyncMock(return_value=True)
    monkeypatch.setattr("app.core.llm.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("app.core.cost_tracker.cost_tracker.track_openai_cost", tracked)
    FakeAsyncClient.post_response = FakeResponse(
        {
            "choices": [{"message": {"content": " complete "}}],
            "usage": {"prompt_tokens": 100, "completion_tokens": 20},
        }
    )

    result = await client._call_openai("system", "user", "account-model-test", 50, 0.2)

    assert result == "complete"
    request_client = FakeAsyncClient.instances[0]
    assert request_client.options["follow_redirects"] is False
    assert request_client.options["trust_env"] is False
    url, payload, headers = request_client.calls[0]
    assert url == "https://api.openai.com/v1/chat/completions"
    assert payload["model"] == "account-model-test"
    assert payload["messages"] == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "user"},
    ]
    assert payload["max_completion_tokens"] == 50
    assert "max_tokens" not in payload
    assert "temperature" not in payload
    assert headers["Authorization"] == "Bearer unit-test-key"
    tracked.assert_awaited_once_with(
        model="account-model-test",
        input_tokens=100,
        output_tokens=20,
        cost_usd=Decimal("0.00028"),
    )
    assert client.get_provider_readiness()["status"] == "healthy"


@pytest.mark.asyncio
async def test_openai_json_mode_uses_chat_completions_response_format(monkeypatch):
    client = LLMClient(openai_settings())
    client._validate_openai_target = AsyncMock(return_value=None)
    client._track_openai_usage = AsyncMock()
    monkeypatch.setattr("app.core.llm.httpx.AsyncClient", FakeAsyncClient)
    FakeAsyncClient.post_response = FakeResponse(
        {
            "choices": [{"message": {"content": '{"ok":true}'}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 3},
        }
    )
    result = await client._call_openai(
        "system", "user", "account-model-test", 50, 0.1, json_mode=True
    )

    assert json.loads(result) == {"ok": True}
    assert FakeAsyncClient.instances[0].calls[0][1]["response_format"] == {
        "type": "json_object"
    }


@pytest.mark.asyncio
async def test_openai_http_errors_are_sanitized(monkeypatch):
    client = LLMClient(openai_settings())
    client._validate_openai_target = AsyncMock(return_value=None)
    monkeypatch.setattr("app.core.llm.httpx.AsyncClient", FakeAsyncClient)
    FakeAsyncClient.post_response = FakeResponse({})
    FakeAsyncClient.post_response.status_code = 401

    with pytest.raises(RuntimeError, match="OpenAI returned HTTP 401") as exc_info:
        await client._call_openai("system", "user", "account-model-test", 50, 0.2)

    assert "unit-test-key" not in str(exc_info.value)


@pytest.mark.asyncio
async def test_complete_json_passes_supported_json_mode_flag():
    client = LLMClient(openai_settings())
    complete = AsyncMock(return_value='{"ok":true}')
    client.complete = complete

    result = await client.complete_json(system="system", user="user")

    assert result == {"ok": True}
    assert complete.await_args.kwargs["json_mode"] is True
    assert "rag_context" not in complete.await_args.kwargs
    assert "rag_query" not in complete.await_args.kwargs


@pytest.mark.asyncio
async def test_openai_stream_uses_usage_event_and_tracks_cost(monkeypatch):
    client = LLMClient(openai_settings())
    client._validate_openai_target = AsyncMock(return_value=None)
    tracked = AsyncMock(return_value=True)
    monkeypatch.setattr("app.core.llm.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("app.core.cost_tracker.cost_tracker.track_openai_cost", tracked)
    FakeAsyncClient.stream_response = FakeStreamResponse(
        [
            'data: {"choices":[{"delta":{"content":"streamed"}}]}',
            'data: {"choices":[],"usage":{"prompt_tokens":20,"completion_tokens":8}}',
            "data: [DONE]",
        ]
    )

    chunks = [
        chunk
        async for chunk in client._call_openai_stream(
            "system", "user", "account-model-test", 40, 0.2
        )
    ]

    assert chunks == ["streamed"]
    request_client = FakeAsyncClient.instances[0]
    _, url, payload, headers = request_client.calls[0]
    assert url.endswith("/chat/completions")
    assert payload["stream"] is True
    assert payload["stream_options"] == {"include_usage": True}
    assert payload["max_completion_tokens"] == 40
    assert "max_tokens" not in payload
    assert "temperature" not in payload
    assert headers["Authorization"] == "Bearer unit-test-key"
    tracked.assert_awaited_once_with(
        model="account-model-test",
        input_tokens=20,
        output_tokens=8,
        cost_usd=Decimal("0.000072"),
    )


@pytest.mark.asyncio
async def test_partial_openai_stream_never_falls_back_to_complete(monkeypatch):
    client = LLMClient(openai_settings())
    client._track_request = AsyncMock(return_value=True)
    client._get_cache = AsyncMock(return_value=None)
    client._set_cache = AsyncMock()
    client._log_call = AsyncMock()
    complete = AsyncMock(return_value="duplicate")
    client.complete = complete

    async def partial_stream(*args, **kwargs):
        yield "partial"
        raise RuntimeError("stream interrupted")

    monkeypatch.setattr(client, "_call_openai_stream", partial_stream)
    chunks = []
    stream = client.generate_stream(
        system="system", user="user", model="account-model-test", max_tokens=20
    )
    with pytest.raises(RuntimeError, match="stream interrupted"):
        async for chunk in stream:
            chunks.append(chunk)

    assert chunks == ["partial"]
    complete.assert_not_awaited()


@pytest.mark.asyncio
async def test_openai_request_is_blocked_when_prompt_upper_bound_exceeds_single_call_cap(monkeypatch):
    client = LLMClient(
        openai_settings(
            OPENAI_INPUT_PRICE_USD_PER_1M=1_000.0,
            OPENAI_OUTPUT_PRICE_USD_PER_1M=1_000.0,
            MAX_SINGLE_LLM_CALL_COST_USD=0.10,
        )
    )
    track_request = AsyncMock(return_value=True)
    call_openai = AsyncMock(return_value="must not run")
    emit = AsyncMock()
    monkeypatch.setattr(client, "_track_request", track_request)
    monkeypatch.setattr(client, "_call_openai", call_openai)
    monkeypatch.setattr("app.core.event_bus.event_bus.emit", emit)

    result = await client.complete(
        system="s" * 1_000,
        user="u",
        max_tokens=100,
    )

    assert result is None
    track_request.assert_not_awaited()
    call_openai.assert_not_awaited()


def test_openai_key_does_not_select_provider_or_imply_readiness():
    client = LLMClient(openai_settings(LLM_PROVIDER=""))

    status = client.get_provider_readiness()

    assert client.openai_key == ""
    assert status["provider"] is None
    assert status["configured"] is False
    assert status["ready"] is False


def test_configured_openai_model_remains_unverified_until_successful_inference():
    client = LLMClient(openai_settings())

    status = client.get_provider_readiness()

    assert status["configured"] is True
    assert status["verified"] is False
    assert status["ready"] is False
    assert status["status"] == "unverified"


@pytest.mark.parametrize(
    "url",
    [
        "http://api.openai.com/v1",
        "https://user:pass@api.openai.com/v1",
        "https://api.openai.com/v1?key=x",
        "https://api.openai.com/v1#fragment",
        "https://127.0.0.1/v1",
        "https://localhost/v1",
        "https://proxy.example/v1",
    ],
)
def test_openai_base_url_rejects_unsafe_or_unapproved_targets(url):
    with pytest.raises(ValueError):
        LLMClient._validated_openai_base_url(url)


def test_openai_base_url_allows_only_official_host():
    assert LLMClient._validated_openai_base_url("https://api.openai.com/v1").hostname == "api.openai.com"


@pytest.mark.asyncio
async def test_openai_target_rejects_private_dns_results():
    client = LLMClient(openai_settings())
    client._resolve_openai_host = AsyncMock(return_value={"10.1.2.3"})

    with pytest.raises(RuntimeError, match="non-public address"):
        await client._validate_openai_target()


@pytest.mark.asyncio
async def test_openai_target_accepts_only_public_dns_results():
    client = LLMClient(openai_settings())
    client._resolve_openai_host = AsyncMock(return_value={"93.184.216.34"})

    parsed = await client._validate_openai_target()

    assert parsed.hostname == "api.openai.com"


def test_custom_openai_proxy_is_rejected_even_with_legacy_opt_in():
    client = LLMClient(
        openai_settings(OPENAI_BASE_URL="https://proxy.example/v1")
    )
    assert client.get_provider_readiness()["configured"] is False

    with pytest.raises(ValueError):
        LLMClient._validated_openai_base_url("https://proxy.example/v1")


@pytest.mark.asyncio
async def test_openclaw_gemini_fallback_is_gated_and_records_actual_provider(monkeypatch):
    client = LLMClient(openclaw_settings())
    client.openclaw_key = "unit-test-openclaw-key"
    client.api_key = "unit-test-gemini-key"
    client._track_request = AsyncMock(return_value=True)
    client._get_cache = AsyncMock(return_value=None)
    client._set_cache = AsyncMock()
    client._sync_runtime_readiness = lambda: None
    client._call_openclaw = AsyncMock(side_effect=RuntimeError("gateway unavailable"))
    client._call_gemini = AsyncMock(return_value="gemini fallback")
    client._log_call = AsyncMock()
    monkeypatch.setattr("app.telegram_bot.bot.send_message", AsyncMock())

    result = await client.complete(
        system="system",
        user="user",
        model="openclaw-test",
        allow_fallback=True,
    )

    assert result == "gemini fallback"
    client._call_gemini.assert_awaited_once()
    log_args = client._log_call.await_args
    assert log_args.args[0] == "gemini-test"
    assert log_args.kwargs["provider"] == "gemini"
    assert log_args.kwargs["was_fallback"] is True
    assert client.get_provider_readiness()["verified"] is False


@pytest.mark.asyncio
async def test_openclaw_failure_does_not_use_gemini_when_fallback_is_disabled(monkeypatch):
    client = LLMClient(openclaw_settings())
    client.openclaw_key = "unit-test-openclaw-key"
    client.api_key = "unit-test-gemini-key"
    client._track_request = AsyncMock(return_value=True)
    client._get_cache = AsyncMock(return_value=None)
    client._set_cache = AsyncMock()
    client._sync_runtime_readiness = lambda: None
    client._call_openclaw = AsyncMock(side_effect=RuntimeError("gateway unavailable"))
    client._call_gemini = AsyncMock(return_value="must not be called")
    client._log_call = AsyncMock()
    monkeypatch.setattr("app.telegram_bot.bot.send_message", AsyncMock())

    result = await client.complete(
        system="system",
        user="user",
        model="openclaw-test",
        allow_fallback=False,
    )

    assert result is None
    client._call_gemini.assert_not_awaited()


@pytest.mark.asyncio
async def test_openai_request_counter_is_separate_from_gemini_calls(monkeypatch):
    class FakeRedis:
        def __init__(self):
            self.counts = {}

        async def incr(self, key):
            self.counts[key] = self.counts.get(key, 0) + 1
            return self.counts[key]

        async def expire(self, _key, _seconds):
            return True

        async def get(self, key):
            return self.counts.get(key)

    client = LLMClient(openai_settings())
    redis = FakeRedis()
    client._get_redis = AsyncMock(return_value=redis)

    assert await client._track_request() is True

    assert len(redis.counts) == 1
    assert next(iter(redis.counts)).startswith("openai_requests:")
    assert await client.get_call_count_today("gemini") == 0
    assert await client.get_call_count_today("openai") == 1
    assert await client.get_total_call_count_today() == 1


@pytest.mark.asyncio
async def test_openai_stream_error_before_first_chunk_is_sanitized_and_propagated(monkeypatch):
    client = LLMClient(openai_settings())
    client._track_request = AsyncMock(return_value=True)
    client._get_cache = AsyncMock(return_value=None)
    client._sync_runtime_readiness = lambda: None

    async def failed_stream(*_args, **_kwargs):
        raise RuntimeError("unit-test-key leaked from transport")
        yield ""

    monkeypatch.setattr(client, "_call_openai_stream", failed_stream)

    with pytest.raises(RuntimeError, match="OpenAI stream failed before the first chunk") as exc_info:
        async for _chunk in client.generate_stream(
            system="system", user="user", model="account-model-test"
        ):
            pass

    assert "unit-test-key" not in str(exc_info.value)


def _probe_ready_client() -> LLMClient:
    client = LLMClient(openai_settings())
    client._validate_openai_target = AsyncMock(return_value=None)
    client._track_openai_usage = AsyncMock()
    client._track_request = AsyncMock(return_value=True)
    client._get_cache = AsyncMock(return_value=None)
    client._set_cache = AsyncMock()
    client._log_call = AsyncMock()
    client._sync_runtime_readiness = lambda: None
    return client


@pytest.mark.asyncio
async def test_verify_provider_marks_openai_verified_through_the_production_path(monkeypatch):
    client = _probe_ready_client()
    monkeypatch.setattr("app.core.llm.httpx.AsyncClient", FakeAsyncClient)
    FakeAsyncClient.post_response = FakeResponse(
        {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1},
        }
    )

    assert await client.verify_provider() is True

    assert client.get_provider_readiness()["status"] == "healthy"
    _, payload, _ = FakeAsyncClient.instances[0].calls[0]
    assert payload["model"] == "account-model-test"


@pytest.mark.asyncio
async def test_verify_provider_sends_a_fresh_nonce_so_cached_answers_cannot_skip_the_probe(monkeypatch):
    client = _probe_ready_client()
    monkeypatch.setattr("app.core.llm.httpx.AsyncClient", FakeAsyncClient)
    FakeAsyncClient.post_response = FakeResponse(
        {
            "choices": [{"message": {"content": "OK"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 1},
        }
    )

    await client.verify_provider()
    await client.verify_provider()

    prompts = [instance.calls[0][1]["messages"][1]["content"] for instance in FakeAsyncClient.instances]
    assert len(prompts) == 2
    assert prompts[0] != prompts[1]


@pytest.mark.asyncio
async def test_verify_provider_reports_failure_without_marking_ready(monkeypatch):
    client = _probe_ready_client()
    monkeypatch.setattr("app.core.llm.httpx.AsyncClient", FakeAsyncClient)
    monkeypatch.setattr("app.telegram_bot.bot.send_message", AsyncMock())
    FakeAsyncClient.post_response = FakeResponse({})
    FakeAsyncClient.post_response.status_code = 401

    assert await client.verify_provider() is False

    status = client.get_provider_readiness()
    assert status["status"] == "unverified"
    assert status["verified"] is False
