"""
Base Social Agent - พื้นฐานสำหรับทุก Social Media Agent
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from app.core.agent_identity import AgentCapability, AgentIdentity, AgentType, identity_manager

logger = logging.getLogger(__name__)


@dataclass
class SocialMessage:
    """ข้อความที่เข้ามาจาก Social Media"""

    message_id: str
    platform: str  # facebook, line, instagram, etc.
    sender_id: str
    sender_name: str
    content: str
    message_type: str = "text"  # text, image, video, sticker, etc.
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, Any] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class SocialResponse:
    """การตอบกลับที่จะส่งไปยัง Social Media"""

    content: str
    response_type: str = "text"  # text, image, carousel, quick_reply, etc.
    attachments: list[dict] | None = None
    quick_replies: list[dict] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseSocialAgent(ABC):
    """
    พื้นฐานสำหรับ Social Media Agents ทุกตัว
    มีบัญชีเป็นของตัวเองและสามารถคุยกับ Agent อื่นได้
    """

    def __init__(
        self,
        agent_name: str,
        platform: str,
        bio: str = "",
        capabilities: list[AgentCapability] | None = None,
    ):
        self.agent_name = agent_name
        self.platform = platform
        self.bio = bio or f"AI Agent สำหรับจัดการ {platform}"
        self.capabilities = capabilities or []
        self.identity: AgentIdentity | None = None
        self.message_handlers: list[Callable[[SocialMessage], SocialResponse | None]] = []
        self.is_running = False

    async def initialize(self):
        """สร้าง identity และเตรียม Agent"""
        # ค้นหาหรือสร้าง identity
        existing = await identity_manager.get_agent_by_name(self.agent_name)

        if existing:
            self.identity = existing
            logger.info(f"Loaded existing agent: {self.agent_name}")
        else:
            self.identity = await identity_manager.create_agent(
                name=self.agent_name,
                agent_type=AgentType.SOCIAL,
                bio=self.bio,
                capabilities=self.capabilities,
            )
            logger.info(f"Created new agent: {self.agent_name} (ID: {self.identity.agent_id})")

        # ลงทะเบียน handlers พื้นฐาน
        self._register_default_handlers()

    def _register_default_handlers(self):
        """ลงทะเบียน message handlers พื้นฐาน"""
        self.message_handlers.append(self._handle_help)
        self.message_handlers.append(self._handle_status)

    def _handle_help(self, message: SocialMessage) -> SocialResponse | None:
        """ตอบคำสั่ง help"""
        if "help" in message.content.lower() or "ช่วยเหลือ" in message.content:
            return SocialResponse(
                content=f"สวัสดี! ฉันคือ {self.agent_name}\n\nความสามารถ:\n"
                + "\n".join([f"• {cap.name}: {cap.description}" for cap in self.capabilities]),
                response_type="text",
            )
        return None

    def _handle_status(self, message: SocialMessage) -> SocialResponse | None:
        """ตอบคำสั่ง status"""
        if message.content.lower() in ["status", "สถานะ"]:
            if self.identity:
                return SocialResponse(
                    content=f"🤖 {self.agent_name}\n"
                    + f"สถานะ: {'พร้อมทำงาน' if self.identity.is_available else 'ไม่พร้อม'}\n"
                    + f"งานที่ทำสำเร็จ: {self.identity.completed_tasks}\n"
                    + f"อัตราความสำเร็จ: {self.identity.success_rate * 100:.1f}%\n"
                    + f"คะแนนความน่าเชื่อถือ: {self.identity.reputation_score:.1f}/100",
                    response_type="text",
                )
            return SocialResponse(content="Agent ยังไม่พร้อมใช้งาน", response_type="text")
        return None

    @abstractmethod
    async def connect(self):
        """เชื่อมต่อกับแพลตฟอร์ม (implement ในแต่ละ platform)"""
        pass

    @abstractmethod
    async def disconnect(self):
        """ยกเลิกการเชื่อมต่อ"""
        pass

    @abstractmethod
    async def send_message(self, recipient_id: str, response: SocialResponse) -> bool:
        """ส่งข้อความไปยังผู้ใช้"""
        pass

    async def receive_message(self, message: SocialMessage) -> SocialResponse | None:
        """รับและประมวลผลข้อความที่เข้ามา"""
        start_time = asyncio.get_event_loop().time()

        # ลองผ่าน handlers ทั้งหมด
        for handler in self.message_handlers:
            try:
                response = handler(message)
                if response:
                    # บันทึกสถิติ
                    end_time = asyncio.get_event_loop().time()
                    await identity_manager.record_task_completion(
                        self.identity.agent_id, success=True, response_time=end_time - start_time
                    )
                    return response
            except Exception as e:
                logger.error(f"Handler error: {e}")

        # ถ้าไม่มี handler ตอบ ให้ใช้ AI ตอบ
        return await self._generate_ai_response(message)

    async def _generate_ai_response(self, message: SocialMessage) -> SocialResponse:
        """ใช้ LLM สร้างการตอบกลับ (override ได้)"""
        # ส่งต่อให้ LLM client
        from app.core.llm import llm_client

        try:
            system_prompt = f"""คุณคือ {self.agent_name} - {self.bio}
            กำลังคุยกับผู้ใช้บน {self.platform}
            ตอบอย่างกระชับ เป็นกันเอง และเป็นประโยชน์"""

            response = await llm_client.generate_completion(
                system_prompt=system_prompt, user_prompt=message.content
            )

            return SocialResponse(content=response, response_type="text")
        except Exception as e:
            logger.error(f"AI response generation failed: {e}")
            return SocialResponse(content="ขออภัย ฉันไม่สามารถตอบได้ในขณะนี้", response_type="text")

    def add_message_handler(self, handler: Callable[[SocialMessage], SocialResponse | None]):
        """เพิ่ม message handler"""
        self.message_handlers.append(handler)

    async def broadcast_to_agents(self, message: str, target_platforms: list[str] | None = None):
        """ส่งข้อความไปยัง Agents อื่นๆ"""
        # ส่งผ่าน message bus
        from app.core.enhanced_message_bus import AgentMessage, message_bus

        await message_bus.publish(
            "agent_communication",
            AgentMessage(
                sender=self.agent_name,
                topic="agent_communication",
                content={
                    "type": "broadcast",
                    "message": message,
                    "from_platform": self.platform,
                    "target_platforms": target_platforms,
                },
            ),
        )

    async def negotiate_with_agent(
        self, target_agent_name: str, task: str, deadline: datetime | None = None
    ) -> dict[str, Any]:
        """
        เจรจาให้ Agent อื่นช่วยทำงาน
        ส่ง request และรอรับ response
        """
        from app.core.enhanced_message_bus import AgentMessage, message_bus

        negotiation_id = f"nego_{asyncio.get_event_loop().time()}"

        # ส่งข้อเสนอ
        await message_bus.publish(
            f"negotiation:{target_agent_name}",
            AgentMessage(
                sender=self.agent_name,
                receiver=target_agent_name,
                topic="negotiation_request",
                content={
                    "negotiation_id": negotiation_id,
                    "task": task,
                    "deadline": deadline.isoformat() if deadline else None,
                    "proposed_by": self.agent_name,
                },
            ),
        )

        # รอรับตอบกลับ (timeout 30 วินาที)
        # ใน implementation จริงควรใช้ future/promise pattern
        return {
            "negotiation_id": negotiation_id,
            "status": "pending",
            "message": f"ส่งข้อเสนอไปยัง {target_agent_name} แล้ว",
        }

    async def get_stats(self) -> dict[str, Any]:
        """ดึงสถิติของ Agent"""
        if not self.identity:
            return {}

        return {
            "agent_id": self.identity.agent_id,
            "name": self.identity.agent_name,
            "type": self.identity.agent_type.value,
            "platform": self.platform,
            "reputation_score": self.identity.reputation_score,
            "completed_tasks": self.identity.completed_tasks,
            "success_rate": self.identity.success_rate,
            "response_time_avg": self.identity.response_time_avg,
            "is_available": self.identity.is_available,
            "accounts": list(self.identity.accounts.keys()),
        }
