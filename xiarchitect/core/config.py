"""
xiarchitect.core.config — Configuration schema and loader
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class XiArchitectConfig:
    """Configuration for xiarchitect analysis"""
    
    # Privacy & AI
    privacy_mode: str = "local-only"  # local-only | hybrid | cloud-ai
    ai_enabled: bool = False
    ai_provider: str = "none"  # none | openai | anthropic | gemini | ollama
    ai_model: str = "gpt-4o-mini"
    
    # Scanning
    max_file_size_kb: int = 1024
    max_files: int = 50000
    additional_ignore_patterns: List[str] = field(default_factory=list)
    always_include_patterns: List[str] = field(default_factory=list)
    
    # Diagram
    default_diagram_type: str = "system-overview"
    default_abstraction_level: int = 2
    diagram_theme: str = "auto"  # auto | light | dark
    
    # Export
    output_dir: str = "docs/xiarchitect"
    export_formats: List[str] = field(default_factory=lambda: ["markdown", "mermaid", "json"])
    
    # Security
    redact_secrets: bool = True
    
    # Performance
    max_parallel_files: int = 20
    
    # Watch mode
    watch_enabled: bool = False
    watch_debounce_ms: int = 2000
    
    # Health
    confidence_threshold: float = 0.4
    
    # Telemetry
    telemetry_enabled: bool = False
    
    # Workspace
    workspace_root: Optional[Path] = None
    
    @classmethod
    def default(cls, workspace_root: Optional[Path] = None) -> "XiArchitectConfig":
        """Create default configuration"""
        return cls(workspace_root=workspace_root)
    
    @classmethod
    def from_dict(cls, data: dict, workspace_root: Optional[Path] = None) -> "XiArchitectConfig":
        """Create configuration from dictionary"""
        config = cls(workspace_root=workspace_root)
        for key, value in data.items():
            if hasattr(config, key):
                setattr(config, key, value)
        return config
