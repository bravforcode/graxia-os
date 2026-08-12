"""
Tests for broker/mt5_gateway.py — READ-ONLY MT5 broker interface.

Covers:
- connect/disconnect lifecycle (initialize_mt5 / shutdown_mt5)
- Order check (check_order)
- Position / tick query (get_current_tick)
- Account info query (get_account_info)
- Contract spec retrieval (get_contract_spec)
- Profit / margin calculation (calc_profit, calc_margin)
- Error handling when MT5 not available
- Retry / lazy import behavior
- Safety assertion (no order_send/modify/close)

MetaTrader5 module is fully mocked — no real MT5 dependency.
"""

from __future__ import annotations

import sys
import types
from datetime import datetime, UTC
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _reset_mt5_globals():
    """Reset module-level lazy-import cache so each test starts clean."""
    import broker.mt5_gateway as gw
    gw._mt5_imported = False
    gw._mt5 = None


def _make_mock_mt5() -> MagicMock:
    """Create a fully functional mock of the MetaTrader5 module."""
    mt5 = MagicMock()
    mt5.initialize.return_value = True
    mt5.last_error.return_value = (0, "No error")

    # symbol_info mock
    info = MagicMock()
    info.digits = 2
    info.point = 0.01
    info.trade_contract_size = 100.0
    info.trade_tick_size = 0.01
    info.trade_tick_value = 1.0
    info.volume_min = 0.01
    info.volume_max = 100.0
    info.volume_step = 0.01
    info.stops_level = 50
    info.freeze_level = 10
    info.currency_base = "XAU"
    info.currency_profit = "USD"
    info.currency_margin = "USD"
    info.trade_mode = 0
    info.filling_mode = 1
    info.execution_mode = 0
    mt5.symbol_info.return_value = info

    # account_info mock
    acct = MagicMock()
    acct.login = 123456
    acct.server = "Pepperstone-Demo"
    acct.currency = "USD"
    acct.leverage = 100
    acct.balance = 10000.0
    acct.equity = 10050.0
    acct.margin = 200.0
    acct.margin_free = 9850.0
    acct.margin_level = 5025.0
    acct.profit = 50.0
    mt5.account_info.return_value = acct

    # symbol_info_tick mock
    tick = MagicMock()
    tick.bid = 2300.00
    tick.ask = 2300.20
    tick.last = 2300.10
    tick.volume = 150
    tick.time = int(datetime.now(UTC).timestamp())
    mt5.symbol_info_tick.return_value = tick

    # ORDER_TYPE constants
    mt5.ORDER_TYPE_BUY = 0
    mt5.ORDER_TYPE_SELL = 1

    # order_calc_profit mock
    mt5.order_calc_profit.return_value = 123.45

    # order_calc_margin mock
    mt5.order_calc_margin.return_value = 230.0

    # order_check mock
    check_result = MagicMock()
    check_result.retcode = 10009
    check_result.comment = "Done"
    check_result.volume = 0.1
    check_result.price = 2300.10
    check_result.bid = 2300.00
    check_result.ask = 2300.20
    mt5.order_check.return_value = check_result

    return mt5


# ---------------------------------------------------------------------------
# Tests: Lazy Import
# ---------------------------------------------------------------------------

class TestLazyImport:
    """Tests for the lazy MetaTrader5 import mechanism."""

    def test_import_mt5_unavailable(self):
        """Mt5UnavailableError raised when MetaTrader5 not installed."""
        _reset_mt5_globals()
        import broker.mt5_gateway as gw
        # Remove MetaTrader5 from sys.modules if present
        sys.modules.pop("MetaTrader5", None)
        with patch.dict(sys.modules, {"MetaTrader5": None}):
            with pytest.raises(gw.Mt5UnavailableError, match="not installed"):
                gw._get_mt5()

    def test_import_mt5_cached(self):
        """After successful import, _get_mt5 returns cached module."""
        _reset_mt5_globals()
        mock_mt5 = _make_mock_mt5()
        import broker.mt5_gateway as gw
        with patch.dict(sys.modules, {"MetaTrader5": mock_mt5}):
            result = gw._get_mt5()
            assert result is mock_mt5
            # Second call should return same cached object
            result2 = gw._get_mt5()
            assert result2 is mock_mt5

    def test_previously_failed_import_raises(self):
        """If _mt5_imported=True but _mt5=None, raises immediately."""
        _reset_mt5_globals()
        import broker.mt5_gateway as gw
        gw._mt5_imported = True
        gw._mt5 = None
        with pytest.raises(gw.Mt5UnavailableError, match="not installed"):
            gw._get_mt5()


# ---------------------------------------------------------------------------
# Tests: initialize_mt5
# ---------------------------------------------------------------------------

class TestInitializeMt5:
    """Tests for MT5 terminal initialization."""

    def setup_method(self):
        _reset_mt5_globals()
        self.mock_mt5 = _make_mock_mt5()

    def test_initialize_success(self):
        """initialize_mt5 returns True when mt5.initialize() succeeds."""
        import broker.mt5_gateway as gw
        with patch.dict(sys.modules, {"MetaTrader5": self.mock_mt5}):
            result = gw.initialize_mt5(path="C:\\MT5\\terminal64.exe")
            assert result is True
            self.mock_mt5.initialize.assert_called_once_with(
                path="C:\\MT5\\terminal64.exe", timeout=10000
            )

    def test_initialize_failure(self):
        """initialize_mt5 raises Mt5UnavailableError when mt5.initialize() returns False."""
        import broker.mt5_gateway as gw
        self.mock_mt5.initialize.return_value = False
        self.mock_mt5.last_error.return_value = (1, "Config not found")
        with patch.dict(sys.modules, {"MetaTrader5": self.mock_mt5}):
            with pytest.raises(gw.Mt5UnavailableError, match="MT5 init failed"):
                gw.initialize_mt5(path="bad_path")

    def test_initialize_exception(self):
        """initialize_mt5 wraps unexpected exceptions into Mt5UnavailableError."""
        import broker.mt5_gateway as gw
        self.mock_mt5.initialize.side_effect = OSError("File not found")
        with patch.dict(sys.modules, {"MetaTrader5": self.mock_mt5}):
            with pytest.raises(gw.Mt5UnavailableError, match="initialization error"):
                gw.initialize_mt5(path="bad_path")

    def test_initialize_custom_timeout(self):
        """initialize_mt5 passes custom timeout to mt5.initialize()."""
        import broker.mt5_gateway as gw
        with patch.dict(sys.modules, {"MetaTrader5": self.mock_mt5}):
            gw.initialize_mt5(path="C:\\MT5\\terminal64.exe", timeout_ms=30000)
            self.mock_mt5.initialize.assert_called_once_with(
                path="C:\\MT5\\terminal64.exe", timeout=30000
            )


# ---------------------------------------------------------------------------
# Tests: shutdown_mt5
# ---------------------------------------------------------------------------

class TestShutdownMt5:
    """Tests for MT5 connection shutdown."""

    def setup_method(self):
        _reset_mt5_globals()
        self.mock_mt5 = _make_mock_mt5()

    def test_shutdown_calls_mt5_shutdown(self):
        """shutdown_mt5 calls mt5.shutdown() without error."""
        import broker.mt5_gateway as gw
        with patch.dict(sys.modules, {"MetaTrader5": self.mock_mt5}):
            gw._mt5_imported = True
            gw._mt5 = self.mock_mt5
            gw.shutdown_mt5()
            self.mock_mt5.shutdown.assert_called_once()

    def test_shutdown_swallows_errors(self):
        """shutdown_mt5 does not raise even if mt5.shutdown() throws."""
        import broker.mt5_gateway as gw
        self.mock_mt5.shutdown.side_effect = RuntimeError("Already shut down")
        with patch.dict(sys.modules, {"MetaTrader5": self.mock_mt5}):
            gw._mt5_imported = True
            gw._mt5 = self.mock_mt5
            # Should not raise
            gw.shutdown_mt5()


# ---------------------------------------------------------------------------
# Tests: get_current_tick
# ---------------------------------------------------------------------------

class TestGetCurrentTick:
    """Tests for get_current_tick()."""

    def setup_method(self):
        _reset_mt5_globals()
        self.mock_mt5 = _make_mock_mt5()
        import broker.mt5_gateway as gw
        gw._mt5_imported = True
        gw._mt5 = self.mock_mt5

    def test_get_current_tick_success(self):
        """Returns dict with bid, ask, last, volume, time."""
        import broker.mt5_gateway as gw
        tick = gw.get_current_tick("XAUUSD")
        assert tick["bid"] == 2300.00
        assert tick["ask"] == 2300.20
        assert tick["last"] == 2300.10
        assert tick["volume"] == 150.0
        assert isinstance(tick["time"], int)

    def test_get_current_tick_none(self):
        """Mt5UnavailableError when symbol_info_tick returns None."""
        import broker.mt5_gateway as gw
        self.mock_mt5.symbol_info_tick.return_value = None
        with pytest.raises(gw.Mt5UnavailableError, match="Could not get tick"):
            gw.get_current_tick("INVALID")


# ---------------------------------------------------------------------------
# Tests: get_account_info
# ---------------------------------------------------------------------------

class TestGetAccountInfo:
    """Tests for get_account_info()."""

    def setup_method(self):
        _reset_mt5_globals()
        self.mock_mt5 = _make_mock_mt5()
        import broker.mt5_gateway as gw
        gw._mt5_imported = True
        gw._mt5 = self.mock_mt5

    def test_get_account_info_success(self):
        """Returns dict with all account fields."""
        import broker.mt5_gateway as gw
        info = gw.get_account_info()
        assert info["login"] == 123456
        assert info["server"] == "Pepperstone-Demo"
        assert info["currency"] == "USD"
        assert info["leverage"] == 100
        assert info["balance"] == 10000.0
        assert info["equity"] == 10050.0
        assert info["margin"] == 200.0
        assert info["margin_free"] == 9850.0
        assert info["margin_level"] == 5025.0
        assert info["profit"] == 50.0

    def test_get_account_info_none(self):
        """Mt5UnavailableError when account_info returns None."""
        import broker.mt5_gateway as gw
        self.mock_mt5.account_info.return_value = None
        with pytest.raises(gw.Mt5UnavailableError, match="Could not get account info"):
            gw.get_account_info()

    def test_get_account_info_exception(self):
        """Mt5UnavailableError wraps unexpected exceptions."""
        import broker.mt5_gateway as gw
        self.mock_mt5.account_info.side_effect = OSError("Connection lost")
        with pytest.raises(gw.Mt5UnavailableError, match="Account info error"):
            gw.get_account_info()


# ---------------------------------------------------------------------------
# Tests: calc_profit
# ---------------------------------------------------------------------------

class TestCalcProfit:
    """Tests for calc_profit()."""

    def setup_method(self):
        _reset_mt5_globals()
        self.mock_mt5 = _make_mock_mt5()
        import broker.mt5_gateway as gw
        gw._mt5_imported = True
        gw._mt5 = self.mock_mt5

    def test_calc_profit_buy(self):
        """calc_profit for BUY returns float from order_calc_profit."""
        import broker.mt5_gateway as gw
        result = gw.calc_profit("XAUUSD", "BUY", 0.1, 2300.0, 2310.0)
        assert result == 123.45
        self.mock_mt5.order_calc_profit.assert_called_once_with(
            0, "XAUUSD", 0.1, 2300.0, 2310.0
        )

    def test_calc_profit_sell(self):
        """calc_profit for SELL uses ORDER_TYPE_SELL."""
        import broker.mt5_gateway as gw
        gw.calc_profit("XAUUSD", "SELL", 0.1, 2300.0, 2290.0)
        self.mock_mt5.order_calc_profit.assert_called_once_with(
            1, "XAUUSD", 0.1, 2300.0, 2290.0
        )

    def test_calc_profit_none_result(self):
        """Returns None when MT5 returns None."""
        import broker.mt5_gateway as gw
        self.mock_mt5.order_calc_profit.return_value = None
        result = gw.calc_profit("XAUUSD", "BUY", 0.1, 2300.0, 2310.0)
        assert result is None

    def test_calc_profit_exception(self):
        """Returns None on any exception (graceful degradation)."""
        import broker.mt5_gateway as gw
        self.mock_mt5.order_calc_profit.side_effect = RuntimeError("fail")
        result = gw.calc_profit("XAUUSD", "BUY", 0.1, 2300.0, 2310.0)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: calc_margin
# ---------------------------------------------------------------------------

class TestCalcMargin:
    """Tests for calc_margin()."""

    def setup_method(self):
        _reset_mt5_globals()
        self.mock_mt5 = _make_mock_mt5()
        import broker.mt5_gateway as gw
        gw._mt5_imported = True
        gw._mt5 = self.mock_mt5

    def test_calc_margin_success(self):
        """calc_margin returns float from order_calc_margin."""
        import broker.mt5_gateway as gw
        result = gw.calc_margin("XAUUSD", 0.1, 2300.0)
        assert result == 230.0
        self.mock_mt5.order_calc_margin.assert_called_once_with(
            0, "XAUUSD", 0.1, 2300.0
        )

    def test_calc_margin_exception(self):
        """Returns None on exception."""
        import broker.mt5_gateway as gw
        self.mock_mt5.order_calc_margin.side_effect = RuntimeError("fail")
        result = gw.calc_margin("XAUUSD", 0.1, 2300.0)
        assert result is None


# ---------------------------------------------------------------------------
# Tests: check_order
# ---------------------------------------------------------------------------

class TestCheckOrder:
    """Tests for check_order()."""

    def setup_method(self):
        _reset_mt5_globals()
        self.mock_mt5 = _make_mock_mt5()
        import broker.mt5_gateway as gw
        gw._mt5_imported = True
        gw._mt5 = self.mock_mt5

    def test_check_order_success(self):
        """Returns dict with retcode, comment, volume, price, bid, ask."""
        import broker.mt5_gateway as gw
        result = gw.check_order({"type": 0, "symbol": "XAUUSD", "volume": 0.1})
        assert result["retcode"] == 10009
        assert result["comment"] == "Done"
        assert result["volume"] == 0.1
        assert result["price"] == 2300.10
        assert result["bid"] == 2300.00
        assert result["ask"] == 2300.20

    def test_check_order_none(self):
        """Returns None when MT5 order_check returns None."""
        import broker.mt5_gateway as gw
        self.mock_mt5.order_check.return_value = None
        result = gw.check_order({"type": 0})
        assert result is None

    def test_check_order_exception(self):
        """Returns None on exception."""
        import broker.mt5_gateway as gw
        self.mock_mt5.order_check.side_effect = RuntimeError("fail")
        result = gw.check_order({"type": 0})
        assert result is None


# ---------------------------------------------------------------------------
# Tests: get_contract_spec
# ---------------------------------------------------------------------------

class TestGetContractSpec:
    """Tests for get_contract_spec()."""

    def setup_method(self):
        _reset_mt5_globals()
        self.mock_mt5 = _make_mock_mt5()
        import broker.mt5_gateway as gw
        gw._mt5_imported = True
        gw._mt5 = self.mock_mt5

    def test_get_contract_spec_success(self):
        """Returns a valid ContractSpec with correct fields."""
        import broker.mt5_gateway as gw
        spec = gw.get_contract_spec("XAUUSD", broker="Pepperstone", server="Pepperstone-Demo")
        assert spec.symbol == "XAUUSD"
        assert spec.broker == "Pepperstone"
        assert spec.server == "Pepperstone-Demo"
        assert spec.account_currency == "USD"
        assert spec.digits == 2
        assert spec.point == Decimal("0.01")
        assert spec.trade_contract_size == Decimal("100.0")
        assert spec.trade_tick_size == Decimal("0.01")
        assert spec.trade_tick_value == Decimal("1.0")
        assert spec.volume_min == Decimal("0.01")
        assert spec.volume_max == Decimal("100.0")
        assert spec.volume_step == Decimal("0.01")
        assert spec.stops_level_points == 50
        assert spec.freeze_level_points == 10
        assert spec.currency_base == "XAU"
        assert spec.currency_profit == "USD"
        assert spec.currency_margin == "USD"
        assert spec.snapshot_hash  # non-empty

    def test_get_contract_spec_symbol_info_none(self):
        """Mt5UnavailableError when symbol_info returns None."""
        import broker.mt5_gateway as gw
        self.mock_mt5.symbol_info.return_value = None
        with pytest.raises(gw.Mt5UnavailableError, match="Could not get symbol info"):
            gw.get_contract_spec("INVALID")

    def test_get_contract_spec_account_info_none(self):
        """Mt5UnavailableError when account_info returns None."""
        import broker.mt5_gateway as gw
        self.mock_mt5.account_info.return_value = None
        with pytest.raises(gw.Mt5UnavailableError, match="Could not get account info"):
            gw.get_contract_spec("XAUUSD")

    def test_get_contract_spec_infer_broker(self):
        """Broker/server inferred from account_info when not provided."""
        import broker.mt5_gateway as gw
        spec = gw.get_contract_spec("XAUUSD")
        assert spec.broker == "Pepperstone"  # from "Pepperstone-Demo".split("-")[0]
        assert spec.server == "Pepperstone-Demo"

    def test_get_contract_spec_empty_server(self):
        """Handles empty server string gracefully."""
        import broker.mt5_gateway as gw
        self.mock_mt5.account_info.return_value.server = ""
        spec = gw.get_contract_spec("XAUUSD")
        assert spec.broker == ""
        assert spec.server == ""

    def test_get_contract_spec_exception_wrapping(self):
        """Unexpected exceptions wrapped in Mt5UnavailableError."""
        import broker.mt5_gateway as gw
        self.mock_mt5.symbol_info.side_effect = OSError("Disk error")
        with pytest.raises(gw.Mt5UnavailableError, match="Failed to build ContractSpec"):
            gw.get_contract_spec("XAUUSD")


# ---------------------------------------------------------------------------
# Tests: Safety Assertion
# ---------------------------------------------------------------------------

class TestReadonlySafety:
    """Verify the module-level safety assertion holds."""

    def test_no_order_send_exists(self):
        """mt5_gateway must NOT contain order_send, order_modify, or order_close."""
        import broker.mt5_gateway as gw
        assert not hasattr(gw, "order_send"), "order_send must not exist"
        assert not hasattr(gw, "order_modify"), "order_modify must not exist"
        assert not hasattr(gw, "order_close"), "order_close must not exist"
