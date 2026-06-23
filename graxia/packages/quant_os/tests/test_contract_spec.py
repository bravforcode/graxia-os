"""ContractSpec resolution tests"""
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
        """1 lot XAUUSD at 2000 with 10 pip SL"""
        resolver = ContractSpecResolver(mock_mt5)
        spec = resolver.resolve("XAUUSD")
        # With contract_size=100, 1 lot = 100 units
        # 10 pip * 100 * 0.01 = $10 risk per lot
        contract_value = 1.0 * spec.contract_size  # 100
        pip_value = spec.point  # 0.01
        risk = 10 * pip_value * contract_value
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
