"""Tests for Phase BE-P0 — Broker connection with identity verification."""
from graxia.packages.quant_os.runtime.broker_connection import BrokerConnection


def _make(**overrides):
    defaults = dict(
        server="MetaQuotes-Demo",
        login=12345678,
        password="",
        account_mode="DEMO",
        account_currency="USD",
    )
    defaults.update(overrides)
    return BrokerConnection(**defaults)


def test_broker_connection_creation():
    conn = _make()
    assert conn.server == "MetaQuotes-Demo"
    assert conn.login == 12345678
    assert conn.password == ""
    assert conn.account_mode == "DEMO"
    assert conn.account_currency == "USD"


def test_broker_connection_validate_success():
    conn = _make()
    ok, msg = conn.validate_against("MetaQuotes-Demo", 12345678, "DEMO")
    assert ok is True
    assert msg == "OK"


def test_broker_connection_validate_server_mismatch():
    conn = _make()
    ok, msg = conn.validate_against("Other-Server", 12345678, "DEMO")
    assert ok is False
    assert "server_mismatch" in msg


def test_broker_connection_validate_login_mismatch():
    conn = _make()
    ok, msg = conn.validate_against("MetaQuotes-Demo", 99999999, "DEMO")
    assert ok is False
    assert "login_mismatch" in msg


def test_broker_connection_validate_mode_mismatch():
    conn = _make()
    ok, msg = conn.validate_against("MetaQuotes-Demo", 12345678, "LIVE")
    assert ok is False
    assert "mode_mismatch" in msg


def test_broker_connection_repr_no_leak():
    conn = _make(password="secret123")
    r = repr(conn)
    assert "secret123" not in r
    assert "MetaQuotes-Demo" in r
    assert "12345678" in r
