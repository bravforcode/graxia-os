"""Phase BE-P2 — Canonical tick schema."""
from dataclasses import dataclass, asdict
import hashlib
import json


@dataclass
class TickRecord:
    """Canonical tick schema per BE-P2 spec."""
    tick_id: int = 0
    ingest_sequence: int = 0
    source_timestamp_utc: str = ""
    source_time_msc: int = 0
    received_at_utc: str = ""
    received_monotonic_ns: int = 0
    broker: str = ""
    server_fingerprint: str = ""
    account_mode: str = ""
    symbol: str = ""
    bid: float = 0.0
    ask: float = 0.0
    last: float = 0.0
    spread_price: float = 0.0
    spread_points: float = 0.0
    flags: int = 0
    volume: float = 0.0
    volume_real: float = 0.0
    session_id: str = ""
    contract_snapshot_id: str = ""
    raw_payload_hash: str = ""
    partition_hash: str = ""

    def compute_hashes(self) -> None:
        """Compute raw payload and partition hashes."""
        d = asdict(self)
        d.pop("raw_payload_hash", None)
        d.pop("partition_hash", None)
        self.raw_payload_hash = hashlib.sha256(
            json.dumps(d, sort_keys=True, default=str).encode()
        ).hexdigest()

    def compute_spread(self) -> None:
        """Compute spread from bid/ask."""
        if self.bid > 0 and self.ask > 0:
            self.spread_price = round(self.ask - self.bid, 10)
            # Points spread = spread_price / point (approximate)
            self.spread_points = round(self.spread_price / 0.01, 10) if self.symbol == "XAUUSD" else round(self.spread_price / 0.00001, 10)

    def validate(self) -> tuple[bool, list[str]]:
        """Validate tick against data quality rules."""
        issues = []
        if self.bid <= 0:
            issues.append("bid must be > 0")
        if self.ask <= 0:
            issues.append("ask must be > 0")
        if self.ask < self.bid:
            issues.append("ask < bid (inverted quote)")
        if not self.symbol:
            issues.append("symbol is required")
        if not self.source_timestamp_utc:
            issues.append("source_timestamp_utc is required")
        return len(issues) == 0, issues

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TickRecord":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})
