"""
xiarchitect.scanner.workspace_scanner — Orchestrates full workspace scan
"""

from pathlib import Path
from typing import List, Optional

from ..core.config import XiArchitectConfig
from ..core.logger import get_logger
from ..core.types import ScannedFile
from .file_walker import FileWalker
from .ignore_rules import IgnoreRules

logger = get_logger(__name__)


class WorkspaceScanner:
    """Orchestrates full workspace scanning"""
    
    def __init__(self, config: XiArchitectConfig):
        """
        Initialize workspace scanner.
        
        Args:
            config: xiarchitect configuration
        """
        self.config = config
        self.workspace_root = config.workspace_root or Path.cwd()
        
        # Initialize ignore rules
        self.ignore_rules = IgnoreRules(
            workspace_root=self.workspace_root,
            additional_patterns=config.additional_ignore_patterns,
        )
        
        # Initialize file walker
        self.file_walker = FileWalker(
            workspace_root=self.workspace_root,
            ignore_rules=self.ignore_rules,
            max_file_size_kb=config.max_file_size_kb,
        )
    
    def scan(self) -> List[ScannedFile]:
        """
        Perform full workspace scan.
        
        Returns:
            List of scanned files
        """
        logger.info(f"Starting workspace scan: {self.workspace_root}")
        
        scanned_files: List[ScannedFile] = []
        file_count = 0
        
        for scanned_file in self.file_walker.walk():
            scanned_files.append(scanned_file)
            file_count += 1
            
            if file_count % 100 == 0:
                logger.info(f"Scanned {file_count} files...")
            
            # Check max files limit
            if file_count >= self.config.max_files:
                logger.warning(f"Reached max files limit: {self.config.max_files}")
                break
        
        logger.info(f"Scan complete: {len(scanned_files)} files scanned")
        
        return scanned_files
    
    def scan_file(self, file_path: Path) -> Optional[ScannedFile]:
        """
        Scan a single file.
        
        Args:
            file_path: Path to file
        
        Returns:
            ScannedFile or None
        """
        return self.file_walker._scan_file(file_path)
