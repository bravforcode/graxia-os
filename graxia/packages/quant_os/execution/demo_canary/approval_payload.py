"""Human approval payload model."""
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import secrets

@dataclass(frozen=True)
class ApprovalPayload:
    """
    Human operator approval. Bound to one canary plan.

    Contains: canary_id, plan_hash_prefix, environment, nonce, expiry.
    NO credentials, NO raw account identity.
    """
    schema_version: str = "1.0"
    canary_id: str = ""
    plan_hash: str = ""
    environment: str = "PEPPERSTONE_DEMO_ONLY"
    purpose: str = "EXECUTION_LIFECYCLE_VALIDATION"
    symbol: str = "XAUUSD"
    volume: str = "0.01"
    expires_at_utc: str = ""
    approval_nonce: str = ""
    operator_fingerprint: str = ""

    @staticmethod
    def generate_nonce() -> str:
        return secrets.token_hex(32)

    def is_expired(self) -> bool:
        if not self.expires_at_utc:
            return False
        from datetime import datetime
        expiry = datetime.fromisoformat(self.expires_at_utc)
        return datetime.now(timezone.utc) > expiry
