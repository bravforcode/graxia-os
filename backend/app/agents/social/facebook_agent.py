"""
Facebook Agent - มีบัญชี Facebook เป็นของตัวเอง
จัดการ Page, Messenger, Comments, และ Posts
"""

import asyncio
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings
from app.core.agent_identity import AgentCapability, PlatformType, identity_manager

from .base_social_agent import BaseSocialAgent, SocialMessage, SocialResponse

logger = logging.getLogger(__name__)


class FacebookAgent(BaseSocialAgent):
    """
    AI Agent สำหรับจัดการ Facebook Page และ Messenger
    มีบัญชีเป็นของตัวเองและสามารถคุยกับ Agents อื่นได้
    """

    def __init__(self):
        capabilities = [
            AgentCapability(
                name="post_management",
                description="สร้างและจัดการโพสต์บน Facebook Page",
                skill_level=8,
            ),
            AgentCapability(
                name="messenger_response", description="ตอบข้อความ Messenger อัตโนมัติ", skill_level=9
            ),
            AgentCapability(
                name="comment_management",
                description="ตอบคอมเมนต์และจัดการ engagement",
                skill_level=7,
            ),
            AgentCapability(name="lead_capture", description="เก็บข้อมูลลูกค้าที่สนใจ", skill_level=8),
        ]

        super().__init__(
            agent_name="Facebook Social Agent",
            platform="facebook",
            bio="AI Agent จัดการ Facebook Page - โพสต์ ตอบข้อความ และ engage กับลูกค้า",
            capabilities=capabilities,
        )

        # Facebook Graph API settings
        self.app_id = getattr(settings, "FACEBOOK_APP_ID", None)
        self.app_secret = getattr(settings, "FACEBOOK_APP_SECRET", None)
        self.access_token = getattr(settings, "FACEBOOK_ACCESS_TOKEN", None)
        self.page_id = getattr(settings, "FACEBOOK_PAGE_ID", None)

        self.enabled = getattr(settings, "FACEBOOK_AGENT_ENABLED", False)
        self.base_url = "https://graph.facebook.com/v18.0"

        self._client: httpx.AsyncClient | None = None
        self._webhook_handlers: list[Callable] = []
        self._message_queue: asyncio.Queue = asyncio.Queue()

    async def initialize(self):
        """เริ่มต้น Agent และเชื่อมต่อ Facebook"""
        await super().initialize()

        if not self.enabled or not self.access_token:
            logger.warning("Facebook Agent disabled - missing configuration")
            return

        # สร้าง HTTP client
        self._client = httpx.AsyncClient(timeout=30.0)

        # เพิ่มบัญชี Facebook ให้กับ identity
        if self.page_id:
            await identity_manager.add_account(
                agent_id=self.identity.agent_id,
                platform=PlatformType.FACEBOOK,
                account_id=self.page_id,
                username=f"page_{self.page_id}",
                credentials={"access_token": self.access_token, "app_id": self.app_id}
                if self.app_id
                else None,
            )

        logger.info(f"Facebook Agent initialized for Page: {self.page_id}")

    async def connect(self):
        """เชื่อมต่อกับ Facebook Graph API"""
        if not self._client:
            self._client = httpx.AsyncClient(timeout=30.0)

        # ตรวจสอบ token ว่าใช้ได้
        try:
            response = await self._client.get(
                f"{self.base_url}/me", params={"access_token": self.access_token}
            )
            response.raise_for_status()
            data = response.json()
            logger.info(f"Facebook connection verified: {data.get('name')}")
            self.is_running = True
        except Exception as e:
            logger.error(f"Facebook connection failed: {e}")
            raise

    async def disconnect(self):
        """ยกเลิกการเชื่อมต่อ"""
        self.is_running = False
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send_message(self, recipient_id: str, response: SocialResponse) -> bool:
        """ส่งข้อความผ่าน Messenger"""
        if not self._client or not self.access_token:
            return False

        try:
            url = f"{self.base_url}/me/messages"

            payload = {
                "recipient": {"id": recipient_id},
                "message": {"text": response.content},
                "messaging_type": "RESPONSE",
            }

            # ถ้ามี quick replies
            if response.quick_replies:
                payload["message"]["quick_replies"] = response.quick_replies

            resp = await self._client.post(
                url, params={"access_token": self.access_token}, json=payload
            )
            resp.raise_for_status()

            logger.info(f"Message sent to {recipient_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return False

    async def post_to_page(
        self, message: str, link: str | None = None, image_url: str | None = None
    ) -> str | None:
        """โพสต์ลง Facebook Page"""
        if not self._client or not self.access_token or not self.page_id:
            logger.error("Facebook not configured for posting")
            return None

        try:
            url = f"{self.base_url}/{self.page_id}/feed"

            payload = {"message": message}
            if link:
                payload["link"] = link
            if image_url:
                # สำหรับรูปภาพต้องใช้ endpoint ต่างหาก
                url = f"{self.base_url}/{self.page_id}/photos"
                payload["url"] = image_url
                payload.pop("message", None)
                payload["caption"] = message

            resp = await self._client.post(
                url, params={"access_token": self.access_token}, json=payload
            )
            resp.raise_for_status()
            data = resp.json()

            post_id = data.get("id")
            logger.info(f"Posted to Facebook: {post_id}")

            # บันทึก activity ลง Obsidian
            await self._log_activity_to_obsidian("post", message, post_id)

            return post_id

        except Exception as e:
            logger.error(f"Failed to post: {e}")
            return None

    async def reply_to_comment(self, comment_id: str, message: str) -> bool:
        """ตอบกลับคอมเมนต์"""
        if not self._client or not self.access_token:
            return False

        try:
            url = f"{self.base_url}/{comment_id}/comments"

            resp = await self._client.post(
                url, params={"access_token": self.access_token}, json={"message": message}
            )
            resp.raise_for_status()

            logger.info(f"Replied to comment: {comment_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to reply to comment: {e}")
            return False

    async def get_page_insights(self) -> dict[str, Any]:
        """ดึงสถิติของ Page"""
        if not self._client or not self.access_token or not self.page_id:
            return {}

        try:
            url = f"{self.base_url}/{self.page_id}/insights"

            params = {
                "access_token": self.access_token,
                "metric": "page_impressions,page_engaged_users,page_fan_adds",
                "period": "day",
            }

            resp = await self._client.get(url, params=params)
            resp.raise_for_status()

            return resp.json()

        except Exception as e:
            logger.error(f"Failed to get insights: {e}")
            return {}

    async def handle_webhook(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """
        จัดการ webhook ที่เข้ามาจาก Facebook
        รองรับ messaging, feed changes, etc.
        """
        responses = []

        # Messenger events
        if "entry" in payload:
            for entry in payload["entry"]:
                if "messaging" in entry:
                    for messaging_event in entry["messaging"]:
                        # แปลงเป็น SocialMessage
                        message = self._convert_messaging_event(messaging_event)
                        if message:
                            # ประมวลผล
                            response = await self.receive_message(message)
                            if response:
                                # ส่งตอบกลับ
                                success = await self.send_message(message.sender_id, response)
                                responses.append(
                                    {
                                        "message_id": message.message_id,
                                        "sent": success,
                                        "response": response.content,
                                    }
                                )

        return responses

    def _convert_messaging_event(self, event: dict) -> SocialMessage | None:
        """แปลง Facebook messaging event เป็น SocialMessage"""
        try:
            sender_id = event.get("sender", {}).get("id")
            message_data = event.get("message", {})

            if not sender_id:
                return None

            content = message_data.get("text", "")
            message_id = message_data.get("mid", f"msg_{datetime.now().timestamp()}")

            # ดึงชื่อผู้ส่ง (ต้องเรียก API เพิ่มใน production)
            sender_name = f"User_{sender_id[:8]}"

            return SocialMessage(
                message_id=message_id,
                platform="facebook",
                sender_id=sender_id,
                sender_name=sender_name,
                content=content,
                message_type="text" if content else "unknown",
                raw_data=event,
            )

        except Exception as e:
            logger.error(f"Failed to convert messaging event: {e}")
            return None

    async def _log_activity_to_obsidian(
        self, activity_type: str, content: str, external_id: str | None = None
    ):
        """บันทึกกิจกรรมลง Obsidian"""
        try:
            from app.integrations.obsidian import get_obsidian

            obsidian = await get_obsidian()

            timestamp = datetime.now(UTC).isoformat()
            note_content = f"""# Facebook Activity - {activity_type}

**Time:** {timestamp}
**Agent:** {self.agent_name}
**Type:** {activity_type}
**External ID:** {external_id or "N/A"}

## Content
{content}
"""

            await obsidian.write_note(
                filename=f"fb_{activity_type}_{int(datetime.now().timestamp())}",
                content=note_content,
                folder="Social Media/Facebook/Activities",
                frontmatter={
                    "type": "social_activity",
                    "platform": "facebook",
                    "activity_type": activity_type,
                    "agent": self.agent_name,
                    "timestamp": timestamp,
                    "external_id": external_id,
                },
            )

        except Exception as e:
            logger.warning(f"Failed to log to Obsidian: {e}")

    async def sync_with_other_agents(self):
        """
        ส่งข้อมูลที่สำคัญไปให้ Agents อื่นรับรู้
        เช่น ถ้ามีลูกค้าถามราคา ส่งต่อให้ Sales Agent
        """
        # ตรวจสอบข้อความล่าสุด
        # ถ้าพบคำสั่งซื้อ/สอบถามราคา ส่งไปยัง Business Agents
        pass

    async def start_listening(self):
        """เริ่มรับ webhook (ใน production ใช้ webhook, ใน dev อาจใช้ polling)"""
        if not self.is_running:
            await self.connect()

        logger.info("Facebook Agent started listening")

        # ใน implementation จริงจะใช้ webhook server
        # หรือ Realtime API ถ้ามี
        while self.is_running:
            await asyncio.sleep(1)


# Singleton instance
facebook_agent = FacebookAgent()
