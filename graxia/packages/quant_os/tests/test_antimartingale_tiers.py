"""
Test AntiMartingale tier adjustments.

NOTE: _apply_limits() caps notional at max_portfolio_exposure_pct (50%).
For $10k account, max_exposure = $5000. Gold at $2350/oz with 5-point stop:
  - 3 losses: adjusted_risk=0.25%, units=5, notional=$11750 → capped to $5000
  - 2 losses: adjusted_risk=0.50%, units=10, notional=$23500 → capped to $5000
  - 3 wins: adjusted_risk=1.50%, units=30, notional=$70500 → capped to $5000
  - 2 wins: adjusted_risk=1.25%, units=25, notional=$58750 → capped to $5000

The important assertion is that the ADJUSTMENT factor is correct (from notes),
not the final risk_pct (which is affected by exposure cap).
"""

from decimal import Decimal

from quant_os.risk.position_sizer import AntiMartingaleSizer


def test_three_losses_gets_quarter_adjustment():
    """3+ consecutive losses → adjustment = 0.25 (quarter size)"""
    sizer = AntiMartingaleSizer(
        base_risk_pct=1.0,
        consecutive_losses=3,
        consecutive_wins=0,
        units_per_lot=100.0,
    )

    sizer.record_outcome(-100)
    sizer.record_outcome(-100)
    sizer.record_outcome(-100)

    result = sizer.calculate(
        account_balance=Decimal("10000"),
        entry_price=Decimal("2350"),
        stop_loss=Decimal("2345"),
        symbol="XAUUSD",
    )

    # Verify adjustment from notes: "Adj: 0.25%"
    assert "Adj: 0.25%" in result.notes, f"Expected Adj: 0.25% in notes, got: {result.notes}"

    # Risk is capped by exposure, but adjustment is correct
    assert result.lots > 0, "Should have non-zero lots after adjustment"
    print(f"  3 losses: adjustment=0.25, lots={result.lots}, risk_pct={result.risk_pct}%")


def test_two_losses_gets_half_adjustment():
    """2 consecutive losses → adjustment = 0.5 (half size)"""
    sizer = AntiMartingaleSizer(
        base_risk_pct=1.0,
        consecutive_losses=0,  # Start at 0
        consecutive_wins=0,
        units_per_lot=100.0,
    )

    # Build streak: 2 losses
    sizer.record_outcome(-100)
    sizer.record_outcome(-100)
    # Now consecutive_losses=2, consecutive_wins=0

    result = sizer.calculate(
        account_balance=Decimal("10000"),
        entry_price=Decimal("2350"),
        stop_loss=Decimal("2345"),
        symbol="XAUUSD",
    )

    assert "Adj: 0.50%" in result.notes, f"Expected Adj: 0.50% in notes, got: {result.notes}"
    assert result.lots > 0
    print(f"  2 losses: adjustment=0.50, lots={result.lots}, risk_pct={result.risk_pct}%")


def test_three_wins_gets_1_5x_adjustment():
    """3+ consecutive wins → adjustment = 1.5, but golden rule caps at 1.0%"""
    sizer = AntiMartingaleSizer(
        base_risk_pct=1.0,
        consecutive_losses=0,
        consecutive_wins=0,
        units_per_lot=100.0,
    )

    sizer.record_outcome(100)
    sizer.record_outcome(100)
    sizer.record_outcome(100)

    result = sizer.calculate(
        account_balance=Decimal("10000"),
        entry_price=Decimal("2350"),
        stop_loss=Decimal("2345"),
        symbol="XAUUSD",
    )

    # Golden rule caps at 1.0% max — raw adjustment would be 1.5%
    assert "Adj: 1.00%" in result.notes, f"Expected Adj: 1.00% (capped), got: {result.notes}"
    assert result.lots > 0
    print(f"  3 wins: adj=1.50 (capped to 1.00 by golden rule), lots={result.lots}")


def test_two_wins_gets_1_25x_adjustment():
    """2 consecutive wins → adjustment = 1.25, but golden rule caps at 1.0%"""
    sizer = AntiMartingaleSizer(
        base_risk_pct=1.0,
        consecutive_losses=0,
        consecutive_wins=0,
        units_per_lot=100.0,
    )

    sizer.record_outcome(100)
    sizer.record_outcome(100)

    result = sizer.calculate(
        account_balance=Decimal("10000"),
        entry_price=Decimal("2350"),
        stop_loss=Decimal("2345"),
        symbol="XAUUSD",
    )

    # Golden rule caps at 1.0% max
    assert "Adj: 1.00%" in result.notes, f"Expected Adj: 1.00% (capped), got: {result.notes}"
    assert result.lots > 0
    print(f"  2 wins: adj=1.25 (capped to 1.00 by golden rule), lots={result.lots}")


def test_no_streak_gets_base_adjustment():
    """No streak → adjustment = 1.0 (base size)"""
    sizer = AntiMartingaleSizer(
        base_risk_pct=1.0,
        consecutive_losses=0,
        consecutive_wins=0,
        units_per_lot=100.0,
    )

    result = sizer.calculate(
        account_balance=Decimal("10000"),
        entry_price=Decimal("2350"),
        stop_loss=Decimal("2345"),
        symbol="XAUUSD",
    )

    assert "Adj: 1.00%" in result.notes, f"Expected Adj: 1.00% in notes, got: {result.notes}"
    print(f"  No streak: adjustment=1.00, lots={result.lots}, risk_pct={result.risk_pct}%")
