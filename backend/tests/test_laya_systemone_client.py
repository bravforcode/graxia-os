import json

import httpx
import pytest

from app.core.laya_client import LayaClient, LayaError

QUESTIONS = {
    "pick": {
        "type": "choice",
        "instructions": "Pick the best action",
        "criteria": ["accept", "reject"],
    }
}
ANSWERS = {"pick": {"type": "choice", "choice": "reject"}}


def _client(handler, api_key="laya-test-key"):
    return LayaClient(
        base_url="http://laya.test",
        api_key=api_key,
        transport=httpx.MockTransport(handler),
    )


@pytest.mark.asyncio
async def test_systemone_posts_state_and_questions_with_bearer_key():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(
            200,
            json={"model": "laya-rl-agent", "answers": ANSWERS, "usage": {}, "routing": {}},
        )

    answers = await _client(handler).systemone("Customer asks for a refund.", QUESTIONS)

    assert answers == ANSWERS
    request = seen[0]
    assert str(request.url) == "http://laya.test/v1/systemone"
    assert request.headers["authorization"] == "Bearer laya-test-key"
    assert json.loads(request.content) == {
        "state": "Customer asks for a refund.",
        "questions": QUESTIONS,
    }


@pytest.mark.asyncio
async def test_systemone_omits_authorization_when_no_key_configured():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"answers": ANSWERS})

    await _client(handler, api_key="").systemone("state", QUESTIONS)

    assert "authorization" not in seen[0].headers


@pytest.mark.asyncio
async def test_systemone_raises_laya_error_with_status_on_http_failure():
    client = _client(lambda request: httpx.Response(401, json={"detail": "Unauthorized"}))

    with pytest.raises(LayaError) as excinfo:
        await client.systemone("state", QUESTIONS)

    assert excinfo.value.status_code == 401
