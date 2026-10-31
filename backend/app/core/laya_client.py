"""Client for the Laya System-1 decision endpoint (POST /v1/systemone).

Laya answers choice and score questions over a state. It is a decision engine,
not a text generator, so it is kept apart from the llm provider layer.
"""

import httpx

from app.config import settings


class LayaError(Exception):
    def __init__(self, status_code: int, body: str):
        super().__init__(f"laya /v1/systemone failed: HTTP {status_code}: {body[:500]}")
        self.status_code = status_code


class LayaClient:
    def __init__(
        self,
        base_url: str,
        api_key: str = "",
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._url = f"{base_url.rstrip('/')}/v1/systemone"
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout
        self._transport = transport

    async def systemone(self, state: str | dict | list, questions: dict) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout, transport=self._transport) as client:
            response = await client.post(
                self._url,
                json={"state": state, "questions": questions},
                headers=self._headers,
            )
        if response.status_code != 200:
            raise LayaError(response.status_code, response.text)
        return response.json()["answers"]


def laya_client_from_settings() -> LayaClient:
    if not settings.LAYA_BASE_URL:
        raise RuntimeError("LAYA_BASE_URL is not set")
    return LayaClient(
        base_url=settings.LAYA_BASE_URL,
        api_key=settings.LAYA_API_KEY,
        timeout=settings.LAYA_TIMEOUT_SECONDS,
    )
