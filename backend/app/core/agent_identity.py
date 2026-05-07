"""
Agent Identity & Account Management System
ให้แต่ละ Agent มีบัญชีและตัวตนเป็นของตัวเอง
"""

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import redis.asyncio as redis

from app.config import settings


class AgentType(StrEnum):
    SOCIAL = "social"
    BUSINESS = "business"
    CREATIVE = "creative"
    TECHNICAL = "technical"
    ANALYTICS = "analytics"
    HYBRID = "hybrid"


class PlatformType(StrEnum):
    FACEBOOK = "facebook"
    LINE = "line"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    LINKEDIN = "linkedin"
    TIKTOK = "tiktok"
    TELEGRAM = "telegram"
    DISCORD = "discord"
    WHATSAPP = "whatsapp"
    YOUTUBE = "youtube"
    EMAIL = "email"
    SLACK = "slack"


@dataclass
class AgentCapability:
    name: str
    description: str
    skill_level: int = 1  # 1-10
    success_rate: float = 0.0
    total_executions: int = 0


@dataclass
class AgentAccount:
    platform: PlatformType
    account_id: str
    username: str
    display_name: str | None = None
    avatar_url: str | None = None
    is_active: bool = True
    credentials_hash: str | None = None
    rate_limit_per_hour: int = 100
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentIdentity:
    agent_id: str
    agent_name: str
    agent_type: AgentType
    avatar_url: str | None = None
    bio: str = ""
    capabilities: list[AgentCapability] = field(default_factory=list)
    accounts: dict[str, AgentAccount] = field(default_factory=dict)

    # สถิติและคะแนน
    reputation_score: float = 100.0  # 0-100
    completed_tasks: int = 0
    failed_tasks: int = 0
    success_rate: float = 0.0
    response_time_avg: float = 0.0  # วินาที

    # สถานะ
    is_active: bool = True
    is_available: bool = True
    current_load: int = 0
    max_concurrent_tasks: int = 5

    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["agent_type"] = self.agent_type.value
        for _key, account in data["accounts"].items():
            account["platform"] = (
                account["platform"].value
                if isinstance(account["platform"], PlatformType)
                else account["platform"]
            )
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentIdentity":
        data["agent_type"] = AgentType(data["agent_type"])
        accounts = {}
        for key, acc in data.get("accounts", {}).items():
            acc["platform"] = PlatformType(acc["platform"])
            accounts[key] = AgentAccount(**acc)
        data["accounts"] = accounts
        data["capabilities"] = [AgentCapability(**c) for c in data.get("capabilities", [])]
        return cls(**data)


class AgentIdentityManager:
    """
    จัดการตัวตนและบัญชีของ Agents ทั้งหมด
    """

    def __init__(self):
        self.redis_url = getattr(settings, "REDIS_URL", "redis://localhost:6379/0")
        self._redis: redis.Redis | None = None
        self._local_storage: dict[str, AgentIdentity] = {}

    async def connect(self):
        """เชื่อมต่อกับ Redis สำหรับเก็บข้อมูล Agent"""
        try:
            self._redis = redis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
        except Exception as e:
            print(f"Redis connection failed, using local storage: {e}")
            self._redis = None

    def _get_key(self, agent_id: str) -> str:
        return f"agent:identity:{agent_id}"

    def _get_all_key(self) -> str:
        return "agent:identities:all"

    async def create_agent(
        self,
        name: str,
        agent_type: AgentType,
        bio: str = "",
        avatar_url: str | None = None,
        capabilities: list[AgentCapability] | None = None,
    ) -> AgentIdentity:
        """สร้าง Agent ใหม่พร้อมบัญชีอิสระ"""
        agent_id = str(uuid.uuid4())

        agent = AgentIdentity(
            agent_id=agent_id,
            agent_name=name,
            agent_type=agent_type,
            bio=bio,
            avatar_url=avatar_url,
            capabilities=capabilities or [],
        )

        # บันทึกลง storage
        if self._redis:
            await self._redis.set(self._get_key(agent_id), json.dumps(agent.to_dict()))
            await self._redis.sadd(self._get_all_key(), agent_id)
        else:
            self._local_storage[agent_id] = agent

        return agent

    async def get_agent(self, agent_id: str) -> AgentIdentity | None:
        """ดึงข้อมูล Agent ตาม ID"""
        if self._redis:
            data = await self._redis.get(self._get_key(agent_id))
            if data:
                return AgentIdentity.from_dict(json.loads(data))
            return None
        return self._local_storage.get(agent_id)

    async def get_agent_by_name(self, name: str) -> AgentIdentity | None:
        """ค้นหา Agent ตามชื่อ"""
        all_agents = await self.get_all_agents()
        for agent in all_agents:
            if agent.agent_name == name:
                return agent
        return None

    async def get_all_agents(self) -> list[AgentIdentity]:
        """ดึง Agents ทั้งหมด"""
        agents = []

        if self._redis:
            agent_ids = await self._redis.smembers(self._get_all_key())
            for agent_id in agent_ids:
                agent = await self.get_agent(agent_id)
                if agent:
                    agents.append(agent)
        else:
            agents = list(self._local_storage.values())

        return agents

    async def get_agents_by_type(self, agent_type: AgentType) -> list[AgentIdentity]:
        """ดึง Agents ตามประเภท"""
        all_agents = await self.get_all_agents()
        return [a for a in all_agents if a.agent_type == agent_type]

    async def get_agents_by_platform(self, platform: PlatformType) -> list[AgentIdentity]:
        """ดึง Agents ที่มีบัญชีบนแพลตฟอร์มนั้น"""
        all_agents = await self.get_all_agents()
        return [
            a for a in all_agents if any(acc.platform == platform for acc in a.accounts.values())
        ]

    async def add_account(
        self,
        agent_id: str,
        platform: PlatformType,
        account_id: str,
        username: str,
        credentials: dict[str, str] | None = None,
        **kwargs,
    ) -> AgentAccount | None:
        """เพิ่มบัญชีใหม่ให้กับ Agent"""
        agent = await self.get_agent(agent_id)
        if not agent:
            return None

        # Hash credentials ถ้ามี
        credentials_hash = None
        if credentials:
            cred_str = json.dumps(credentials, sort_keys=True)
            credentials_hash = hashlib.sha256(cred_str.encode()).hexdigest()

        account = AgentAccount(
            platform=platform,
            account_id=account_id,
            username=username,
            credentials_hash=credentials_hash,
            **kwargs,
        )

        agent.accounts[platform.value] = account
        agent.updated_at = datetime.now(UTC).isoformat()

        # บันทึก
        await self._save_agent(agent)

        return account

    async def update_agent_status(
        self, agent_id: str, is_available: bool | None = None, current_load: int | None = None
    ) -> bool:
        """อัพเดทสถานะ Agent"""
        agent = await self.get_agent(agent_id)
        if not agent:
            return False

        if is_available is not None:
            agent.is_available = is_available
        if current_load is not None:
            agent.current_load = current_load

        agent.updated_at = datetime.now(UTC).isoformat()
        await self._save_agent(agent)
        return True

    async def record_task_completion(self, agent_id: str, success: bool, response_time: float):
        """บันทึกสถิติการทำงาน"""
        agent = await self.get_agent(agent_id)
        if not agent:
            return

        if success:
            agent.completed_tasks += 1
        else:
            agent.failed_tasks += 1

        total = agent.completed_tasks + agent.failed_tasks
        agent.success_rate = agent.completed_tasks / total if total > 0 else 0

        # คำนวณ response time เฉลี่ย
        total_time = agent.response_time_avg * (total - 1) + response_time
        agent.response_time_avg = total_time / total if total > 0 else response_time

        # ปรับ reputation score
        if success:
            agent.reputation_score = min(100, agent.reputation_score + 0.1)
        else:
            agent.reputation_score = max(0, agent.reputation_score - 1)

        agent.updated_at = datetime.now(UTC).isoformat()
        await self._save_agent(agent)

    async def _save_agent(self, agent: AgentIdentity):
        """บันทึก Agent ลง storage"""
        if self._redis:
            await self._redis.set(self._get_key(agent.agent_id), json.dumps(agent.to_dict()))
        else:
            self._local_storage[agent.agent_id] = agent

    async def delete_agent(self, agent_id: str) -> bool:
        """ลบ Agent"""
        if self._redis:
            await self._redis.delete(self._get_key(agent_id))
            await self._redis.srem(self._get_all_key(), agent_id)
        else:
            self._local_storage.pop(agent_id, None)
        return True

    async def find_agents_by_capability(
        self, capability_name: str, min_skill_level: int = 1
    ) -> list[AgentIdentity]:
        """หา Agents ที่มีความสามารถเฉพาะ"""
        all_agents = await self.get_all_agents()
        matching = []
        for agent in all_agents:
            for cap in agent.capabilities:
                if cap.name == capability_name and cap.skill_level >= min_skill_level:
                    matching.append(agent)
                    break
        # เรียงตาม skill level และ reputation
        return sorted(
            matching,
            key=lambda a: (
                next((c.skill_level for c in a.capabilities if c.name == capability_name), 0),
                a.reputation_score,
            ),
            reverse=True,
        )


# Singleton instance
identity_manager = AgentIdentityManager()
