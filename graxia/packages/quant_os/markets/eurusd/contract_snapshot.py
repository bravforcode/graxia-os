import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class EURUSDContractSnapshot:
    """EURUSD MT5 contract specification."""

    symbol: str = "EURUSD"
    contract_size: Decimal = Decimal("100000")  # Standard lot = 100k units
    min_volume: Decimal = Decimal("0.01")
    max_volume: Decimal = Decimal("100.0")
    volume_step: Decimal = Decimal("0.01")
    tick_size: Decimal = Decimal("0.00001")  # 1 point (1/10 pip)
    tick_value: Decimal = Decimal("1.0")  # $1 per point per standard lot
    digits: int = 5
    spread_typical: Decimal = Decimal("1.0")  # 1 pip typical
    swap_long: Decimal = Decimal("-0.5")
    swap_short: Decimal = Decimal("0.3")
    margin_currency: str = "USD"
    profit_currency: str = "USD"

    def fingerprint(self) -> str:
        data = json.dumps(
            {
                "symbol": self.symbol,
                "contract_size": str(self.contract_size),
                "tick_size": str(self.tick_size),
                "tick_value": str(self.tick_value),
                "digits": self.digits,
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()

    def validate(self) -> tuple[bool, list[str]]:
        issues = []
        if self.contract_size <= 0:
            issues.append("contract_size must be positive")
        if self.tick_size <= 0:
            issues.append("tick_size must be positive")
        if self.min_volume >= self.max_volume:
            issues.append("min_volume must be less than max_volume")
        if self.digits < 2:
            issues.append("digits must be at least 2")
        return len(issues) == 0, issues


@dataclass(frozen=True)
class XAUUSDContractSnapshot:
    """XAUUSD MT5 contract specification (for reference/comparison only)."""

    symbol: str = "XAUUSD"
    contract_size: Decimal = Decimal("100")  # 100 oz per lot
    min_volume: Decimal = Decimal("0.01")
    max_volume: Decimal = Decimal("100.0")
    volume_step: Decimal = Decimal("0.01")
    tick_size: Decimal = Decimal("0.01")
    tick_value: Decimal = Decimal("1.0")
    digits: int = 2
    spread_typical: Decimal = Decimal("3.0")  # 30 points
    swap_long: Decimal = Decimal("-2.5")
    swap_short: Decimal = Decimal("0.5")
    margin_currency: str = "USD"
    profit_currency: str = "USD"
