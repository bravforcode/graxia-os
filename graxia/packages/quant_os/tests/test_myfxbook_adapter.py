"""Tests for the Myfxbook gateway + adapter (mocked HTTP, no real credentials).

These verify the XML parsing, field mapping, session caching, and the
read-only fail-closed behaviour of trading operations — without touching the
network or requiring MYFXBOOK_EMAIL / MYFXBOOK_PASSWORD.
"""

import urllib.request

import pytest

from graxia.packages.quant_os.broker.myfxbook_gateway import (
    MyfxbookError,
    MyfxbookGateway,
)
from graxia.packages.quant_os.execution.adapters.base import AccountInfo, Order, OrderStatus
from graxia.packages.quant_os.execution.adapters.myfxbook import MyfxbookAdapter

_LOGIN_XML = '<response error="false" message="">' "<session>DSL07vu14QxHWErTIAFrH40</session>" "</response>"
_ACCOUNTS_XML = """
<response error="false" message="">
  <accounts>
    <account>
      <id>12345</id>
      <name>Holy Grail</name>
      <balance>10892.45</balance>
      <equity>10892.45</equity>
      <gain>8.92</gain>
      <drawdown>53.53</drawdown>
      <profitFactor>0.16</profitFactor>
      <pips>81.20</pips>
      <currency>USD</currency>
      <demo>true</demo>
    </account>
  </accounts>
</response>
"""
_TRADES_XML = """
<response error="false" message="">
  <opentrades>
    <trade>
      <openDate>03/01/2010 13:39</openDate>
      <symbol>GBPUSD</symbol>
      <action>Sell</action>
      <sizing><type>lots</type><value>0.01</value></sizing>
      <openPrice>1.4802</openPrice>
      <tp>1.4832</tp>
      <sl>0</sl>
      <profit>-10.8</profit>
      <pips>-108.0</pips>
      <swap>0.0</swap>
      <comment>Best trade ever</comment>
      <magic>24129962</magic>
    </trade>
  </opentrades>
</response>
"""
_LOGOUT_XML = '<response error="false" message="Logged out."></response>'
_ERROR_XML = '<response error="true" message="Wrong email/password"><session></session></response>'


class _FakeResponse:
    def __init__(self, data: str) -> None:
        self._data = data.encode("utf-8")

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _router(url: str, *args, **kwargs) -> _FakeResponse:
    if "login" in url:
        return _FakeResponse(_LOGIN_XML)
    if "get-my-accounts" in url:
        return _FakeResponse(_ACCOUNTS_XML)
    if "get-open-trades" in url:
        return _FakeResponse(_TRADES_XML)
    if "logout" in url:
        return _FakeResponse(_LOGOUT_XML)
    if "get-history" in url:
        return _FakeResponse('<response error="false" message=""><history></history></response>')
    return _FakeResponse('<response error="false" message=""></response>')


def _patched(monkeypatch):
    counter = {"calls": 0}

    def _side_effect(url, *args, **kwargs):
        counter["calls"] += 1
        return _router(url, *args, **kwargs)

    monkeypatch.setattr(urllib.request, "urlopen", _side_effect)
    return counter


def test_login_returns_session(monkeypatch):
    _patched(monkeypatch)
    gw = MyfxbookGateway(email="a@b.com", password="secret")
    assert gw.login() == "DSL07vu14QxHWErTIAFrH40"


def test_get_my_accounts_parses(monkeypatch):
    _patched(monkeypatch)
    gw = MyfxbookGateway(email="a@b.com", password="secret")
    accounts = gw.get_my_accounts()
    assert isinstance(accounts, list) and len(accounts) == 1
    assert accounts[0]["balance"] == "10892.45"
    assert accounts[0]["currency"] == "USD"


def test_session_is_cached(monkeypatch):
    counter = _patched(monkeypatch)
    gw = MyfxbookGateway(email="a@b.com", password="secret")
    gw.login()
    gw.get_my_accounts()  # should reuse cached session, not re-login
    gw.get_my_accounts()
    # login called once; get-my-accounts called twice -> 3 total urlopen calls
    assert counter["calls"] == 3


def test_api_error_raises(monkeypatch):
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResponse(_ERROR_XML))
    gw = MyfxbookGateway(email="a@b.com", password="wrong")
    with pytest.raises(MyfxbookError):
        gw.get_my_accounts()


def test_adapter_get_account_info_maps(monkeypatch):
    _patched(monkeypatch)
    adapter = MyfxbookAdapter(email="a@b.com", password="secret")
    info = adapter.get_account_info()
    assert isinstance(info, AccountInfo)
    assert info.equity == 10892.45
    assert info.cash == 10892.45
    assert info.margin_used == 0.0
    assert info.margin_available == 10892.45


def test_adapter_get_positions_maps(monkeypatch):
    _patched(monkeypatch)
    adapter = MyfxbookAdapter(email="a@b.com", password="secret")
    positions = adapter.get_positions()
    assert len(positions) == 1
    assert positions[0]["symbol"] == "GBPUSD"
    assert positions[0]["side"] == "SELL"
    assert positions[0]["quantity"] == 0.01
    assert positions[0]["avg_price"] == 1.4802


def test_adapter_is_read_only_fail_closed(monkeypatch):
    _patched(monkeypatch)
    adapter = MyfxbookAdapter(email="a@b.com", password="secret")
    order = Order(order_id="x", signal_id="", symbol="EURUSD", asset_class="", side="BUY", quantity=0.1)
    assert adapter.submit_order(order).status == OrderStatus.FAILED
    assert adapter.cancel_order("b").status == OrderStatus.FAILED
    assert adapter.get_order_status("b").status == OrderStatus.FAILED
    assert adapter.close_position("p", 0.1).status == OrderStatus.FAILED
    assert adapter.set_stop_loss(1, "EURUSD", 1.1) is False


def test_adapter_analytics_exposes_full_dict(monkeypatch):
    _patched(monkeypatch)
    adapter = MyfxbookAdapter(email="a@b.com", password="secret")
    analytics = adapter.get_account_analytics()
    assert analytics["gain"] == "8.92"
    assert analytics["drawdown"] == "53.53"
