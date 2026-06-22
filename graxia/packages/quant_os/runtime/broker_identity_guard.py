"""Phase BE-P0 — Broker identity guard. Refuse startup on profile mismatch."""
from dataclasses import dataclass
import hashlib
import json


@dataclass
class BrokerProfile:
    profile_id: str
    expected_server: str
    account_mode: str  # DEMO, LIVE
    account_currency: str
    account_login: int
    terminal_path_hash: str = ""
    login_identity_hash: str = ""
    symbol_mappings: dict = None
    required_contract_fields: list = None
    
    def __post_init__(self):
        if self.symbol_mappings is None:
            self.symbol_mappings = {}
        if self.required_contract_fields is None:
            self.required_contract_fields = [
                "trade_contract_size", "volume_min", "volume_max",
                "volume_step", "trade_tick_size", "trade_tick_value", "stops_level"
            ]


@dataclass
class ProfileFingerprint:
    server_hash: str
    login_hash: str
    account_mode: str
    account_currency: str
    captured_at: str


class BrokerIdentityGuard:
    """Enforces broker identity match at startup."""
    
    def __init__(self, expected_profile: BrokerProfile):
        self._expected = expected_profile
        self._violations: list[str] = []
    
    def validate(self, actual_server: str, actual_login: int, 
                 actual_mode: str, actual_currency: str) -> tuple[bool, list[str]]:
        """Validate actual broker profile against expected."""
        self._violations = []
        
        if actual_server != self._expected.expected_server:
            self._violations.append(
                f"server_mismatch: expected={self._expected.expected_server}, got={actual_server}"
            )
        
        if actual_mode != self._expected.account_mode:
            self._violations.append(
                f"account_mode_mismatch: expected={self._expected.account_mode}, got={actual_mode}"
            )
        
        if actual_currency != self._expected.account_currency:
            self._violations.append(
                f"currency_mismatch: expected={self._expected.account_currency}, got={actual_currency}"
            )
        
        if actual_login != self._expected.account_login:
            self._violations.append(
                f"login_mismatch: expected={self._expected.account_login}, got={actual_login}"
            )
        
        return len(self._violations) == 0, self._violations
    
    def compute_fingerprint(self, server: str, login: int,
                            mode: str = "", currency: str = "") -> ProfileFingerprint:
        """Compute fingerprint for the actual profile with timestamp."""
        from datetime import datetime, timezone
        return ProfileFingerprint(
            server_hash=hashlib.sha256(server.encode()).hexdigest(),
            login_hash=hashlib.sha256(str(login).encode()).hexdigest(),
            account_mode=mode,
            account_currency=currency,
            captured_at=datetime.now(timezone.utc).isoformat()
        )
    
    def is_violation(self) -> bool:
        return len(self._violations) > 0
    
    def get_violations(self) -> list[str]:
        return self._violations.copy()
