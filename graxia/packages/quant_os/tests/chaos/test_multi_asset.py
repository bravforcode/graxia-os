"""Tests for core.multi_asset — multi-asset configuration and pip calculations."""

import pytest

from graxia.packages.quant_os.core.multi_asset import (
    ASSETS,
    AssetConfig,
    calculate_pip_value,
    get_all_symbols,
    get_asset,
)


class TestGetAsset:
    def test_returns_xauusd_config(self):
        asset = get_asset("XAUUSD")
        assert asset is not None
        assert asset.symbol == "XAUUSD"
        assert asset.pip_value == 0.01
        assert asset.spread_pips == 0.35
        assert asset.news_impact == "high"

    def test_returns_eurusd_config(self):
        asset = get_asset("EURUSD")
        assert asset is not None
        assert asset.symbol == "EURUSD"
        assert asset.pip_value == 0.0001
        assert asset.spread_pips == 0.10
        assert asset.news_impact == "medium"

    def test_returns_gbpusd_config(self):
        asset = get_asset("GBPUSD")
        assert asset is not None
        assert asset.symbol == "GBPUSD"
        assert asset.pip_value == 0.0001
        assert asset.spread_pips == 0.15
        assert asset.news_impact == "medium"

    def test_case_insensitive(self):
        asset = get_asset("eurusd")
        assert asset is not None
        assert asset.symbol == "EURUSD"

    def test_unknown_symbol_returns_none(self):
        assert get_asset("USDJPY") is None
        assert get_asset("BTCUSD") is None
        assert get_asset("") is None


class TestGetAllSymbols:
    def test_returns_three_symbols(self):
        symbols = get_all_symbols()
        assert len(symbols) == 3

    def test_contains_expected_symbols(self):
        symbols = get_all_symbols()
        assert "XAUUSD" in symbols
        assert "EURUSD" in symbols
        assert "GBPUSD" in symbols


class TestCalculatePipValue:
    def test_xauusd_pip_value(self):
        # 0.01 * 1.0 * 100000 = 1000.0
        result = calculate_pip_value("XAUUSD", 1.0)
        assert result == pytest.approx(1000.0)

    def test_eurusd_pip_value(self):
        # 0.0001 * 1.0 * 100000 = 10.0
        result = calculate_pip_value("EURUSD", 1.0)
        assert result == pytest.approx(10.0)

    def test_gbpusd_pip_value(self):
        # 0.0001 * 1.0 * 100000 = 10.0
        result = calculate_pip_value("GBPUSD", 1.0)
        assert result == pytest.approx(10.0)

    def test_fractional_lot_size(self):
        result = calculate_pip_value("EURUSD", 0.5)
        assert result == pytest.approx(5.0)

    def test_unknown_symbol_returns_zero(self):
        result = calculate_pip_value("USDJPY", 1.0)
        assert result == 0.0


class TestAssetsRegistry:
    def test_all_assets_are_dataclass_instances(self):
        for key, asset in ASSETS.items():
            assert isinstance(asset, AssetConfig)
            assert asset.symbol == key

    def test_all_have_session_hours(self):
        for asset in ASSETS.values():
            assert len(asset.session_hours) == 2
            assert asset.session_hours[0] < asset.session_hours[1]
