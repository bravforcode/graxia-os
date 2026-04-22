import logging
from pathlib import Path
from typing import Any
import yaml

from app.config import settings

logger = logging.getLogger(__name__)

class ObsidianHub:
    def __init__(self):
        self.vault_path = getattr(settings, "OBSIDIAN_VAULT_PATH", None)
        
    def write_research(self, date_str: str, summary: str):
        if not self.vault_path:
            return
        p = Path(self.vault_path) / "Research"
        p.mkdir(parents=True, exist_ok=True)
        file_path = p / f"{date_str}.md"
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"\n## Research Digest\n{summary}\n")

    async def search_vault(self, query: str, top_k: int = 5) -> str:
        if not self.vault_path:
            return ""
            
        p = Path(self.vault_path)
        if not p.exists():
            return ""
            
        md_files = list(p.rglob("*.md"))
        results = []
        
        query_words = set(query.lower().split())
        
        for f in md_files:
            try:
                content = f.read_text(encoding="utf-8")
                content_lower = content.lower()
                matches = sum(1 for w in query_words if w in content_lower)
                if matches > 0:
                    results.append((matches, f.name, content))
            except Exception:
                pass
                
        results.sort(key=lambda x: x[0], reverse=True)
        top_results = results[:top_k]
        
        if not top_results:
            return ""
            
        snippets = []
        for _, name, content in top_results:
            snippets.append(f"Source: {name}\n{content[:500]}...")
            
        ctx_text = "\n\n".join(snippets)
        return f"<context>\n{ctx_text}\n</context>"

obsidian_hub = ObsidianHub()
