"""G4.3 Failure Matrix — validates all failure modes without real broker calls.

Every failure mode of submit_order_once() is verified:
- Exactly one submission attempt
- No retry
- Evidence dict correctly shaped
- Submission gate lifecycle
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from unittest.mock import MagicMock, patch

from execution.demo_canary.order_submission import (
    submit_order_once, enable_submission, disable_submission,
    is_submission_enabled,
)

_REQUEST = {
    "action": 0,
    "symbol": "XAUUSD",
    "volume": 0.01,
    "type": 0,
    "price": 4077.61,
    "sl": 4076.58,
    "tp": 4078.10,
    "deviation": 10,
    "magic": 12345678,
    "comment": "CANARY_TEST",
}


def _make_result(retcode: int, deal: int = 0, order: int = 0,
                 volume: float = 0.01, price: float = 0.0,
                 comment: str = "") -> MagicMock:
    r = MagicMock()
    r.retcode = retcode
    r.deal = deal
    r.order = order
    r.volume = volume
    r.price = price
    r.comment = comment
    r.request_id = 0
    r.retcode_external = 0
    return r


@pytest.fixture(autouse=True)
def reset_submission():
    disable_submission()
    yield
    disable_submission()


@pytest.fixture
def mock_mt5():
    with patch("execution.demo_canary.order_submission.mt5") as m:
        yield m


class TestFailureMatrix:

    # ── Gate lock ──

    def test_submission_disabled(self, mock_mt5):
        """Gate lock prevents any call to order_send."""
        resp = submit_order_once(_REQUEST)
        assert resp["retcode"] == -999
        assert resp["error"] == "SUBMISSION_DISABLED"
        mock_mt5.order_send.assert_not_called()

    # ── None result (most dangerous case) ──

    def test_none_result(self, mock_mt5):
        """None from order_send -> SUBMISSION_UNKNOWN, no retry."""
        mock_mt5.order_send.return_value = None

        enable_submission()
        resp = submit_order_once(_REQUEST)
        disable_submission()

        assert resp["retcode"] == -1
        assert resp["error"] == "SUBMISSION_UNKNOWN"
        assert "None" in resp["comment"]
        mock_mt5.order_send.assert_called_once()

    def test_none_exactly_one_attempt(self, mock_mt5):
        """Prove no retry: exactly one call even on None."""
        mock_mt5.order_send.return_value = None

        enable_submission()
        resp = submit_order_once(_REQUEST)
        disable_submission()

        assert resp["retcode"] == -1
        mock_mt5.order_send.assert_called_once()

    # ── Broker rejection retcodes ──

    def test_requote(self, mock_mt5):
        """REQUOTE retcode -> evidence returned, no retry."""
        mock_mt5.order_send.return_value = _make_result(10004, comment="Requote")

        enable_submission()
        resp = submit_order_once(_REQUEST)
        disable_submission()

        assert resp["retcode"] == 10004
        assert resp["comment"] == "Requote"
        mock_mt5.order_send.assert_called_once()

    def test_reject(self, mock_mt5):
        """REJECT retcode -> evidence returned, no retry."""
        mock_mt5.order_send.return_value = _make_result(10006, comment="Rejected")

        enable_submission()
        resp = submit_order_once(_REQUEST)
        disable_submission()

        assert resp["retcode"] == 10006
        mock_mt5.order_send.assert_called_once()

    def test_invalid_stops(self, mock_mt5):
        """INVALID_STOPS retcode -> evidence returned, no retry."""
        mock_mt5.order_send.return_value = _make_result(10016, comment="Invalid stops/loss")

        enable_submission()
        resp = submit_order_once(_REQUEST)
        disable_submission()

        assert resp["retcode"] == 10016
        mock_mt5.order_send.assert_called_once()

    def test_market_closed(self, mock_mt5):
        """MARKET_CLOSED retcode -> evidence returned, no retry."""
        mock_mt5.order_send.return_value = _make_result(10019, comment="Market is closed")

        enable_submission()
        resp = submit_order_once(_REQUEST)
        disable_submission()

        assert resp["retcode"] == 10019
        mock_mt5.order_send.assert_called_once()

    def test_no_money(self, mock_mt5):
        """NO_MONEY retcode -> evidence returned, no retry."""
        mock_mt5.order_send.return_value = _make_result(10014, comment="Insufficient money")

        enable_submission()
        resp = submit_order_once(_REQUEST)
        disable_submission()

        assert resp["retcode"] == 10014
        mock_mt5.order_send.assert_called_once()

    def test_trade_disabled(self, mock_mt5):
        """TRADE_DISABLED retcode -> evidence returned, no retry."""
        mock_mt5.order_send.return_value = _make_result(10007, comment="Trade disabled by server")

        enable_submission()
        resp = submit_order_once(_REQUEST)
        disable_submission()

        assert resp["retcode"] == 10007
        mock_mt5.order_send.assert_called_once()

    # ── Edge / unexpected failures ──

    def test_connection_lost_returns_none(self, mock_mt5):
        """mt5.shutdown() externally -> order_send returns None -> SUBMISSION_UNKNOWN.
        ponytail: MT5 C extension returns None (not exception) on disconnected order_send.
        Covered by None test, but named here for traceability."""
        mock_mt5.order_send.return_value = None

        enable_submission()
        resp = submit_order_once(_REQUEST)
        disable_submission()

        assert resp["retcode"] == -1
        assert resp["error"] == "SUBMISSION_UNKNOWN"
        mock_mt5.order_send.assert_called_once()

    def test_unexpected_exception_propagates(self, mock_mt5):
        """Unexpected error from order_send propagates to caller,
        who handles cleanup via finally block."""
        mock_mt5.order_send.side_effect = RuntimeError("Unexpected failure")

        enable_submission()
        with pytest.raises(RuntimeError, match="Unexpected failure"):
            submit_order_once(_REQUEST)
        disable_submission()

        mock_mt5.order_send.assert_called_once()
        assert not is_submission_enabled()

    # ── Evidence dict shape ──

    def test_evidence_dict_shape(self, mock_mt5):
        """Evidence dict has all expected fields for all retcodes."""
        for retcode in [10004, 10006, 10007, 10014, 10016, 10019]:
            mock_mt5.order_send.return_value = _make_result(retcode, deal=12345, order=67890)

            enable_submission()
            resp = submit_order_once(_REQUEST)
            disable_submission()

            assert "retcode" in resp
            assert resp["retcode"] == retcode
            assert "deal" in resp
            assert "order" in resp
            assert "volume" in resp
            assert "price" in resp
            assert "comment" in resp
            assert "request_id" in resp
            assert "retcode_external" in resp

    # ── Submission gate lifecycle ──

    def test_submission_gate_lifecycle(self, mock_mt5):
        """enable before, disable after, no residual enabled state."""
        assert not is_submission_enabled()
        enable_submission()
        assert is_submission_enabled()

        mock_mt5.order_send.return_value = _make_result(10004)
        submit_order_once(_REQUEST)

        disable_submission()
        assert not is_submission_enabled()

    def test_all_failure_modes_no_retries(self, mock_mt5):
        """All seven failure modes — exactly one call each."""
        modes = [None, 10004, 10006, 10007, 10014, 10016, 10019]

        for retcode in modes:
            mock_mt5.order_send.return_value = (
                None if retcode is None else _make_result(retcode)
            )

            enable_submission()
            submit_order_once(_REQUEST)
            disable_submission()

            mock_mt5.order_send.assert_called_once()
            mock_mt5.order_send.reset_mock()
