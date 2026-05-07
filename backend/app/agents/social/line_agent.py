"""
LINE Agent - มี LINE Official Account เป็นของตัวเอง
จัดการข้อความ, Rich Menu, Broadcast, และ Quick Reply
"""

import logging
from datetime import UTC, datetime
from typing import Any

import httpx

from app.config import settings
from app.core.agent_identity import AgentCapability, PlatformType, identity_manager

from .base_social_agent import BaseSocialAgent, SocialMessage, SocialResponse

logger = logging.getLogger(__name__)


class LineAgent(BaseSocialAgent):
    """
    AI Agent สำหรับจัดการ LINE Official Account
    รองรับข้อความ, สติ๊กเกอร์, รูปภาพ, และ Rich Menu
    """

    def __init__(self):
        capabilities = [
            AgentCapability(
                name="message_response", description="ตอบข้อความ LINE อัตโนมัติ", skill_level=9
            ),
            AgentCapability(
                name="rich_menu_management", description="จัดการ Rich Menu", skill_level=8
            ),
            AgentCapability(
                name="broadcast", description="ส่งข้อควBroadcast ถึง followers", skill_level=7
            ),
            AgentCapability(
                name="quick_reply", description="ใช้ Quick Reply สำหรับการโต้ตอบ", skill_level=8
            ),
            AgentCapability(
                name="multilingual", description="รองรับภาษาไทย, อังกฤษ, และอื่นๆ", skill_level=9
            ),
        ]

        super().__init__(
            agent_name="LINE Official Agent",
            platform="line",
            bio="AI Agent จัดการ LINE OA - ตอบลูกค้า, ส่ง broadcast, และจัดการ Rich Menu",
            capabilities=capabilities,
        )

        # LINE Messaging API settings
        self.channel_id = getattr(settings, "LINE_CHANNEL_ID", None)
        self.channel_secret = getattr(settings, "LINE_CHANNEL_SECRET", None)
        self.channel_access_token = getattr(settings, "LINE_CHANNEL_ACCESS_TOKEN", None)
        self.admin_user_id = getattr(settings, "LINE_ADMIN_USER_ID", None)

        self.enabled = getattr(settings, "LINE_AGENT_ENABLED", False)
        self.api_base = "https://api.line.me/v2"
        self.data_api_base = "https://api-data.line.me/v2"

        self._client: httpx.AsyncClient | None = None
        self._rich_menu_id: str | None = None

    async def initialize(self):
        """เริ่มต้น Agent และเตรียม LINE connection"""
        await super().initialize()

        if not self.enabled or not self.channel_access_token:
            logger.warning("LINE Agent disabled - missing configuration")
            return

        # สร้าง HTTP client พร้อม headers
        self._client = httpx.AsyncClient(
            timeout=30.0,
            headers={
                "Authorization": f"Bearer {self.channel_access_token}",
                "Content-Type": "application/json",
            },
        )

        # เพิ่มบัญชี LINE ให้กับ identity
        if self.channel_id:
            await identity_manager.add_account(
                agent_id=self.identity.agent_id,
                platform=PlatformType.LINE,
                account_id=self.channel_id,
                username=f"oa_{self.channel_id}",
                display_name="LINE Official Account",
                credentials={
                    "channel_access_token": self.channel_access_token,
                    "channel_id": self.channel_id,
                }
                if self.channel_id
                else None,
            )

        logger.info(f"LINE Agent initialized for Channel: {self.channel_id}")

    async def connect(self):
        """เชื่อมต่อและตรวจสอบ LINE API"""
        if not self._client:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                headers={
                    "Authorization": f"Bearer {self.channel_access_token}",
                    "Content-Type": "application/json",
                },
            )

        try:
            # ตรวจสอบ bot info
            resp = await self._client.get(f"{self.api_base}/bot/info")
            resp.raise_for_status()
            data = resp.json()
            logger.info(f"LINE connection verified: {data.get('displayName')}")
            self.is_running = True
        except Exception as e:
            logger.error(f"LINE connection failed: {e}")
            raise

    async def disconnect(self):
        """ยกเลิกการเชื่อมต่อ"""
        self.is_running = False
        if self._client:
            await self._client.aclose()
            self._client = None

    async def send_message(self, recipient_id: str, response: SocialResponse) -> bool:
        """ส่งข้อความผ่าน LINE Messaging API"""
        if not self._client:
            return False

        try:
            url = f"{self.api_base}/bot/message/push"

            messages = []

            # สร้าง message object ตาม type
            if response.response_type == "text":
                msg = {"type": "text", "text": response.content}

                # เพิ่ม quick reply ถ้ามี
                if response.quick_replies:
                    msg["quickReply"] = {
                        "items": [
                            {
                                "type": "action",
                                "action": {
                                    "type": "message",
                                    "label": qr.get("label", "Button"),
                                    "text": qr.get("text", qr.get("payload", "")),
                                },
                            }
                            for qr in response.quick_replies
                        ]
                    }

                messages.append(msg)

            payload = {"to": recipient_id, "messages": messages}

            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()

            logger.info(f"LINE message sent to {recipient_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to send LINE message: {e}")
            return False

    async def reply_to_message(self, reply_token: str, response: SocialResponse) -> bool:
        """ตอบกลับข้อความด้วย reply token (ภายใน 1 นาที)"""
        if not self._client:
            return False

        try:
            url = f"{self.api_base}/bot/message/reply"

            messages = []

            if response.response_type == "text":
                messages.append({"type": "text", "text": response.content})
            elif response.response_type == "sticker":
                messages.append(
                    {
                        "type": "sticker",
                        "packageId": response.metadata.get("package_id", "1"),
                        "stickerId": response.metadata.get("sticker_id", "1"),
                    }
                )
            elif response.response_type == "image":
                messages.append(
                    {
                        "type": "image",
                        "originalContentUrl": response.metadata.get("image_url"),
                        "previewImageUrl": response.metadata.get("preview_url"),
                    }
                )
            elif response.response_type == "flex":
                # LINE Flex Message (rich UI)
                messages.append(
                    {
                        "type": "flex",
                        "altText": response.metadata.get("alt_text", "Flex Message"),
                        "contents": response.metadata.get("flex_content", {}),
                    }
                )

            payload = {"replyToken": reply_token, "messages": messages}

            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()

            logger.info("LINE reply sent")
            return True

        except Exception as e:
            logger.error(f"Failed to send LINE reply: {e}")
            return False

    async def send_multicast(self, user_ids: list[str], message: str) -> bool:
        """ส่งข้อความหลายคนพร้อมกัน (Multicast)"""
        if not self._client or len(user_ids) > 500:  # LINE limit
            return False

        try:
            url = f"{self.api_base}/bot/message/multicast"

            payload = {"to": user_ids, "messages": [{"type": "text", "text": message}]}

            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()

            logger.info(f"LINE multicast sent to {len(user_ids)} users")
            return True

        except Exception as e:
            logger.error(f"Failed to send multicast: {e}")
            return False

    async def broadcast_message(self, message: str) -> bool:
        """Broadcast ถึงทุกคนที่เป็นเพื่อน"""
        if not self._client:
            return False

        try:
            url = f"{self.api_base}/bot/message/broadcast"

            payload = {"messages": [{"type": "text", "text": message}]}

            resp = await self._client.post(url, json=payload)
            resp.raise_for_status()

            logger.info("LINE broadcast sent")

            # บันทึกลง Obsidian
            await self._log_activity_to_obsidian("broadcast", message)

            return True

        except Exception as e:
            logger.error(f"Failed to broadcast: {e}")
            return False

    async def set_rich_menu(self, rich_menu: dict[str, Any]) -> str | None:
        """ตั้งค่า Rich Menu"""
        if not self._client:
            return None

        try:
            # 1. สร้าง Rich Menu
            url = f"{self.api_base}/bot/richmenu"

            resp = await self._client.post(url, json=rich_menu)
            resp.raise_for_status()
            data = resp.json()

            rich_menu_id = data.get("richMenuId")

            # 2. ตั้งเป็นค่าเริ่มต้น
            if rich_menu_id:
                await self._client.post(f"{self.api_base}/bot/user/all/richmenu/{rich_menu_id}")
                self._rich_menu_id = rich_menu_id
                logger.info(f"Rich Menu set: {rich_menu_id}")

            return rich_menu_id

        except Exception as e:
            logger.error(f"Failed to set Rich Menu: {e}")
            return None

    async def get_user_profile(self, user_id: str) -> dict[str, Any]:
        """ดึงข้อมูลผู้ใช้"""
        if not self._client:
            return {}

        try:
            url = f"{self.api_base}/bot/profile/{user_id}"
            resp = await self._client.get(url)
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            logger.error(f"Failed to get user profile: {e}")
            return {}

    async def get_follower_count(self) -> int:
        """ดึงจำนวน followers"""
        if not self._client:
            return 0

        try:
            url = f"{self.api_base}/bot/followers/count"
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            return data.get("followers", 0)
        except Exception as e:
            logger.error(f"Failed to get follower count: {e}")
            return 0

    def _convert_line_event(self, event: dict) -> SocialMessage | None:
        """แปลง LINE webhook event เป็น SocialMessage"""
        try:
            event_type = event.get("type")

            if event_type != "message":
                return None

            message_data = event.get("message", {})
            source = event.get("source", {})

            user_id = source.get("userId")
            message_type = message_data.get("type", "text")

            # แปลง content ตาม type
            if message_type == "text":
                content = message_data.get("text", "")
            elif message_type == "sticker":
                content = (
                    f"[Sticker: {message_data.get('packageId')}/{message_data.get('stickerId')}]"
                )
            elif message_type == "image":
                content = "[Image]"
            elif message_type == "location":
                content = f"[Location: {message_data.get('address')} ({message_data.get('latitude')}, {message_data.get('longitude')})]"
            else:
                content = f"[{message_type}]"

            # ดึงชื่อผู้ใช้ถ้าเป็นไปได้
            sender_name = user_id[:8] if user_id else "Unknown"

            return SocialMessage(
                message_id=message_data.get("id", f"line_{datetime.now().timestamp()}"),
                platform="line",
                sender_id=user_id,
                sender_name=sender_name,
                content=content,
                message_type=message_type,
                metadata={
                    "reply_token": event.get("replyToken"),
                    "timestamp": event.get("timestamp"),
                },
                raw_data=event,
            )

        except Exception as e:
            logger.error(f"Failed to convert LINE event: {e}")
            return None

    async def handle_webhook(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        """จัดการ webhook จาก LINE"""
        responses = []

        events = payload.get("events", [])

        for event in events:
            # แปลงเป็น SocialMessage
            message = self._convert_line_event(event)

            if message:
                # ประมวลผล
                response = await self.receive_message(message)

                if response:
                    # ส่งตอบกลับด้วย reply token
                    reply_token = event.get("replyToken")
                    if reply_token:
                        success = await self.reply_to_message(reply_token, response)
                        responses.append(
                            {
                                "event_id": event.get("message", {}).get("id"),
                                "sent": success,
                                "response": response.content,
                            }
                        )

        return responses

    async def _log_activity_to_obsidian(
        self, activity_type: str, content: str, external_id: str | None = None
    ):
        """บันทึกกิจกรรมลง Obsidian"""
        try:
            from app.integrations.obsidian import get_obsidian

            obsidian = await get_obsidian()

            timestamp = datetime.now(UTC).isoformat()
            note_content = f"""# LINE Activity - {activity_type}

**Time:** {timestamp}
**Agent:** {self.agent_name}
**Type:** {activity_type}
**External ID:** {external_id or "N/A"}

## Content
{content}
"""

            await obsidian.write_note(
                filename=f"line_{activity_type}_{int(datetime.now().timestamp())}",
                content=note_content,
                folder="Social Media/LINE/Activities",
                frontmatter={
                    "type": "social_activity",
                    "platform": "line",
                    "activity_type": activity_type,
                    "agent": self.agent_name,
                    "timestamp": timestamp,
                    "external_id": external_id,
                },
            )

        except Exception as e:
            logger.warning(f"Failed to log to Obsidian: {e}")

    async def create_default_rich_menu(self) -> str | None:
        """สร้าง Rich Menu เริ่มต้น"""
        rich_menu = {
            "size": {"width": 2500, "height": 1686},
            "selected": True,
            "name": "Default Menu",
            "chatBarText": "เมนูหลัก",
            "areas": [
                {
                    "bounds": {"x": 0, "y": 0, "width": 833, "height": 843},
                    "action": {"type": "message", "text": "สินค้า"},
                },
                {
                    "bounds": {"x": 834, "y": 0, "width": 833, "height": 843},
                    "action": {"type": "message", "text": "ติดต่อ"},
                },
                {
                    "bounds": {"x": 1667, "y": 0, "width": 833, "height": 843},
                    "action": {"type": "message", "text": "โปรโมชั่น"},
                },
                {
                    "bounds": {"x": 0, "y": 844, "width": 1250, "height": 843},
                    "action": {"type": "message", "text": "ช่วยเหลือ"},
                },
                {
                    "bounds": {"x": 1251, "y": 844, "width": 1250, "height": 843},
                    "action": {"type": "uri", "uri": "https://line.me"},
                },
            ],
        }

        return await self.set_rich_menu(rich_menu)


# Singleton instance
line_agent = LineAgent()
