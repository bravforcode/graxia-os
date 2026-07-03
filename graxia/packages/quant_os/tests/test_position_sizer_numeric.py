"""
Position Sizer Test — Assert actual numeric values.

Verifies that units_per_lot config is correctly used in position sizing.
Calculates expected values by hand and asserts them.

NOTE: _apply_limits() caps position based on max_portfolio_exposure_pct (50%).
For $10k account, max_exposure = $5000. Any notional > $5000 gets scaled down.
"""

from decimal import Decimal

import pytest
from quant_os.risk.position_sizer import FixedFractionalSizer


class TestPositionSizerNumeric:
    """
    Assert exact numeric values for position sizing.

    Key insight: _apply_limits() caps notional at max_portfolio_exposure_pct (50%).
    For $10k account, max_exposure = $5000. Positions above this get scaled down.

    Case 1: Gold, 1% risk, $10k, 5-point stop
        risk_amount = 10000 * 1.0 / 100 = 100
        price_risk = abs(2350 - 2345) = 5
        units = 100 / 5 = 20
        lots = 20 / 100 = 0.2
        notional = 20 * 2350 = 47000
        BUT: max_exposure = 10000 * 50% = 5000
        Scale: ratio = 5000 / 47000 = 0.1064
        Final: lots = 0.2 * 0.1064 → 0.02, units = 20 * 0.1064 → 2

    Case 2: Gold, small stop (1 point), same account
        units = 100 / 1 = 100
        notional = 100 * 2350 = 235000
        Scale: ratio = 5000 / 235000 = 0.0213
        Final: lots = 0.01, units = 2

    Case 3: Gold vs Forex — same risk, different lot sizes
        The ratio of lots should reflect units_per_lot difference
    """

    def test_gold_exposure_cap_applied(self):
        """Gold: notional capped by max_portfolio_exposure_pct"""
        sizer = FixedFractionalSizer(risk_pct=1.0, units_per_lot=100.0)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("2350"),
            stop_loss=Decimal("2345"),
            symbol="XAUUSD",
        )

        # Hand calc with exposure cap:
        # risk=100, price_risk=5, units=20, lots=0.2
        # notional=20*2350=47000, max_exposure=5000
        # ratio=5000/47000=0.1064, final_lots=0.2*0.1064=0.021→0.02
        assert result.lots == Decimal("0.02"), f"Expected 0.02 lots (capped), got {result.lots}"
        assert result.units == Decimal("2"), f"Expected 2 units (capped), got {result.units}"
        assert result.risk_pct == pytest.approx(0.1, abs=0.01)

    def test_gold_small_stop(self):
        """Gold: 1-point stop → smaller position"""
        sizer = FixedFractionalSizer(risk_pct=1.0, units_per_lot=100.0)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("2350"),
            stop_loss=Decimal("2349"),  # 1 point stop
            symbol="XAUUSD",
        )

        # risk=100, price_risk=1, units=100, lots=1.0
        # notional=100*2350=235000, max_exposure=5000
        # ratio=5000/235000=0.0213, final_lots=1.0*0.0213=0.021→0.02
        assert result.lots == Decimal("0.02"), f"Expected 0.02 lots, got {result.lots}"

    def test_gold_no_exposure_cap_when_small(self):
        """Gold: small notional doesn't hit exposure cap"""
        sizer = FixedFractionalSizer(risk_pct=0.1, units_per_lot=100.0)
        result = sizer.calculate(
            account_balance=Decimal("100000"),  # Large account
            entry_price=Decimal("2350"),
            stop_loss=Decimal("2345"),
            symbol="XAUUSD",
        )

        # risk=100, price_risk=5, units=20, lots=0.2
        # notional=20*2350=47000, max_exposure=100000*50%=50000
        # 47000 < 50000, so NO cap applied
        assert result.lots == Decimal("0.20"), f"Expected 0.20 lots (no cap), got {result.lots}"
        assert result.units == Decimal("20"), f"Expected 20 units, got {result.units}"

    def test_forex_exposure_cap(self):
        """Forex: notional capped by exposure limit"""
        sizer = FixedFractionalSizer(risk_pct=1.0, units_per_lot=100000.0)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("1.0850"),
            stop_loss=Decimal("1.0840"),
            symbol="EURUSD",
        )

        # risk=100, price_risk=0.0010, units=100000, lots=1.0
        # notional=100000*1.0850=108500, max_exposure=5000
        # ratio=5000/108500=0.0461, final_lots=1.0*0.0461=0.046→0.04
        assert result.lots == Decimal("0.04"), f"Expected 0.04 lots (capped), got {result.lots}"

    def test_gold_vs_forex_different_lots(self):
        """Gold and forex must produce different lot sizes"""
        gold_sizer = FixedFractionalSizer(risk_pct=0.1, units_per_lot=100.0)
        forex_sizer = FixedFractionalSizer(risk_pct=0.1, units_per_lot=100000.0)

        gold_result = gold_sizer.calculate(
            account_balance=Decimal("100000"),
            entry_price=Decimal("2350"),
            stop_loss=Decimal("2345"),
            symbol="XAUUSD",
        )

        forex_result = forex_sizer.calculate(
            account_balance=Decimal("100000"),
            entry_price=Decimal("1.0850"),
            stop_loss=Decimal("1.0840"),
            symbol="EURUSD",
        )

        # Lots must differ
        assert (
            gold_result.lots != forex_result.lots
        ), f"Gold ({gold_result.lots}) should differ from forex ({forex_result.lots})"

        # Gold should have fewer lots
        assert gold_result.lots < forex_result.lots

    def test_zero_stop_loss_returns_zero(self):
        """Stop loss at entry price → zero size"""
        sizer = FixedFractionalSizer(risk_pct=1.0, units_per_lot=100.0)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("2350"),
            stop_loss=Decimal("2350"),
            symbol="XAUUSD",
        )

        assert result.lots == Decimal("0")
        assert result.units == Decimal("0")
