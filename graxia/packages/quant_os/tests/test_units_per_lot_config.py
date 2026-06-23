"""Tests for units_per_lot configuration: config-driven defaults, no hardcoded 100000."""
import sys, os
sys.path.insert(0, os.getcwd())

from decimal import Decimal
import pytest

from graxia.packages.quant_os.core.config import get_config, reset_config
from graxia.packages.quant_os.risk.position_sizer import FixedFractionalSizer, KellySizer, ATRSizer, AntiMartingaleSizer
from graxia.packages.quant_os.risk.engine import RiskEngine


@pytest.fixture(autouse=True)
def _reset_config():
    reset_config()
    yield
    reset_config()


class TestPositionSizerReadsConfig:
    """Sizer constructors read units_per_lot from config when not provided."""

    @pytest.mark.parametrize("SizerClass", [
        FixedFractionalSizer,
        KellySizer,
        ATRSizer,
        AntiMartingaleSizer,
    ])
    def test_default_units_per_lot_from_config(self, SizerClass):
        config = get_config()
        sizer = SizerClass()
        assert sizer.units_per_lot == config.units_per_lot == 100.0


class TestPositionSizerOverride:
    """Explicit units_per_lot argument overrides config."""

    def test_fixed_fractional_override(self):
        sizer = FixedFractionalSizer(units_per_lot=1000)
        assert sizer.units_per_lot == 1000

    def test_kelly_override(self):
        sizer = KellySizer(units_per_lot=500)
        assert sizer.units_per_lot == 500

    def test_atr_override(self):
        sizer = ATRSizer(units_per_lot=200)
        assert sizer.units_per_lot == 200

    def test_anti_martingale_override(self):
        sizer = AntiMartingaleSizer(units_per_lot=250)
        assert sizer.units_per_lot == 250


class TestRiskEngineUsesConfig:
    """RiskEngine reads units_per_lot from config."""

    def test_risk_engine_default(self):
        engine = RiskEngine(db_session=None)
        assert engine.units_per_lot == 100.0


class TestCalculateCorrectSize:
    """Position sizing with XAUUSD-like parameters produces reasonable lot counts."""

    def test_calculate_gold_sizing(self):
        sizer = FixedFractionalSizer(risk_pct=1.0, units_per_lot=100.0)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("2000"),
            stop_loss=Decimal("1990"),
        )
        # risk = 10000 * 1% = 100 USD
        # price_risk = 10, units = 100/10 = 10, lots = 10/100 = 0.1
        assert 0.01 <= result.lots <= 1.0, f"Expected reasonable lots, got {result.lots}"

    def test_forex_still_works(self):
        sizer = FixedFractionalSizer(risk_pct=1.0, units_per_lot=100000.0)
        result = sizer.calculate(
            account_balance=Decimal("10000"),
            entry_price=Decimal("1.1000"),
            stop_loss=Decimal("1.0900"),
        )
        # risk = 100, price_risk = 0.01, units = 100/0.01 = 10000, lots = 10000/100000 = 0.1
        assert 0.01 <= result.lots <= 10.0, f"Expected reasonable lots, got {result.lots}"
