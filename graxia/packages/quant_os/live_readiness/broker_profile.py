"""Broker profile model — defines expected runtime configuration per broker."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BrokerProfile:
    profile_id: str
    adapter: str  # must be "mt5"
    execution_mode: str  # "demo" | "live"
    expected_server: str
    account_currency: str
    symbols: dict[str, str]  # canonical_symbol -> broker_symbol mapping
    allowed_actions: list[str] = field(default_factory=lambda: ["READ_ONLY"])

    def __post_init__(self) -> None:
        if self.adapter != "mt5":
            raise ValueError(f"adapter must be 'mt5', got '{self.adapter}'")
        if self.execution_mode not in ("demo", "live"):
            raise ValueError(f"execution_mode must be 'demo' or 'live', got '{self.execution_mode}'")
        if "READ_ONLY" not in self.allowed_actions:
            raise ValueError("allowed_actions must include 'READ_ONLY' in Phase 3.2")


DEFAULT_PROFILE = BrokerProfile(
    profile_id="icmarkets_demo_mt5",
    adapter="mt5",
    execution_mode="demo",
    expected_server="ICMarkets-Demo02",
    account_currency="USD",
    symbols={
        "XAUUSD": "XAUUSD",
        "EURUSD": "EURUSD",
        "GBPUSD": "GBPUSD",
        "USDJPY": "USDJPY",
        "AUDUSD": "AUDUSD",
    },
    allowed_actions=["READ_ONLY"],
)
