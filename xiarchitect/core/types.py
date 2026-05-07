"""
xiarchitect.core.types — Root type definitions
All core types used throughout the xiarchitect system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────────────


class Language(str, Enum):
    """Supported programming languages"""
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    JAVASCRIPT = "javascript"
    GO = "go"
    RUST = "rust"
    YAML = "yaml"
    JSON = "json"
    TOML = "toml"
    MARKDOWN = "markdown"
    DOCKERFILE = "dockerfile"
    SHELL = "shell"
    UNKNOWN = "unknown"


class FileRole(str, Enum):
    """Architecture role classification for files"""
    # Entry points
    ENTRYPOINT = "entrypoint"
    APP_CONFIG = "app_config"
    
    # API layer
    API_ROUTE = "api_route"
    API_MIDDLEWARE = "api_middleware"
    API_SCHEMA = "api_schema"
    API_CLIENT = "api_client"
    
    # Service / business logic
    SERVICE = "service"
    USE_CASE = "use_case"
    REPOSITORY = "repository"
    
    # Database
    DATABASE_MODEL = "database_model"
    MIGRATION = "migration"
    SEED = "seed"
    QUERY = "query"
    
    # Background / async
    BACKGROUND_TASK = "background_task"
    SCHEDULER = "scheduler"
    EVENT_HANDLER = "event_handler"
    
    # AI / Automation
    AGENT = "agent"
    PROMPT = "prompt"
    SCRAPER = "scraper"
    WORKFLOW = "workflow"
    
    # Frontend
    FRONTEND_COMPONENT = "frontend_component"
    FRONTEND_PAGE = "frontend_page"
    FRONTEND_HOOK = "frontend_hook"
    FRONTEND_STORE = "frontend_store"
    FRONTEND_LAYOUT = "frontend_layout"
    
    # Infrastructure
    INFRASTRUCTURE = "infrastructure"
    CI_CD = "ci_cd"
    IAC = "iac"
    
    # Project meta
    CONFIG = "config"
    TEST = "test"
    DOCUMENTATION = "documentation"
    SCRIPT = "script"
    UNKNOWN = "unknown"


class ArchNodeType(str, Enum):
    """Architecture node types"""
    USER = "user"
    FRONTEND = "frontend"
    API = "api"
    SERVICE = "service"
    REPOSITORY = "repository"
    DATABASE = "database"
    CACHE = "cache"
    QUEUE = "queue"
    WORKER = "worker"
    SCHEDULER = "scheduler"
    AI_PROVIDER = "ai_provider"
    AGENT = "agent"
    AUTOMATION = "automation"
    EXTERNAL_SERVICE = "external_service"
    AUTH = "auth"
    NOTIFICATION = "notification"
    STORAGE = "storage"
    DEPLOYMENT = "deployment"
    MONITORING = "monitoring"
    CONFIG = "config"
    UNKNOWN = "unknown"


class ArchLayer(str, Enum):
    """Architecture layers"""
    FRONTEND = "frontend"
    BACKEND = "backend"
    WORKER = "worker"
    AI = "ai"
    SHARED = "shared"
    INFRA = "infra"
    AUTOMATION = "automation"
    EXTERNAL = "external"


class RawEdgeType(str, Enum):
    """Raw dependency edge types"""
    IMPORT = "import"
    DYNAMIC_IMPORT = "dynamic_import"
    ROUTE = "route"
    CONFIG = "config"
    TASK = "task"
    API_CALL = "api_call"
    DATABASE = "database"
    COMPOSE_DEPENDS = "compose_depends"
    INFRA = "infra"
    INFERRED = "inferred"


class EvidenceType(str, Enum):
    """Evidence types for confidence scoring"""
    DOCKER_SERVICE_DECLARATION = "docker_service_declaration"
    FRAMEWORK_ROUTE_DECORATOR = "framework_route_decorator"
    EXPLICIT_IMPORT = "explicit_import"
    OPENAPI_SPEC = "openapi_spec"
    PACKAGE_JSON_DEPENDENCY = "package_json_dependency"
    ENV_VAR_REFERENCE = "env_var_reference"
    FOLDER_NAMING_CONVENTION = "folder_naming_convention"
    README_MENTION = "readme_mention"
    AI_INFERENCE = "ai_inference"
    UNKNOWN = "unknown"


# ──────────────────────────────────────────────────────────────────────────────
# Data Classes
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class Evidence:
    """Evidence backing an architecture claim"""
    file: str
    line: Optional[int] = None
    snippet: Optional[str] = None
    reason: str = ""
    confidence: float = 0.5
    type: EvidenceType = EvidenceType.UNKNOWN


@dataclass
class ScannedFile:
    """Metadata for a scanned file"""
    # Identity
    path: str
    relative_path: str
    workspace_root: str
    package_root: Optional[str] = None
    
    # Classification
    extension: str = ""
    language: Optional[Language] = None
    role: FileRole = FileRole.UNKNOWN
    importance_score: float = 0.0
    
    # Metadata
    size_bytes: int = 0
    hash: str = ""
    last_modified: float = 0.0
    
    # Safety flags
    is_ignored: bool = False
    is_sensitive: bool = False
    is_binary: bool = False
    is_readable: bool = True
    
    # Content (only present if file was read)
    content: Optional[str] = None


@dataclass
class DetectedTechnology:
    """A detected technology in the stack"""
    name: str
    version: Optional[str] = None
    confidence: float = 0.0
    evidence: List[Evidence] = field(default_factory=list)


@dataclass
class StackSummary:
    """Complete stack detection summary"""
    languages: List[DetectedTechnology] = field(default_factory=list)
    frontend: List[DetectedTechnology] = field(default_factory=list)
    backend: List[DetectedTechnology] = field(default_factory=list)
    database: List[DetectedTechnology] = field(default_factory=list)
    cache: List[DetectedTechnology] = field(default_factory=list)
    queue: List[DetectedTechnology] = field(default_factory=list)
    workers: List[DetectedTechnology] = field(default_factory=list)
    ai_providers: List[DetectedTechnology] = field(default_factory=list)
    infrastructure: List[DetectedTechnology] = field(default_factory=list)
    testing: List[DetectedTechnology] = field(default_factory=list)
    deployment: List[DetectedTechnology] = field(default_factory=list)
    monitoring: List[DetectedTechnology] = field(default_factory=list)
    authentication: List[DetectedTechnology] = field(default_factory=list)
    overall_confidence: float = 0.0


@dataclass
class ArchitectureNode:
    """High-level architecture node"""
    id: str
    label: str
    type: ArchNodeType
    layer: ArchLayer
    source_files: List[str] = field(default_factory=list)
    confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    evidence: List[Evidence] = field(default_factory=list)


@dataclass
class ArchitectureEdge:
    """High-level architecture edge"""
    id: str
    from_node: str
    to_node: str
    type: str
    confidence: float = 0.0
    evidence: List[Evidence] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ArchitectureGraph:
    """Complete architecture graph"""
    nodes: List[ArchitectureNode] = field(default_factory=list)
    edges: List[ArchitectureEdge] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ImportRelation:
    """Import relationship between files"""
    from_file: str
    to_file: str
    import_type: RawEdgeType
    line_number: Optional[int] = None
    confidence: float = 0.85


@dataclass
class RouteDeclaration:
    """API route declaration"""
    method: str
    path: str
    handler: str
    file: str
    line_number: Optional[int] = None


@dataclass
class ModelDeclaration:
    """Database model declaration"""
    name: str
    file: str
    table_name: Optional[str] = None
    line_number: Optional[int] = None


@dataclass
class TaskDeclaration:
    """Background task declaration"""
    name: str
    file: str
    line_number: Optional[int] = None
    task_type: str = "celery"


@dataclass
class AnalyzerResult:
    """Result from a file analyzer"""
    file: str
    imports: List[ImportRelation] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    routes: List[RouteDeclaration] = field(default_factory=list)
    models: List[ModelDeclaration] = field(default_factory=list)
    tasks: List[TaskDeclaration] = field(default_factory=list)
    api_calls: List[str] = field(default_factory=list)
    evidence: List[Evidence] = field(default_factory=list)
