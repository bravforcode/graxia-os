from dataclasses import dataclass, field
from typing import Optional
import hashlib
import json

@dataclass
class BrokerValidationCheck:
    name: str
    passed: bool
    evidence: str

@dataclass
class BrokerValidationReport:
    checks: list[BrokerValidationCheck] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def add_check(self, name: str, passed: bool, evidence: str) -> None:
        self.checks.append(BrokerValidationCheck(name=name, passed=passed, evidence=evidence))

    def fingerprint(self) -> str:
        data = json.dumps([{"name": c.name, "passed": c.passed} for c in self.checks], sort_keys=True)
        return hashlib.sha256(data.encode()).hexdigest()

class BrokerValidator:
    """Validate broker behavior before canary execution."""

    def validate_account_mode(self, account_mode: str) -> BrokerValidationCheck:
        if account_mode != "DEMO":
            return BrokerValidationCheck("ACCOUNT_MODE", False, f"mode={account_mode}, required=DEMO")
        return BrokerValidationCheck("ACCOUNT_MODE", True, "DEMO account verified")

    def validate_symbol(self, symbol: str, contract_specs: dict) -> BrokerValidationCheck:
        if not contract_specs:
            return BrokerValidationCheck("CONTRACT_SPECS", False, f"no specs for {symbol}")
        return BrokerValidationCheck("CONTRACT_SPECS", True, f"specs loaded for {symbol}")

    def validate_stop_loss(self, order: dict) -> BrokerValidationCheck:
        sl = order.get("stop_loss")
        if not sl or sl <= 0:
            return BrokerValidationCheck("STOP_LOSS", False, f"sl={sl}")
        return BrokerValidationCheck("STOP_LOSS", True, f"sl={sl}")

    def validate_position_limits(self, open_positions: int, max_positions: int) -> BrokerValidationCheck:
        if open_positions >= max_positions:
            return BrokerValidationCheck("POSITION_LIMIT", False, f"open={open_positions}, max={max_positions}")
        return BrokerValidationCheck("POSITION_LIMIT", True, f"open={open_positions}, max={max_positions}")

    def validate_daily_orders(self, orders_today: int, max_orders: int) -> BrokerValidationCheck:
        if orders_today >= max_orders:
            return BrokerValidationCheck("DAILY_ORDER_LIMIT", False, f"today={orders_today}, max={max_orders}")
        return BrokerValidationCheck("DAILY_ORDER_LIMIT", True, f"today={orders_today}, max={max_orders}")

    def validate_full(self, config, symbol: str, contract_specs: dict, order: dict = None,
                      open_positions: int = 0, orders_today: int = 0) -> BrokerValidationReport:
        report = BrokerValidationReport()
        report.add_check(*self.validate_account_mode(config.account_mode_required))
        report.add_check(*self.validate_symbol(symbol, contract_specs))

        if order:
            report.add_check(*self.validate_stop_loss(order))

        report.add_check(*self.validate_position_limits(open_positions, config.max_open_positions))
        report.add_check(*self.validate_daily_orders(orders_today, config.max_orders_per_day))

        return report
