"""
xiarchitect.analyzers.analyzer_registry — Registry and dispatcher for analyzers
"""

from pathlib import Path
from typing import List

from ..core.logger import get_logger
from ..core.types import AnalyzerResult, ScannedFile
from .python_analyzer import PythonAnalyzer

logger = get_logger(__name__)


class AnalyzerRegistry:
    """Registry for all file analyzers"""
    
    def __init__(self, workspace_root: Path):
        """
        Initialize analyzer registry.
        
        Args:
            workspace_root: Root directory of workspace
        """
        self.workspace_root = workspace_root
        self.analyzers = [
            PythonAnalyzer(workspace_root),
            # TypeScriptAnalyzer(workspace_root),  # v0.2+
            # GoAnalyzer(workspace_root),  # v0.2+
        ]
    
    def analyze(self, file: ScannedFile) -> AnalyzerResult:
        """
        Analyze a file using appropriate analyzer.
        
        Args:
            file: Scanned file
        
        Returns:
            Analysis result
        """
        # Find appropriate analyzer
        for analyzer in self.analyzers:
            if analyzer.can_analyze(file):
                try:
                    return analyzer.analyze(file)
                except Exception as e:
                    logger.error(f"Error analyzing {file.relative_path}: {e}")
                    return AnalyzerResult(file=file.relative_path)
        
        # No analyzer found
        return AnalyzerResult(file=file.relative_path)
    
    def analyze_batch(self, files: List[ScannedFile]) -> List[AnalyzerResult]:
        """
        Analyze multiple files.
        
        Args:
            files: List of scanned files
        
        Returns:
            List of analysis results
        """
        results = []
        for file in files:
            result = self.analyze(file)
            if result.imports or result.routes or result.models or result.tasks:
                results.append(result)
        
        return results
