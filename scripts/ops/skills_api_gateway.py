"""
Skills API Gateway - ให้ Claude, Codex, Gemini API access ไปยังสกิลใน Obsidian Vault
FastAPI server serving skills at localhost:8000
"""

import json
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

app = FastAPI(
    title="Skills API Gateway",
    description="Central API for accessing AI agent skills from Obsidian vault",
    version="1.0.0",
)

# CORS for external AI services
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Paths
SKILLS_DIR = Path.home() / "Documents" / "ObsidianVault" / "Second Brain" / "brain" / "skills"
REGISTRY_FILE = (
    Path.home()
    / "Documents"
    / "ObsidianVault"
    / "Second Brain"
    / "brain"
    / "ai-gateway"
    / "skills-registry.json"
)


def get_registry() -> dict:
    """Load skills registry"""
    if REGISTRY_FILE.exists():
        return json.loads(REGISTRY_FILE.read_text(encoding="utf-8"))
    return {"skills": {}}


def parse_skill_content(content: str) -> dict:
    """Parse skill markdown with frontmatter"""
    result = {"metadata": {}, "body": ""}

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            # Parse frontmatter
            fm = parts[1]
            for line in fm.strip().split("\n"):
                if ":" in line:
                    k, v = line.split(":", 1)
                    result["metadata"][k.strip()] = v.strip().strip("\"'")
            result["body"] = parts[2].strip()
    else:
        result["body"] = content

    return result


# ==================== Health & Info ====================


@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "ok",
        "skills_directory": str(SKILLS_DIR),
        "registry_file": str(REGISTRY_FILE),
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/")
async def root():
    """API Overview"""
    return {
        "name": "Skills API Gateway",
        "version": "1.0.0",
        "description": "Access AI agent skills from Obsidian",
        "endpoints": {
            "/api/skills": "List all skills",
            "/api/skills/{skill_id}": "Get skill details",
            "/api/skills/{skill_id}/content": "Get full skill markdown",
            "/api/search": "Search skills (query param)",
            "/api/tags": "List all tags",
            "/docs": "Interactive API docs (Swagger)",
        },
    }


# ==================== Skills API ====================


@app.get("/api/skills")
async def list_skills(
    tag: str | None = Query(None, description="Filter by tag"),
    limit: int = Query(100, ge=1, le=1000),
):
    """List all available skills"""
    registry = get_registry()
    skills = list(registry.get("skills", {}).values())

    if tag:
        skills = [s for s in skills if tag in s.get("tags", [])]

    return {"total": len(skills), "skills": skills[:limit], "timestamp": datetime.now().isoformat()}


@app.get("/api/skills/{skill_id}")
async def get_skill(skill_id: str):
    """Get skill metadata"""
    registry = get_registry()
    skill = registry.get("skills", {}).get(skill_id)

    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}' not found")

    return skill


@app.get("/api/skills/{skill_id}/content")
async def get_skill_content(skill_id: str):
    """Get full skill content in markdown"""
    skill_file = SKILLS_DIR / f"{skill_id}.md"

    if not skill_file.exists():
        raise HTTPException(status_code=404, detail=f"Skill file '{skill_id}.md' not found")

    content = skill_file.read_text(encoding="utf-8")
    parsed = parse_skill_content(content)

    return {
        "skill_id": skill_id,
        "metadata": parsed["metadata"],
        "content": parsed["body"],
        "file_path": str(skill_file),
        "file_size_bytes": skill_file.stat().st_size,
        "last_modified": datetime.fromtimestamp(skill_file.stat().st_mtime).isoformat(),
    }


@app.get("/api/skills/{skill_id}/download")
async def download_skill(skill_id: str):
    """Download skill as markdown file"""
    skill_file = SKILLS_DIR / f"{skill_id}.md"

    if not skill_file.exists():
        raise HTTPException(status_code=404, detail=f"Skill '{skill_id}.md' not found")

    return FileResponse(skill_file, filename=f"{skill_id}.md", media_type="text/markdown")


# ==================== Search ====================


@app.get("/api/search")
async def search_skills(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(20, ge=1, le=100),
):
    """Search skills by name, description, or tags"""
    registry = get_registry()
    query = q.lower()

    results = []
    for skill_id, skill in registry.get("skills", {}).items():
        score = 0

        # Scoring
        if query in skill_id.lower():
            score += 10
        if query in skill.get("name", "").lower():
            score += 5
        if query in skill.get("description", "").lower():
            score += 3

        # Tags matching
        for tag in skill.get("tags", []):
            if query in tag.lower():
                score += 2

        if score > 0:
            results.append({"skill": skill, "relevance_score": score})

    # Sort by score
    results.sort(key=lambda x: x["relevance_score"], reverse=True)

    return {
        "query": q,
        "results_count": len(results),
        "results": results[:limit],
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/api/tags")
async def list_tags():
    """List all available tags across skills"""
    registry = get_registry()
    tags = {}

    for skill in registry.get("skills", {}).values():
        for tag in skill.get("tags", []):
            tags[tag] = tags.get(tag, 0) + 1

    return {
        "total_tags": len(tags),
        "tags": dict(sorted(tags.items())),
        "timestamp": datetime.now().isoformat(),
    }


# ==================== Registry ====================


@app.get("/api/registry")
async def get_full_registry():
    """Get full skills registry (for syncing)"""
    return get_registry()


@app.post("/api/refresh")
async def refresh_registry():
    """Manually trigger registry regeneration (runs migration script)"""
    import subprocess

    try:
        result = subprocess.run(
            ["python", "scripts/migrate_skills_to_obsidian.py"],
            cwd="c:\\brav os",
            capture_output=True,
            text=True,
            timeout=30,
        )

        return {
            "status": "success",
            "message": "Registry refreshed",
            "output": result.stdout,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Registry refresh failed: {str(e)}")


# ==================== AI Integration Info ====================


@app.get("/api/integrations")
async def integration_info():
    """Integration guide for Claude, Codex, Gemini, etc."""
    return {
        "integrations": {
            "claude": {
                "base_url": "http://localhost:8000/api",
                "endpoints": {
                    "list_skills": "GET /skills",
                    "get_skill": "GET /skills/{skill_id}",
                    "search": "GET /search?q=query",
                    "content": "GET /skills/{skill_id}/content",
                },
                "example": "curl http://localhost:8000/api/skills/brain-crew",
            },
            "codex": {
                "doc_url": "http://localhost:8000/api/skills/{skill_id}/content",
                "registry": "http://localhost:8000/api/registry",
                "note": "Pull skill content and inject into system prompt",
            },
            "gemini": {
                "retrieval_url": "http://localhost:8000/api/search",
                "usage": "Call /search endpoint with natural language query",
            },
        }
    }


if __name__ == "__main__":
    import uvicorn

    print("🚀 Starting Skills API Gateway...")
    print(f"📍 Skills directory: {SKILLS_DIR}")
    print(f"📍 Registry file: {REGISTRY_FILE}")
    print()
    print("Access at: http://localhost:8000")
    print("Docs at: http://localhost:8000/docs")
    print()

    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
