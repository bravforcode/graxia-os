import asyncio
import uuid
import json
import logging
from typing import Any, Dict, List, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime
import redis.asyncio as redis
from core.config import settings

logger = logging.getLogger(__name__)

class AgentMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    sender: str
    receiver: Optional[str] = None
    topic: str
    content: Any
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    def to_json(self) -> str:
        return self.model_dump_json()

    @classmethod
    def from_json(cls, json_str: str) -> "AgentMessage":
        return cls.model_validate_json(json_str)

class AgentMessageBus:
    def __init__(self, redis_url: Optional[str] = None):
        self.redis_url = redis_url or settings.REDIS_URL
        self._redis: Optional[redis.Redis] = None
        self._local_subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._pubsub_tasks: Dict[str, asyncio.Task] = {}
        self._use_redis = False

    async def connect(self):
        if self.redis_url:
            try:
                self._redis = redis.from_url(self.redis_url, decode_responses=True)
                await self._redis.ping()
                self._use_redis = True
                logger.info(f"Connected to Redis at {self.redis_url}")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}. Falling back to local message bus.")
                self._use_redis = False

    async def publish(self, topic: str, message: AgentMessage):
        if self._use_redis and self._redis:
            try:
                await self._redis.publish(topic, message.to_json())
                await self._redis.publish("all", message.to_json())
                return
            except Exception as e:
                logger.error(f"Redis publish failed: {e}. Falling back to local.")
        
        # Local Fallback
        await self._local_publish(topic, message)
        await self._local_publish("all", message)

    async def _local_publish(self, topic: str, message: AgentMessage):
        if topic in self._local_subscribers:
            for queue in self._local_subscribers[topic]:
                await queue.put(message)

    async def subscribe(self, topic: str) -> asyncio.Queue:
        queue = asyncio.Queue()
        
        if topic not in self._local_subscribers:
            self._local_subscribers[topic] = []
        self._local_subscribers[topic].append(queue)

        if self._use_redis and self._redis and topic not in self._pubsub_tasks:
            # Start a background task to listen to Redis and put into local queues
            self._pubsub_tasks[topic] = asyncio.create_task(self._redis_listener(topic))
            
        return queue

    async def _redis_listener(self, topic: str):
        while True:
            try:
                pubsub = self._redis.pubsub()
                await pubsub.subscribe(topic)
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        data = message["data"]
                        agent_msg = AgentMessage.from_json(data)
                        await self._local_publish(topic, agent_msg)
            except asyncio.CancelledError:
                # Clean exit on task cancellation
                await pubsub.unsubscribe(topic)
                break
            except Exception as e:
                logger.error(f"Redis listener for topic {topic} failed: {e}. Retrying in 5 seconds...")
                try:
                    await pubsub.unsubscribe(topic)
                except:
                    pass
                await asyncio.sleep(5)

    async def unsubscribe(self, topic: str, queue: asyncio.Queue):
        if topic in self._local_subscribers and queue in self._local_subscribers[topic]:
            self._local_subscribers[topic].remove(queue)
            
        if not self._local_subscribers.get(topic) and topic in self._pubsub_tasks:
            self._pubsub_tasks[topic].cancel()
            del self._pubsub_tasks[topic]

# Global singleton instance for the process
message_bus = AgentMessageBus()
# Initialization should be called at startup: await message_bus.connect()
