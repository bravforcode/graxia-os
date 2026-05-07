"""
Revenue OS Redis Streams Client
Consumer and producer for agent choreography via Redis Streams
"""
from typing import Optional, Callable, Dict, Any, List, Coroutine
from datetime import datetime
import json
import structlog
import asyncio

logger = structlog.get_logger()

# Stream configuration
REVENUE_OS_STREAM = "revenue_os:events"
CONSUMER_GROUP = "revenue_os:agents"


class RedisStreamClient:
    """
    Redis Streams client for Revenue OS event-driven architecture.

    Used by:
    - Celery process_outbox task (producer)
    - Agent consumers (Visionary, Sales, ChiefOfStaff)
    """

    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or "redis://localhost:6379"
        self._redis = None
        self._connected = False

    async def connect(self):
        """Connect to Redis."""
        try:
            import aioredis
            self._redis = await aioredis.from_url(
                self.redis_url,
                decode_responses=True
            )
            self._connected = True
            logger.info("redis_connected", url=self.redis_url)
        except ImportError:
            logger.error("aioredis not installed")
            raise
        except Exception as e:
            logger.error("redis_connection_failed", error=str(e))
            raise

    async def disconnect(self):
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()
            self._connected = False
            logger.info("redis_disconnected")

    async def publish_event(
        self,
        event_type: str,
        aggregate_type: str,
        aggregate_id: str,
        payload: Dict[str, Any],
        headers: Optional[Dict] = None,
        correlation_id: Optional[str] = None,
        causation_id: Optional[str] = None,
    ) -> str:
        """
        Publish event to Redis Stream.

        Args:
            event_type: Type of event (order_created, lead_identified, etc.)
            aggregate_type: Type of aggregate (order, lead, campaign)
            aggregate_id: Aggregate UUID
            payload: Event payload data
            headers: Optional message headers
            correlation_id: For distributed tracing
            causation_id: For event sourcing

        Returns:
            str: Message ID from Redis
        """
        if not self._connected:
            await self.connect()

        message = {
            "event_type": event_type,
            "aggregate_type": aggregate_type,
            "aggregate_id": aggregate_id,
            "payload": json.dumps(payload),
            "headers": json.dumps(headers or {}),
            "correlation_id": correlation_id or "",
            "causation_id": causation_id or "",
            "timestamp": datetime.utcnow().isoformat(),
        }

        message_id = await self._redis.xadd(REVENUE_OS_STREAM, message)

        logger.debug(
            "event_published_to_stream",
            stream=REVENUE_OS_STREAM,
            event_type=event_type,
            aggregate_id=aggregate_id,
            message_id=message_id,
        )

        return message_id

    async def create_consumer_group(self) -> bool:
        """
        Create consumer group if it doesn't exist.

        Returns:
            bool: True if created or already exists
        """
        if not self._connected:
            await self.connect()

        try:
            await self._redis.xgroup_create(
                REVENUE_OS_STREAM,
                CONSUMER_GROUP,
                id="0",  # Start from beginning
                mkstream=True
            )
            logger.info("consumer_group_created", group=CONSUMER_GROUP)
            return True
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug("consumer_group_already_exists", group=CONSUMER_GROUP)
                return True
            logger.error("consumer_group_creation_failed", error=str(e))
            return False

    async def consume_events(
        self,
        consumer_name: str,
        handler: Callable[[Dict[str, Any]], Coroutine],
        block_ms: int = 5000,
        count: int = 10,
    ) -> int:
        """
        Consume events from stream as part of consumer group.

        Args:
            consumer_name: Unique name for this consumer instance
            handler: Async callable to process each event
            block_ms: Block for this many milliseconds waiting for events
            count: Maximum events to fetch per call

        Returns:
            int: Number of events processed
        """
        if not self._connected:
            await self.connect()

        # Ensure consumer group exists
        await self.create_consumer_group()

        try:
            # Read events from stream
            messages = await self._redis.xreadgroup(
                groupname=CONSUMER_GROUP,
                consumername=consumer_name,
                streams={REVENUE_OS_STREAM: ">"},  # Only undelivered messages
                count=count,
                block=block_ms,
            )

            processed = 0

            if not messages:
                return 0

            for stream_name, stream_messages in messages:
                for message_id, fields in stream_messages:
                    try:
                        # Parse message
                        event = self._parse_message(message_id, fields)

                        # Process with handler
                        await handler(event)
                        processed += 1

                        # Acknowledge message
                        await self._redis.xack(
                            REVENUE_OS_STREAM,
                            CONSUMER_GROUP,
                            message_id
                        )

                    except Exception as e:
                        logger.error(
                            "event_processing_failed",
                            message_id=message_id,
                            error=str(e),
                            event_type=fields.get("event_type", "unknown"),
                        )
                        # Don't acknowledge - message will be redelivered

            return processed

        except Exception as e:
            logger.error("consume_events_failed", error=str(e))
            return 0

    async def claim_pending_messages(
        self,
        consumer_name: str,
        min_idle_ms: int = 60000,  # 1 minute
        count: int = 10,
    ) -> List[Dict[str, Any]]:
        """
        Claim pending messages from dead consumers.

        Args:
            consumer_name: Consumer claiming the messages
            min_idle_ms: Minimum idle time before claiming
            count: Maximum messages to claim

        Returns:
            List of claimed messages
        """
        if not self._connected:
            await self.connect()

        try:
            # Get pending messages
            pending = await self._redis.xpending(
                REVENUE_OS_STREAM,
                CONSUMER_GROUP,
                start="-",
                end="+",
                count=count,
            )

            claimed = []

            for item in pending:
                message_id, consumer, idle_time, delivery_count = item

                if idle_time > min_idle_ms:
                    # Claim this message
                    claimed_result = await self._redis.xclaim(
                        REVENUE_OS_STREAM,
                        CONSUMER_GROUP,
                        consumer_name,
                        min_idle_time=min_idle_ms,
                        message_ids=[message_id],
                    )

                    for msg_id, fields in claimed_result:
                        event = self._parse_message(msg_id, fields)
                        claimed.append(event)

            if claimed:
                logger.info(
                    "claimed_pending_messages",
                    count=len(claimed),
                    consumer=consumer_name,
                )

            return claimed

        except Exception as e:
            logger.error("claim_pending_failed", error=str(e))
            return []

    def _parse_message(
        self,
        message_id: str,
        fields: Dict[str, str]
    ) -> Dict[str, Any]:
        """Parse Redis stream message into event dict."""
        return {
            "id": message_id,
            "event_type": fields.get("event_type", ""),
            "aggregate_type": fields.get("aggregate_type", ""),
            "aggregate_id": fields.get("aggregate_id", ""),
            "payload": json.loads(fields.get("payload", "{}")),
            "headers": json.loads(fields.get("headers", "{}")),
            "correlation_id": fields.get("correlation_id", ""),
            "causation_id": fields.get("causation_id", ""),
            "timestamp": fields.get("timestamp", ""),
        }

    async def get_stream_info(self) -> Dict[str, Any]:
        """Get stream statistics."""
        if not self._connected:
            await self.connect()

        try:
            info = await self._redis.xinfo_stream(REVENUE_OS_STREAM)
            groups = await self._redis.xinfo_groups(REVENUE_OS_STREAM)

            return {
                "length": info.get("length", 0),
                "radix_tree_keys": info.get("radix-tree-keys", 0),
                "radix_tree_nodes": info.get("radix-tree-nodes", 0),
                "groups": len(groups),
                "last_generated_id": info.get("last-generated-id", ""),
                "first_entry": info.get("first-entry", None),
                "last_entry": info.get("last-entry", None),
            }
        except Exception as e:
            logger.error("stream_info_failed", error=str(e))
            return {}

    async def get_pending_summary(self) -> Dict[str, Any]:
        """Get summary of pending messages."""
        if not self._connected:
            await self.connect()

        try:
            summary = await self._redis.xpending(
                REVENUE_OS_STREAM,
                CONSUMER_GROUP,
            )

            return {
                "pending_count": summary.get("pending", 0),
                "min_id": summary.get("min", ""),
                "max_id": summary.get("max", ""),
                "consumers": summary.get("consumers", []),
            }
        except Exception as e:
            logger.error("pending_summary_failed", error=str(e))
            return {}


# Singleton instance
_redis_client: Optional[RedisStreamClient] = None


def get_redis_client(redis_url: str = None) -> RedisStreamClient:
    """Get or create Redis stream client singleton."""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisStreamClient(redis_url)
    return _redis_client
