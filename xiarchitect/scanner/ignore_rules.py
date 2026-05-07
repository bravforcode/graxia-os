"""
xiarchitect.scanner.ignore_rules — .gitignore + built-in ignore rules
"""

import re
from pathlib import Path
from typing import List, Set


class IgnoreRules:
    """Manages file ignore patterns"""
    
    # Built-in ignore patterns (always applied)
    BUILTIN_PATTERNS = [
        # Build artifacts
        "node_modules/",
        ".venv/",
        "venv/",
        "env/",
        "dist/",
        "build/",
        "out/",
        ".next/",
        ".nuxt/",
        "target/",
        "__pycache__/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        
        # Version control
        ".git/",
        ".svn/",
        ".hg/",
        ".claude/",
        ".codex/",
        ".cursor/",
        ".kiro/",
        ".superpowers/",
        ".trunk/",
        ".windsurf/",
        ".worktrees/",
        ".antigravity/",
        
        # IDE and OS
        ".DS_Store",
        ".vscode/",
        ".idea/",
        "*.suo",
        "Thumbs.db",
        
        # Dependency locks (read package.json instead)
        "pnpm-lock.yaml",
        "yarn.lock",
        "package-lock.json",
        
        # Generated
        "coverage/",
        ".cache/",
        "*.min.js",
        "*.min.css",
        
        # Media
        "*.png",
        "*.jpg",
        "*.jpeg",
        "*.gif",
        "*.svg",
        "*.ico",
        "*.mp4",
        "*.mp3",
        "*.wav",
        "*.mov",
        "*.avi",
        
        # Archives
        "*.zip",
        "*.tar",
        "*.gz",
        "*.bz2",
        "*.7z",
        "*.rar",
        
        # Logs
        "*.log",
        "*.logs",
    ]
    
    # Secret patterns (never read content)
    SECRET_PATTERNS = [
        r"^\.env(\..+)?$",
        r"\.(pem|key|crt|pfx|p12)$",
        r"(_rsa|_dsa|_ecdsa|_ed25519)$",
        r"private[_-]?key",
        r"secret[_-]?key",
    ]
    
    # Always include (never skip)
    ALWAYS_INCLUDE = [
        "README.md",
        "CONTRIBUTING.md",
        "ARCHITECTURE.md",
        "package.json",
        "pyproject.toml",
        "requirements.txt",
        "requirements-dev.txt",
        "setup.py",
        "Cargo.toml",
        "go.mod",
        "docker-compose.yml",
        "docker-compose.*.yml",
        "Dockerfile",
        "Dockerfile.*",
        ".env.example",
        "tsconfig.json",
        "vite.config.ts",
        "next.config.js",
        "turbo.json",
        "nx.json",
        "pnpm-workspace.yaml",
        "alembic.ini",
    ]
    
    def __init__(self, workspace_root: Path, additional_patterns: List[str] = None):
        """
        Initialize ignore rules.
        
        Args:
            workspace_root: Root directory of workspace
            additional_patterns: Additional user-defined patterns
        """
        self.workspace_root = workspace_root
        self.patterns: Set[str] = set(self.BUILTIN_PATTERNS)
        self.secret_patterns = [re.compile(p, re.IGNORECASE) for p in self.SECRET_PATTERNS]
        
        if additional_patterns:
            self.patterns.update(additional_patterns)
        
        # Load .gitignore if exists
        self._load_gitignore()
    
    def _load_gitignore(self):
        """Load patterns from .gitignore"""
        gitignore_path = self.workspace_root / ".gitignore"
        if gitignore_path.exists():
            try:
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            self.patterns.add(line)
            except Exception:
                pass  # Silently fail if .gitignore can't be read
    
    def should_ignore(self, path: Path) -> bool:
        """
        Check if a path should be ignored.
        
        Args:
            path: Path to check (relative to workspace root)
        
        Returns:
            True if path should be ignored
        """
        path_str = str(path)
        
        # Check if in always-include list
        if any(pattern in path_str for pattern in self.ALWAYS_INCLUDE):
            return False
        
        # Check against patterns
        for pattern in self.patterns:
            if self._matches_pattern(path_str, pattern):
                return True
        
        return False
    
    def is_sensitive(self, path: Path) -> bool:
        """
        Check if a file contains sensitive data (secrets).
        
        Args:
            path: Path to check
        
        Returns:
            True if file is sensitive
        """
        path_str = str(path)
        return any(pattern.search(path_str) for pattern in self.secret_patterns)
    
    @staticmethod
    def _matches_pattern(path: str, pattern: str) -> bool:
        """
        Check if path matches a gitignore-style pattern.
        
        Args:
            path: Path string
            pattern: Pattern string
        
        Returns:
            True if matches
        """
        # Simple pattern matching (not full gitignore spec)
        if pattern.endswith("/"):
            # Directory pattern
            return pattern.rstrip("/") in path
        elif "*" in pattern:
            # Wildcard pattern
            regex = pattern.replace(".", r"\.").replace("*", ".*")
            return bool(re.search(regex, path))
        else:
            # Exact match
            return pattern in path
