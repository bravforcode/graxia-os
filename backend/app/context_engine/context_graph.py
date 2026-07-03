"""Context graph — maps relationships between project files.

Detects imports, routes, models, services, tests, and other relationships
using lightweight pattern matching (no full AST).
"""
from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from app.context_engine.schemas import ContextGraph, ContextGraphEdge, ContextGraphNode, ProjectFileInfo, ProjectIndex


class ContextGraphBuilder:
    """Builds a ContextGraph from a ProjectIndex by detecting file relationships."""

    def build_from_index(self, project_index: ProjectIndex) -> ContextGraph:
        """Build a context graph from a project index.

        Uses lightweight pattern matching on file paths and summaries.
        """
        nodes: dict[str, ContextGraphNode] = {}
        edges: list[ContextGraphEdge] = []

        # Create nodes for all indexed files
        for file_info in project_index.files:
            node_id = file_info.path
            nodes[node_id] = ContextGraphNode(
                id=node_id,
                type="file",
                label=Path(file_info.path).name,
                path=file_info.path,
                metadata={
                    "category": file_info.category,
                    "language": file_info.language,
                    "estimated_tokens": file_info.estimated_tokens,
                },
            )

        # Detect relationships
        for file_info in project_index.files:
            source_id = file_info.path
            path_str = file_info.path.replace("\\", "/")
            summary = file_info.summary or ""

            # Python import relationships
            if file_info.language == "python":
                import_targets = self._detect_python_imports(summary, path_str)
                for target in import_targets:
                    target_path = self._resolve_import_target(target, project_index.files)
                    if target_path and target_path in nodes:
                        edges.append(ContextGraphEdge(
                            source=source_id,
                            target=target_path,
                            relation="imports",
                            confidence=0.8,
                        ))

            # Test relationships
            if file_info.category == "test":
                tested_file = self._find_tested_file(path_str, project_index.files)
                if tested_file:
                    edges.append(ContextGraphEdge(
                        source=source_id,
                        target=tested_file,
                        relation="tests",
                        confidence=0.9,
                    ))

            # Service-file relationships (import patterns in summary)
            if "service" in path_str or "service" in summary.lower():
                for model_file in self._find_model_files(project_index.files):
                    if model_file != source_id:
                        edges.append(ContextGraphEdge(
                            source=source_id,
                            target=model_file,
                            relation="uses",
                            confidence=0.7,
                        ))

            # Route-file relationships
            if "routes:" in summary:
                edges.append(ContextGraphEdge(
                    source=source_id,
                    target=path_str.replace("/api/", "/models/").replace("router", "model").rsplit(".", 1)[0] + ".py",
                    relation="routes_to",
                    confidence=0.5,
                ))

        # Add feature-relationship nodes
        for feat_name, feat_pattern in _FEATURE_NODES.items():
            feat_id = f"feature:{feat_name}"
            if feat_id not in nodes:
                nodes[feat_id] = ContextGraphNode(
                    id=feat_id,
                    type="feature",
                    label=feat_name,
                    metadata={"feature": feat_name},
                )
            for f in project_index.files:
                if feat_pattern in f.path:
                    edges.append(ContextGraphEdge(
                        source=feat_id,
                        target=f.path,
                        relation="feature_contains",
                        confidence=0.9,
                    ))

        return ContextGraph(
            nodes=list(nodes.values()),
            edges=edges,
            generated_at=datetime.now(UTC).isoformat(),
        )

    @staticmethod
    def _detect_python_imports(summary: str, path_str: str) -> list[str]:
        """Detect Python import targets from a summary."""
        targets = []
        imports = re.findall(r"from\s+(\S+)\s+import|\bimport\s+(\S+)", summary)
        for imp in imports:
            module = imp[0] or imp[1]
            if module and not module.startswith("__"):
                targets.append(module.replace(".", "/"))
        return targets

    @staticmethod
    def _resolve_import_target(target: str, files: list[ProjectFileInfo]) -> str | None:
        """Resolve a Python import target to a file path."""
        for ext in [".py", ""]:
            for f in files:
                path_no_ext = f.path.rsplit(".", 1)[0].replace("\\", "/")
                if path_no_ext == target or path_no_ext.endswith("/" + target):
                    return f.path
        return None

    @staticmethod
    def _find_tested_file(test_path: str, files: list[ProjectFileInfo]) -> str | None:
        """Find the file that a test file tests."""
        path_str = test_path.replace("\\", "/")

        # Remove test_ prefix or _test suffix
        name = path_str.rsplit("/", 1)[-1] if "/" in path_str else path_str
        tested_name = name.replace("test_", "", 1).replace("_test", "", 1)
        tested_name = tested_name.replace(".py", "")

        for f in files:
            if f.category == "test":
                continue
            f_name = f.path.rsplit("/", 1)[-1].replace(".py", "")
            if f_name == tested_name:
                return f.path

        return None

    @staticmethod
    def _find_model_files(files: list[ProjectFileInfo]) -> list[str]:
        """Find model-related files."""
        models = []
        for f in files:
            if "models" in f.path.replace("\\", "/").split("/"):
                models.append(f.path)
        return models


# Feature nodes for the context graph
_FEATURE_NODES: dict[str, str] = {
    "funnel": "backend/app/models/funnel",
    "mcp": "backend/app/mcp/",
    "context_engine": "backend/app/context_engine",
    "workspace": "backend/app/integrations/google_workspace",
    "approval": "backend/app/models/approval_request",
}
