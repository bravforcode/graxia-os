"""
data_bridge.py — Bridge between DuckDB pipeline data and trading logic.

Reads from DuckDB (pipeline output) + live API calls,
computes regime/sentiment metrics, and writes to MacroRegimeCache.

This ensures pipeline data (market, macro, news) actually reaches
trading decisions via the existing MacroRegime → portfolio_manager/risk_engine path.

Usage:
    from data_bridge import DataBridge
    bridge = DataBridge()
    regime = bridge.update_macro_regime()  # reads pipeline data, updates cache
"""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
sys.path.insert(0, str(Path(__file__).parent))


logger = logging.getLogger(__name__)


class DataBridge:
    """
    Reads pipeline data from DuckDB + live APIs,
    computes regime signals, writes to MacroRegimeCache.

    Data flow:
        Pipeline (scheduled) → DuckDB → DataBridge → MacroRegimeCache → Trading
    """

    def __init__(self):
        self._duckdb = None
        self._onchain = None

    @property
    def duckdb(self):
        if self._duckdb is None:
            from storage.duckdb_store import DuckDBStore

            self._duckdb = DuckDBStore()
        return self._duckdb

    def close(self):
        if self._duckdb:
            self._duckdb.close()
            self._duckdb = None

    # ── Market Data ──────────────────────────────────────────────────

    def get_latest_price(self, symbol: str) -> dict:
        """Get latest price from DuckDB (pipeline data)."""
        try:
            return self.duckdb.get_latest_price(symbol)
        except Exception as e:
            logger.warning("data_bridge.price_failed symbol=%s error=%s", symbol, str(e))
            return {}

    def get_market_snapshot(self, symbols: list[str] | None = None) -> dict:
        """Get latest prices for all tradeable symbols."""
        if symbols is None:
            symbols = ["GC=F", "EURUSD=X", "BTC-USD", "BTC/USDT", "ETH/USDT", "SPY"]
        snapshot = {}
        for sym in symbols:
            price = self.get_latest_price(sym)
            if price:
                snapshot[sym] = price
        return snapshot

    # ── Macro Data ───────────────────────────────────────────────────

    def get_macro_latest(self, series_ids: list[str] | None = None) -> dict:
        """Get latest macro series values from DuckDB."""
        if series_ids is None:
            series_ids = ["VIXCLS", "DGS10", "DTWEXBGS", "FEDFUNDS", "DCOILWTICO"]
        result = {}
        for sid in series_ids:
            try:
                df = self.duckdb.query(f"""
                    SELECT series_id, value, timestamp
                    FROM macro_data
                    WHERE series_id = '{sid}'
                    ORDER BY timestamp DESC
                    LIMIT 1
                """)
                if len(df) > 0:
                    result[sid] = {
                        "value": float(df.iloc[0]["value"]),
                        "date": str(df.iloc[0]["timestamp"]),
                    }
            except Exception as e:
                logger.warning("data_bridge.macro_failed series=%s error=%s", sid, str(e))
        return result

    # ── News Sentiment ───────────────────────────────────────────────

    def get_sentiment_summary(self, days: int = 1) -> dict:
        """Get aggregate news sentiment from DuckDB."""
        try:
            df = self.duckdb.get_sentiment_summary(days=days)
            if len(df) > 0:
                return {
                    "avg_sentiment": float(df["avg_sentiment"].mean()),
                    "avg_polarity": float(df["avg_polarity"].mean()),
                    "total_articles": int(df["articles"].sum()),
                    "queries": df["query"].tolist(),
                }
        except Exception as e:
            logger.warning("data_bridge.sentiment_failed error=%s", str(e))
        return {}

    # ── Fear & Greed ─────────────────────────────────────────────────

    def get_fear_greed(self) -> dict:
        """Get current Fear & Greed Index (live API call)."""
        try:
            from onchain_features import OnChainFeatureExtractor

            if self._onchain is None:
                self._onchain = OnChainFeatureExtractor()
            fgi = self._onchain._fetch_fear_greed()
            return fgi
        except Exception as e:
            logger.warning("data_bridge.fgi_failed error=%s", str(e))
            return {"value": 50, "label": "Neutral"}

    # ── Regime Computation ───────────────────────────────────────────

    def compute_regime_from_data(self) -> dict:
        """
        Compute macro regime from ALL pipeline data sources.
        Returns dict with: bias, confidence, position_multiplier, regime_label, source, reasoning.
        """
        from core.canonical.macro_regime import RegimeBias

        signals = []
        reasoning_parts = []

        # 1. Fear & Greed Index
        fgi = self.get_fear_greed()
        fgi_val = fgi.get("value", 50)
        if fgi_val <= 20:
            signals.append(("bullish_contrarian", 0.8, "Extreme Fear = contrarian buy"))
            reasoning_parts.append(f"FGI={fgi_val} (Extreme Fear)")
        elif fgi_val <= 35:
            signals.append(("bullish_mild", 0.6, "Fear = mild bullish"))
            reasoning_parts.append(f"FGI={fgi_val} (Fear)")
        elif fgi_val >= 80:
            signals.append(("bearish_contrarian", 0.8, "Extreme Greed = contrarian sell"))
            reasoning_parts.append(f"FGI={fgi_val} (Extreme Greed)")
        elif fgi_val >= 65:
            signals.append(("bearish_mild", 0.6, "Greed = mild bearish"))
            reasoning_parts.append(f"FGI={fgi_val} (Greed)")
        else:
            signals.append(("neutral", 0.3, "Neutral sentiment"))
            reasoning_parts.append(f"FGI={fgi_val} (Neutral)")

        # 2. VIX (from DuckDB macro data)
        macro = self.get_macro_latest(["VIXCLS", "DGS10", "DTWEXBGS"])
        vix = macro.get("VIXCLS", {}).get("value")
        if vix is not None:
            if vix >= 30:
                signals.append(("bearish_fear", 0.8, "VIX high = market fear"))
                reasoning_parts.append(f"VIX={vix:.1f} (High)")
            elif vix >= 20:
                signals.append(("bearish_mild", 0.5, "VIX elevated"))
                reasoning_parts.append(f"VIX={vix:.1f} (Elevated)")
            elif vix <= 12:
                signals.append(("bullish_calm", 0.5, "VIX very low = complacency"))
                reasoning_parts.append(f"VIX={vix:.1f} (Very Low)")
            else:
                signals.append(("neutral", 0.3, "VIX normal"))
                reasoning_parts.append(f"VIX={vix:.1f} (Normal)")

        # 3. News Sentiment
        sentiment = self.get_sentiment_summary(days=1)
        avg_sent = sentiment.get("avg_sentiment", 0)
        if avg_sent <= -0.15:
            signals.append(("bearish_news", 0.6, "Negative news sentiment"))
            reasoning_parts.append(f"News sentiment={avg_sent:.3f} (Negative)")
        elif avg_sent >= 0.15:
            signals.append(("bullish_news", 0.6, "Positive news sentiment"))
            reasoning_parts.append(f"News sentiment={avg_sent:.3f} (Positive)")
        else:
            signals.append(("neutral", 0.2, "Neutral news"))
            reasoning_parts.append(f"News sentiment={avg_sent:.3f} (Neutral)")

        # ── Aggregate ────────────────────────────────────────────────
        bull_score = sum(c for s, c, _ in signals if "bullish" in s)
        bear_score = sum(c for s, c, _ in signals if "bearish" in s)
        total = bull_score + bear_score

        if total == 0:
            bias = RegimeBias.NEUTRAL
            confidence = 0.3
        elif bear_score > bull_score * 1.5:
            bias = RegimeBias.BEARISH
            confidence = min(bear_score / (total + 1), 0.9)
        elif bull_score > bear_score * 1.5:
            bias = RegimeBias.BULLISH
            confidence = min(bull_score / (total + 1), 0.9)
        else:
            bias = RegimeBias.NEUTRAL
            confidence = 0.4

        # Regime label
        if vix and vix >= 35:
            regime_label = "CRISIS"
            pos_mult = 0.25
        elif vix and vix >= 25:
            regime_label = "HIGH_UNCERTAINTY"
            pos_mult = 0.5
        elif bear_score > bull_score * 2:
            regime_label = "HIGH_UNCERTAINTY"
            pos_mult = 0.6
        else:
            regime_label = "NORMAL"
            pos_mult = 1.0

        return {
            "bias": bias,
            "confidence": confidence,
            "position_multiplier": pos_mult,
            "regime_label": regime_label,
            "source": "data_bridge",
            "headline": f"Pipeline data: {', '.join(reasoning_parts[:3])}",
            "reasoning": "; ".join(reasoning_parts),
        }

    def update_macro_regime(self, force: bool = False):
        """
        Compute regime from pipeline data and write to MacroRegimeCache.

        Behavior:
        - If cache has recent LLM data (< 30 min, source != "default"), DON'T overwrite.
          LLM analysis of headlines is more accurate than raw data signals.
        - If cache is stale (default or > 30 min), write data-driven regime as fallback.
        - If force=True, always write (used by pipeline scheduler after data refresh).

        This ensures pipeline data fills gaps when LLM is unavailable, but doesn't
        override more nuanced LLM analysis.
        """

        from core.canonical.macro_regime import MacroRegime, MacroRegimeCache

        cache = MacroRegimeCache()
        current = cache.get()

        # Check if LLM has written recently
        if not force and current.source != "default":
            age = (datetime.now(UTC) - current.updated_at).total_seconds()
            if age < 1800:  # 30 minutes
                logger.info(
                    "data_bridge.cache_fresh source=%s age=%ds bias=%s regime=%s",
                    current.source,
                    int(age),
                    current.bias.value,
                    current.regime_label,
                )
                return current

        # Cache is stale or forced — write data-driven regime
        regime_data = self.compute_regime_from_data()

        regime = MacroRegime(
            bias=regime_data["bias"],
            confidence=regime_data["confidence"],
            position_multiplier=regime_data["position_multiplier"],
            regime_label=regime_data["regime_label"],
            source=regime_data["source"],
            headline=regime_data["headline"],
        )

        cache.update(regime)

        logger.info(
            "data_bridge.regime_updated bias=%s conf=%.2f regime=%s pos_mult=%.2f source=%s",
            regime.bias.value,
            regime.confidence,
            regime.regime_label,
            regime.position_multiplier,
            regime.source,
        )
        return regime

    def get_data_health(self) -> dict:
        """Check freshness of all pipeline data sources."""
        health = {}

        # Market data freshness
        try:
            df = self.duckdb.query("""
                SELECT source, MAX(timestamp) as latest, COUNT(*) as rows
                FROM market_data
                GROUP BY source
            """)
            health["market_data"] = df.to_dict("records") if len(df) > 0 else []
        except Exception:
            health["market_data"] = []

        # Macro data freshness
        try:
            df = self.duckdb.query("""
                SELECT series_id, MAX(timestamp) as latest, COUNT(*) as rows
                FROM macro_data
                GROUP BY series_id
            """)
            health["macro_data"] = df.to_dict("records") if len(df) > 0 else []
        except Exception:
            health["macro_data"] = []

        # News freshness
        try:
            df = self.duckdb.query("""
                SELECT COUNT(*) as total, MAX(fetched_at) as latest
                FROM news_sentiment
            """)
            health["news_sentiment"] = df.to_dict("records")[0] if len(df) > 0 else {}
        except Exception:
            health["news_sentiment"] = {}

        return health
