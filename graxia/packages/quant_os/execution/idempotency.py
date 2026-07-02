"""Idempotency checker for duplicate order prevention"""

import hashlib
import logging
import time
from typing import Optional, Dict, Any
from decimal import Decimal

import redis
from sqlalchemy.orm import Session

from ..core.config import get_config
from ..core.exceptions import DuplicateOrderError
from ..data.models import Order as OrderModel

logger = logging.getLogger(__name__)


class IdempotencyChecker:
    """
    Prevents duplicate orders using idempotency keys.

    Strategy: symbol + side + quantity + timestamp_bucket (1 minute)
    """

    def __init__(self, redis_client: Optional[redis.Redis] = None, db_session: Optional[Session] = None):
        self.redis = redis_client
        self.db = db_session
        self.config = get_config()

        # Initialize Redis if not provided
        if self.redis is None:
            try:
                self.redis = redis.from_url(self.config.redis_url, decode_responses=True)
            except Exception:
                self.redis = None

    def generate_key(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        strategy_id: str,
        signal_id: Optional[str] = None,
        timestamp_bucket_seconds: int = 60
    ) -> str:
        """
        Generate idempotency key.

        Key includes:
        - symbol
        - side (BUY/SELL)
        - quantity (rounded to 4 decimals)
        - strategy_id
        - timestamp bucket (to prevent duplicates within time window)
        """
        # Round quantity to prevent floating point issues
        qty_rounded = round(float(quantity), 4)

        # Time bucket - orders within same bucket are considered duplicates
        time_bucket = int(time.time()) // timestamp_bucket_seconds

        # Build key components
        components = [
            symbol.upper(),
            side.upper(),
            str(qty_rounded),
            strategy_id,
            str(signal_id) if signal_id else "",
            str(time_bucket)
        ]

        key_string = ":".join(components)

        # Hash to fixed length
        return hashlib.sha256(key_string.encode()).hexdigest()

    def is_duplicate(
        self,
        idempotency_key: str,
        check_db: bool = True,
        check_redis: bool = True
    ) -> bool:
        """
        Check if this is a duplicate order.

        Checks both Redis (fast) and database (authoritative).
        """
        # Check Redis first (fast cache)
        if check_redis and self.redis:
            try:
                if self.redis.exists(f"idempotency:{idempotency_key}"):
                    return True
            except Exception:
                logger.warning("idempotency.redis_check_failed", exc_info=True)

        # Check database (authoritative)
        if check_db and self.db:
            existing = self.db.query(OrderModel).filter(
                OrderModel.idempotency_key == idempotency_key
            ).first()
            if existing:
                return True

        return False

    def record_key(
        self,
        idempotency_key: str,
        order_id: str,
        ttl_seconds: int = 3600
    ) -> None:
        """
        Record idempotency key to prevent future duplicates.

        Args:
            idempotency_key: The key to store
            order_id: Associated order ID
            ttl_seconds: How long to keep in Redis (default 1 hour)
        """
        if self.redis:
            try:
                self.redis.setex(
                    f"idempotency:{idempotency_key}",
                    time=ttl_seconds,
                    value=order_id
                )
            except Exception:
                logger.warning("idempotency.redis_record_failed order_id=%s", order_id, exc_info=True)

    def check_and_record(
        self,
        idempotency_key: str,
        order_id: str,
        raise_on_duplicate: bool = True
    ) -> bool:
        """
        Check for duplicate and record key atomically.

        Returns True if key was newly recorded (not duplicate).
        Raises DuplicateOrderError if duplicate and raise_on_duplicate is True.
        """
        is_dup = self.is_duplicate(idempotency_key)

        if is_dup:
            if raise_on_duplicate:
                raise DuplicateOrderError(
                    f"Duplicate order detected with key: {idempotency_key[:16]}...",
                    idempotency_key=idempotency_key
                )
            return False

        self.record_key(idempotency_key, order_id)
        return True

    def get_order_by_key(self, idempotency_key: str) -> Optional[Dict[str, Any]]:
        """Get order details by idempotency key"""
        # Check Redis first
        if self.redis:
            try:
                order_id = self.redis.get(f"idempotency:{idempotency_key}")
                if order_id:
                    return {"order_id": order_id, "source": "redis"}
            except Exception:
                logger.warning("idempotency.redis_get_failed", exc_info=True)

        # Check database
        if self.db:
            order = self.db.query(OrderModel).filter(
                OrderModel.idempotency_key == idempotency_key
            ).first()
            if order:
                return {
                    "order_id": str(order.id),
                    "status": order.status.value,
                    "symbol": order.symbol,
                    "source": "database"
                }

        return None

    def clear_key(self, idempotency_key: str) -> None:
        """Clear idempotency key (for testing or manual cleanup)"""
        if self.redis:
            try:
                self.redis.delete(f"idempotency:{idempotency_key}")
            except Exception:
                logger.warning("idempotency.redis_delete_failed", exc_info=True)

    def get_stats(self) -> Dict[str, Any]:
        """Get idempotency checker statistics"""
        stats = {
            "redis_connected": self.redis is not None,
            "db_connected": self.db is not None,
        }

        if self.redis:
            try:
                # Count keys matching pattern (SCAN instead of KEYS for production safety)
                count = 0
                for _ in self.redis.scan_iter("idempotency:*", count=100):
                    count += 1
                stats["cached_keys_count"] = count
            except Exception as e:
                stats["redis_error"] = str(e)

        return stats


class WindowedIdempotencyChecker(IdempotencyChecker):
    """
    Extended checker with configurable time windows per strategy.
    """

    DEFAULT_WINDOW_SECONDS = 60
    STRATEGY_WINDOWS = {
        "mtm": 60,      # 1 minute for momentum
        "mrb": 120,     # 2 minutes for mean reversion
        "mlb": 60,      # 1 minute for ML breakout
    }

    def get_window(self, strategy_id: str) -> int:
        """Get idempotency window for strategy"""
        return self.STRATEGY_WINDOWS.get(strategy_id, self.DEFAULT_WINDOW_SECONDS)

    def generate_key(
        self,
        symbol: str,
        side: str,
        quantity: Decimal,
        strategy_id: str,
        signal_id: Optional[str] = None,
        timestamp_bucket_seconds: Optional[int] = None
    ) -> str:
        """Generate key with strategy-specific window"""
        window = timestamp_bucket_seconds or self.get_window(strategy_id)
        return super().generate_key(symbol, side, quantity, strategy_id, signal_id, window)
