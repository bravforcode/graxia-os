"""
Cross-Sectional Momentum Strategy — Weekly rebalance of top altcoins.

Logic:
1. Every Monday, scan Binance for top 50 altcoins by 24h volume
2. Calculate 14-day returns for each
3. Select top 4 performers (momentum leaders)
4. Hold equal-weight positions for 7 days
5. Rebalance next Monday

Data source: ccxt_feeder.py (Binance async)
Output: EventBus signal.new events

Usage:
    python scripts/cross_sectional_momentum.py --dry-run
    python scripts/cross_sectional_momentum.py --live
"""

from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT.parent))


# ── Config ─────────────────────────────────────────────────────────


@dataclass
class MomentumConfig:
    """Strategy configuration."""
    top_n: int = 50  # scan top N altcoins by volume
    select_n: int = 4  # hold top N performers
    lookback_days: int = 14  # momentum lookback
    rebalance_interval_days: int = 7  # weekly rebalance
    min_volume_usdt: float = 1_000_000  # minimum 24h volume
    position_size_pct: float = 25.0  # % of portfolio per position (25% x 4 = 100%)


# ── Data Classes ───────────────────────────────────────────────────


@dataclass
class CoinMomentum:
    """Momentum data for a single coin."""
    symbol: str
    price_now: float
    price_lookback: float
    return_pct: float
    volume_24h: float


@dataclass
class RebalanceResult:
    """Result of a rebalance operation."""
    timestamp: str
    selected: list[dict[str, Any]]
    removed: list[dict[str, Any]]
    added: list[dict[str, Any]]
    portfolio_value: float


# ── Strategy ───────────────────────────────────────────────────────


class CrossSectionalMomentum:
    """
    Weekly momentum strategy for crypto altcoins.

    Uses ccxt_feeder for data, outputs signals to EventBus.
    """

    def __init__(self, config: MomentumConfig | None = None):
        self.config = config or MomentumConfig()
        self._positions: dict[str, dict[str, Any]] = {}  # symbol -> position info
        self._last_rebalance: datetime | None = None
        self._state_path = ROOT / "state" / "xsmomentum_state.json"
        self._load_state()

    def _load_state(self) -> None:
        """Load persistent state from disk."""
        if self._state_path.exists():
            with open(self._state_path) as f:
                state = json.load(f)
            self._positions = state.get("positions", {})
            last_reb = state.get("last_rebalance")
            if last_reb:
                self._last_rebalance = datetime.fromisoformat(last_reb)

    def _save_state(self) -> None:
        """Persist state to disk."""
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "positions": self._positions,
            "last_rebalance": self._last_rebalance.isoformat() if self._last_rebalance else None,
        }
        with open(self._state_path, "w") as f:
            json.dump(state, f, indent=2)

    async def scan_and_rank(self) -> list[CoinMomentum]:
        """
        Scan Binance for top altcoins and rank by 14-day momentum.

        Returns list of CoinMomentum sorted by return_pct (descending).
        """
        from ..market_data.ccxt_feeder import BinanceFeeder

        async with BinanceFeeder() as feeder:
            # 1. Scan top altcoins by volume
            top_coins = await feeder.scan_top_altcoins(
                min_volume_usdt=self.config.min_volume_usdt,
                limit=self.config.top_n,
            )
            logger.info("xsmomentum.scanned", count=len(top_coins))

            # 2. Fetch 14-day OHLCV for each coin (daily candles)
            results = []
            for coin in top_coins:
                symbol = coin["symbol"]
                try:
                    bars = await feeder.fetch_ohlcv(
                        symbol, "1d", limit=self.config.lookback_days + 1
                    )
                    if len(bars) < 2:
                        continue

                    price_now = bars[-1].close
                    price_lookback = bars[0].close
                    return_pct = (price_now - price_lookback) / price_lookback * 100

                    results.append(CoinMomentum(
                        symbol=symbol,
                        price_now=price_now,
                        price_lookback=price_lookback,
                        return_pct=return_pct,
                        volume_24h=coin["volume_24h_usdt"],
                    ))
                except Exception as exc:
                    logger.warning("xsmomentum.fetch_failed", symbol=symbol, error=str(exc))

            # 3. Sort by momentum (descending)
            results.sort(key=lambda x: x.return_pct, reverse=True)
            return results

    def select_top_n(self, ranked: list[CoinMomentum]) -> list[CoinMomentum]:
        """Select top N coins by momentum."""
        return ranked[:self.config.select_n]

    def calculate_rebalance(
        self, selected: list[CoinMomentum]
    ) -> RebalanceResult:
        """
        Calculate what positions to add/remove.

        Returns RebalanceResult with adds, removes, and current portfolio.
        """
        selected_symbols = {c.symbol for c in selected}
        current_symbols = set(self._positions.keys())

        # Coins to add (in selected but not in current)
        to_add = selected_symbols - current_symbols
        # Coins to remove (in current but not in selected)
        to_remove = current_symbols - selected_symbols

        added = []
        removed = []

        # Remove old positions
        for sym in to_remove:
            pos = self._positions.pop(sym)
            removed.append({"symbol": sym, **pos})
            logger.info("xsmomentum.removed", symbol=sym, return_pct=pos.get("return_pct"))

        # Add new positions
        for coin in selected:
            if coin.symbol in to_add:
                self._positions[coin.symbol] = {
                    "entry_price": coin.price_now,
                    "entry_time": datetime.now(UTC).isoformat(),
                    "return_pct": coin.return_pct,
                    "volume_24h": coin.volume_24h,
                }
                added.append({
                    "symbol": coin.symbol,
                    "entry_price": coin.price_now,
                    "return_pct": coin.return_pct,
                })
                logger.info("xsmomentum.added", symbol=coin.symbol, return_pct=coin.return_pct)

        self._last_rebalance = datetime.now(UTC)
        self._save_state()

        total_value = sum(
            pos.get("entry_price", 0) for pos in self._positions.values()
        )

        return RebalanceResult(
            timestamp=datetime.now(UTC).isoformat(),
            selected=[{"symbol": c.symbol, "return_pct": c.return_pct} for c in selected],
            removed=removed,
            added=added,
            portfolio_value=total_value,
        )

    def should_rebalance(self) -> bool:
        """Check if it's time to rebalance."""
        if self._last_rebalance is None:
            return True
        elapsed = datetime.now(UTC) - self._last_rebalance
        return elapsed.days >= self.config.rebalance_interval_days

    async def run(self, dry_run: bool = True) -> RebalanceResult | None:
        """
        Main strategy loop.

        If dry_run=True, only prints signals without sending to EventBus.
        """
        if not self.should_rebalance():
            logger.info("xsmomentum.skip_not_rebalance_day")
            return None

        logger.info("xsmomentum.rebalancing")

        # 1. Scan and rank
        ranked = await self.scan_and_rank()
        if not ranked:
            logger.warning("xsmomentum.no_coins_found")
            return None

        # 2. Select top N
        selected = self.select_top_n(ranked)
        logger.info(
            "xsmomentum.selected",
            coins=[f"{c.symbol}({c.return_pct:+.1f}%)" for c in selected],
        )

        # 3. Calculate rebalance
        result = self.calculate_rebalance(selected)

        # 4. Output signals
        if dry_run:
            print("\n=== Cross-Sectional Momentum Rebalance ===")
            print(f"Time: {result.timestamp}")
            print(f"Selected: {json.dumps(result.selected, indent=2)}")
            if result.added:
                print(f"Added: {json.dumps(result.added, indent=2)}")
            if result.removed:
                print(f"Removed: {json.dumps(result.removed, indent=2)}")
            print(f"Portfolio: {len(self._positions)} positions")
        else:
            # Send signals to EventBus (ponytail: connect to actual bus)
            for coin in selected:
                signal = {
                    "symbol": coin.symbol.replace("/", ""),
                    "signal_type": "BUY",
                    "confidence": min(0.9, 0.5 + coin.return_pct / 100),
                    "source": "cross_sectional_momentum",
                    "metadata": {
                        "return_pct": coin.return_pct,
                        "volume_24h": coin.volume_24h,
                        "rebalance_date": result.timestamp,
                    },
                }
                logger.info("xsmomentum.signal", **signal)

        return result


# ── Entry Point ────────────────────────────────────────────────────


async def main():
    import argparse
    parser = argparse.ArgumentParser(description="Cross-Sectional Momentum Strategy")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Run without sending signals (default)")
    parser.add_argument("--live", action="store_true",
                        help="Run with live signal output")
    args = parser.parse_args()

    strategy = CrossSectionalMomentum()
    await strategy.run(dry_run=not args.live)


if __name__ == "__main__":
    asyncio.run(main())
