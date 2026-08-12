"""Tests for LiveSpreadTracker."""
import time


from graxia.packages.quant_os.core.live_spread import LiveSpreadTracker, SpreadSnapshot


class TestDefaultSpreads:
    def test_xauusd_default(self):
        tracker = LiveSpreadTracker()
        assert tracker.get_spread("XAUUSD") == 0.35

    def test_eurusd_default(self):
        tracker = LiveSpreadTracker()
        assert tracker.get_spread("EURUSD") == 0.10

    def test_gbpusd_default(self):
        tracker = LiveSpreadTracker()
        assert tracker.get_spread("GBPUSD") == 0.15

    def test_unknown_symbol_returns_05(self):
        tracker = LiveSpreadTracker()
        assert tracker.get_spread("BTCUSD") == 0.5


class TestUpdateSpread:
    def test_update_changes_value(self):
        tracker = LiveSpreadTracker()
        tracker.update_spread("XAUUSD", bid=2350.00, ask=2350.35)
        assert tracker.get_spread("XAUUSD") == 3.5

    def test_update_xauusd_pip_conversion(self):
        tracker = LiveSpreadTracker()
        tracker.update_spread("XAUUSD", bid=2350.00, ask=2350.50)
        assert tracker.get_spread("XAUUSD") == 5.0

    def test_update_eurusd_raw_difference(self):
        tracker = LiveSpreadTracker()
        tracker.update_spread("EURUSD", bid=1.1000, ask=1.1015)
        assert tracker.get_spread("EURUSD") == 0.0

    def test_update_snapshot_fields(self):
        tracker = LiveSpreadTracker()
        tracker.update_spread("XAUUSD", bid=2350.00, ask=2350.35)
        snapshot = tracker._cache["XAUUSD"]
        assert isinstance(snapshot, SpreadSnapshot)
        assert snapshot.symbol == "XAUUSD"
        assert snapshot.bid == 2350.00
        assert snapshot.ask == 2350.35


class TestGetAllSpreads:
    def test_returns_dict(self):
        tracker = LiveSpreadTracker()
        spreads = tracker.get_all_spreads()
        assert isinstance(spreads, dict)
        assert "XAUUSD" in spreads
        assert "EURUSD" in spreads
        assert "GBPUSD" in spreads

    def test_values_match_get_spread(self):
        tracker = LiveSpreadTracker()
        spreads = tracker.get_all_spreads()
        for symbol, spread in spreads.items():
            assert spread == tracker.get_spread(symbol)


class TestCacheExpiry:
    def test_cache_expires_after_interval(self):
        tracker = LiveSpreadTracker()
        tracker._update_interval = 0.1  # 100ms for test
        tracker.update_spread("XAUUSD", bid=2350.00, ask=2350.50)
        assert tracker.get_spread("XAUUSD") == 5.0
        time.sleep(0.15)
        assert tracker.get_spread("XAUUSD") == 0.35  # back to default

    def test_cache_persists_before_expiry(self):
        tracker = LiveSpreadTracker()
        tracker._update_interval = 10.0  # long interval
        tracker.update_spread("XAUUSD", bid=2350.00, ask=2350.50)
        assert tracker.get_spread("XAUUSD") == 5.0
