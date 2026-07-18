"""
Tests for data_bridge.py — Pipeline data → MacroRegimeCache wiring.

Covers:
  1. Regime computation correctness (FGI, VIX, sentiment thresholds)
  2. Staleness threshold (>30 min) — cache freshness logic
  3. JSON round-trip — MacroRegime.to_dict / from_dict
  4. Force flag bypasses staleness
  5. Error handling — graceful degradation on DuckDB/API failure
  6. Regime label / position_multiplier mapping
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from graxia.packages.quant_os.core.canonical.macro_regime import (
    MacroRegime,
    MacroRegimeCache,
    RegimeBias,
)


# ── Helpers ─────────────────────────────────────────────────────────


def _make_bridge(**duckdb_overrides):
    """Create DataBridge with mocked DuckDB and onchain."""
    from graxia.packages.quant_os.data_pipeline.data_bridge import DataBridge

    bridge = DataBridge()
    mock_duckdb = MagicMock()
    bridge._duckdb = mock_duckdb
    # Default: empty macro query
    mock_duckdb.query.return_value = MagicMock(__len__=lambda s: 0)
    mock_duckdb.get_sentiment_summary.return_value = MagicMock(__len__=lambda s: 0)
    for k, v in duckdb_overrides.items():
        setattr(mock_duckdb, k, v)
    return bridge


def _fresh_cache(tmp_path):
    """Create a fresh MacroRegimeCache pointing at tmp_path."""
    cache = object.__new__(MacroRegimeCache)
    cache._regime = MacroRegime()
    cache._lock = __import__("threading").Lock()
    cache._STATE_PATH = tmp_path / "macro_regime_state.json"
    return cache


# ── 1. JSON Round-Trip ──────────────────────────────────────────────


class TestMacroRegimeRoundTrip:
    """MacroRegime.to_dict → from_dict must be lossless."""

    def test_default_round_trip(self):
        m = MacroRegime()
        d = m.to_dict()
        m2 = MacroRegime.from_dict(d)
        assert m2.bias == m.bias
        assert m2.confidence == m.confidence
        assert m2.position_multiplier == m.position_multiplier
        assert m2.regime_label == m.regime_label
        assert m2.source == m.source

    def test_bullish_round_trip(self):
        m = MacroRegime(
            bias=RegimeBias.BULLISH,
            confidence=0.85,
            position_multiplier=1.2,
            regime_label="NORMAL",
            source="data_bridge",
            headline="FGI=25 (Fear), VIX=15 (Normal)",
        )
        d = m.to_dict()
        m2 = MacroRegime.from_dict(d)
        assert m2.bias == RegimeBias.BULLISH
        assert m2.confidence == 0.85
        assert m2.position_multiplier == 1.2
        assert m2.source == "data_bridge"
        assert m2.headline == "FGI=25 (Fear), VIX=15 (Normal)"

    def test_json_serializable(self):
        """to_dict output must survive json.dumps/loads."""
        m = MacroRegime(bias=RegimeBias.BEARISH, confidence=0.7)
        d = m.to_dict()
        raw = json.dumps(d)
        d2 = json.loads(raw)
        m2 = MacroRegime.from_dict(d2)
        assert m2.bias == RegimeBias.BEARISH
        assert m2.confidence == 0.7

    def test_crisis_regime_round_trip(self):
        m = MacroRegime(
            bias=RegimeBias.BEARISH,
            confidence=0.9,
            position_multiplier=0.25,
            regime_label="CRISIS",
            source="data_bridge",
        )
        d = m.to_dict()
        m2 = MacroRegime.from_dict(d)
        assert m2.regime_label == "CRISIS"
        assert m2.position_multiplier == 0.25


# ── 2. Regime Computation Correctness ───────────────────────────────


class TestComputeRegimeFromData:
    """compute_regime_from_data must map FGI/VIX/sentiment to correct bias."""

    def _bridge_with_signals(self, fgi_val, vix_val=None, sentiment_val=0.0):
        """Create bridge with controlled signal inputs."""
        bridge = _make_bridge()

        # Mock fear_greed
        mock_onchain = MagicMock()
        mock_onchain._fetch_fear_greed.return_value = {"value": fgi_val, "label": "test"}
        bridge._onchain = mock_onchain

        # Mock VIX from macro_data
        if vix_val is not None:
            import pandas as pd

            vix_df = pd.DataFrame([{"series_id": "VIXCLS", "value": vix_val, "timestamp": "2026-01-01"}])
            macro_df = pd.DataFrame(columns=["series_id", "value", "timestamp"])
            # Query returns VIX first, then other series get empty
            call_count = [0]

            def mock_query(sql):
                call_count[0] += 1
                if "VIXCLS" in sql:
                    return vix_df
                return MagicMock(__len__=lambda s: 0)

            bridge.duckdb.query = mock_query
        else:
            bridge.duckdb.query = MagicMock(return_value=MagicMock(__len__=lambda s: 0))

        # Mock sentiment
        if sentiment_val != 0.0:
            import pandas as pd

            sent_df = pd.DataFrame(
                [{"avg_sentiment": sentiment_val, "avg_polarity": 0.0, "articles": 10, "query": "test"}]
            )
            bridge.duckdb.get_sentiment_summary = MagicMock(return_value=sent_df)

        return bridge

    def test_extreme_fear_bullish(self):
        """FGI ≤ 20 → bullish_contrarian signal."""
        bridge = self._bridge_with_signals(fgi_val=15)
        result = bridge.compute_regime_from_data()
        # Extreme fear should produce bullish bias
        assert result["bias"] in (RegimeBias.BULLISH, RegimeBias.NEUTRAL)
        assert "FGI=15" in result["reasoning"]

    def test_extreme_greed_bearish(self):
        """FGI ≥ 80 → bearish_contrarian signal."""
        bridge = self._bridge_with_signals(fgi_val=85)
        result = bridge.compute_regime_from_data()
        assert result["bias"] in (RegimeBias.BEARISH, RegimeBias.NEUTRAL)
        assert "FGI=85" in result["reasoning"]

    def test_neutral_fgi(self):
        """FGI 35-65 → neutral."""
        bridge = self._bridge_with_signals(fgi_val=50)
        result = bridge.compute_regime_from_data()
        assert result["bias"] == RegimeBias.NEUTRAL

    def test_high_vix_bearish(self):
        """VIX ≥ 30 → bearish_fear signal, regime=HIGH_UNCERTAINTY."""
        bridge = self._bridge_with_signals(fgi_val=50, vix_val=32)
        result = bridge.compute_regime_from_data()
        assert "VIX=32.0" in result["reasoning"]
        # VIX 32 ≥ 30 but < 35 → HIGH_UNCERTAINTY
        assert result["regime_label"] == "HIGH_UNCERTAINTY"
        assert result["position_multiplier"] == 0.5

    def test_crisis_vix(self):
        """VIX ≥ 35 → CRISIS regime, position_multiplier=0.25."""
        bridge = self._bridge_with_signals(fgi_val=50, vix_val=38)
        result = bridge.compute_regime_from_data()
        assert result["regime_label"] == "CRISIS"
        assert result["position_multiplier"] == 0.25

    def test_very_low_vix_bullish(self):
        """VIX ≤ 12 → bullish_calm signal."""
        bridge = self._bridge_with_signals(fgi_val=50, vix_val=10)
        result = bridge.compute_regime_from_data()
        assert "VIX=10.0" in result["reasoning"]

    def test_negative_news_bearish(self):
        """Sentiment ≤ -0.15 → bearish_news signal."""
        bridge = self._bridge_with_signals(fgi_val=50, sentiment_val=-0.2)
        result = bridge.compute_regime_from_data()
        assert "News sentiment=-0.200" in result["reasoning"]

    def test_positive_news_bullish(self):
        """Sentiment ≥ 0.15 → bullish_news signal."""
        bridge = self._bridge_with_signals(fgi_val=50, sentiment_val=0.2)
        result = bridge.compute_regime_from_data()
        assert "News sentiment=0.200" in result["reasoning"]

    def test_all_bearish_signals_compound(self):
        """FGI=85 (bearish) + VIX=35 (bearish) → strong bearish."""
        bridge = self._bridge_with_signals(fgi_val=85, vix_val=35, sentiment_val=-0.3)
        result = bridge.compute_regime_from_data()
        assert result["bias"] == RegimeBias.BEARISH
        assert result["regime_label"] == "CRISIS"

    def test_result_has_required_keys(self):
        bridge = self._bridge_with_signals(fgi_val=50)
        result = bridge.compute_regime_from_data()
        required = {"bias", "confidence", "position_multiplier", "regime_label", "source", "headline", "reasoning"}
        assert required.issubset(result.keys())


# ── 3. Staleness Threshold (>30 min) ────────────────────────────────


class TestStalenessThreshold:
    """update_macro_regime respects 30-min freshness window.

    Uses direct cache manipulation instead of patching the singleton,
    which avoids module resolution issues with sys.path vs package paths.
    """

    def _setup_bridge_with_cache(self, tmp_path, regime):
        """Create a bridge + cache with controlled state."""
        bridge = _make_bridge()

        # Mock onchain to prevent real API calls if stale path is hit
        mock_onchain = MagicMock()
        mock_onchain._fetch_fear_greed.return_value = {"value": 50, "label": "Neutral"}
        bridge._onchain = mock_onchain

        # Create a fresh cache instance pointing at tmp dir
        cache = object.__new__(MacroRegimeCache)
        cache._regime = regime
        cache._lock = __import__("threading").Lock()
        cache._STATE_PATH = tmp_path / "macro_regime_state.json"

        # Must set _instance on the sys.path-resolved module (core.canonical.macro_regime)
        # because data_bridge.py imports MacroRegimeCache via sys.path, not package path
        import importlib
        import sys
        # Ensure the sys.path module is loaded
        mod = sys.modules.get("core.canonical.macro_regime")
        if mod is None:
            mod = importlib.import_module("core.canonical.macro_regime")
        mod.MacroRegimeCache._instance = cache

        return bridge, cache

    def _cleanup_singleton(self):
        """Reset singleton on both module paths."""
        import sys
        mod = sys.modules.get("core.canonical.macro_regime")
        if mod is not None:
            mod.MacroRegimeCache._instance = None
        MacroRegimeCache._instance = None

    def test_fresh_cache_not_overwritten(self, tmp_path):
        """Cache with recent LLM data (<30 min) should NOT be overwritten."""
        fresh_regime = MacroRegime(
            bias=RegimeBias.BULLISH,
            confidence=0.9,
            source="sentiment_agent",
            updated_at=datetime.now(UTC),
        )
        bridge, cache = self._setup_bridge_with_cache(tmp_path, fresh_regime)
        try:
            result = bridge.update_macro_regime(force=False)
            assert result.source == "sentiment_agent"
            assert result.confidence == 0.9
        finally:
            self._cleanup_singleton()

    def test_stale_cache_overwritten(self, tmp_path):
        """Cache with data >30 min old should be overwritten."""
        stale_regime = MacroRegime(
            bias=RegimeBias.NEUTRAL,
            confidence=0.5,
            source="sentiment_agent",
            updated_at=datetime.now(UTC) - timedelta(minutes=31),
        )
        bridge, cache = self._setup_bridge_with_cache(tmp_path, stale_regime)
        try:
            result = bridge.update_macro_regime(force=False)
            assert result.source == "data_bridge"
        finally:
            self._cleanup_singleton()

    def test_default_source_always_overwritten(self, tmp_path):
        """Cache with source='default' should always be overwritten (no LLM data yet)."""
        default_regime = MacroRegime(source="default", updated_at=datetime.now(UTC))
        bridge, cache = self._setup_bridge_with_cache(tmp_path, default_regime)
        try:
            result = bridge.update_macro_regime(force=False)
            assert result.source == "data_bridge"
        finally:
            self._cleanup_singleton()

    def test_force_overwrites_fresh_cache(self, tmp_path):
        """force=True should overwrite even fresh cache."""
        fresh_regime = MacroRegime(
            bias=RegimeBias.BULLISH,
            confidence=0.9,
            source="sentiment_agent",
            updated_at=datetime.now(UTC),
        )
        bridge, cache = self._setup_bridge_with_cache(tmp_path, fresh_regime)
        try:
            result = bridge.update_macro_regime(force=True)
            assert result.source == "data_bridge"
        finally:
            self._cleanup_singleton()


# ── 4. Error Handling ───────────────────────────────────────────────


class TestDataBridgeErrorHandling:
    """Graceful degradation when DuckDB/API fails."""

    def test_duckdb_failure_returns_empty(self):
        """get_latest_price returns {} on DuckDB failure."""
        bridge = _make_bridge()
        bridge.duckdb.get_latest_price.side_effect = Exception("DuckDB down")
        result = bridge.get_latest_price("GC=F")
        assert result == {}

    def test_macro_query_failure_skips_series(self):
        """get_macro_latest skips failed series, returns others."""
        bridge = _make_bridge()
        call_count = [0]

        def mock_query(sql):
            call_count[0] += 1
            if "VIXCLS" in sql and call_count[0] == 1:
                raise Exception("VIX query failed")
            return MagicMock(__len__=lambda s: 0)

        bridge.duckdb.query = mock_query
        result = bridge.get_macro_latest(["VIXCLS", "DGS10"])
        # VIXCLS failed, DGS10 returned empty — result should have no VIXCLS
        assert "VIXCLS" not in result

    def test_sentiment_failure_returns_empty(self):
        """get_sentiment_summary returns {} on failure."""
        bridge = _make_bridge()
        bridge.duckdb.get_sentiment_summary.side_effect = Exception("DB error")
        result = bridge.get_sentiment_summary(days=1)
        assert result == {}

    def test_fgi_failure_returns_neutral(self):
        """get_fear_greed returns neutral default on failure."""
        bridge = _make_bridge()
        bridge._onchain = MagicMock()
        bridge._onchain._fetch_fear_greed.side_effect = Exception("API down")
        result = bridge.get_fear_greed()
        assert result == {"value": 50, "label": "Neutral"}

    def test_compute_regime_with_all_failures(self):
        """compute_regime_from_data degrades gracefully when all sources fail."""
        bridge = _make_bridge()
        # All sources fail → neutral regime with defaults
        result = bridge.compute_regime_from_data()
        assert "bias" in result
        assert result["source"] == "data_bridge"
        assert result["regime_label"] in ("NORMAL", "HIGH_UNCERTAINTY", "CRISIS")

    def test_close_cleans_up(self):
        """close() sets _duckdb to None."""
        bridge = _make_bridge()
        assert bridge._duckdb is not None
        bridge.close()
        assert bridge._duckdb is None


# ── 5. Regime Label / Position Multiplier Mapping ───────────────────


class TestRegimeLabelMapping:
    """Verify regime_label ↔ position_multiplier consistency."""

    def test_crisis_always_025(self):
        """VIX ≥ 35 → CRISIS, position_multiplier=0.25."""
        bridge = _make_bridge()
        mock_onchain = MagicMock()
        mock_onchain._fetch_fear_greed.return_value = {"value": 50, "label": "Neutral"}
        bridge._onchain = mock_onchain

        import pandas as pd

        vix_df = pd.DataFrame([{"series_id": "VIXCLS", "value": 40, "timestamp": "2026-01-01"}])

        def mock_query(sql):
            if "VIXCLS" in sql:
                return vix_df
            return MagicMock(__len__=lambda s: 0)

        bridge.duckdb.query = mock_query

        result = bridge.compute_regime_from_data()
        assert result["regime_label"] == "CRISIS"
        assert result["position_multiplier"] == 0.25

    def test_normal_always_1(self):
        """All signals neutral → NORMAL, position_multiplier=1.0."""
        bridge = _make_bridge()
        mock_onchain = MagicMock()
        mock_onchain._fetch_fear_greed.return_value = {"value": 50, "label": "Neutral"}
        bridge._onchain = mock_onchain
        bridge.duckdb.query = MagicMock(return_value=MagicMock(__len__=lambda s: 0))

        result = bridge.compute_regime_from_data()
        assert result["regime_label"] == "NORMAL"
        assert result["position_multiplier"] == 1.0
