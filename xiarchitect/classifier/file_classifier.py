"""
xiarchitect.classifier.file_classifier — Assigns FileRole to each file
"""

import re
from typing import List, Optional

from ..core.logger import get_logger
from ..core.types import FileRole, ScannedFile

logger = get_logger(__name__)


class ClassificationRule:
    """A single classification rule"""
    
    def __init__(
        self,
        role: FileRole,
        path_pattern: Optional[str] = None,
        content_pattern: Optional[str] = None,
        sensitive: bool = False,
    ):
        """
        Initialize classification rule.
        
        Args:
            role: FileRole to assign
            path_pattern: Regex pattern for file path
            content_pattern: Regex pattern for file content
            sensitive: Mark file as sensitive
        """
        self.role = role
        self.path_pattern = re.compile(path_pattern) if path_pattern else None
        self.content_pattern = re.compile(content_pattern, re.MULTILINE) if content_pattern else None
        self.sensitive = sensitive
    
    def matches(self, file: ScannedFile) -> bool:
        """
        Check if rule matches file.
        
        Args:
            file: Scanned file
        
        Returns:
            True if matches
        """
        # Check path pattern
        if self.path_pattern and self.path_pattern.search(file.relative_path):
            return True
        
        # Check content pattern (only if content available)
        if self.content_pattern and file.content:
            if self.content_pattern.search(file.content):
                return True
        
        return False


class FileClassifier:
    """Classifies files into architecture roles"""
    
    # Classification rules (evaluated in order, first match wins)
    RULES: List[ClassificationRule] = [
        # Secrets — highest priority
        ClassificationRule(FileRole.CONFIG, path_pattern=r"^\.env(\..+)?$", sensitive=True),
        ClassificationRule(FileRole.CONFIG, path_pattern=r"\.(pem|key|crt|pfx)$", sensitive=True),
        
        # Infrastructure
        ClassificationRule(FileRole.INFRASTRUCTURE, path_pattern=r"docker-compose(\..+)?\.ya?ml$"),
        ClassificationRule(FileRole.INFRASTRUCTURE, path_pattern=r"Dockerfile(\..+)?$"),
        ClassificationRule(FileRole.CI_CD, path_pattern=r"\.github/workflows/.+\.ya?ml$"),
        ClassificationRule(FileRole.INFRASTRUCTURE, path_pattern=r"helm/.+/Chart\.ya?ml$"),
        ClassificationRule(FileRole.IAC, path_pattern=r"\.tf$"),
        
        # Python entrypoints
        ClassificationRule(FileRole.ENTRYPOINT, path_pattern=r"^(app|src|backend)/main\.py$"),
        ClassificationRule(FileRole.ENTRYPOINT, path_pattern=r"^main\.py$"),
        ClassificationRule(
            FileRole.ENTRYPOINT,
            content_pattern=r"FastAPI\(\)|Flask\(__name__\)|app = Django"
        ),
        
        # Python API routes
        ClassificationRule(FileRole.API_ROUTE, path_pattern=r"/(api|routes?|views?|endpoints?)/"),
        ClassificationRule(
            FileRole.API_ROUTE,
            content_pattern=r"@(app|router)\.(get|post|put|delete|patch)\("
        ),
        
        # Python models
        ClassificationRule(FileRole.DATABASE_MODEL, path_pattern=r"/(models?|schemas?|entities?)/"),
        ClassificationRule(
            FileRole.DATABASE_MODEL,
            content_pattern=r"class .+\(Base\)|class .+\(BaseModel\)"
        ),
        
        # Python tasks
        ClassificationRule(FileRole.BACKGROUND_TASK, path_pattern=r"/(tasks?|workers?|jobs?|celery)/"),
        ClassificationRule(
            FileRole.BACKGROUND_TASK,
            content_pattern=r"@celery\.task|@app\.task|@shared_task"
        ),
        
        # Python agents
        ClassificationRule(FileRole.AGENT, path_pattern=r"/(agents?|ai|llm)/"),
        ClassificationRule(
            FileRole.AGENT,
            content_pattern=r"LLMChain|AgentExecutor|llm\.invoke|openai\.chat"
        ),
        
        # Python services
        ClassificationRule(FileRole.SERVICE, path_pattern=r"/(services?|use.?cases?|commands?)/"),
        
        # Python repositories
        ClassificationRule(FileRole.REPOSITORY, path_pattern=r"/(repositories?|daos?|stores?)/"),
        
        # Python core/shared
        ClassificationRule(FileRole.CONFIG, path_pattern=r"/(core|common|shared|utils?|helpers?)/"),
        
        # TypeScript frontend
        ClassificationRule(FileRole.FRONTEND_PAGE, path_pattern=r"src/(pages|app)/.+\.(tsx|jsx)$"),
        ClassificationRule(FileRole.FRONTEND_COMPONENT, path_pattern=r"src/components/.+\.(tsx|jsx)$"),
        ClassificationRule(FileRole.FRONTEND_HOOK, path_pattern=r"src/hooks/.+\.(ts|tsx)$"),
        ClassificationRule(FileRole.FRONTEND_STORE, path_pattern=r"src/(store|stores?|state)/.+\.ts$"),
        
        # TypeScript backend
        ClassificationRule(
            FileRole.ENTRYPOINT,
            content_pattern=r"express\(\)|new NestFactory|Hono\(\)"
        ),
        ClassificationRule(FileRole.API_ROUTE, path_pattern=r"routes?/.+\.(ts|js)$"),
        ClassificationRule(FileRole.API_ROUTE, path_pattern=r"controllers?/.+\.(ts|js)$"),
        ClassificationRule(FileRole.SERVICE, path_pattern=r"services?/.+\.(ts|js)$"),
        ClassificationRule(FileRole.REPOSITORY, path_pattern=r"repositories?/.+\.(ts|js)$"),
        
        # Tests
        ClassificationRule(FileRole.TEST, path_pattern=r"\.(test|spec)\.(ts|js|tsx|jsx|py)$"),
        ClassificationRule(FileRole.TEST, path_pattern=r"^tests?/"),
        
        # Docs
        ClassificationRule(FileRole.DOCUMENTATION, path_pattern=r"\.(md|mdx|rst|txt)$"),
        
        # Config
        ClassificationRule(FileRole.CONFIG, path_pattern=r"\.(json|ya?ml|toml|ini|cfg|conf)$"),
        
        # Migrations
        ClassificationRule(FileRole.MIGRATION, path_pattern=r"/migrations?/versions?/"),
        ClassificationRule(FileRole.MIGRATION, path_pattern=r"alembic/versions/"),
    ]
    
    def classify(self, file: ScannedFile) -> ScannedFile:
        """
        Classify a file and assign its role.
        
        Args:
            file: Scanned file
        
        Returns:
            File with role assigned
        """
        # Apply rules in order
        for rule in self.RULES:
            if rule.matches(file):
                file.role = rule.role
                if rule.sensitive:
                    file.is_sensitive = True
                return file
        
        # No match — keep as UNKNOWN
        file.role = FileRole.UNKNOWN
        return file
    
    def classify_batch(self, files: List[ScannedFile]) -> List[ScannedFile]:
        """
        Classify multiple files.
        
        Args:
            files: List of scanned files
        
        Returns:
            Files with roles assigned
        """
        return [self.classify(file) for file in files]
