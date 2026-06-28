import pytest
from dataclasses import dataclass


@dataclass
class RiskLimits:
    max_daily_loss_pct: float = 0.03
    max_positions: int = 5
    max_position_size: float = 1.0


@dataclass
class PortfolioState:
    daily_pnl_pct: float = 0.0
    open_positions: int = 0


class RiskEngine:
    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()

    def check(self, portfolio: PortfolioState) -> tuple[bool, str]:
        if portfolio.daily_pnl_pct <= -self.limits.max_daily_loss_pct:
            return False, "daily_loss_exceeded"
        if portfolio.open_positions >= self.limits.max_positions:
            return False, "max_positions_exceeded"
        return True, "approved"


@pytest.fixture
def engine():
    return RiskEngine()


class TestRiskApproval:
    def test_within_limits_approved(self, engine):
        state = PortfolioState(daily_pnl_pct=-0.01, open_positions=2)
        ok, reason = engine.check(state)
        assert ok is True
        assert reason == "approved"


class TestDailyLoss:
    def test_exceeds_daily_loss_rejected(self, engine):
        state = PortfolioState(daily_pnl_pct=-0.035, open_positions=1)
        ok, reason = engine.check(state)
        assert ok is False
        assert reason == "daily_loss_exceeded"

    def test_exactly_at_limit_rejected(self, engine):
        state = PortfolioState(daily_pnl_pct=-0.03, open_positions=1)
        ok, reason = engine.check(state)
        assert ok is False
        assert reason == "daily_loss_exceeded"


class TestMaxPositions:
    def test_exceeds_max_positions_rejected(self, engine):
        state = PortfolioState(daily_pnl_pct=0.0, open_positions=5)
        ok, reason = engine.check(state)
        assert ok is False
        assert reason == "max_positions_exceeded"

    def test_under_max_positions_approved(self, engine):
        state = PortfolioState(daily_pnl_pct=0.0, open_positions=4)
        ok, reason = engine.check(state)
        assert ok is True
        assert reason == "approved"
