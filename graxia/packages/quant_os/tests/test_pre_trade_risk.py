"""Tests for risk/pre_trade_risk.py — pre-trade risk gate.

Each risk check (kill switch, circuit breaker, daily/weekly/drawdown limits,
position count, order rate, margin level) is tested in isolation and combined.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock

from graxia.packages.quant_os.risk.pre_trade_risk import (
    pre_trade_check,
)

# ---------------------------------------------------------------------------
# Helpers — lightweight mock replacements for heavy dependencies
# ---------------------------------------------------------------------------


def _make_sizing_result(rejected: bool = False, rejection_reasons: list[str] | None = None) -> MagicMock:
    """Create a mock SizingResult."""
    sr = MagicMock()
    sr.rejected = rejected
    sr.rejection_reasons = rejection_reasons or []
    return sr


def _make_risk_policy(
    risk_per_trade_bps: int = 10,
    max_daily_loss_bps: int = 50,
    max_weekly_loss_bps: int = 150,
    max_total_drawdown_bps: int = 300,
    max_open_positions: int = 1,
    max_orders_per_day: int = 3,
    min_margin_level_pct: int = 500,
) -> MagicMock:
    """Create a mock RiskPolicy with fraction properties."""
    rp = MagicMock()
    rp.risk_per_trade_fraction = Decimal(risk_per_trade_bps) / Decimal(10000)
    rp.max_daily_loss_fraction = Decimal(max_daily_loss_bps) / Decimal(10000)
    rp.max_weekly_loss_fraction = Decimal(max_weekly_loss_bps) / Decimal(10000)
    rp.max_total_drawdown_fraction = Decimal(max_total_drawdown_bps) / Decimal(10000)
    rp.max_positions = max_open_positions
    rp.max_orders_per_day = max_orders_per_day
    rp.min_margin_level_pct = Decimal(min_margin_level_pct)
    return rp


def _make_risk_ledger(
    daily_realized_loss: float = 0.0,
    weekly_realized_loss: float = 0.0,
    total_drawdown: float = 0.0,
    open_positions: int = 0,
    orders_today: int = 0,
) -> MagicMock:
    """Create a mock RiskLedger."""
    rl = MagicMock()
    rl.daily_realized_loss = daily_realized_loss
    rl.weekly_realized_loss = weekly_realized_loss
    rl.total_drawdown = total_drawdown
    rl.open_positions = open_positions
    rl.orders_today = orders_today
    return rl


def _make_kill_switch(active: bool = False) -> MagicMock:
    """Create a mock KillSwitch."""
    ks = MagicMock()
    ks.is_active.return_value = active
    return ks


def _make_circuit_breaker(open: bool = False, reason: str = "") -> MagicMock:
    """Create a mock CircuitBreaker."""
    cb = MagicMock()
    cb.is_open.return_value = open
    cb.reason = reason
    return cb


# ---------------------------------------------------------------------------
# Tests — individual checks
# ---------------------------------------------------------------------------


class TestKillSwitch:
    """Kill switch integration with pre-trade gate."""

    def test_kill_switch_blocks_trade(self) -> None:
        """When kill switch is active, trade is rejected with clear reason."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(),
            risk_ledger=_make_risk_ledger(),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=True),
        )
        assert not result.approved
        assert any("Kill switch" in r for r in result.reasons)

    def test_kill_switch_none_rejects_trade(self) -> None:
        """When kill_switch=None, trade is rejected (fail-closed)."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(),
            risk_ledger=_make_risk_ledger(),
            account_equity=Decimal("10000"),
            kill_switch=None,
        )
        assert not result.approved
        assert any("kill_switch is required" in r for r in result.reasons)


class TestCircuitBreaker:
    """Circuit breaker integration with pre-trade gate."""

    def test_circuit_breaker_blocks_trade(self) -> None:
        """When circuit breaker is open for the asset class, trade is rejected."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(),
            risk_ledger=_make_risk_ledger(),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
            circuit_breaker=_make_circuit_breaker(open=True, reason="3 consecutive losses"),
            asset_class="metals",
        )
        assert not result.approved
        assert any("Circuit breaker" in r for r in result.reasons)

    def test_circuit_breaker_closed_allows_trade(self) -> None:
        """When circuit breaker is closed, trade passes this check."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(),
            risk_ledger=_make_risk_ledger(),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
            circuit_breaker=_make_circuit_breaker(open=False),
            asset_class="metals",
        )
        assert result.approved

    def test_circuit_breaker_no_asset_class_skipped(self) -> None:
        """When asset_class is empty, circuit breaker check is skipped."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(),
            risk_ledger=_make_risk_ledger(),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
            circuit_breaker=_make_circuit_breaker(open=True),
            asset_class="",
        )
        assert result.approved


class TestSizerRejection:
    """Sizer rejection propagation."""

    def test_sizer_rejected_blocks_trade(self) -> None:
        """When sizer rejects, reasons are forwarded."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(rejected=True, rejection_reasons=["Volume below minimum"]),
            risk_policy=_make_risk_policy(),
            risk_ledger=_make_risk_ledger(),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
        )
        assert not result.approved
        assert "Volume below minimum" in result.reasons


class TestDailyLossLimit:
    """Daily loss limit check."""

    def test_daily_loss_limit_blocks_trade(self) -> None:
        """When daily loss >= max daily loss fraction * equity, trade is rejected."""
        # max_daily_loss_bps=50 → fraction=0.005 → 0.5% of $10000 = $50
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(max_daily_loss_bps=50),
            risk_ledger=_make_risk_ledger(daily_realized_loss=50.0),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
        )
        assert not result.approved
        assert any("Daily loss" in r for r in result.reasons)

    def test_daily_loss_below_limit_passes(self) -> None:
        """When daily loss is below limit, trade passes."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(max_daily_loss_bps=50),
            risk_ledger=_make_risk_ledger(daily_realized_loss=49.99),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
        )
        assert result.approved


class TestWeeklyLossLimit:
    """Weekly loss limit check."""

    def test_weekly_loss_limit_blocks_trade(self) -> None:
        """When weekly loss >= max weekly loss fraction * equity, trade is rejected."""
        # max_weekly_loss_bps=150 → fraction=0.015 → 1.5% of $10000 = $150
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(max_weekly_loss_bps=150),
            risk_ledger=_make_risk_ledger(weekly_realized_loss=150.0),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
        )
        assert not result.approved
        assert any("Weekly loss" in r for r in result.reasons)


class TestDrawdownLimit:
    """Total drawdown limit check."""

    def test_drawdown_limit_blocks_trade(self) -> None:
        """When drawdown >= max drawdown fraction * equity, trade is rejected."""
        # max_total_drawdown_bps=300 → fraction=0.03 → 3% of $10000 = $300
        # total_drawdown in ledger is compared as absolute: Decimal(str(value)) >= equity * fraction
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(max_total_drawdown_bps=300),
            risk_ledger=_make_risk_ledger(total_drawdown=300.0),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
        )
        assert not result.approved
        assert any("Drawdown" in r for r in result.reasons)


class TestMaxPositions:
    """Max open positions check."""

    def test_max_positions_blocks_trade(self) -> None:
        """When open positions >= max_positions, trade is rejected."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(max_open_positions=1),
            risk_ledger=_make_risk_ledger(open_positions=1),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
        )
        assert not result.approved
        assert any("Max positions" in r for r in result.reasons)


class TestMaxOrdersPerDay:
    """Max orders per day check."""

    def test_max_orders_blocks_trade(self) -> None:
        """When orders_today >= max_orders_per_day, trade is rejected."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(max_orders_per_day=3),
            risk_ledger=_make_risk_ledger(orders_today=3),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
        )
        assert not result.approved
        assert any("Max orders" in r for r in result.reasons)


class TestMarginLevel:
    """Margin level check."""

    def test_margin_level_too_low_blocks_trade(self) -> None:
        """When margin_level_pct < min_margin_level_pct, trade is rejected."""
        # min_margin_level_pct=500 → need >= 500%
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(min_margin_level_pct=500),
            risk_ledger=_make_risk_ledger(),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
            margin_level_pct=Decimal("499"),
        )
        assert not result.approved
        assert any("Margin level" in r for r in result.reasons)

    def test_margin_level_none_skips_check(self) -> None:
        """When margin_level_pct=None, the margin check is skipped."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(min_margin_level_pct=500),
            risk_ledger=_make_risk_ledger(),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
            margin_level_pct=None,
        )
        assert result.approved


# ---------------------------------------------------------------------------
# Tests — happy path and combined scenarios
# ---------------------------------------------------------------------------


class TestHappyPath:
    """All checks pass → trade approved."""

    def test_all_checks_pass(self) -> None:
        """When every check passes, trade is approved with empty reasons."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(),
            risk_ledger=_make_risk_ledger(),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
            circuit_breaker=_make_circuit_breaker(open=False),
            asset_class="metals",
            margin_level_pct=Decimal("1000"),
        )
        assert result.approved
        assert result.reasons == []
        assert result.risk_budget > 0

    def test_risk_budget_calculated_correctly(self) -> None:
        """risk_budget = account_equity * risk_per_trade_fraction."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(risk_per_trade_bps=10),
            risk_ledger=_make_risk_ledger(),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
        )
        # 10 bps = 0.001 → $10000 * 0.001 = $10
        assert result.risk_budget == Decimal("10.0000")


class TestMultipleFailures:
    """Multiple checks fail → all reasons returned."""

    def test_multiple_failures_reported(self) -> None:
        """When multiple checks fail, all rejection reasons are collected."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(rejected=True, rejection_reasons=["Sizer: volume too small"]),
            risk_policy=_make_risk_policy(
                max_daily_loss_bps=50,
                max_weekly_loss_bps=150,
                max_open_positions=1,
            ),
            risk_ledger=_make_risk_ledger(
                daily_realized_loss=100.0,
                weekly_realized_loss=200.0,
                open_positions=2,
            ),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=True),
        )
        assert not result.approved
        # Should have at least: kill switch, sizer, daily loss, weekly loss, max positions
        assert len(result.reasons) >= 4

    def test_result_metadata_populated(self) -> None:
        """RiskCheckResult fields are populated even on rejection."""
        result = pre_trade_check(
            sizing_result=_make_sizing_result(),
            risk_policy=_make_risk_policy(),
            risk_ledger=_make_risk_ledger(
                daily_realized_loss=10.0,
                weekly_realized_loss=20.0,
                total_drawdown=0.001,
                orders_today=2,
                open_positions=1,
            ),
            account_equity=Decimal("10000"),
            kill_switch=_make_kill_switch(active=False),
        )
        assert result.daily_loss == Decimal("10.0")
        assert result.weekly_loss == Decimal("20.0")
        assert result.total_drawdown == Decimal("0.001")
        assert result.orders_today == 2
        assert result.open_positions == 1
