import redis
import json
import os
import uuid
from typing import Any, Dict, Optional, Generator, Tuple

class EventBus:
    """Legacy Pub/Sub EventBus (maintained for backward compatibility)."""
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.r = redis.from_url(self.redis_url, decode_responses=True)

    def emit(self, topic: str, payload: Dict[str, Any]):
        """Emits an event to the Redis Pub/Sub bus."""
        event_data = json.dumps(payload)
        self.r.publish(topic, event_data)
        print(f"📡 [EventBus] Emitted {topic}")

    def subscribe(self, topic: str):
        """Creates a generator to listen for events on a specific topic."""
        pubsub = self.r.pubsub()
        pubsub.subscribe(topic)
        for message in pubsub.listen():
            if message['type'] == 'message':
                yield json.loads(message['data'])

class RedisEventBus:
    """Enterprise-grade EventBus using Redis Streams for durability."""
    def __init__(self):
        self.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
        self.r = redis.from_url(self.redis_url, decode_responses=True)

    def emit(self, topic: str, envelope: Dict[str, Any]):
        """Emits a BWCP envelope to a Redis Stream."""
        # Ensure envelope is a dict
        if hasattr(envelope, "dict"):
            envelope = envelope.dict()
            
        data = {"payload": json.dumps(envelope, default=str)}
        message_id = self.r.xadd(topic, data)
        print(f"📡 [RedisEventBus] Emitted to {topic} with ID {message_id}")
        return message_id

    def subscribe(self, topic: str, consumer_group: str, consumer_name: Optional[str] = None) -> Generator[Tuple[str, Dict[str, Any]], None, None]:
        """Subscribes to a Redis Stream using a consumer group."""
        if not consumer_name:
            consumer_name = f"consumer-{uuid.uuid4().hex[:8]}"
            
        # Create group if not exists
        try:
            self.r.xgroup_create(topic, consumer_group, id="0", mkstream=True)
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise e

        while True:
            # Read from group
            # Using ">" to read new messages
            messages = self.r.xreadgroup(consumer_group, consumer_name, {topic: ">"}, count=1, block=5000)
            if messages:
                for stream, msgs in messages:
                    for msg_id, data in msgs:
                        yield msg_id, json.loads(data["payload"])
                        # Note: Acknowledgment should be done by the caller if they want manual control,
                        # but for this simple implementation, we can do it here or provide an ack method.
                        # For now, let's auto-ack as per simple 'subscribe' requirement.
                        self.r.xack(topic, consumer_group, msg_id)
