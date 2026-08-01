"""
Order Book Features — Extract signals from order book depth.

Expected improvement: +10-20% signal quality.

ponytail: Simple depth-based features. Upgrade path: level-2 heatmap, queue imbalance.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class OrderBookFeatures:
    """Extracted order book features."""

    spread: float
    spread_pct: float
    ob_imbalance: float
    bid_support: float
    ask_resistance: float
    total_bid_liquidity: float
    total_ask_liquidity: float
    depth_ratio: float
    price_level_skew: float


class OrderBookFeatureExtractor:
    """Extract features from order book data.

    Features:
    - spread: Bid-ask spread in price units
    - spread_pct: Spread as percentage of mid price
    - ob_imbalance: Order book imbalance (-1 to +1)
    - bid_support: Max bid liquidity in top 5 levels
    - ask_resistance: Max ask liquidity in top 5 levels
    - depth_ratio: Bid depth / Ask depth
    - price_level_skew: Concentration difference bid vs ask

    Example:
        extractor = OrderBookFeatureExtractor(depth=20)
        features = extractor.extract(orderbook)
        feature_dict = extractor.to_dict(features)
    """

    def __init__(self, depth: int = 20):
        self.depth = depth

    def extract(self, orderbook: dict) -> OrderBookFeatures:
        """
        Extract features from order book.

        Args:
            orderbook: Dict with 'bids' and 'asks' lists of [price, quantity]

        Returns:
            OrderBookFeatures with all computed features
        """
        bids = orderbook.get("bids", [])[: self.depth]
        asks = orderbook.get("asks", [])[: self.depth]

        if not bids or not asks:
            return self._empty_features()

        # Spread
        best_bid = bids[0][0]
        best_ask = asks[0][0]
        spread = best_ask - best_bid
        mid_price = (best_bid + best_ask) / 2
        spread_pct = spread / mid_price if mid_price > 0 else 0

        # Liquidity
        bid_depth = sum(qty for _, qty in bids)
        ask_depth = sum(qty for _, qty in asks)
        total_liquidity = bid_depth + ask_depth

        # Imbalance: positive = more bids (bullish), negative = more asks (bearish)
        ob_imbalance = (bid_depth - ask_depth) / total_liquidity if total_liquidity > 0 else 0

        # Support/Resistance (max single level in top 5)
        bid_support = max(qty for _, qty in bids[:5]) if bids else 0
        ask_resistance = max(qty for _, qty in asks[:5]) if asks else 0

        # Depth ratio (cap at 10 to avoid infinity)
        depth_ratio = min(bid_depth / ask_depth, 10.0) if ask_depth > 0 else 10.0

        # Price level skew (concentration of liquidity)
        bid_concentration = bids[0][1] / bid_depth if bid_depth > 0 else 0
        ask_concentration = asks[0][1] / ask_depth if ask_depth > 0 else 0
        price_level_skew = bid_concentration - ask_concentration

        return OrderBookFeatures(
            spread=spread,
            spread_pct=spread_pct,
            ob_imbalance=ob_imbalance,
            bid_support=bid_support,
            ask_resistance=ask_resistance,
            total_bid_liquidity=bid_depth,
            total_ask_liquidity=ask_depth,
            depth_ratio=depth_ratio,
            price_level_skew=price_level_skew,
        )

    def _empty_features(self) -> OrderBookFeatures:
        return OrderBookFeatures(
            spread=0,
            spread_pct=0,
            ob_imbalance=0,
            bid_support=0,
            ask_resistance=0,
            total_bid_liquidity=0,
            total_ask_liquidity=0,
            depth_ratio=10.0,  # capped max, not 1.0 (which implies balance)
            price_level_skew=0,
        )

    def to_dict(self, features: OrderBookFeatures) -> dict[str, float]:
        """Convert to dict for ML pipeline.

        Args:
            features: OrderBookFeatures instance

        Returns:
            Dict with feature names as keys
        """
        return {
            "ob_spread": features.spread,
            "ob_spread_pct": features.spread_pct,
            "ob_imbalance": features.ob_imbalance,
            "ob_bid_support": features.bid_support,
            "ob_ask_resistance": features.ask_resistance,
            "ob_bid_liquidity": features.total_bid_liquidity,
            "ob_ask_liquidity": features.total_ask_liquidity,
            "ob_depth_ratio": features.depth_ratio,
            "ob_price_skew": features.price_level_skew,
        }
