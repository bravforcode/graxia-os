"""Secret-safe exclusion policy — controls which files are excluded from indexing.

Never reads excluded file contents. Only uses path/name metadata.
"""
from __future__ import annotations

import fnmatch
import os
from pathlib import Path


class ExclusionPolicy:
    """Policy for excluding secret, sensitive, or irrelevant files from indexing.

    Excludes by path pattern only — never reads excluded file contents.
    """

    def __init__(self) -> None:
        self._exact_patterns: set[str] = {
            # Secret files — never index
            ".env",
            ".env.local",
            ".env.development",
            ".env.staging",
            ".env.production",
            ".env.example",
            # Keys and certificates
            "*.pem",
            "*.key",
            "*.p12",
            "*.pfx",
            "id_rsa",
            "id_rsa.pub",
            "id_ed25519",
            "id_ed25519.pub",
            # Credentials
            "secrets.*",
            "credentials.*",
            "service-account*.json",
            "google-credentials*.json",
            # Git
            ".git/",
            ".gitignore",
            ".gitattributes",
            ".gitmodules",
        }

        self._dir_patterns: set[str] = {
            # Dependencies
            "node_modules/",
            ".venv/",
            "venv/",
            ".tox/",
            ".nox/",
            # Cache
            "__pycache__/",
            ".pytest_cache/",
            ".mypy_cache/",
            ".ruff_cache/",
            ".cache/",
            ".hypothesis/",
            # Build
            "dist/",
            "build/",
            ".next/",
            ".nuxt/",
            # Coverage
            "coverage/",
            "htmlcov/",
            ".coverage*",
            # Logs
            "logs/",
            # OS
            ".DS_Store",
            "Thumbs.db",
        }

        self._ext_exclusions: set[str] = {
            ".pyc",
            ".pyo",
            ".so",
            ".dll",
            ".dylib",
            ".exe",
            ".bin",
            ".o",
            ".a",
            ".lib",
            ".obj",
            ".min.js",
            ".min.css",
            ".map",
            ".sqlite",
            ".sqlite3",
            ".db",
            ".dump",
            ".bak",
            ".log",
            ".cache",
        }

        self._large_generated_exclusions: set[str] = {
            "package-lock.json",
            "pnpm-lock.yaml",
            "yarn.lock",
            "bun.lock",
            "bun.lockb",
            "Gemfile.lock",
            "poetry.lock",
            "Cargo.lock",
            "go.sum",
        }

    def should_exclude(self, path: Path) -> tuple[bool, str | None]:
        """Check if a path should be excluded.

        Returns (excluded: bool, reason: str | None).
        Never reads file contents.
        """
        path_str = str(path)
        name = path.name
        ext = path.suffix.lower()

        # Check exact patterns
        for pattern in self._exact_patterns:
            if fnmatch.fnmatch(name, pattern):
                return True, f"Matched secret pattern: {pattern}"

        # Check large generated files
        if name in self._large_generated_exclusions:
            return True, f"Large generated file: {name}"

        # Check directory patterns in path
        normalized_path = path_str.replace("\\", "/") + "/"
        for pattern in self._dir_patterns:
            norm_pattern = pattern.rstrip("/")
            # Check both with leading slash (subdirectory) and as start of path
            if f"/{norm_pattern}/" in normalized_path or normalized_path.startswith(f"{norm_pattern}/"):
                return True, f"Matched directory pattern: {pattern}"

        # Check extension exclusions
        if ext in self._ext_exclusions:
            return True, f"Matched extension exclusion: {ext}"

        # Check dotfiles at root (but not .py, .env, etc. — env already handled)
        if name.startswith(".") and ext not in {".py", ".md", ".yml", ".yaml", ".toml", ".cfg", ".ini", ".txt", ".json"}:
            # Allow common config dotfiles
            allowed_dotfiles = {
                ".python-version",
                ".pre-commit-config.yaml",
                ".editorconfig",
                ".dockerignore",
                ".vercelignore",
                ".cursorrules",
                ".windsurfrules",
                ".openclaude-profile.json",
            }
            if name not in allowed_dotfiles:
                return True, f"Unknown dotfile: {name}"

        return False, None

    def is_binary_likely(self, path: Path) -> bool:
        """Check if a file is likely binary based on extension."""
        binary_exts = {
            ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg",
            ".woff", ".woff2", ".ttf", ".eot",
            ".mp3", ".mp4", ".avi", ".mov",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
            ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
            ".wasm",
        }
        return path.suffix.lower() in binary_exts

    def get_all_excluded_patterns(self) -> list[str]:
        """Get all exclusion patterns for reporting."""
        patterns = list(self._exact_patterns)
        patterns.extend(f"dir:{p}" for p in self._dir_patterns)
        patterns.extend(f"ext:{p}" for p in self._ext_exclusions)
        patterns.extend(f"large:{p}" for p in self._large_generated_exclusions)
        return sorted(patterns)

    @property
    def count(self) -> int:
        return len(self._exact_patterns) + len(self._dir_patterns) + len(self._ext_exclusions) + len(self._large_generated_exclusions)
