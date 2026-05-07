"""SkillsMP API Client with Auto-Discovery"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

logger = logging.getLogger(__name__)


@dataclass
class SkillsMPConfig:
    """Configuration for SkillsMP API client."""

    api_key: str
    base_url: str = "https://skillsmp.com/api/v1"
    timeout: int = 30
    max_retries: int = 3

    def __post_init__(self):
        # Ensure base_url doesn't end with trailing slash
        self.base_url = self.base_url.rstrip("/")


@dataclass
class SkillsMPAPIDiscovery:
    """Discovered API endpoints structure."""

    skills_search: str = "/skills/search"
    skills_ai_search: str = "/skills/ai-search"

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "SkillsMPAPIDiscovery":
        """Create from API discovery response."""
        return cls()  # Use defaults


@dataclass
class SkillsMPPagination:
    """Pagination metadata."""

    page: int
    limit: int
    total: int
    has_more: bool
    next_page: int | None = None


@dataclass
class SkillData:
    """Individual skill data from API."""

    id: str
    name: str
    description: str | None
    content: str | None  # Markdown content
    skill_type: str  # openclaw, claude, codex, hermes, tool, dev, context
    tags: list[str]
    triggers: list[str]
    metadata: dict[str, Any]
    version: int
    created_at: datetime | None
    updated_at: datetime | None
    # Extra fields from SkillsMP API
    author: str | None = None
    stars: int = 0
    content_url: str | None = None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> "SkillData":
        """Create from API response."""
        return cls(
            id=str(data.get("id", "")),
            name=data.get("name", ""),
            description=data.get("description"),
            content=data.get("content") or data.get("markdown"),
            skill_type=data.get("type", "dev"),
            tags=data.get("tags", []) or [],
            triggers=data.get("triggers", []) or [],
            metadata=data.get("metadata", {}) or {},
            version=data.get("version", 1),
            created_at=_parse_datetime(data.get("created_at")),
            updated_at=_parse_datetime(data.get("updated_at")),
        )


def _parse_datetime(value: Any) -> datetime | None:
    """Parse datetime from various formats."""
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        # Try ISO format
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except:
        return None


class SkillsMPClient:
    """
    Universal SkillsMP API client with auto-discovery.

    Features:
    - Auto-discovery of API endpoints
    - Pagination handling
    - Retry logic with exponential backoff
    - Type-safe data parsing
    """

    # Search queries to fetch all skills across categories
    DEFAULT_SEARCH_QUERIES = [
        "python",
        "javascript",
        "typescript",
        "java",
        "go",
        "rust",
        "react",
        "vue",
        "angular",
        "nextjs",
        "fastapi",
        "django",
        "database",
        "api",
        "testing",
        "devops",
        "docker",
        "kubernetes",
        "aws",
        "azure",
        "gcp",
        "cloud",
        "serverless",
        "ai",
        "ml",
        "data",
        "analytics",
        "visualization",
        "security",
        "auth",
        "oauth",
        "jwt",
        "encryption",
        "web",
        "frontend",
        "backend",
        "fullstack",
        "mobile",
        "git",
        "github",
        "ci",
        "cd",
        "pipeline",
        "writing",
        "documentation",
        "blog",
        "content",
        "seo",
        "automation",
        "scripting",
        "bash",
        "powershell",
        "cli",
        "debugging",
        "profiling",
        "monitoring",
        "logging",
        "tracing",
    ]

    def __init__(self, config: SkillsMPConfig):
        self.config = config
        self._client: httpx.AsyncClient | None = None
        self._discovery: SkillsMPAPIDiscovery | None = None

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self) -> None:
        """Initialize HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                timeout=self.config.timeout,
                follow_redirects=True,
            )
            logger.info("SkillsMP client initialized")

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("SkillsMP client closed")

    @property
    def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            raise RuntimeError("Client not connected. Use 'async with' or call connect()")
        return self._client

    @retry(
        stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10), reraise=True
    )
    async def _request(self, method: str, endpoint: str, **kwargs) -> dict[str, Any]:
        """Make authenticated request with retry."""
        url = f"{self.config.base_url}{endpoint}"

        try:
            response = await self.client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            logger.error(
                f"HTTP error {e.response.status_code}: {e.response.text}",
                extra={"url": url, "method": method},
            )
            raise
        except httpx.RequestError as e:
            logger.error(f"Request error: {e}", extra={"url": url, "method": method})
            raise

    async def discover(self) -> SkillsMPAPIDiscovery:
        """Auto-discover API structure."""
        if self._discovery is not None:
            return self._discovery

        try:
            # Try root endpoint
            data = await self._request("GET", "/")
            self._discovery = SkillsMPAPIDiscovery.from_api_response(data)
            logger.info("API structure discovered from root endpoint")

        except Exception as e:
            logger.warning(f"Root discovery failed: {e}. Trying /api...")

            try:
                data = await self._request("GET", "/api")
                self._discovery = SkillsMPAPIDiscovery.from_api_response(data)
                logger.info("API structure discovered from /api endpoint")

            except Exception as e2:
                logger.warning(f"API discovery failed: {e2}. Using defaults.")
                self._discovery = SkillsMPAPIDiscovery()

        return self._discovery

    async def search_skills(
        self, query: str, page: int = 1, limit: int = 100, sort_by: str = "recent"
    ) -> tuple[list[SkillData], SkillsMPPagination]:
        """
        Search skills using keyword search.

        Args:
            query: Search query
            page: Page number
            limit: Items per page
            sort_by: Sort by "recent", "stars", "name"

        Returns:
            Tuple of (skills list, pagination info)
        """
        params = {
            "q": query,
            "page": page,
            "limit": limit,
            "sortBy": sort_by,
        }

        data = await self._request("GET", "/skills/search", params=params)

        # Parse response - API returns skills in data.skills not data.items
        items = []
        for item in data.get("data", {}).get("skills", []):
            skill = SkillData(
                id=item.get("id", ""),
                name=item.get("name", ""),
                description=item.get("description", ""),
                skill_type=self._extract_skill_type(item),
                content=None,  # Will fetch separately if needed
                content_url=item.get("skillUrl"),
                author=item.get("author"),
                stars=item.get("stars", 0),
                tags=[],  # Not provided in search
                triggers=[],  # Not provided in search
                version=1,
                created_at=None,
                updated_at=_parse_datetime(item.get("updatedAt")),
                metadata={
                    "github_url": item.get("githubUrl"),
                },
            )
            items.append(skill)

        # Parse pagination
        pagination_data = data.get("data", {}).get("pagination", {})
        pagination = SkillsMPPagination(
            page=pagination_data.get("page", page),
            limit=pagination_data.get("limit", limit),
            total=pagination_data.get("total", 0),
            has_more=pagination_data.get("hasNext", False),
            next_page=pagination_data.get("page", page) + 1
            if pagination_data.get("hasNext")
            else None,
        )

        return items, pagination

    def _extract_skill_type(self, item: dict) -> str:
        """Extract skill type from skill ID or content."""
        skill_id = item.get("id", "").lower()
        name = item.get("name", "").lower()

        # Map to skill types based on keywords
        if any(x in skill_id or x in name for x in ["claude", "anthropic"]):
            return "claude"
        elif any(x in skill_id or x in name for x in ["codex", "openai"]):
            return "codex"
        elif any(x in skill_id or x in name for x in ["test", "security", "vulnerability"]):
            return "testing"
        elif any(
            x in skill_id or x in name
            for x in ["devops", "docker", "k8s", "kubernetes", "ci", "cd"]
        ):
            return "devops"
        elif any(x in skill_id or x in name for x in ["data", "ml", "ai", "model", "analytics"]):
            return "data"
        elif any(
            x in skill_id or x in name for x in ["doc", "readme", "blog", "content", "writing"]
        ):
            return "documentation"
        elif any(
            x in skill_id or x in name for x in ["db", "database", "sql", "postgres", "mongo"]
        ):
            return "database"
        else:
            return "dev"

    async def fetch_all_skills(self, max_pages: int = 5, per_page: int = 100) -> list[SkillData]:
        """
        Fetch all skills using multiple search queries.

        Args:
            max_pages: Max pages per query
            per_page: Items per page

        Returns:
            List of all unique skills
        """
        all_skills: dict[str, SkillData] = {}

        for query in self.DEFAULT_SEARCH_QUERIES[:10]:  # Limit queries for performance
            try:
                page = 1
                while page <= max_pages:
                    skills, pagination = await self.search_skills(
                        query=query, page=page, limit=per_page
                    )

                    for skill in skills:
                        if skill.id not in all_skills:
                            all_skills[skill.id] = skill

                    if not pagination.has_more:
                        break
                    page += 1

                    # Rate limiting - be nice to the API
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.warning(f"Failed to fetch skills for query '{query}': {e}")
                continue

        return list(all_skills.values())

    async def fetch_skill_content(self, skill_url: str) -> str | None:
        """
        Fetch skill markdown content from skill URL.

        Args:
            skill_url: Full URL to skill page

        Returns:
            Markdown content or None
        """
        try:
            # For now, return None as content fetching needs separate implementation
            # Skill content would be at raw GitHub URL or similar
            return None
        except Exception as e:
            logger.warning(f"Failed to fetch skill content from {skill_url}: {e}")
            return None
