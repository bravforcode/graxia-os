"""
xiarchitect.analyzers.python_analyzer — Python import and framework analyzer
"""

import ast
import re
from pathlib import Path
from typing import List, Optional

from ..core.logger import get_logger
from ..core.types import (
    AnalyzerResult,
    Evidence,
    EvidenceType,
    ImportRelation,
    ModelDeclaration,
    RawEdgeType,
    RouteDeclaration,
    ScannedFile,
    TaskDeclaration,
)

logger = get_logger(__name__)


class PythonAnalyzer:
    """Analyzes Python files for imports, routes, models, and tasks"""
    
    def __init__(self, workspace_root: Path):
        """
        Initialize Python analyzer.
        
        Args:
            workspace_root: Root directory of workspace
        """
        self.workspace_root = workspace_root
        self.search_roots = self._build_search_roots()
    
    def can_analyze(self, file: ScannedFile) -> bool:
        """
        Check if this analyzer can handle the file.
        
        Args:
            file: Scanned file
        
        Returns:
            True if file is Python
        """
        return file.extension == ".py" and file.content is not None
    
    def analyze(self, file: ScannedFile) -> AnalyzerResult:
        """
        Analyze a Python file.
        
        Args:
            file: Scanned file
        
        Returns:
            Analysis result with imports, routes, models, tasks
        """
        if not file.content:
            return AnalyzerResult(file=file.relative_path)
        
        result = AnalyzerResult(file=file.relative_path)
        
        # Analyze imports
        result.imports = self._analyze_imports(file)
        
        # Analyze routes (FastAPI, Flask, Django)
        result.routes = self._analyze_routes(file)
        
        # Analyze models (SQLAlchemy, Pydantic)
        result.models = self._analyze_models(file)
        
        # Analyze tasks (Celery)
        result.tasks = self._analyze_tasks(file)
        
        # Analyze API calls
        result.api_calls = self._analyze_api_calls(file)
        
        # Collect evidence
        result.evidence = self._collect_evidence(file, result)
        
        return result
    
    def _analyze_imports(self, file: ScannedFile) -> List[ImportRelation]:
        """
        Analyze Python imports.
        
        Detects:
        - import module
        - from module import name
        - from .relative import name
        """
        imports: List[ImportRelation] = []

        if not file.content:
            return imports

        try:
            tree = ast.parse(file.content, filename=file.relative_path)
        except SyntaxError:
            return self._analyze_imports_regex(file)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        ImportRelation(
                            from_file=file.relative_path,
                            to_file=self._resolve_import(alias.name, file),
                            import_type=RawEdgeType.IMPORT,
                            line_number=getattr(node, "lineno", None),
                            confidence=0.95,
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    for alias in node.names:
                        imports.append(
                            ImportRelation(
                                from_file=file.relative_path,
                                to_file=self._resolve_relative_import(
                                    module_name=node.module,
                                    level=node.level,
                                    file=file,
                                    imported_name=alias.name,
                                ),
                                import_type=RawEdgeType.IMPORT,
                                line_number=getattr(node, "lineno", None),
                                confidence=0.90,
                            )
                        )
                elif node.module:
                    imports.append(
                        ImportRelation(
                            from_file=file.relative_path,
                            to_file=self._resolve_import(node.module, file),
                            import_type=RawEdgeType.IMPORT,
                            line_number=getattr(node, "lineno", None),
                            confidence=0.95,
                        )
                    )

        return imports
    
    def _analyze_routes(self, file: ScannedFile) -> List[RouteDeclaration]:
        """
        Analyze API routes.
        
        Detects:
        - @app.get/post/put/delete/patch(path)
        - @router.get/post/put/delete/patch(path)
        - @app.route(path, methods=[...])
        """
        routes: List[RouteDeclaration] = []
        
        if not file.content:
            return routes
        
        lines = file.content.split("\n")
        
        for line_num, line in enumerate(lines, start=1):
            line = line.strip()
            
            # FastAPI: @app.get("/path") or @router.get("/path")
            match = re.match(
                r"@(app|router)\.(get|post|put|delete|patch)\(['\"]([^'\"]+)['\"]",
                line
            )
            if match:
                method = match.group(2).upper()
                path = match.group(3)
                
                # Get handler name from next line
                handler = "unknown"
                if line_num < len(lines):
                    next_line = lines[line_num].strip()
                    handler_match = re.match(r"(async\s+)?def\s+([a-zA-Z0-9_]+)", next_line)
                    if handler_match:
                        handler = handler_match.group(2)
                
                routes.append(
                    RouteDeclaration(
                        method=method,
                        path=path,
                        handler=handler,
                        file=file.relative_path,
                        line_number=line_num,
                    )
                )
                continue
            
            # Flask: @app.route("/path", methods=["GET", "POST"])
            match = re.match(r"@app\.route\(['\"]([^'\"]+)['\"]", line)
            if match:
                path = match.group(1)
                
                # Extract methods if present
                methods_match = re.search(r"methods\s*=\s*\[([^\]]+)\]", line)
                methods = ["GET"]  # Default
                if methods_match:
                    methods_str = methods_match.group(1)
                    methods = [m.strip().strip("'\"") for m in methods_str.split(",")]
                
                # Get handler name from next line
                handler = "unknown"
                if line_num < len(lines):
                    next_line = lines[line_num].strip()
                    handler_match = re.match(r"def\s+([a-zA-Z0-9_]+)", next_line)
                    if handler_match:
                        handler = handler_match.group(1)
                
                for method in methods:
                    routes.append(
                        RouteDeclaration(
                            method=method,
                            path=path,
                            handler=handler,
                            file=file.relative_path,
                            line_number=line_num,
                        )
                    )
        
        return routes
    
    def _analyze_models(self, file: ScannedFile) -> List[ModelDeclaration]:
        """
        Analyze database models.
        
        Detects:
        - class Model(Base)
        - class Model(BaseModel)
        - class Model(DeclarativeBase)
        """
        models: List[ModelDeclaration] = []
        
        if not file.content:
            return models
        
        lines = file.content.split("\n")
        
        for line_num, line in enumerate(lines, start=1):
            line = line.strip()
            
            # SQLAlchemy: class Model(Base)
            match = re.match(
                r"class\s+([A-Z][a-zA-Z0-9_]*)\s*\(\s*(Base|DeclarativeBase|AbstractBase)",
                line
            )
            if match:
                model_name = match.group(1)
                
                # Try to find __tablename__
                table_name = None
                for i in range(line_num, min(line_num + 10, len(lines))):
                    table_match = re.search(r"__tablename__\s*=\s*['\"]([^'\"]+)['\"]", lines[i])
                    if table_match:
                        table_name = table_match.group(1)
                        break
                
                models.append(
                    ModelDeclaration(
                        name=model_name,
                        file=file.relative_path,
                        table_name=table_name,
                        line_number=line_num,
                    )
                )
                continue
            
            # Pydantic: class Model(BaseModel)
            match = re.match(
                r"class\s+([A-Z][a-zA-Z0-9_]*)\s*\(\s*BaseModel",
                line
            )
            if match:
                model_name = match.group(1)
                models.append(
                    ModelDeclaration(
                        name=model_name,
                        file=file.relative_path,
                        line_number=line_num,
                    )
                )
        
        return models
    
    def _analyze_tasks(self, file: ScannedFile) -> List[TaskDeclaration]:
        """
        Analyze background tasks.
        
        Detects:
        - @celery.task
        - @app.task
        - @shared_task
        """
        tasks: List[TaskDeclaration] = []
        
        if not file.content:
            return tasks
        
        lines = file.content.split("\n")
        
        for line_num, line in enumerate(lines, start=1):
            line = line.strip()
            
            # Celery task decorators
            if re.match(r"@(celery\.task|app\.task|shared_task)", line):
                # Get task name from next line
                task_name = "unknown"
                if line_num < len(lines):
                    next_line = lines[line_num].strip()
                    task_match = re.match(r"(async\s+)?def\s+([a-zA-Z0-9_]+)", next_line)
                    if task_match:
                        task_name = task_match.group(2)
                
                tasks.append(
                    TaskDeclaration(
                        name=task_name,
                        file=file.relative_path,
                        line_number=line_num,
                        task_type="celery",
                    )
                )
        
        return tasks
    
    def _analyze_api_calls(self, file: ScannedFile) -> List[str]:
        """
        Analyze external API calls.
        
        Detects:
        - requests.get/post/put/delete
        - httpx.get/post/put/delete
        - stripe.*, openai.*, anthropic.*
        """
        api_calls: List[str] = []
        
        if not file.content:
            return api_calls
        
        # Detect HTTP client calls
        if re.search(r"(requests|httpx)\.(get|post|put|delete|patch)", file.content):
            api_calls.append("http_client")
        
        # Detect specific services
        if "stripe." in file.content or "import stripe" in file.content:
            api_calls.append("stripe")
        
        if "openai." in file.content or "import openai" in file.content:
            api_calls.append("openai")
        
        if "anthropic." in file.content or "import anthropic" in file.content:
            api_calls.append("anthropic")
        
        if "resend." in file.content or "import resend" in file.content:
            api_calls.append("resend")
        
        return api_calls
    
    def _analyze_imports_regex(self, file: ScannedFile) -> List[ImportRelation]:
        """Fallback import analyzer for files that fail AST parsing."""
        imports: List[ImportRelation] = []

        if not file.content:
            return imports

        lines = file.content.split("\n")

        for line_num, line in enumerate(lines, start=1):
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            relative_match = re.match(r"^from\s+(\.+[a-zA-Z0-9_\.]*)\s+import", line)
            if relative_match:
                module = relative_match.group(1)
                imports.append(
                    ImportRelation(
                        from_file=file.relative_path,
                        to_file=self._resolve_relative_import(
                            module_name=module.lstrip(".") or None,
                            level=len(module) - len(module.lstrip(".")),
                            file=file,
                        ),
                        import_type=RawEdgeType.IMPORT,
                        line_number=line_num,
                        confidence=0.90,
                    )
                )
                continue

            match = re.match(r"^import\s+([a-zA-Z0-9_\.]+)", line)
            if match:
                module = match.group(1)
                imports.append(
                    ImportRelation(
                        from_file=file.relative_path,
                        to_file=self._resolve_import(module, file),
                        import_type=RawEdgeType.IMPORT,
                        line_number=line_num,
                        confidence=0.95,
                    )
                )
                continue

            match = re.match(r"^from\s+([a-zA-Z0-9_\.]+)\s+import", line)
            if match:
                module = match.group(1)
                imports.append(
                    ImportRelation(
                        from_file=file.relative_path,
                        to_file=self._resolve_import(module, file),
                        import_type=RawEdgeType.IMPORT,
                        line_number=line_num,
                        confidence=0.95,
                    )
                )

        return imports

    def _resolve_import(self, module: str, file: ScannedFile) -> str:
        """
        Resolve absolute import to file path.
        
        Args:
            module: Module name (e.g., "graxia.packages.revenue_os.models")
            file: Current file
        
        Returns:
            Resolved file path or module name
        """
        module = module.strip(".")
        if not module:
            return file.relative_path.replace("\\", "/")

        parts = [part for part in module.split(".") if part]
        if not parts:
            return module

        for root in self._candidate_roots(file):
            resolved = self._resolve_module_from_root(root, parts)
            if resolved:
                return resolved

        return module

    def _resolve_relative_import(
        self,
        module_name: Optional[str],
        level: int,
        file: ScannedFile,
        imported_name: Optional[str] = None,
    ) -> str:
        """
        Resolve relative import to file path.
        
        Args:
            module_name: Relative module without leading dots
            level: Relative import level from AST
            file: Current file
            imported_name: Imported symbol when module_name is empty
        
        Returns:
            Resolved file path
        """
        # Get current file's directory
        current_dir = Path(file.relative_path).parent

        for _ in range(max(level - 1, 0)):
            current_dir = current_dir.parent

        target_parts: List[str] = []
        if module_name:
            target_parts.extend(part for part in module_name.split(".") if part)
        elif imported_name and imported_name != "*":
            target_parts.append(imported_name)

        target_path = current_dir.joinpath(*target_parts) if target_parts else current_dir
        resolved = self._resolve_relative_path(target_path)
        if resolved:
            return resolved

        return str(target_path).replace("\\", "/")

    def _build_search_roots(self) -> List[Path]:
        """Build source roots commonly used by local Python imports."""
        roots = [self.workspace_root]
        for name in ("backend", "graxia", "core", "services", "packages"):
            candidate = self.workspace_root / name
            if candidate.exists() and candidate.is_dir():
                roots.append(candidate)
        return roots

    def _candidate_roots(self, file: ScannedFile) -> List[Path]:
        roots = list(self.search_roots)
        relative_parts = Path(file.relative_path).parts
        if relative_parts:
            top_level_root = self.workspace_root / relative_parts[0]
            if top_level_root.exists() and top_level_root not in roots:
                roots.insert(0, top_level_root)
        return roots

    def _resolve_module_from_root(self, root: Path, parts: List[str]) -> Optional[str]:
        module_path = Path(*parts)

        file_candidate = root / module_path.with_suffix(".py")
        if file_candidate.exists():
            return str(file_candidate.relative_to(self.workspace_root)).replace("\\", "/")

        package_candidate = root / module_path / "__init__.py"
        if package_candidate.exists():
            return str(package_candidate.relative_to(self.workspace_root)).replace("\\", "/")

        return None

    def _resolve_relative_path(self, target_path: Path) -> Optional[str]:
        file_candidate = self.workspace_root / target_path.with_suffix(".py")
        if file_candidate.exists():
            return str(file_candidate.relative_to(self.workspace_root)).replace("\\", "/")

        package_candidate = self.workspace_root / target_path / "__init__.py"
        if package_candidate.exists():
            return str(package_candidate.relative_to(self.workspace_root)).replace("\\", "/")

        return None
    
    def _collect_evidence(self, file: ScannedFile, result: AnalyzerResult) -> List[Evidence]:
        """Collect evidence from analysis"""
        evidence: List[Evidence] = []
        
        if result.routes:
            evidence.append(
                Evidence(
                    file=file.relative_path,
                    reason=f"Found {len(result.routes)} API routes",
                    confidence=0.95,
                    type=EvidenceType.FRAMEWORK_ROUTE_DECORATOR,
                )
            )
        
        if result.models:
            evidence.append(
                Evidence(
                    file=file.relative_path,
                    reason=f"Found {len(result.models)} database models",
                    confidence=0.90,
                    type=EvidenceType.EXPLICIT_IMPORT,
                )
            )
        
        if result.tasks:
            evidence.append(
                Evidence(
                    file=file.relative_path,
                    reason=f"Found {len(result.tasks)} background tasks",
                    confidence=0.95,
                    type=EvidenceType.FRAMEWORK_ROUTE_DECORATOR,
                )
            )
        
        return evidence
