"""Unit tests for the real 4-Layer RiskEngine.

Imports from risk.engine -- no inline class definitions.
"""

import time

import pytest

from graxia.packages.quant_os.risk.circuit_breaker import CircuitBreaker
from graxia.packages.quant_os.risk.engine import (
    AccountState,
    PortfolioState,
    RejectReason,
    RiskEngine,
    Signal,
)


class _FakeKillSwitch:
    """Minimal kill-switch mock that is never active."""

    def is_active(self):
        return False

    def is_paused(self):
        return False


@pytest.fixture
def engine():
    return RiskEngine(
        kill_switch=_FakeKillSwitch(),
        circuit_breaker=CircuitBreaker(),
    )


def _fresh_signal(**overrides) -> Signal:
    """Build a Signal with timestamp_epoch=now so it passes the staleness check."""
    defaults = dict(
        symbol="XAUUSD",
        conviction=0.8,
        entry_price=2400.0,
        stop_loss=2390.0,
        take_profit=2420.0,
        direction="BUY",
        timestamp_epoch=time.time(),
    )
    defaults.update(overrides)
    return Signal(**defaults)


class TestRiskApproval:
    def test_within_limits_approved(self, engine):
        signal = _fresh_signal()
        account = AccountState(equity=100_000, daily_pnl=0, weekly_pnl=0, open_positions=2)
        portfolio = PortfolioState(total_exposure_pct=0.2, position_symbols=["SYM1", "SYM2"])
        verdict = engine.evaluate(signal, account, portfolio)
        assert verdict.approved is True
        assert verdict.approved_quantity > 0


class TestLowConviction:
    def test_below_min_conviction_rejected(self, engine):
        signal = _fresh_signal(conviction=0.3)
        account = AccountState()
        portfolio = PortfolioState()
        verdict = engine.evaluate(signal, account, portfolio)
        assert verdict.approved is False
        assert verdict.reason_code == RejectReason.LOW_CONVICTION


class TestDailyLoss:
    def test_exceeds_daily_loss_rejected(self, engine):
        signal = _fresh_signal()
        account = AccountState(equity=100_000, daily_pnl=-2_500, weekly_pnl=0)
        portfolio = PortfolioState()
        verdict = engine.evaluate(signal, account, portfolio)
        assert verdict.approved is False
        assert verdict.reason_code == RejectReason.DAILY_LOSS_LIMIT


class TestMaxPositions:
    def test_at_max_positions_rejected(self, engine):
        signal = _fresh_signal()
        account = AccountState()
        # 20 symbols = default max for 100k equity
        symbols = [f"SYM{i}" for i in range(20)]
        portfolio = PortfolioState(position_symbols=symbols)
        verdict = engine.evaluate(signal, account, portfolio)
        assert verdict.approved is False
        assert verdict.reason_code == RejectReason.MAX_POSITIONS_REACHED

    def test_under_max_positions_approved(self, engine):
        signal = _fresh_signal()
        account = AccountState()
        portfolio = PortfolioState(position_symbols=["SYM1", "SYM2", "SYM3"])
        verdict = engine.evaluate(signal, account, portfolio)
        assert verdict.approved is True
