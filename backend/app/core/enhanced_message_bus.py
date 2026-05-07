"""
Enhanced Agent Message Bus
ระบบสื่อสารระหว่าง Agents ขั้นสูง
รองรับ: publish/subscribe, request/response, negotiation, และ swarm coordination
"""

import asyncio
import json
import logging
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)


class MessagePriority(Enum):
    LOW = 1
    NORMAL = 5
    HIGH = 10
    CRITICAL = 20


class MessageType(Enum):
    BROADCAST = "broadcast"
    DIRECT = "direct"
    REQUEST = "request"
    RESPONSE = "response"
    NEGOTIATION = "negotiation"
    SWARM_COORDINATION = "swarm_coordination"
    EVENT = "event"
    TASK_ASSIGNMENT = "task_assignment"


@dataclass
class AgentMessage:
    """ข้อความที่ส่งระหว่าง Agents"""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    sender: str = ""
    receiver: str | None = None  # None = broadcast
    topic: str = ""
    message_type: MessageType = MessageType.BROADCAST
    content: Any = field(default_factory=dict)
    priority: MessagePriority = MessagePriority.NORMAL
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    ttl: int | None = None  # วินาทีก่อนหมดอายุ

    def to_json(self) -> str:
        data = asdict(self)
        data["message_type"] = self.message_type.value
        data["priority"] = self.priority.value
        return json.dumps(data)

    @classmethod
    def from_json(cls, json_str: str) -> "AgentMessage":
        data = json.loads(json_str)
        data["message_type"] = MessageType(data["message_type"])
        data["priority"] = MessagePriority(data["priority"])
        return cls(**data)


@dataclass
class NegotiationSession:
    """Session สำหรับการเจรจาระหว่าง Agents"""

    negotiation_id: str
    initiator: str
    responder: str
    task: str
    proposed_terms: dict[str, Any]
    status: str = "pending"  # pending, accepted, rejected, negotiating
    counter_terms: dict[str, Any] | None = None
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    expires_at: str | None = None


class EnhancedMessageBus:
    """
    Message Bus ขั้นสูงสำหรับระบบ Agent
    รองรับหลายรูปแบบการสื่อสาร
    """

    def __init__(self):
        self.redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
        self._redis: redis.Redis | None = None
        self._use_redis = False

        # Local subscribers
        self._subscribers: dict[str, list[asyncio.Queue]] = {}
        self._pattern_subscribers: dict[str, list[asyncio.Queue]] = {}

        # Request/Response correlation
        self._pending_requests: dict[str, asyncio.Future] = {}

        # Negotiation sessions
        self._negotiations: dict[str, NegotiationSession] = {}

        # Message history (สำหรับ debug และ replay)
        self._message_history: list[AgentMessage] = []
        self._max_history = 1000

        # Callbacks สำหรับ message types พิเศษ
        self._negotiation_handlers: list[Callable] = []
        self._swarm_handlers: list[Callable] = []

    async def connect(self):
        """เชื่อมต่อกับ Redis"""
        try:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            self._use_redis = True
            logger.info("EnhancedMessageBus connected to Redis")

            # เริ่ม listener สำหรับ Redis
            asyncio.create_task(self._redis_listener())
        except Exception as e:
            logger.warning(f"Redis connection failed, using local mode: {e}")
            self._use_redis = False

    async def _redis_listener(self):
        """Background task ฟังข้อความจาก Redis"""
        while True:
            try:
                pubsub = self._redis.pubsub()
                await pubsub.subscribe("agent_messages")

                async for message in pubsub.listen():
                    if message["type"] == "message":
                        try:
                            agent_msg = AgentMessage.from_json(message["data"])
                            await self._route_message(agent_msg)
                        except Exception as e:
                            logger.error(f"Failed to process Redis message: {e}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Redis listener error: {e}")
                await asyncio.sleep(5)

    async def publish(self, topic: str, message: AgentMessage, persist: bool = False):
        """ส่งข้อความไปยัง topic"""
        # บันทึก history
        self._message_history.append(message)
        if len(self._message_history) > self._max_history:
            self._message_history.pop(0)

        # ส่งผ่าน Redis ถ้าใช้งานได้
        if self._use_redis and self._redis:
            try:
                await self._redis.publish("agent_messages", message.to_json())

                # เก็บใน stream ถ้าต้องการ persist
                if persist:
                    await self._redis.xadd(
                        f"stream:{topic}", {"message": message.to_json()}, maxlen=1000
                    )
            except Exception as e:
                logger.error(f"Redis publish failed: {e}")

        # Route ใน local
        await self._route_message(message)

    async def _route_message(self, message: AgentMessage):
        """Route ข้อความไปยัง subscribers ที่เหมาะสม"""
        # Direct message
        if message.receiver:
            target_queues = self._subscribers.get(f"agent:{message.receiver}", [])
        else:
            # Broadcast ไปยัง topic
            target_queues = self._subscribers.get(message.topic, [])

        # ส่งไปยังทุก queue
        for queue in target_queues:
            try:
                await queue.put(message)
            except Exception as e:
                logger.error(f"Failed to put message in queue: {e}")

        # ตรวจสอบ pattern subscribers
        for pattern, queues in self._pattern_subscribers.items():
            if self._match_pattern(message.topic, pattern):
                for queue in queues:
                    try:
                        await queue.put(message)
                    except Exception as e:
                        logger.error(f"Failed to put message in pattern queue: {e}")

        # จัดการ message types พิเศษ
        if message.message_type == MessageType.NEGOTIATION:
            await self._handle_negotiation_message(message)
        elif message.message_type == MessageType.SWARM_COORDINATION:
            await self._handle_swarm_message(message)
        elif message.message_type == MessageType.REQUEST:
            await self._handle_request_message(message)

    def _match_pattern(self, topic: str, pattern: str) -> bool:
        """ตรวจสอบว่า topic match กับ pattern หรือไม่ (* wildcard)"""
        if pattern == "*":
            return True
        if "*" in pattern:
            prefix = pattern.rstrip("*")
            return topic.startswith(prefix)
        return topic == pattern

    async def subscribe(self, topic: str) -> asyncio.Queue:
        """สมัครรับข้อความจาก topic"""
        queue = asyncio.Queue()

        if topic not in self._subscribers:
            self._subscribers[topic] = []
        self._subscribers[topic].append(queue)

        return queue

    async def subscribe_pattern(self, pattern: str) -> asyncio.Queue:
        """สมัครรับข้อความที่ match pattern (เช่น "agent.*")"""
        queue = asyncio.Queue()

        if pattern not in self._pattern_subscribers:
            self._pattern_subscribers[pattern] = []
        self._pattern_subscribers[pattern].append(queue)

        return queue

    async def unsubscribe(self, topic: str, queue: asyncio.Queue):
        """ยกเลิกการสมัคร"""
        if topic in self._subscribers and queue in self._subscribers[topic]:
            self._subscribers[topic].remove(queue)

    async def request(
        self, receiver: str, content: dict[str, Any], timeout: float = 30.0
    ) -> AgentMessage | None:
        """
        ส่ง request และรอรับ response (RPC pattern)
        """
        request_id = str(uuid.uuid4())
        future = asyncio.get_event_loop().create_future()
        self._pending_requests[request_id] = future

        message = AgentMessage(
            sender="system",  # หรือใส่ชื่อ agent ที่เรียก
            receiver=receiver,
            topic=f"request:{receiver}",
            message_type=MessageType.REQUEST,
            content={**content, "_request_id": request_id},
        )

        await self.publish(message.topic, message)

        try:
            response = await asyncio.wait_for(future, timeout=timeout)
            return response
        except TimeoutError:
            logger.warning(f"Request timeout: {request_id}")
            return None
        finally:
            self._pending_requests.pop(request_id, None)

    async def respond(self, request_message: AgentMessage, content: dict[str, Any]):
        """ตอบกลับ request"""
        request_id = request_message.content.get("_request_id")

        if request_id and request_id in self._pending_requests:
            response = AgentMessage(
                sender=request_message.receiver or "system",
                receiver=request_message.sender,
                topic=f"response:{request_message.sender}",
                message_type=MessageType.RESPONSE,
                content={**content, "_in_response_to": request_id},
            )

            # แก้ไข future โดยตรง
            future = self._pending_requests.get(request_id)
            if future and not future.done():
                future.set_result(response)

        await self.publish(f"response:{request_message.sender}", response)

    async def _handle_request_message(self, message: AgentMessage):
        """จัดการ request message"""
        # ใน implementation จริงจะ route ไปยัง handler ที่เหมาะสม
        pass

    async def start_negotiation(
        self,
        initiator: str,
        responder: str,
        task: str,
        terms: dict[str, Any],
        timeout_minutes: int = 10,
    ) -> NegotiationSession:
        """
        เริ่มการเจรจาระหว่าง 2 Agents
        """
        negotiation_id = f"nego_{uuid.uuid4().hex[:8]}"

        expires = datetime.now(UTC)
        expires = expires.replace(minute=expires.minute + timeout_minutes)

        session = NegotiationSession(
            negotiation_id=negotiation_id,
            initiator=initiator,
            responder=responder,
            task=task,
            proposed_terms=terms,
            expires_at=expires.isoformat(),
        )

        self._negotiations[negotiation_id] = session

        # ส่งข้อเสนอไปยัง responder
        message = AgentMessage(
            sender=initiator,
            receiver=responder,
            topic=f"negotiation:{responder}",
            message_type=MessageType.NEGOTIATION,
            content={
                "negotiation_id": negotiation_id,
                "action": "propose",
                "task": task,
                "terms": terms,
            },
        )

        await self.publish(message.topic, message)

        return session

    async def respond_to_negotiation(
        self, negotiation_id: str, accept: bool, counter_terms: dict[str, Any] | None = None
    ) -> bool:
        """ตอบรับหรือต่อรองข้อเสนอ"""
        session = self._negotiations.get(negotiation_id)
        if not session:
            return False

        if accept:
            session.status = "accepted"
        elif counter_terms:
            session.status = "negotiating"
            session.counter_terms = counter_terms
        else:
            session.status = "rejected"

        # ส่งผลกลับไปยัง initiator
        message = AgentMessage(
            sender=session.responder,
            receiver=session.initiator,
            topic=f"negotiation:{session.initiator}",
            message_type=MessageType.NEGOTIATION,
            content={
                "negotiation_id": negotiation_id,
                "action": "accept" if accept else "counter" if counter_terms else "reject",
                "terms": counter_terms if counter_terms else session.proposed_terms,
            },
        )

        await self.publish(message.topic, message)
        return True

    async def _handle_negotiation_message(self, message: AgentMessage):
        """จัดการ negotiation message"""
        for handler in self._negotiation_handlers:
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"Negotiation handler error: {e}")

    def on_negotiation(self, handler: Callable[[AgentMessage], None]):
        """ลงทะเบียน handler สำหรับ negotiation"""
        self._negotiation_handlers.append(handler)

    async def _handle_swarm_message(self, message: AgentMessage):
        """จัดการ swarm coordination message"""
        for handler in self._swarm_handlers:
            try:
                await handler(message)
            except Exception as e:
                logger.error(f"Swarm handler error: {e}")

    def on_swarm(self, handler: Callable[[AgentMessage], None]):
        """ลงทะเบียน handler สำหรับ swarm coordination"""
        self._swarm_handlers.append(handler)

    async def coordinate_swarm(
        self, swarm_id: str, agent_ids: list[str], objective: str, strategy: dict[str, Any]
    ):
        """ส่งคำสั่ง coordination ไปยัง swarm"""
        message = AgentMessage(
            sender="swarm_coordinator",
            message_type=MessageType.SWARM_COORDINATION,
            topic=f"swarm:{swarm_id}",
            content={
                "swarm_id": swarm_id,
                "objective": objective,
                "strategy": strategy,
                "participants": agent_ids,
            },
        )

        await self.publish(message.topic, message)

    async def get_message_history(
        self,
        topic: str | None = None,
        sender: str | None = None,
        since: str | None = None,
        limit: int = 100,
    ) -> list[AgentMessage]:
        """ดึงประวัติข้อความ"""
        messages = self._message_history

        if topic:
            messages = [m for m in messages if m.topic == topic]
        if sender:
            messages = [m for m in messages if m.sender == sender]
        if since:
            messages = [m for m in messages if m.timestamp >= since]

        return messages[-limit:]

    async def get_active_negotiations(self) -> list[NegotiationSession]:
        """ดึง negotiation ที่กำลังดำเนินอยู่"""
        now = datetime.now(UTC).isoformat()
        return [
            n
            for n in self._negotiations.values()
            if n.status in ["pending", "negotiating"]
            and (n.expires_at is None or n.expires_at > now)
        ]


# Global singleton
message_bus = EnhancedMessageBus()
