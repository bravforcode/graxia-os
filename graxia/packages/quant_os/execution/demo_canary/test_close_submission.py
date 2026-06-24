"""Tests for order_submission close path. No MT5 dependency."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

import pytest
from unittest.mock import MagicMock, patch

from execution.demo_canary.order_submission import (
    submit_close_once, enable_submission, disable_submission,
    is_submission_enabled,
)


@pytest.fixture(autouse=True)
def reset_submission():
    disable_submission()
    yield
    disable_submission()


@pytest.fixture
def mock_mt5():
    with patch("execution.demo_canary.order_submission.mt5") as m:
        yield m


class TestCloseSubmission:

    def test_close_success(self, mock_mt5):
        pos = MagicMock(ticket=12345, magic=999)
        mock_mt5.positions_get.return_value = (pos,)
        result = MagicMock(retcode=10009, deal=67890, order=0, volume=0.01,
                           price=4078.50, comment="", request_id=0, retcode_external=0)
        mock_mt5.position_close.return_value = result

        enable_submission()
        resp = submit_close_once(position_ticket=12345, expected_magic=999)
        disable_submission()

        assert resp["retcode"] == 10009
        assert resp["deal"] == 67890
        mock_mt5.position_close.assert_called_once_with(ticket=12345, deviation=20)

    def test_close_unknown_on_none(self, mock_mt5):
        mock_mt5.positions_get.return_value = (MagicMock(ticket=12345, magic=999),)
        mock_mt5.position_close.return_value = None

        enable_submission()
        resp = submit_close_once(position_ticket=12345, expected_magic=999)
        disable_submission()

        assert resp["retcode"] == -1
        assert resp["error"] == "CLOSE_UNKNOWN"
        mock_mt5.position_close.assert_called_once()

    def test_close_position_not_found(self, mock_mt5):
        mock_mt5.positions_get.return_value = None

        enable_submission()
        resp = submit_close_once(position_ticket=99999, expected_magic=999)
        disable_submission()

        assert resp["retcode"] == -2
        assert resp["error"] == "POSITION_NOT_FOUND"
        mock_mt5.position_close.assert_not_called()

    def test_magic_mismatch(self, mock_mt5):
        mock_mt5.positions_get.return_value = (MagicMock(ticket=12345, magic=888),)

        enable_submission()
        resp = submit_close_once(position_ticket=12345, expected_magic=999)
        disable_submission()

        assert resp["retcode"] == -3
        assert resp["error"] == "POSITION_MAGIC_MISMATCH"
        mock_mt5.position_close.assert_not_called()

    def test_submission_disabled(self, mock_mt5):
        resp = submit_close_once(position_ticket=12345, expected_magic=999)
        assert resp["retcode"] == -999
        assert resp["error"] == "SUBMISSION_DISABLED"
        mock_mt5.position_close.assert_not_called()
        mock_mt5.positions_get.assert_not_called()

    def test_enable_disable_pattern(self, mock_mt5):
        assert not is_submission_enabled()
        enable_submission()
        assert is_submission_enabled()

        mock_mt5.positions_get.return_value = (MagicMock(ticket=12345, magic=999),)
        mock_mt5.position_close.return_value = MagicMock(retcode=10009)

        submit_close_once(position_ticket=12345, expected_magic=999)

        disable_submission()
        assert not is_submission_enabled()

    def test_only_one_close_attempt(self, mock_mt5):
        mock_mt5.positions_get.return_value = (MagicMock(ticket=12345, magic=999),)
        mock_mt5.position_close.return_value = None

        enable_submission()
        resp = submit_close_once(position_ticket=12345, expected_magic=999)
        disable_submission()

        assert resp["retcode"] == -1
        mock_mt5.position_close.assert_called_once()
