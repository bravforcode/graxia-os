"""Risk-based authentication evaluation and TOTP step-up helpers."""
from __future__ import annotations

import base64
import hashlib
import hmac
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable

from app.models.user import User


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass(slots=True)
class RiskAssessment:
    total: int
    level: RiskLevel
    factors: list[str] = field(default_factory=list)

    @property
    def requires_step_up(self) -> bool:
        return self.level in {RiskLevel.HIGH, RiskLevel.CRITICAL}

    @property
    def should_block(self) -> bool:
        return self.level == RiskLevel.CRITICAL


class RiskEngine:
    """Heuristic login risk scoring built around current session history."""

    def evaluate_login(
        self,
        *,
        user: User,
        device_fingerprint: str,
        ip_address: str,
        known_devices: Iterable[str],
        prior_failures: int = 0,
        recent_login_count: int = 0,
    ) -> RiskAssessment:
        score = 0
        factors: list[str] = []

        known_devices_set = {item for item in known_devices if item}
        if device_fingerprint not in known_devices_set:
            score += 35
            factors.append("new_device")

        if prior_failures >= 3:
            score += min(prior_failures * 10, 30)
            factors.append("prior_failures")

        if recent_login_count >= 3:
            score += min((recent_login_count - 2) * 10, 20)
            factors.append("high_velocity")

        if ip_address.startswith(("45.", "89.", "91.", "185.")):
            score += 20
            factors.append("high_risk_network")

        if not user.is_active:
            score = 100
            factors.append("inactive_user")

        if score >= 86:
            level = RiskLevel.CRITICAL
        elif score >= 61:
            level = RiskLevel.HIGH
        elif score >= 31:
            level = RiskLevel.MEDIUM
        else:
            level = RiskLevel.LOW

        return RiskAssessment(total=min(score, 100), level=level, factors=factors)


def _normalize_base32(secret: str) -> str:
    raw = "".join(secret.split()).upper()
    padding = (-len(raw)) % 8
    return raw + ("=" * padding)


def generate_totp_code(secret: str, *, at_time: int | None = None, period: int = 30, digits: int = 6) -> str:
    timestamp = int(at_time or time.time())
    counter = timestamp // period
    key = base64.b32decode(_normalize_base32(secret), casefold=True)
    message = struct.pack(">Q", counter)
    digest = hmac.new(key, message, hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    binary = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    code = binary % (10**digits)
    return str(code).zfill(digits)


def verify_totp_code(secret: str, code: str | None, *, at_time: int | None = None, window: int = 1) -> bool:
    if not secret or not code or not code.isdigit():
        return False
    now = int(at_time or time.time())
    for delta in range(-window, window + 1):
        expected = generate_totp_code(secret, at_time=now + (delta * 30))
        if hmac.compare_digest(expected, code):
            return True
    return False
