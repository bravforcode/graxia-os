"""
xiarchitect.scanner.file_walker — Recursive file traversal
"""

import hashlib
from pathlib import Path
from typing import Iterator, List, Optional

from ..core.logger import get_logger
from ..core.types import Language, ScannedFile
from .ignore_rules import IgnoreRules

logger = get_logger(__name__)


class FileWalker:
    """Walks workspace directory tree and yields scanned files"""
    
    # Binary file extensions to skip
    BINARY_EXTENSIONS = {
        ".pyc", ".pyo", ".so", ".dylib", ".dll", ".exe",
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg",
        ".mp4", ".mp3", ".wav", ".mov", ".avi",
        ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar",
        ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    }
    
    # Language detection by extension
    LANGUAGE_MAP = {
        ".py": Language.PYTHON,
        ".ts": Language.TYPESCRIPT,
        ".tsx": Language.TYPESCRIPT,
        ".js": Language.JAVASCRIPT,
        ".jsx": Language.JAVASCRIPT,
        ".go": Language.GO,
        ".rs": Language.RUST,
        ".yaml": Language.YAML,
        ".yml": Language.YAML,
        ".json": Language.JSON,
        ".toml": Language.TOML,
        ".md": Language.MARKDOWN,
        ".sh": Language.SHELL,
        ".bash": Language.SHELL,
    }
    
    def __init__(
        self,
        workspace_root: Path,
        ignore_rules: IgnoreRules,
        max_file_size_kb: int = 1024,
    ):
        """
        Initialize file walker.
        
        Args:
            workspace_root: Root directory to scan
            ignore_rules: Ignore rules instance
            max_file_size_kb: Maximum file size to read (KB)
        """
        self.workspace_root = workspace_root
        self.ignore_rules = ignore_rules
        self.max_file_size_bytes = max_file_size_kb * 1024
    
    def walk(self) -> Iterator[ScannedFile]:
        """
        Walk workspace and yield scanned files.
        
        Yields:
            ScannedFile instances
        """
        for file_path in self._walk_directory(self.workspace_root):
            scanned_file = self._scan_file(file_path)
            if scanned_file:
                yield scanned_file
    
    def _walk_directory(self, directory: Path) -> Iterator[Path]:
        """
        Recursively walk directory.
        
        Args:
            directory: Directory to walk
        
        Yields:
            File paths
        """
        try:
            for item in directory.iterdir():
                if item.is_file():
                    yield item
                elif item.is_dir():
                    # Check if directory should be ignored
                    rel_path = item.relative_to(self.workspace_root)
                    if not self.ignore_rules.should_ignore(rel_path):
                        yield from self._walk_directory(item)
        except PermissionError:
            logger.warning(f"Permission denied: {directory}")
        except Exception as e:
            logger.error(f"Error walking {directory}: {e}")
    
    def _scan_file(self, file_path: Path) -> Optional[ScannedFile]:
        """
        Scan a single file.
        
        Args:
            file_path: Path to file
        
        Returns:
            ScannedFile or None if should be skipped
        """
        try:
            # Get relative path
            rel_path = file_path.relative_to(self.workspace_root)
            
            # Check if should be ignored
            if self.ignore_rules.should_ignore(rel_path):
                return None
            
            # Get file stats
            stat = file_path.stat()
            size_bytes = stat.st_size
            last_modified = stat.st_mtime
            
            # Check file size
            if size_bytes > self.max_file_size_bytes:
                logger.debug(f"Skipping large file: {rel_path} ({size_bytes} bytes)")
                return None
            
            # Detect language
            extension = file_path.suffix.lower()
            language = self.LANGUAGE_MAP.get(extension, Language.UNKNOWN)
            
            # Check if binary
            is_binary = extension in self.BINARY_EXTENSIONS
            
            # Check if sensitive
            is_sensitive = self.ignore_rules.is_sensitive(rel_path)
            
            # Compute hash
            file_hash = self._compute_hash(file_path)
            
            # Read content if not binary and not sensitive
            content = None
            is_readable = not is_binary and not is_sensitive
            if is_readable:
                try:
                    content = file_path.read_text(encoding="utf-8")
                except UnicodeDecodeError:
                    # File is actually binary
                    is_binary = True
                    is_readable = False
                except Exception as e:
                    logger.warning(f"Could not read {rel_path}: {e}")
                    is_readable = False
            
            return ScannedFile(
                path=str(file_path),
                relative_path=str(rel_path),
                workspace_root=str(self.workspace_root),
                extension=extension,
                language=language,
                size_bytes=size_bytes,
                hash=file_hash,
                last_modified=last_modified,
                is_binary=is_binary,
                is_sensitive=is_sensitive,
                is_readable=is_readable,
                content=content,
            )
        
        except Exception as e:
            logger.error(f"Error scanning {file_path}: {e}")
            return None
    
    @staticmethod
    def _compute_hash(file_path: Path) -> str:
        """
        Compute SHA256 hash of file.
        
        Args:
            file_path: Path to file
        
        Returns:
            Hex digest of hash
        """
        try:
            hasher = hashlib.sha256()
            with open(file_path, "rb") as f:
                for chunk in iter(lambda: f.read(8192), b""):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return ""
