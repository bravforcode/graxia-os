import httpx
import pytest

from app.core.laya_client import LayaClient
from app.core.laya_probe import probe


def _client(answer):
    def handler(request):
        return httpx.Response(200, json={"model": "laya-rl-agent", "answers": {"action": answer}})

    return LayaClient(base_url="http://laya.test", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_probe_returns_chosen_action_from_laya():
    client = _client({"type": "choice", "choice": "reject_refund"})

    assert await probe(client) == "reject_refund"


@pytest.mark.asyncio
async def test_probe_raises_when_laya_choice_is_not_a_known_criterion():
    client = _client({"type": "choice", "choice": "maybe"})

    with pytest.raises(RuntimeError):
        await probe(client)
