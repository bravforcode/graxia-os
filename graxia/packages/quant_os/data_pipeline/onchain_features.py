"""
On-Chain + Social Data Features — Crypto-specific signals.

ALL FREE sources (no API key required):
- alternative.me: Fear & Greed Index
- Binance Public: Funding rates, Open Interest, Premium index
- Reddit: Community sentiment (OAuth required, free tier unlimited)

Optional (API key in .env):
- Santiment: Social volume (free tier: 1yr lookback)

Expected improvement: +15-25% alpha for crypto signals.
"""

from __future__ import annotations

import os
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

ONCHAIN_CACHE_DIR = Path(__file__).parent.parent / "data" / "onchain"


@dataclass
class OnChainFeatures:
    """On-chain + social analysis features."""

    # On-chain (from Binance public API)
    funding_rate: float           # Perpetual funding rate (positive = longs pay shorts)
    open_interest: float          # Total open interest in BTC
    open_interest_change_pct: float  # OI change % (rising = new positions)
    basis_spread: float           # Futures premium (mark - index)

    # Sentiment
    fear_greed_index: float       # 0-100
    fear_greed_label: str         # Extreme Fear/Fear/Neutral/Greed/Extreme Greed
    social_volume_change: float   # From Santiment (if configured)
    reddit_sentiment: float       # -1.0 to +1.0 (if configured)
    reddit_volume: int            # Posts in last 24h


class OnChainFeatureExtractor:
    """Extract features from free on-chain + social data sources.

    ALL sources are FREE (no API key needed):
        - alternative.me Fear & Greed Index
        - Binance Public API (funding, OI, premium)
        - Reddit OAuth (free tier: unlimited reads)

    Optional (API key in .env):
        - Santiment (SANTIMENT_API_KEY)

    Example:
        extractor = OnChainFeatureExtractor()
        features = extractor.extract('BTC')
    """

    def __init__(self):
        ONCHAIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def extract(self, symbol: str = "BTC") -> OnChainFeatures:
        """Extract features from all available free sources."""
        # 1. Fear & Greed (free, no key)
        fgi = self._fetch_fear_greed()

        # 2. Binance public (free, no key) — funding, OI, premium
        binance = self._fetch_binance_metrics(symbol)

        # 3. Santiment (if key available)
        santiment = self._fetch_santiment(symbol) if os.getenv("SANTIMENT_API_KEY") else {}

        # 4. Reddit (if credentials available)
        reddit = self._fetch_reddit_sentiment(symbol) if os.getenv("REDDIT_CLIENT_ID") else {}

        return OnChainFeatures(
            funding_rate=binance.get("funding_rate", 0.0),
            open_interest=binance.get("open_interest", 0.0),
            open_interest_change_pct=binance.get("oi_change_pct", 0.0),
            basis_spread=binance.get("basis_spread", 0.0),
            fear_greed_index=fgi.get("value", 50.0),
            fear_greed_label=fgi.get("label", "Neutral"),
            social_volume_change=santiment.get("social_volume_change", 0.0),
            reddit_sentiment=reddit.get("sentiment", 0.0),
            reddit_volume=reddit.get("volume", 0),
        )

    # ── Fear & Greed Index (FREE) ──────────────────────────────────

    def _fetch_fear_greed(self) -> dict:
        """Fetch Crypto Fear & Greed Index from alternative.me."""
        cache_path = ONCHAIN_CACHE_DIR / "fear_greed.json"

        # Cache for 6 hours
        if cache_path.exists():
            try:
                cached = json.loads(cache_path.read_text())
                ts = datetime.fromisoformat(cached.get("timestamp", "2000-01-01"))
                if (datetime.now() - ts).total_seconds() < 21600:  # 6h
                    return {"value": cached["value"], "label": cached["label"]}
            except Exception:
                pass

        try:
            resp = httpx.get("https://api.alternative.me/fng/?limit=1", timeout=10)
            resp.raise_for_status()
            entry = resp.json().get("data", [{}])[0]
            value = float(entry.get("value", 50))
            label = entry.get("value_classification", "Neutral")

            ONCHAIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({
                "value": value, "label": label,
                "timestamp": datetime.now().isoformat(),
            }, indent=2))

            logger.info("fear_greed_fetched", value=value, label=label)
            return {"value": value, "label": label}
        except Exception as e:
            logger.warning("fear_greed_fetch_failed", error=str(e))
            return {"value": 50.0, "label": "Neutral"}

    # ── Binance Public API (FREE — no key needed) ───────────────────

    def _fetch_binance_metrics(self, symbol: str) -> dict:
        """Fetch funding rate, open interest, and basis from Binance public API.

        All endpoints are FREE with no API key required.
        Covers: BTC, ETH, and other major perpetual pairs.
        """
        # Map symbol to Binance perpetual pair
        pair_map = {
            "BTC": "BTCUSDT", "ETH": "ETHUSDT",
            "BNB": "BNBUSDT", "SOL": "SOLUSDT",
            "XRP": "XRPUSDT", "ADA": "ADAUSDT",
        }
        pair = pair_map.get(symbol.upper(), f"{symbol.upper()}USDT")
        metrics = {}

        # 1. Funding Rate (last 3 entries for trend)
        try:
            resp = httpx.get(
                "https://fapi.binance.com/fapi/v1/fundingRate",
                params={"symbol": pair, "limit": 3},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                if data:
                    metrics["funding_rate"] = float(data[-1].get("fundingRate", 0))
        except Exception as e:
            logger.warning("binance_funding_failed", pair=pair, error=str(e))

        # 2. Open Interest
        try:
            resp = httpx.get(
                "https://fapi.binance.com/fapi/v1/openInterest",
                params={"symbol": pair},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                metrics["open_interest"] = float(data.get("openInterest", 0))
        except Exception as e:
            logger.warning("binance_oi_failed", pair=pair, error=str(e))

        # 3. Premium Index (mark price, index price, funding rate)
        try:
            resp = httpx.get(
                "https://fapi.binance.com/fapi/v1/premiumIndex",
                params={"symbol": pair},
                timeout=10,
            )
            if resp.status_code == 200:
                data = resp.json()
                mark = float(data.get("markPrice", 0))
                index = float(data.get("indexPrice", 0))
                if index > 0:
                    metrics["basis_spread"] = (mark - index) / index  # Futures premium %
                # Update funding rate from premium index (more accurate)
                if "funding_rate" not in metrics:
                    metrics["funding_rate"] = float(data.get("lastFundingRate", 0))
        except Exception as e:
            logger.warning("binance_premium_failed", pair=pair, error=str(e))

        # 4. OI change (compare with cache)
        cache_path = ONCHAIN_CACHE_DIR / f"binance_oi_{pair}.json"
        current_oi = metrics.get("open_interest", 0)
        if current_oi > 0:
            prev_oi = 0
            if cache_path.exists():
                try:
                    cached = json.loads(cache_path.read_text())
                    prev_oi = cached.get("open_interest", 0)
                except Exception:
                    pass
            if prev_oi > 0:
                metrics["oi_change_pct"] = (current_oi - prev_oi) / prev_oi
            # Save cache
            ONCHAIN_CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps({
                "open_interest": current_oi,
                "timestamp": datetime.now().isoformat(),
            }, indent=2))

        return metrics

    # ── Santiment (optional, free tier) ─────────────────────────────

    def _fetch_santiment(self, symbol: str) -> dict:
        """Fetch social volume from Santiment (requires SANTIMENT_API_KEY).

        Free tier: 1-year lookback, social_volume_total metric.
        """
        import datetime as dt

        api_key = os.getenv("SANTIMENT_API_KEY", "")
        if not api_key:
            return {}

        slug_map = {"BTC": "bitcoin", "ETH": "ethereum"}
        slug = slug_map.get(symbol.upper(), symbol.lower())

        now = dt.datetime.now(dt.timezone.utc)
        from_date = (now - dt.timedelta(days=7)).isoformat()
        to_date = now.isoformat()

        try:
            resp = httpx.post(
                "https://api.santiment.net/graphql",
                headers={"Authorization": f"Apikey {api_key}"},
                json={
                    "query": """{
                        getMetric(metric: "social_volume_total") {
                            timeseriesData(
                                from: "%s"
                                to: "%s"
                                interval: "1d"
                                slug: "%s"
                            ) {
                                datetime
                                value
                            }
                        }
                    }""" % (from_date, to_date, slug),
                },
                timeout=15,
            )
            if resp.status_code == 200:
                data = resp.json().get("data", {}).get("getMetric", {}).get("timeseriesData", [])
                if data and len(data) > 1:
                    latest = data[-1].get("value", 0)
                    prev = data[-2].get("value", 0)
                    return {"social_volume_change": float((latest - prev) / prev) if prev else 0.0}
        except Exception as e:
            logger.warning("santiment_social_failed", error=str(e))

        return {}

    # ── Reddit Sentiment (free, OAuth required) ─────────────────────

    def _fetch_reddit_sentiment(self, symbol: str) -> dict:
        """Fetch Reddit sentiment using OAuth (requires REDDIT_CLIENT_ID + SECRET).

        Free tier: unlimited reads, 60 requests/minute.
        Setup: https://www.reddit.com/prefs/apps → create "script" app
        """
        from textblob import TextBlob

        client_id = os.getenv("REDDIT_CLIENT_ID", "")
        client_secret = os.getenv("REDDIT_CLIENT_SECRET", "")
        if not client_id or not client_secret:
            return {}

        subreddit_map = {
            "BTC": ["bitcoin", "cryptocurrency", "wallstreetbets"],
            "ETH": ["ethereum", "cryptocurrency", "wallstreetbets"],
            "XAUUSD": ["gold", "wallstreetbets", "forex"],
            "EURUSD": ["forex", "wallstreetbets"],
        }
        subreddits = subreddit_map.get(symbol.upper(), ["wallstreetbets", "cryptocurrency"])

        # Get OAuth token
        try:
            auth_resp = httpx.post(
                "https://www.reddit.com/api/v1/access_token",
                auth=(client_id, client_secret),
                data={"grant_type": "client_credentials"},
                headers={"User-Agent": "quant_os/1.0"},
                timeout=10,
            )
            if auth_resp.status_code != 200:
                return {}
            token = auth_resp.json().get("access_token", "")
        except Exception:
            return {}

        headers = {"Authorization": f"Bearer {token}", "User-Agent": "quant_os/1.0"}
        all_scores = []
        total_posts = 0

        for sub in subreddits:
            try:
                resp = httpx.get(
                    f"https://oauth.reddit.com/r/{sub}/search",
                    params={"q": symbol, "restrict_sr": "true", "sort": "new", "t": "day", "limit": 25},
                    headers=headers,
                    timeout=10,
                )
                if resp.status_code == 200:
                    posts = resp.json().get("data", {}).get("children", [])
                    total_posts += len(posts)
                    for post in posts:
                        title = post.get("data", {}).get("title", "")
                        body = post.get("data", {}).get("selftext", "")
                        text = f"{title} {body}".strip()
                        if text:
                            all_scores.append(TextBlob(text).sentiment.polarity)
            except Exception as e:
                logger.warning("reddit_fetch_failed", subreddit=sub, error=str(e))

        avg = sum(all_scores) / len(all_scores) if all_scores else 0.0
        return {"sentiment": avg, "volume": total_posts}

    # ── Derived Features ────────────────────────────────────────────

    def compute_derived_features(self, ohlcv: dict, onchain: OnChainFeatures) -> dict[str, float]:
        """Compute derived features combining price and on-chain data."""
        import numpy as np

        close = np.array(ohlcv.get("close", []))
        features = {}

        # Price momentum vs OI change
        if len(close) >= 20:
            price_momentum = (close[-1] / close[-20] - 1) if close[-20] > 0 else 0
            features["price_oi_momentum"] = price_momentum * onchain.open_interest_change_pct

        # Fear/greed contrarian signal
        if onchain.fear_greed_index < 25:
            features["fear_greed_contrarian"] = 1.0   # Extreme Fear = buy signal
        elif onchain.fear_greed_index > 75:
            features["fear_greed_contrarian"] = -1.0  # Extreme Greed = sell signal
        else:
            features["fear_greed_contrarian"] = 0.0

        # Funding rate signal (positive = overleveraged longs)
        if onchain.funding_rate > 0.001:
            features["funding_bearish"] = -1.0  # Overleveraged longs
        elif onchain.funding_rate < -0.001:
            features["funding_bullish"] = 1.0   # Overleveraged shorts
        else:
            features["funding_neutral"] = 0.0

        # Basis spread (futures premium = bullish sentiment)
        features["basis_signal"] = min(max(onchain.basis_spread * 100, -1.0), 1.0)

        # OI divergence (price up + OI up = trend continuation, price up + OI down = squeeze)
        if len(close) >= 5:
            price_up = close[-1] > close[-5]
            oi_up = onchain.open_interest_change_pct > 0
            if price_up and oi_up:
                features["trend_continuation"] = 1.0
            elif price_up and not oi_up:
                features["short_squeeze"] = 1.0
            elif not price_up and oi_up:
                features["new_shorts"] = -1.0
            else:
                features["capitulation"] = -0.5

        # Reddit contrarian signal
        if onchain.reddit_sentiment > 0.5:
            features["reddit_contrarian"] = -0.5  # Overly bullish = potential top
        elif onchain.reddit_sentiment < -0.5:
            features["reddit_contrarian"] = 0.5   # Overly bearish = potential bottom
        else:
            features["reddit_contrarian"] = 0.0

        # Reddit volume spike (high attention = potential volatility)
        features["reddit_volume_spike"] = 1.0 if onchain.reddit_volume > 50 else 0.0

        return features
