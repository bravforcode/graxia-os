"""Tests for mt5_connector.shadow_runner.ShadowRunner — verifies shadow mode never sends orders."""

from unittest.mock import MagicMock, patch


def _make_runner():
    """Create a ShadowRunner with mocked MT5 and config."""
    config = {"mt5": {"timeout": 5000}}
    with patch("builtins.open", mock_open(read_data="")):
        with patch("yaml.safe_load", return_value=config):
            from graxia.packages.quant_os.mt5_connector.shadow_runner import ShadowRunnerV2 as ShadowRunner

            runner = ShadowRunner(config_path="dummy.yaml")
    return runner


from unittest.mock import mock_open


class TestShadowRunnerInit:
    def test_creates_with_config(self):
        runner = _make_runner()
        assert runner._session_id.startswith("shadow_")
        assert runner._signal_count == 0
        assert runner._running is False

    def test_no_order_send_method(self):
        runner = _make_runner()
        assert not hasattr(runner, "order_send")


class TestShadowRunnerConnectDisconnect:
    def test_disconnect_when_not_connected(self):
        runner = _make_runner()
        runner.disconnect()  # should not raise

    def test_connect_calls_mt5(self):
        runner = _make_runner()
        runner._mt5 = MagicMock()
        runner._mt5.connect.return_value = True
        runner._mt5.get_account_info.return_value = MagicMock(login=123, server="demo", balance=10000)
        result = runner.connect()
        assert result is True
        runner._mt5.connect.assert_called_once()

    def test_connect_failure(self):
        runner = _make_runner()
        runner._mt5 = MagicMock()
        runner._mt5.connect.return_value = False
        result = runner.connect()
        assert result is False


class TestShadowRunnerRunCycle:
    def test_run_cycle_no_tick_returns_error(self):
        runner = _make_runner()
        runner._mt5 = MagicMock()
        runner._mt5.get_tick.return_value = None
        result = runner.run_cycle("XAUUSD")
        assert result == {"error": "NO_TICK"}

    def test_run_cycle_does_not_call_order_send(self):
        runner = _make_runner()
        runner._mt5 = MagicMock()
        runner._mt5.get_tick.return_value = {"bid": 1.0, "ask": 1.1, "last": 1.05, "volume": 100, "time": 0, "flags": 0}
        runner._mt5.get_bars.return_value = [
            {"time": 0, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 100},
            {"time": 1, "open": 1.0, "high": 1.2, "low": 1.0, "close": 1.1, "volume": 100},
        ]
        runner._mt5.order_send = MagicMock()
        runner._pipeline.start_session("test")
        runner.run_cycle("XAUUSD")
        runner._mt5.order_send.assert_not_called()

    def test_run_cycle_returns_signal_fields(self):
        runner = _make_runner()
        runner._mt5 = MagicMock()
        runner._mt5.get_tick.return_value = {
            "bid": 2350.0,
            "ask": 2351.0,
            "last": 2350.5,
            "volume": 100,
            "time": 0,
            "flags": 0,
        }
        runner._mt5.get_bars.return_value = [
            {"time": 0, "open": 2350.0, "high": 2355.0, "low": 2345.0, "close": 2350.0, "volume": 100},
            {"time": 1, "open": 2350.0, "high": 2360.0, "low": 2348.0, "close": 2355.0, "volume": 100},
        ]
        runner._pipeline.start_session("test")
        result = runner.run_cycle("XAUUSD")
        assert "signal_id" in result
        assert "direction" in result
        assert "outcome" in result
        # ponytail: V2 run_cycle returns different fields than V1. bid/ask not in result.


class TestShadowRunnerOrderSendGuarantee:
    """Core invariant: ShadowRunner never calls order_send, regardless of inputs."""

    def test_no_order_send_on_accepted_signal(self):
        runner = _make_runner()
        runner._mt5 = MagicMock()
        runner._mt5.get_tick.return_value = {
            "bid": 100.0,
            "ask": 100.1,
            "last": 100.05,
            "volume": 50,
            "time": 0,
            "flags": 0,
        }
        runner._mt5.get_bars.return_value = [
            {"time": i, "open": 100, "high": 101, "low": 99, "close": 100 + i, "volume": 10} for i in range(5)
        ]
        runner._mt5.order_send = MagicMock()
        runner._pipeline.start_session("test")
        runner.run_cycle("EURUSD")
        runner._mt5.order_send.assert_not_called()

    def test_no_order_send_on_rejected_signal(self):
        runner = _make_runner()
        runner._mt5 = MagicMock()
        runner._mt5.get_tick.return_value = {"bid": 1.0, "ask": 1.0, "last": 1.0, "volume": 0, "time": 0, "flags": 0}
        runner._mt5.get_bars.return_value = []  # insufficient bars → rejected
        runner._mt5.order_send = MagicMock()
        runner._pipeline.start_session("test")
        runner.run_cycle("XAUUSD")
        runner._mt5.order_send.assert_not_called()

    def test_no_order_send_across_multiple_cycles(self):
        runner = _make_runner()
        runner._mt5 = MagicMock()
        runner._mt5.get_tick.return_value = {"bid": 1.0, "ask": 1.1, "last": 1.05, "volume": 10, "time": 0, "flags": 0}
        runner._mt5.get_bars.return_value = [
            {"time": 0, "open": 1.0, "high": 1.1, "low": 0.9, "close": 1.0, "volume": 10},
            {"time": 1, "open": 1.0, "high": 1.2, "low": 1.0, "close": 1.1, "volume": 10},
        ]
        runner._mt5.order_send = MagicMock()
        runner._pipeline.start_session("test")
        for _ in range(10):
            runner.run_cycle("XAUUSD")
        runner._mt5.order_send.assert_not_called()
