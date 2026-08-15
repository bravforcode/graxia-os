"""Tests for market_data/universe_discovery.py and broker/mt5_gateway.get_symbols()."""

from __future__ import annotations

import json
import sys

import pytest

from market_data import universe_discovery as ud


class TestClassifySymbol:
    def test_allowlisted_paths(self):
        assert ud.classify_symbol("XAUUSD", "Forex\\Metals") == "metals"
        assert ud.classify_symbol("EURUSD", "Forex") == "forex"
        assert ud.classify_symbol("USOIL", "CFD\\Energies") == "commodities"
        assert ud.classify_symbol("NAS100", "Indices") == "indices"

    def test_rejects_junk_names(self):
        assert ud.classify_symbol("EURSGD.he", "Forex") is None
        assert ud.classify_symbol("tiny", "Forex") is None  # too short


class TestSpreadBps:
    def test_spread_bps_conversion(self):
        tick = {"bid": 2300.00, "ask": 2300.20}
        assert ud.spread_bps_from_tick(tick) == pytest.approx(0.8696, abs=1e-3)

    def test_zero_mid_rejects(self):
        assert ud.spread_bps_from_tick({"bid": 0.0, "ask": 0.0}) == float("inf")


class TestDiscoverNewCandidates:
    def test_only_new_allowlisted_symbols(self):
        symbols = [
            {"name": "EURUSD", "path": "Forex"},
            {"name": "XAUUSD", "path": "Forex\\Metals"},
            {"name": "SOLUSD", "path": "Crypto"},
        ]
        universe = {
            "tradeable": [{"symbol": "XAUUSD"}],
            "candidate": [],
            "measuring": [],
            "verifying": [],
            "excluded": [{"symbol": "GBPUSD"}],
        }
        candidates = ud.discover_new_candidates(symbols, universe)
        assert [c["symbol"] for c in candidates] == ["EURUSD"]


class TestUpdateUniverse:
    def test_appends_candidates_and_preserves_entries(self, tmp_path):
        path = tmp_path / "tradeable_universe.json"
        path.write_text(
            json.dumps(
                {
                    "_meta": {"version": "1.2.0", "updated": "2026-08-01"},
                    "tradeable": [{"symbol": "XAUUSD"}],
                    "measuring": [],
                    "verifying": [],
                    "candidate": [],
                    "excluded": [],
                }
            )
        )
        added = ud.update_universe(path, [{"symbol": "EURUSD", "asset_class": "forex"}])
        assert added == ["EURUSD"]
        universe = json.loads(path.read_text(encoding="utf-8"))
        assert universe["candidate"][0]["symbol"] == "EURUSD"
        assert universe["tradeable"][0]["symbol"] == "XAUUSD"

    def test_duplicate_candidate_not_added_twice(self, tmp_path):
        path = tmp_path / "tradeable_universe.json"
        path.write_text(json.dumps({"_meta": {}, "candidate": [{"symbol": "EURUSD"}]}))
        added = ud.update_universe(path, [{"symbol": "EURUSD", "asset_class": "forex"}])
        assert added == []


class TestGetSymbolsWrapper:
    """Mirror of tests/test_mt5_gateway.py's mocking pattern."""

    def _reset_mt5_globals(self):
        import broker.mt5_gateway as gw

        gw._mt5_imported = False
        gw._mt5 = None

    def _make_mock_mt5(self):
        from unittest.mock import MagicMock

        mt5 = MagicMock()
        s1 = MagicMock()
        s1.name = "XAUUSD"
        s1.path = "Forex\\Metals"
        s1.digits = 2
        s1.trade_mode = 0
        s2 = MagicMock()
        s2.name = "SOLUSD"
        s2.path = "Crypto"
        s2.digits = 8
        s2.trade_mode = 0
        mt5.symbols_get.return_value = [s1, s2]
        return mt5

    def test_get_symbols_returns_dicts(self):
        from unittest.mock import patch

        self._reset_mt5_globals()
        mock_mt5 = self._make_mock_mt5()
        import broker.mt5_gateway as gw

        with patch.dict(sys.modules, {"MetaTrader5": mock_mt5}):
            result = gw.get_symbols()
        assert [r["name"] for r in result] == ["XAUUSD", "SOLUSD"]
        assert result[0]["path"] == "Forex\\Metals"

    def test_get_symbols_none_raises(self):
        from unittest.mock import patch

        self._reset_mt5_globals()
        mock_mt5 = self._make_mock_mt5()
        mock_mt5.symbols_get.return_value = None
        mock_mt5.last_error.return_value = (1, "bad")
        import broker.mt5_gateway as gw

        with (
            patch.dict(sys.modules, {"MetaTrader5": mock_mt5}),
            pytest.raises(gw.Mt5UnavailableError, match="symbols_get failed"),
        ):
            gw.get_symbols()
