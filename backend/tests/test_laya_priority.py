import json

import httpx
import pytest

from app.core.laya_client import LayaClient
from app.core.laya_priority import laya_action_priority

OPPORTUNITY = {
    "type": "hackathon",
    "source_platform": "devpost",
    "location_type": "global",
    "tags": ["ai"],
    "prize_amount": "10000 USD",
    "days_until_deadline": 5,
}


def _client(handler):
    return LayaClient(base_url="http://laya.test", transport=httpx.MockTransport(handler))


def _answering(choice):
    def handler(request):
        return httpx.Response(
            200,
            json={"model": "laya-rl-agent", "answers": {"action_priority": {"type": "choice", "choice": choice}}},
        )

    return _client(handler)


@pytest.mark.asyncio
async def test_returns_laya_choice_for_known_priority():
    assert await laya_action_priority(_answering("do_now"), OPPORTUNITY) == "do_now"


@pytest.mark.asyncio
async def test_sends_opportunity_as_state():
    seen = {}

    def handler(request):
        seen["body"] = request.read()
        return httpx.Response(
            200,
            json={"model": "laya-rl-agent", "answers": {"action_priority": {"type": "choice", "choice": "skip"}}},
        )

    await laya_action_priority(_client(handler), OPPORTUNITY)

    assert json.loads(seen["body"])["state"] == OPPORTUNITY


@pytest.mark.asyncio
async def test_returns_none_when_laya_choice_is_unknown():
    assert await laya_action_priority(_answering("maybe"), OPPORTUNITY) is None


@pytest.mark.asyncio
async def test_returns_none_when_laya_answers_error_status():
    client = _client(lambda request: httpx.Response(500, text="boom"))

    assert await laya_action_priority(client, OPPORTUNITY) is None


@pytest.mark.asyncio
async def test_returns_none_when_laya_unreachable():
    def handler(request):
        raise httpx.ConnectError("tunnel down")

    assert await laya_action_priority(_client(handler), OPPORTUNITY) is None
