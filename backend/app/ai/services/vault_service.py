"""
Vault Service - Obsidian vault integration service
"""

import os
from typing import Any

import httpx

from ..models import (
    SkillInfo,
    SkillSearchResponse,
    VaultFile,
    VaultHealthMetrics,
    VaultQueryRequest,
    VaultQueryResponse,
)


class VaultService:
    """Service for interacting with Obsidian vault via MCP server"""

    def __init__(self):
        self.mcp_host = os.getenv("MCP_HOST", "127.0.0.1")
        self.mcp_port = os.getenv("MCP_PORT", "8001")
        self.base_url = f"http://{self.mcp_host}:{self.mcp_port}/api/v1"
        self.http_client = httpx.AsyncClient(timeout=30.0)

    async def query(self, request: VaultQueryRequest) -> VaultQueryResponse:
        """Query vault with various search types"""

        if request.search_type == "semantic":
            # For now, fall back to keyword search
            results = await self.search(request.query, request.limit)
        elif request.search_type == "keyword":
            results = await self.search(request.query, request.limit)
        elif request.search_type == "graph":
            # Query knowledge graph
            results = await self._graph_query(request.query, request.limit)
        else:
            results = await self.search(request.query, request.limit)

        # Convert to VaultFile objects
        files = [
            VaultFile(
                path=r["path"],
                name=r["name"],
                relevance_score=r.get("score", 0.0),
                content_preview=r.get("snippet"),
                tags=r.get("metadata", {}).get("tags") if "metadata" in r else None,
            )
            for r in results
        ]

        # Get skills suggestions
        skills = await self.search_skills(request.query)
        skill_ids = [s.id for s in skills.results] if skills else None

        return VaultQueryResponse(
            query=request.query, total_results=len(files), files=files, skills_suggested=skill_ids
        )

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """Search vault content"""

        try:
            response = await self.http_client.post(
                f"{self.base_url}/vault/search",
                json={"query": query, "limit": limit, "include_content": True},
            )
            response.raise_for_status()
            data = response.json()
            return data.get("results", [])
        except Exception:
            return []

    async def get_file(self, file_path: str) -> str:
        """Get file content from vault"""

        try:
            response = await self.http_client.post(
                f"{self.base_url}/vault/read", json={"path": file_path, "include_metadata": False}
            )
            response.raise_for_status()
            data = response.json()
            return data.get("content", "")
        except Exception:
            raise FileNotFoundError(f"Could not read file: {file_path}")

    async def get_stats(self) -> VaultHealthMetrics:
        """Get vault health metrics"""

        try:
            response = await self.http_client.post(
                f"{self.base_url}/analytics", json={"metric_type": "summary"}
            )
            response.raise_for_status()
            data = response.json()

            # Get orphans
            orphan_response = await self.http_client.post(
                f"{self.base_url}/analytics", json={"metric_type": "orphans"}
            )
            orphan_data = orphan_response.json() if orphan_response.status_code == 200 else {}

            # Get tasks
            task_response = await self.http_client.post(
                f"{self.base_url}/vault/tasks", json={"status": "all", "limit": 200}
            )
            task_data = task_response.json() if task_response.status_code == 200 else {}

            return VaultHealthMetrics(
                total_files=data.get("total_files", 0),
                orphaned_files=orphan_data.get("orphaned_files", 0),
                broken_links=0,  # Would need separate query
                missing_frontmatter=0,
                tasks_pending=task_data.get("pending", 0),
                tasks_completed=task_data.get("completed", 0),
                last_optimization=None,
            )
        except Exception:
            return VaultHealthMetrics(
                total_files=0,
                orphaned_files=0,
                broken_links=0,
                missing_frontmatter=0,
                tasks_pending=0,
                tasks_completed=0,
                last_optimization=None,
            )

    async def search_skills(self, query: str, limit: int = 5) -> SkillSearchResponse:
        """Search skills registry"""

        try:
            response = await self.http_client.post(
                f"{self.base_url}/skills/query", json={"query": query, "limit": limit}
            )
            response.raise_for_status()
            data = response.json()

            skills = [
                SkillInfo(
                    id=s["id"],
                    name=s["name"],
                    description=s.get("description", ""),
                    category=s.get("category", ""),
                    family=s.get("family", ""),
                    tags=[],  # Would come from registry
                    estimated_tokens=s.get("estimated_tokens", 0),
                    path=s.get("path", ""),
                )
                for s in data.get("results", [])
            ]

            return SkillSearchResponse(
                query=query, total_matches=data.get("total_matches", 0), skills=skills
            )
        except Exception:
            return SkillSearchResponse(query=query, total_matches=0, skills=[])

    async def load_skill(self, skill_id: str, include_content: bool = True) -> dict[str, Any]:
        """Load a specific skill"""

        try:
            response = await self.http_client.post(
                f"{self.base_url}/skills/load",
                json={"skill_id": skill_id, "include_content": include_content},
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    async def search_skills_for_task(self, task_description: str) -> list[dict[str, Any]]:
        """Search skills relevant to a task"""

        result = await self.search_skills(task_description, limit=5)

        return [{"id": s.id, "name": s.name, "description": s.description} for s in result.skills]

    async def get_skill_categories(self) -> dict[str, Any]:
        """Get all skill categories"""

        try:
            response = await self.http_client.get(f"{self.base_url}/skills/categories")
            response.raise_for_status()
            return response.json()
        except Exception:
            return {"categories": []}

    async def auto_classify(self, dry_run: bool = True, max_files: int = 50) -> dict[str, Any]:
        """Run auto classifier"""

        try:
            response = await self.http_client.post(
                f"{self.base_url}/auto/classify", json={"dry_run": dry_run, "max_files": max_files}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def auto_link(self, dry_run: bool = True, limit: int = 100) -> dict[str, Any]:
        """Run auto linker"""

        try:
            response = await self.http_client.post(
                f"{self.base_url}/auto/link", json={"dry_run": dry_run, "limit": limit}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def optimize_all(self) -> dict[str, Any]:
        """Run full vault optimization"""

        try:
            response = await self.http_client.post(f"{self.base_url}/auto/optimize", json={})
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _graph_query(self, query: str, limit: int) -> list[dict]:
        """Query knowledge graph"""

        # This would integrate with the graph tools
        # For now, return empty
        return []

    async def close(self):
        """Close HTTP client"""
        await self.http_client.aclose()
