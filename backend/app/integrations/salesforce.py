from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


def _validate_safe_email(email: str) -> bool:
    """Validate email to prevent SOQL injection."""
    # Basic email validation
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, email):
        return False

    # Check for dangerous characters that could cause SOQL injection
    dangerous_chars = ["'", '"', ';', '--', '/*', '*/', 'xp_', 'sp_']
    if any(char in email.lower() for char in dangerous_chars):
        return False

    return True


class SalesforceClient:
    def __init__(self) -> None:
        self.instance_url = (settings.SALESFORCE_INSTANCE_URL or "").rstrip("/")
        self.access_token = (settings.SALESFORCE_ACCESS_TOKEN or "").strip()

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    async def upsert_lead(self, *, email: str, fields: dict[str, Any]) -> dict[str, Any] | None:
        if not self.instance_url or not self.access_token:
            return None
        if not _validate_safe_email(email):
            return None
        escaped_email = email.replace("'", "\\'")
        query = (
            f"SELECT Id,Email FROM Lead WHERE Email = '{escaped_email}' LIMIT 1"
        )
        async with httpx.AsyncClient(timeout=20.0) as client:
            q = await client.get(f"{self.instance_url}/services/data/v59.0/query", headers=self._headers(), params={"q": query})
            if q.status_code >= 400:
                return None
            records = (q.json() or {}).get("records") or []
            if records:
                lead_id = records[0].get("Id")
                if not lead_id:
                    return None
                patch = await client.patch(
                    f"{self.instance_url}/services/data/v59.0/sobjects/Lead/{lead_id}",
                    headers=self._headers(),
                    json={"Email": email, **fields},
                )
                if patch.status_code >= 400:
                    return None
                return {"id": lead_id, "updated": True}
            create = await client.post(
                f"{self.instance_url}/services/data/v59.0/sobjects/Lead",
                headers=self._headers(),
                json={"Email": email, **fields},
            )
            if create.status_code >= 400:
                return None
            return {"id": (create.json() or {}).get("id"), "created": True}


salesforce_client = SalesforceClient()
