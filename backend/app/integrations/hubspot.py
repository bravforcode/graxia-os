from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class HubSpotClient:
    def __init__(self) -> None:
        self.token = (settings.HUBSPOT_PRIVATE_APP_TOKEN or "").strip()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def upsert_contact(self, *, email: str, properties: dict[str, Any]) -> dict[str, Any] | None:
        if not self.token:
            return None
        url = "https://api.hubapi.com/crm/v3/objects/contacts"
        payload = {"properties": {"email": email, **properties}}
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.post(url, headers=self._headers(), json=payload)
            if resp.status_code == 409:
                search = await client.post(
                    "https://api.hubapi.com/crm/v3/objects/contacts/search",
                    headers=self._headers(),
                    json={
                        "filterGroups": [
                            {"filters": [{"propertyName": "email", "operator": "EQ", "value": email}]}
                        ]
                    },
                )
                if search.status_code >= 400:
                    return None
                results = (search.json() or {}).get("results") or []
                if not results:
                    return None
                contact_id = results[0].get("id")
                if not contact_id:
                    return None
                patch = await client.patch(
                    f"https://api.hubapi.com/crm/v3/objects/contacts/{contact_id}",
                    headers=self._headers(),
                    json=payload,
                )
                if patch.status_code >= 400:
                    return None
                return patch.json()
            if resp.status_code >= 400:
                return None
            return resp.json()


hubspot_client = HubSpotClient()

