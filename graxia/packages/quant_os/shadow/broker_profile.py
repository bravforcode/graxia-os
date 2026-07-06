"""Broker profile for Pepperstone MT5 — verified.

.. deprecated::
    Use ``runtime.broker_identity_guard.BrokerProfile`` instead.
    This module will be removed in a future release.
"""

import hashlib
import json
from dataclasses import asdict, dataclass


@dataclass
class BrokerProfile:
    """Expected broker profile. Mismatch = fail-closed."""

    expected_server: str = "Pepperstone-Demo"
    terminal_path: str = r"C:\Program Files\Pepperstone MetaTrader 5\terminal64.exe"
    # Symbol expectations (XAUUSD)
    expected_symbol: str = "XAUUSD"
    expected_contract_size: float = 100.0
    expected_digits: int = 2
    expected_point: float = 0.01
    # Profile identity
    profile_fingerprint: str = ""
    # Clock provenance (from 4-variant diagnostic)
    tick_time_source: str = "BROKER_SERVER_TIME_NOT_UTC"  # symbol_info_tick uses server time
    copy_ticks_range_source: str = "UTC_VERIFIED"  # copy_ticks_range returns UTC
    copy_ticks_from_source: str = "STALE_CACHE"  # copy_ticks_from returns stale data
    bar_time_source: str = "BROKER_SERVER_TIME_NOT_UTC"  # M1/H1 bars use server time

    def compute_fingerprint(self) -> str:
        d = {
            "expected_server": self.expected_server,
            "expected_symbol": self.expected_symbol,
            "expected_contract_size": self.expected_contract_size,
            "expected_digits": self.expected_digits,
            "expected_point": self.expected_point,
            "terminal_path": self.terminal_path,
        }
        self.profile_fingerprint = hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]
        return self.profile_fingerprint

    def to_dict(self) -> dict:
        return asdict(self)


def validate_broker_match(
    actual_server: str,
    actual_login: int,
    actual_contract_size: float,
    actual_digits: int,
    actual_point: float,
    profile: BrokerProfile,
) -> tuple[bool, list[str]]:
    """Validate actual broker matches expected profile."""
    issues = []
    if actual_server != profile.expected_server:
        issues.append(f"SERVER_MISMATCH: expected={profile.expected_server} actual={actual_server}")
    if abs(actual_contract_size - profile.expected_contract_size) > 0.01:
        issues.append(f"CONTRACT_MISMATCH: expected={profile.expected_contract_size} actual={actual_contract_size}")
    if actual_digits != profile.expected_digits:
        issues.append(f"DIGITS_MISMATCH: expected={profile.expected_digits} actual={actual_digits}")
    if abs(actual_point - profile.expected_point) > 0.0001:
        issues.append(f"POINT_MISMATCH: expected={profile.expected_point} actual={actual_point}")
    return len(issues) == 0, issues
