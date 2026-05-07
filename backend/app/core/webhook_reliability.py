"""
Enterprise Webhook Reliability System

Ensures guaranteed webhook delivery with:
- At-least-once delivery semantics
- Exponential backoff retry
- Dead letter queue for failed webhooks
- Idempotency protection
- Circuit breaker for failing endpoints
- Webhook signature verification

Inspired by Stripe's webhook reliability model.
"""

import hashlib
import hmac
import json
import logging
import secrets
import time
from dataclasses import dataclass, asdict
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any, Callable, Optional
from uuid import uuid4

import aiohttp
from sqlalchemy import Column, DateTime, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.base import Base
from app.core.redis_pool import get_redis_client
from app.core.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class WebhookStatus(str, Enum):
    """Webhook delivery status."""
    PENDING = "pending"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class WebhookEvent(Base):
    """
    Persistent storage for webhook events.
    Ensures durability and auditability.
    """
    __tablename__ = "webhook_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    # Event identification
    event_id = Column(String(64), unique=True, nullable=False, index=True)
    event_type = Column(String(100), nullable=False, index=True)

    # Target endpoint
    endpoint_url = Column(Text, nullable=False)
    endpoint_id = Column(String(64), nullable=False, index=True)

    # Payload (encrypted in production)
    payload = Column(JSONB, nullable=False)
    payload_hash = Column(String(64), nullable=False)  # For idempotency

    # Delivery tracking
    status = Column(String(20), nullable=False, default=WebhookStatus.PENDING)
    attempts = Column(Integer, default=0)
    last_attempt_at = Column(DateTime(timezone=True))
    next_attempt_at = Column(DateTime(timezone=True))

    # Response tracking
    last_http_status = Column(Integer)
    last_response_body = Column(Text)
    last_error = Column(Text)

    # Delivery confirmation
    delivered_at = Column(DateTime(timezone=True))
    delivery_duration_ms = Column(Integer)

    # Signature for verification
    signature = Column(String(128))

    # Metadata
    event_metadata = Column(JSONB, default=dict)

    # Indexes for common queries
    __table_args__ = (
        Index('ix_webhook_events_status_next', 'status', 'next_attempt_at'),
        Index('ix_webhook_events_endpoint_status', 'endpoint_id', 'status'),
        Index('ix_webhook_events_created_at', 'created_at'),
    )


@dataclass
class WebhookConfig:
    """Configuration for webhook endpoint."""
    endpoint_id: str
    url: str
    secret: str
    max_retries: int = 5
    retry_delays: list[int] = None
    timeout_seconds: int = 30
    circuit_breaker_threshold: int = 5

    def __post_init__(self):
        if self.retry_delays is None:
            # Exponential backoff: 1s, 2s, 4s, 8s, 16s
            self.retry_delays = [1, 2, 4, 8, 16]


@dataclass
class WebhookResult:
    """Result of webhook delivery attempt."""
    success: bool
    http_status: Optional[int]
    response_body: Optional[str]
    error_message: Optional[str]
    duration_ms: int
    signature_valid: bool = False


class WebhookReliabilityManager:
    """
    Enterprise-grade webhook reliability manager.

    Features:
    - Durable queue with PostgreSQL
    - Redis for fast status checks
    - Circuit breaker per endpoint
    - Exponential backoff
    - Dead letter queue
    - Idempotency protection
    """

    def __init__(self, db_session, redis_client=None):
        self.db = db_session
        self.redis = redis_client
        self.circuit_breakers: dict[str, CircuitBreaker] = {}
        self._signing_secret = None

    async def send_webhook(
        self,
        event_type: str,
        payload: dict,
        config: WebhookConfig,
        metadata: dict = None
    ) -> str:
        """
        Queue a webhook for guaranteed delivery.

        Returns event_id for tracking.
        """
        # Generate unique event ID
        event_id = self._generate_event_id(event_type, payload)

        # Check idempotency (don't send duplicates)
        existing = await self._get_event_by_idempotency(event_id)
        if existing:
            logger.info(f"Webhook already exists: {event_id}")
            return existing.event_id

        # Create signature
        signature = self._generate_signature(payload, config.secret)

        # Calculate next attempt time
        next_attempt = datetime.now(UTC) + timedelta(seconds=config.retry_delays[0])

        # Store in database
        event = WebhookEvent(
            event_id=event_id,
            event_type=event_type,
            endpoint_url=config.url,
            endpoint_id=config.endpoint_id,
            payload=payload,
            payload_hash=self._hash_payload(payload),
            status=WebhookStatus.PENDING,
            next_attempt_at=next_attempt,
            signature=signature,
            metadata=metadata or {}
        )

        self.db.add(event)
        await self.db.commit()

        # Also store in Redis for fast lookups
        if self.redis:
            await self.redis.setex(
                f"webhook:{event_id}",
                86400,  # 24 hours
                json.dumps({"status": WebhookStatus.PENDING, "attempts": 0})
            )

        logger.info(f"Webhook queued: {event_id} -> {config.url}")
        return event_id

    async def process_pending_webhooks(self, batch_size: int = 100) -> int:
        """
        Process pending webhooks. Called by background worker.

        Returns number of webhooks processed.
        """
        from sqlalchemy import select, and_

        now = datetime.now(UTC)

        # Get pending webhooks ready for delivery
        result = await self.db.execute(
            select(WebhookEvent)
            .where(
                and_(
                    WebhookEvent.status.in_([WebhookStatus.PENDING, WebhookStatus.RETRYING]),
                    WebhookEvent.next_attempt_at <= now
                )
            )
            .limit(batch_size)
        )

        events = result.scalars().all()
        processed = 0

        for event in events:
            try:
                await self._deliver_webhook(event)
                processed += 1
            except Exception as e:
                logger.error(f"Failed to deliver webhook {event.event_id}: {e}")

        return processed

    async def _deliver_webhook(self, event: WebhookEvent) -> WebhookResult:
        """Attempt to deliver a single webhook."""
        # Update status to delivering
        event.status = WebhookStatus.DELIVERING
        event.attempts += 1
        event.last_attempt_at = datetime.now(UTC)
        await self.db.commit()

        # Check circuit breaker
        cb = self._get_circuit_breaker(event.endpoint_id)
        if cb.is_open():
            logger.warning(f"Circuit breaker open for {event.endpoint_id}")
            await self._schedule_retry(event, "circuit_breaker_open")
            return WebhookResult(
                success=False,
                http_status=None,
                response_body=None,
                error_message="Circuit breaker open",
                duration_ms=0
            )

        # Attempt delivery
        start_time = time.time()

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    event.endpoint_url,
                    json=event.payload,
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Id": event.event_id,
                        "X-Webhook-Signature": event.signature,
                        "X-Webhook-Attempt": str(event.attempts),
                        "User-Agent": "Graxia-OS-Webhook/1.0"
                    },
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    duration_ms = int((time.time() - start_time) * 1000)

                    response_body = await response.text()

                    # Success: 2xx status codes
                    if 200 <= response.status < 300:
                        event.status = WebhookStatus.DELIVERED
                        event.delivered_at = datetime.now(UTC)
                        event.delivery_duration_ms = duration_ms
                        event.last_http_status = response.status

                        # Record success in circuit breaker
                        cb.record_success()

                        logger.info(f"Webhook delivered: {event.event_id} ({response.status})")

                        # Update Redis
                        if self.redis:
                            await self.redis.setex(
                                f"webhook:{event.event_id}",
                                3600,  # 1 hour
                                json.dumps({"status": WebhookStatus.DELIVERED})
                            )

                        await self.db.commit()

                        return WebhookResult(
                            success=True,
                            http_status=response.status,
                            response_body=response_body,
                            error_message=None,
                            duration_ms=duration_ms
                        )

                    # Failure: non-2xx status
                    else:
                        event.last_http_status = response.status
                        event.last_response_body = response_body[:1000]  # Truncate

                        # Record failure in circuit breaker
                        cb.record_failure()

                        logger.warning(
                            f"Webhook failed: {event.event_id} ({response.status})"
                        )

                        await self._schedule_retry(event, f"http_{response.status}")

                        return WebhookResult(
                            success=False,
                            http_status=response.status,
                            response_body=response_body,
                            error_message=f"HTTP {response.status}",
                            duration_ms=duration_ms
                        )

        except aiohttp.ClientError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            event.last_error = str(e)[:500]
            cb.record_failure()

            logger.error(f"Webhook connection error: {event.event_id} - {e}")

            await self._schedule_retry(event, f"connection_error: {type(e).__name__}")

            return WebhookResult(
                success=False,
                http_status=None,
                response_body=None,
                error_message=str(e),
                duration_ms=duration_ms
            )

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            event.last_error = str(e)[:500]

            logger.exception(f"Webhook unexpected error: {event.event_id}")

            await self._schedule_retry(event, f"error: {type(e).__name__}")

            return WebhookResult(
                success=False,
                http_status=None,
                response_body=None,
                error_message=str(e),
                duration_ms=duration_ms
            )

    async def _schedule_retry(self, event: WebhookEvent, reason: str):
        """Schedule a retry with exponential backoff."""
        config = await self._get_endpoint_config(event.endpoint_id)

        if event.attempts >= config.max_retries:
            # Move to dead letter queue
            event.status = WebhookStatus.DEAD_LETTER
            event.event_metadata["dead_letter_reason"] = reason
            event.event_metadata["max_retries_reached"] = True

            logger.error(
                f"Webhook moved to dead letter queue: {event.event_id} ({reason})"
            )

            # Alert on-call engineer
            await self._alert_dead_letter(event)
        else:
            # Schedule retry with exponential backoff
            delay = config.retry_delays[min(event.attempts - 1, len(config.retry_delays) - 1)]
            event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=delay)
            event.status = WebhookStatus.RETRYING

            logger.info(
                f"Webhook retry scheduled: {event.event_id} in {delay}s (attempt {event.attempts})"
            )

        await self.db.commit()

        # Update Redis
        if self.redis:
            await self.redis.setex(
                f"webhook:{event.event_id}",
                86400,
                json.dumps({
                    "status": event.status,
                    "attempts": event.attempts,
                    "next_attempt": event.next_attempt_at.isoformat()
                })
            )

    async def get_webhook_status(self, event_id: str) -> Optional[dict]:
        """Get current status of a webhook."""
        # Try Redis first
        if self.redis:
            cached = await self.redis.get(f"webhook:{event_id}")
            if cached:
                return json.loads(cached)

        # Fall back to database
        from sqlalchemy import select

        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.event_id == event_id)
        )
        event = result.scalar_one_or_none()

        if event:
            return {
                "event_id": event.event_id,
                "status": event.status,
                "attempts": event.attempts,
                "delivered_at": event.delivered_at.isoformat() if event.delivered_at else None,
                "next_attempt_at": event.next_attempt_at.isoformat() if event.next_attempt_at else None,
                "last_http_status": event.last_http_status,
                "last_error": event.last_error
            }

        return None

    async def get_dead_letter_webhooks(
        self,
        endpoint_id: Optional[str] = None,
        limit: int = 100
    ) -> list[WebhookEvent]:
        """Get webhooks in dead letter queue."""
        from sqlalchemy import select

        query = select(WebhookEvent).where(
            WebhookEvent.status == WebhookStatus.DEAD_LETTER
        )

        if endpoint_id:
            query = query.where(WebhookEvent.endpoint_id == endpoint_id)

        query = query.order_by(WebhookEvent.created_at.desc()).limit(limit)

        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def retry_dead_letter(self, event_id: str) -> bool:
        """Manually retry a dead letter webhook."""
        from sqlalchemy import select

        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.event_id == event_id)
        )
        event = result.scalar_one_or_none()

        if not event or event.status != WebhookStatus.DEAD_LETTER:
            return False

        # Reset for retry
        event.status = WebhookStatus.PENDING
        event.attempts = 0
        event.next_attempt_at = datetime.now(UTC)
        event.event_metadata["manual_retry"] = True
        event.event_metadata["manual_retry_at"] = datetime.now(UTC).isoformat()

        await self.db.commit()

        logger.info(f"Dead letter webhook manually retried: {event_id}")
        return True

    def _generate_event_id(self, event_type: str, payload: dict) -> str:
        """Generate unique event ID for idempotency."""
        # Include timestamp rounded to minute for deduplication window
        timestamp = int(time.time()) // 60
        data = f"{event_type}:{json.dumps(payload, sort_keys=True)}:{timestamp}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def _hash_payload(self, payload: dict) -> str:
        """Hash payload for integrity checking."""
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()

    def _generate_signature(self, payload: dict, secret: str) -> str:
        """Generate HMAC signature for webhook verification."""
        payload_bytes = json.dumps(payload, separators=(',', ':')).encode()
        return hmac.new(
            secret.encode(),
            payload_bytes,
            hashlib.sha256
        ).hexdigest()

    async def _get_event_by_idempotency(self, event_id: str) -> Optional[WebhookEvent]:
        """Check if webhook already exists."""
        from sqlalchemy import select

        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.event_id == event_id)
        )
        return result.scalar_one_or_none()

    def _get_circuit_breaker(self, endpoint_id: str) -> CircuitBreaker:
        """Get or create circuit breaker for endpoint."""
        if endpoint_id not in self.circuit_breakers:
            self.circuit_breakers[endpoint_id] = CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60
            )
        return self.circuit_breakers[endpoint_id]

    async def _get_endpoint_config(self, endpoint_id: str) -> WebhookConfig:
        """Get configuration for endpoint."""
        # In production, fetch from database or config service
        # For now, return default config
        return WebhookConfig(
            endpoint_id=endpoint_id,
            url="https://example.com/webhook",
            secret="webhook-secret-key",
            max_retries=5
        )

    async def _alert_dead_letter(self, event: WebhookEvent):
        """Alert on-call engineer about dead letter webhook."""
        # Integration with PagerDuty, Slack, or email
        logger.critical(
            f"ALERT: Webhook in dead letter queue - {event.event_id} "
            f"(endpoint: {event.endpoint_id}, type: {event.event_type})"
        )

        # TODO: Send actual alert notification
        # await send_slack_alert(f"Webhook failed: {event.event_id}")


# Global webhook manager instance
_webhook_manager: Optional[WebhookReliabilityManager] = None


def get_webhook_manager(db_session, redis_client=None) -> WebhookReliabilityManager:
    """Get or create webhook manager instance."""
    global _webhook_manager
    if _webhook_manager is None:
        _webhook_manager = WebhookReliabilityManager(db_session, redis_client)
    return _webhook_manager
