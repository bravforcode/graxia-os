"""Project indexer — scans a directory, classifies files, estimates tokens, creates ProjectIndex.

Never reads excluded file contents. Handles binary files safely.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from app.context_engine.exclusions import ExclusionPolicy
from app.context_engine.schemas import ProjectFileInfo, ProjectIndex
from app.context_engine.token_estimator import estimate_file_tokens

logger = logging.getLogger(__name__)

# Language mapping by extension
_EXT_LANG: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".rb": "ruby",
    ".php": "php",
    ".cs": "csharp",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".swift": "swift",
    ".scala": "scala",
    ".r": "r",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "bash",
    ".ps1": "powershell",
    ".bat": "batch",
    ".cmd": "batch",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".toml": "toml",
    ".ini": "ini",
    ".cfg": "ini",
    ".md": "markdown",
    ".rst": "rst",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".dockerfile": "dockerfile",
    ".vue": "vue",
    ".svelte": "svelte",
    ".astro": "astro",
}

# Path-based detection patterns
_BACKEND_DIRS = {"backend/", "backend\\", "app/", "api/", "src/"}
_FRONTEND_DIRS = {"frontend/", "frontend\\", "client/", "ui/"}
_SCRIPT_DIRS = {"scripts/", "script/"}
_DOCS_DIRS = {"docs/", "doc/"}
_TEST_PATTERNS = [re.compile(r"test_.*\.py$"), re.compile(r".*_test\.py$"), re.compile(r".*\.test\.(ts|js|tsx|jsx)$"), re.compile(r".*\.spec\.(ts|js|tsx|jsx)$")]
_MIGRATION_PATTERNS = [re.compile(r".*alembic.*"), re.compile(r".*migration.*"), re.compile(r".*migrate.*")]
_CONFIG_PATTERNS = [re.compile(r".*\.(env|conf|config)\..*")]


class ProjectIndexer:
    """Builds a ProjectIndex by scanning a root directory.

    Classifies files, estimates tokens, applies exclusion policy.
    """

    def __init__(self, exclusion_policy: ExclusionPolicy | None = None) -> None:
        self.exclusion_policy = exclusion_policy or ExclusionPolicy()

    def build_index(self, root_path: str, max_files: int = 5000) -> ProjectIndex:
        """Build a ProjectIndex for the given root path."""
        root = Path(root_path).resolve()
        files: list[ProjectFileInfo] = []
        excluded: list[ProjectFileInfo] = []
        warnings: list[str] = []
        total_tokens = 0

        if not root.exists():
            warnings.append(f"Root path does not exist: {root_path}")
            return ProjectIndex(
                root_path=str(root),
                generated_at=datetime.now(UTC).isoformat(),
                warnings=warnings,
            )

        scanned = 0
        for entry in root.rglob("*"):
            if not entry.is_file():
                continue

            scanned += 1
            if scanned > max_files:
                warnings.append(f"Reached max file scan limit: {max_files}")
                break

            rel_path = str(entry.relative_to(root)).replace("\\", "/")
            info = self._build_file_info(entry, rel_path)

            # Check exclusion (ExclusionPolicy handles all patterns including directories)
            excluded_flag, reason = self.exclusion_policy.should_exclude(entry)
            if excluded_flag:
                info.excluded_reason = reason or "excluded by policy"
                info.is_indexed = False
                excluded.append(info)
                continue

            # Check binary
            if self.exclusion_policy.is_binary_likely(entry):
                info.excluded_reason = "binary file"
                info.is_indexed = False
                excluded.append(info)
                continue

            # Index safe file
            try:
                info.sha256 = self.hash_file(entry)
                info.estimated_tokens = estimate_file_tokens(entry)
                info.is_indexed = True

                # Generate summary for source files
                if info.category in ("backend", "frontend", "test", "script", "migration", "config"):
                    info.summary = self._summarize_file(entry, max_chars=500)

                total_tokens += info.estimated_tokens
            except (OSError, UnicodeDecodeError) as exc:
                warnings.append(f"Could not read safe file: {rel_path} ({exc})")
                info.is_indexed = False

            files.append(info)

        return ProjectIndex(
            root_path=str(root),
            generated_at=datetime.now(UTC).isoformat(),
            total_files_seen=len(files) + len(excluded),
            total_files_indexed=len(files),
            total_files_excluded=len(excluded),
            total_estimated_tokens=total_tokens,
            files=files,
            excluded=excluded,
            warnings=warnings,
        )

    def _build_file_info(self, entry: Path, rel_path: str) -> ProjectFileInfo:
        """Build basic ProjectFileInfo from path metadata."""
        try:
            stat = entry.stat()
            size = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime, tz=UTC).isoformat() if stat.st_mtime else None
        except OSError:
            size = 0
            mtime = None

        return ProjectFileInfo(
            path=rel_path,
            language=_EXT_LANG.get(entry.suffix.lower()),
            size_bytes=size,
            category=self.classify_file(entry),
            modified_at=mtime,
        )

    def classify_file(self, path: Path) -> str:
        """Classify a file into a category based on path and name."""
        path_str = str(path).replace("\\", "/")
        name = path.name.lower()

        # Test files
        for pattern in _TEST_PATTERNS:
            if pattern.search(name) or pattern.search(path_str):
                return "test"

        # Migration files
        for pattern in _MIGRATION_PATTERNS:
            if pattern.search(path_str):
                return "migration"

        # Config files
        for pattern in _CONFIG_PATTERNS:
            if pattern.search(path_str):
                return "config"

        # Backend files
        if any(d in path_str for d in {"backend/", "app/"}) and path.suffix in {".py", ".sql"}:
            return "backend"

        # Frontend files
        if any(d in path_str for d in {"frontend/", "client/", "ui/"}):
            return "frontend"

        # Script files
        if "scripts/" in path_str and path.suffix in {".sh", ".py", ".ps1", ".bat"}:
            return "script"

        # Docs files
        if "docs/" in path_str:
            return "docs"

        # Config by extension
        if path.suffix in {".yml", ".yaml", ".toml", ".ini", ".cfg"}:
            return "config"

        return "unknown"

    @staticmethod
    def hash_file(path: Path) -> str:
        """Compute SHA-256 hash of a file safely."""
        try:
            data = path.read_bytes()
            return hashlib.sha256(data).hexdigest()
        except OSError:
            return ""

    @staticmethod
    def _summarize_file(path: Path, max_chars: int = 500) -> str:
        """Generate a deterministic summary of a safe file.

        Extracts first relevant lines, class/function names, routes, test names.
        No LLM summarization.
        """
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except (OSError, UnicodeDecodeError):
            return ""

        lines = text.split("\n")
        summary_parts: list[str] = []

        # Detect classes
        classes = []
        for line in lines[:200]:
            m = re.search(r"^\s*(?:class|def)\s+(\w+)", line)
            if m:
                classes.append(m.group(1))
        if classes:
            summary_parts.append(f"symbols: {', '.join(classes[:10])}")

        # Detect FastAPI routes
        routes = []
        for line in lines[:200]:
            m = re.search(r'@(?:router|app)\.(?:get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)', line)
            if m:
                routes.append(m.group(1))
        if routes:
            summary_parts.append(f"routes: {', '.join(routes[:5])}")

        # Detect SQLAlchemy models
        models = []
        for line in lines[:100]:
            m = re.search(r"class\s+(\w+)\s*\(.*Base\)", line)
            if m:
                models.append(m.group(1))
        if models:
            summary_parts.append(f"models: {', '.join(models[:5])}")

        # Detect test functions
        tests = []
        for line in lines[:200]:
            m = re.search(r"^\s*(?:async\s+)?def\s+(test_\w+)", line)
            if m:
                tests.append(m.group(1))
        if tests:
            summary_parts.append(f"tests: {', '.join(tests[:8])}")

        summary = " | ".join(summary_parts[:8]) if summary_parts else text[:200].replace("\n", " ").strip()
        return summary[:max_chars]
