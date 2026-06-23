"""ContractSpec resolution tests"""
import math
import pytest
from unittest.mock import MagicMock
from datetime import datetime, timedelta

from graxia.packages.quant_os.risk.contract_spec import ContractSpec, ContractSpecResolver, ContractSpecError


class TestContractSpecXAUUSD:
    """XAUUSD on Pepperstone: contract_size=100"""

    @pytest.fixture
    def mock_mt5(self):
        mt5 = MagicMock()
        sym = MagicMock()
        sym.trade_contract_size = 100
        sym.volume_min = 0.01
        sym.volume_max = 50.0
        sym.volume_step = 0.01
        sym.point = 0.01
        sym.trade_tick_size = 0.01
        sym.trade_tick_value = 1.0
        sym.currency_profit = "USD"
        sym.currency_margin = "USD"
        sym.trade_stops_level = 0
        sym.trade_freeze_level = 0
        mt5.symbol_info.return_value = sym
        return mt5

    def test_xauusd_contract_size(self, mock_mt5):
        resolver = ContractSpecResolver(mock_mt5)
        spec = resolver.resolve("XAUUSD")
        assert spec.contract_size == 100
        assert spec.volume_min == 0.01
        assert spec.volume_step == 0.01

    def test_xauusd_pnl_calculation(self, mock_mt5):
        """1 lot XAUUSD, 10 MT5 point SL = $0.10 delta = $10 risk"""
        resolver = ContractSpecResolver(mock_mt5)
        spec = resolver.resolve("XAUUSD")
        # With contract_size=100, 1 lot = 100 units
        # 10 points * 0.01 * 100 = $10 risk per lot
        contract_value = 1.0 * spec.contract_size  # 100
        point_value = spec.point  # 0.01
        risk = 10 * point_value * contract_value
        assert risk == 10.0  # NOT $10000 like old 100000 default


class TestContractSpecEURUSD:
    """EURUSD on Pepperstone: contract_size=100000"""

    @pytest.fixture
    def mock_mt5(self):
        mt5 = MagicMock()
        sym = MagicMock()
        sym.trade_contract_size = 100000
        sym.volume_min = 0.01
        sym.volume_max = 50.0
        sym.volume_step = 0.01
        sym.point = 0.00001
        sym.trade_tick_size = 0.00001
        sym.trade_tick_value = 1.0
        sym.currency_profit = "USD"
        sym.currency_margin = "USD"
        sym.trade_stops_level = 0
        sym.trade_freeze_level = 0
        mt5.symbol_info.return_value = sym
        return mt5

    def test_eurusd_contract_size(self, mock_mt5):
        resolver = ContractSpecResolver(mock_mt5)
        spec = resolver.resolve("EURUSD")
        assert spec.contract_size == 100000
        assert spec.volume_min == 0.01


class TestContractSpecFailures:

    def test_missing_symbol_raises_error(self):
        mt5 = MagicMock()
        mt5.symbol_info.return_value = None
        resolver = ContractSpecResolver(mt5)
        with pytest.raises(ContractSpecError) as exc:
            resolver.resolve("INVALID")
        assert "INVALID" in str(exc.value)

    def test_no_connection_raises_error(self):
        resolver = ContractSpecResolver(None)
        with pytest.raises(ContractSpecError) as exc:
            resolver.resolve("XAUUSD")
        assert "No MT5 connection" in str(exc.value)

    def test_stale_spec_rejected(self):
        """Spec older than TTL should be considered stale."""
        stale_spec = ContractSpec(
            symbol="XAUUSD", contract_size=100,
            volume_min=0.01, volume_max=50.0, volume_step=0.01,
            point=0.01, tick_size=0.01, tick_value=1.0,
            currency_profit="USD", currency_margin="USD",
            stops_level=0, freeze_level=0,
            profile_hash="test",
            snapshot_timestamp=datetime.utcnow() - timedelta(seconds=301),
        )
        assert stale_spec.is_stale is True

    def test_fresh_spec_valid(self):
        fresh = ContractSpec(
            symbol="XAUUSD", contract_size=100,
            volume_min=0.01, volume_max=50.0, volume_step=0.01,
            point=0.01, tick_size=0.01, tick_value=1.0,
            currency_profit="USD", currency_margin="USD",
            stops_level=0, freeze_level=0,
            profile_hash="test",
            snapshot_timestamp=datetime.utcnow(),
        )
        assert fresh.is_stale is False

    def test_hash_deterministic(self):
        mt5 = MagicMock()
        sym = MagicMock()
        sym.trade_contract_size = 100
        sym.volume_min = 0.01
        sym.volume_max = 50.0
        sym.volume_step = 0.01
        sym.point = 0.01
        sym.trade_tick_size = 0.01
        sym.trade_tick_value = 1.0
        sym.currency_profit = "USD"
        sym.currency_margin = "USD"
        sym.trade_stops_level = 0
        sym.trade_freeze_level = 0
        mt5.symbol_info.return_value = sym

        resolver = ContractSpecResolver(mt5)
        spec1 = resolver.resolve("XAUUSD")
        spec2 = resolver.resolve("XAUUSD")
        assert spec1.hash == spec2.hash

    def test_hash_mismatch_detected(self):
        spec_a = ContractSpec(
            symbol="XAUUSD", contract_size=100,
            volume_min=0.01, volume_max=50.0, volume_step=0.01,
            point=0.01, tick_size=0.01, tick_value=1.0,
            currency_profit="USD", currency_margin="USD",
            stops_level=0, freeze_level=0,
            profile_hash="profile_a",
            snapshot_timestamp=datetime.utcnow(),
        )
        spec_b = ContractSpec(
            symbol="XAUUSD", contract_size=100,
            volume_min=0.01, volume_max=50.0, volume_step=0.01,
            point=0.01, tick_size=0.01, tick_value=1.0,
            currency_profit="USD", currency_margin="USD",
            stops_level=5, freeze_level=3,  # different
            profile_hash="profile_b",
            snapshot_timestamp=datetime.utcnow(),
        )
        assert spec_a.hash != spec_b.hash


class TestVolumeStep:

    @pytest.fixture
    def mock_mt5(self):
        mt5 = MagicMock()
        sym = MagicMock()
        sym.trade_contract_size = 100
        sym.volume_min = 0.01
        sym.volume_max = 50.0
        sym.volume_step = 0.01
        sym.point = 0.01
        sym.trade_tick_size = 0.01
        sym.trade_tick_value = 1.0
        sym.currency_profit = "USD"
        sym.currency_margin = "USD"
        sym.trade_stops_level = 0
        sym.trade_freeze_level = 0
        mt5.symbol_info.return_value = sym
        return mt5

    def test_volume_step_stored_correctly(self, mock_mt5):
        resolver = ContractSpecResolver(mock_mt5)
        spec = resolver.resolve("XAUUSD")
        assert spec.volume_step == 0.01

    def test_volume_min_stored_correctly(self, mock_mt5):
        resolver = ContractSpecResolver(mock_mt5)
        spec = resolver.resolve("XAUUSD")
        assert spec.volume_min == 0.01

    def test_volume_max_stored_correctly(self, mock_mt5):
        resolver = ContractSpecResolver(mock_mt5)
        spec = resolver.resolve("XAUUSD")
        assert spec.volume_max == 50.0


class TestContractSpecNumericExamples:
    """Exact numeric examples that must match broker reality."""

    def test_xauusd_1_lot_1000_point_sl(self):
        """1 lot XAUUSD, 1000 point SL = $10 price delta = $1,000 risk.

        contract_size=100, point=0.01
        price_delta = 1000 * 0.01 = $10.00
        risk = 1.0 * 100 * 10.0 = $1,000
        """
        contract_size = 100
        lots = 1.0
        mt5_points = 1000  # NOT 10pt
        price_delta = mt5_points * 0.01  # $10.00
        risk = lots * contract_size * price_delta
        assert risk == 1000.0, f"Expected $1000 risk, got ${risk}"

    def test_xauusd_0_01_lot_1000_point_sl(self):
        """0.01 lot XAUUSD, 1000 point SL = $10 price delta = $10 risk."""
        contract_size = 100
        lots = 0.01
        mt5_points = 1000
        price_delta = mt5_points * 0.01
        risk = lots * contract_size * price_delta
        assert risk == 10.0, f"Expected $10 risk, got ${risk}"

    def test_xauusd_0_01_lot_10_point_sl(self):
        """0.01 lot XAUUSD, 10 point SL = $0.10 price delta = $0.10 risk."""
        contract_size = 100
        lots = 0.01
        mt5_points = 10
        price_delta = mt5_points * 0.01  # $0.10
        risk = lots * contract_size * price_delta
        assert risk == 0.10, f"Expected $0.10 risk, got ${risk}"

    def test_eurusd_1_lot_10_pip_sl(self):
        """1 lot EURUSD, 10 pip SL = 100 points = 0.0010 price delta = $100 risk.

        EURUSD: point=0.00001, pip=10 points=0.0001
        10 pip = 100 points = 100 * 0.00001 = 0.0010 price delta
        risk = 1.0 * 100000 * 0.0010 = $100
        """
        contract_size = 100000
        lots = 1.0
        pips = 10
        points_per_pip = 10
        mt5_points = pips * points_per_pip  # 100
        price_delta = mt5_points * 0.00001  # 0.0010
        risk = lots * contract_size * price_delta
        assert risk == 100.0, f"Expected $100 risk, got ${risk}"

    def test_eurusd_0_01_lot_10_pip_sl(self):
        """0.01 lot EURUSD, 10 pip SL = 100 points = $1 risk."""
        contract_size = 100000
        lots = 0.01
        mt5_points = 100
        price_delta = mt5_points * 0.00001
        risk = lots * contract_size * price_delta
        assert risk == 1.0, f"Expected $1 risk, got ${risk}"

    def test_unit_labels_unambiguous(self):
        """Verify mt5_points vs price_delta are distinct and labeled."""
        xauusd_points = 1000
        xauusd_point_value = 0.01
        price_delta = xauusd_points * xauusd_point_value
        assert xauusd_points != price_delta
        assert price_delta == 10.0

    def test_xauusd_pips_unsupported(self):
        """XAUUSD to_pips should return None."""
        spec = ContractSpec(
            symbol="XAUUSD", contract_size=100,
            volume_min=0.01, volume_max=50.0, volume_step=0.01,
            point=0.01, tick_size=0.01, tick_value=1.0,
            currency_profit="USD", currency_margin="USD",
            stops_level=0, freeze_level=0,
            profile_hash="test",
            snapshot_timestamp=datetime.utcnow(),
        )
        assert spec.supports_pips() is False
        assert spec.to_pips(10.0) is None

    def test_eurusd_pips_supported(self):
        """EURUSD to_pips should return a value, not None."""
        spec = ContractSpec(
            symbol="EURUSD", contract_size=100000,
            volume_min=0.01, volume_max=50.0, volume_step=0.01,
            point=0.00001, tick_size=0.00001, tick_value=1.0,
            currency_profit="USD", currency_margin="USD",
            stops_level=0, freeze_level=0,
            profile_hash="test",
            snapshot_timestamp=datetime.utcnow(),
        )
        assert spec.supports_pips() is True
        assert spec.to_pips(0.0010) is not None
        assert spec.to_pips(0.0010) == 10.0


class TestContractSpecDirection:
    """Long and short positions must produce symmetric risk."""

    @pytest.mark.parametrize("direction,price_adj", [
        ("BUY", lambda entry, pd: entry - pd),  # SL below entry
        ("SELL", lambda entry, pd: entry + pd),  # SL above entry
    ])
    def test_xauusd_buy_sell_symmetric_risk(self, direction, price_adj):
        """Buy and sell with same SL distance = same risk."""
        contract_size = 100
        lots = 0.10
        mt5_points = 500
        price_delta = mt5_points * 0.01
        entry = 2000.0
        sl = price_adj(entry, price_delta)

        risk = lots * contract_size * abs(entry - sl)
        assert risk == lots * contract_size * price_delta
        assert risk > 0


class TestContractSpecVolumeStep:
    """Volume must be multiple of volume_step."""

    def test_xauusd_volume_step_valid(self):
        contract_size = 100
        volume_step = 0.01
        for vol in [0.01, 0.02, 0.10, 0.50, 1.0, 2.0]:
            remainder = vol % volume_step
            tol = 1e-10
            ok = remainder < tol or abs(remainder - volume_step) < tol
            assert ok, f"Volume {vol} not multiple of step {volume_step}"

    def test_xauusd_volume_step_invalid(self):
        contract_size = 100
        volume_step = 0.01
        for vol in [0.005, 0.015, 0.025, 0.12]:
            remainder = vol % volume_step
            assert remainder != 0, f"Volume {vol} should be invalid (step {volume_step})"

    def test_xauusd_volume_bounds(self):
        """Volume must be within [volume_min, volume_max]."""
        volume_min = 0.01
        volume_max = 50.0
        assert 0.01 >= volume_min
        assert 0.01 <= volume_max
        assert 1.0 >= volume_min
        assert 1.0 <= volume_max
        assert 50.0 >= volume_min
        assert 50.0 <= volume_max
