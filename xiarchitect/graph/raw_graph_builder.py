"""
xiarchitect.graph.raw_graph_builder — Builds raw file-level dependency graph
"""

import hashlib
from typing import Dict, List

from ..core.logger import get_logger
from ..core.types import AnalyzerResult, Evidence, EvidenceType

logger = get_logger(__name__)


class RawNode:
    """Raw graph node (file-level)"""
    
    def __init__(
        self,
        id: str,
        path: str,
        relative_path: str,
        label: str,
        language: str,
        role: str,
        importance_score: float = 0.0,
    ):
        self.id = id
        self.path = path
        self.relative_path = relative_path
        self.label = label
        self.language = language
        self.role = role
        self.importance_score = importance_score
        self.metadata: Dict = {}


class RawEdge:
    """Raw graph edge (import/dependency)"""
    
    def __init__(
        self,
        id: str,
        from_node: str,
        to_node: str,
        edge_type: str,
        confidence: float,
        evidence: List[Evidence],
    ):
        self.id = id
        self.from_node = from_node
        self.to_node = to_node
        self.type = edge_type
        self.confidence = confidence
        self.evidence = evidence


class RawGraph:
    """Raw dependency graph"""
    
    def __init__(self):
        self.nodes: Dict[str, RawNode] = {}
        self.edges: List[RawEdge] = []
    
    def add_node(self, node: RawNode):
        """Add node to graph"""
        self.nodes[node.id] = node
    
    def add_edge(self, edge: RawEdge):
        """Add edge to graph"""
        self.edges.append(edge)
    
    def to_dict(self) -> dict:
        """Convert to dictionary"""
        return {
            "nodes": [
                {
                    "id": node.id,
                    "path": node.relative_path,
                    "label": node.label,
                    "language": node.language,
                    "role": node.role,
                    "importance": node.importance_score,
                    "metadata": node.metadata,
                }
                for node in self.nodes.values()
            ],
            "edges": [
                {
                    "id": edge.id,
                    "from": edge.from_node,
                    "to": edge.to_node,
                    "type": edge.type,
                    "confidence": edge.confidence,
                    "evidence_count": len(edge.evidence),
                }
                for edge in self.edges
            ],
        }


class RawGraphBuilder:
    """Builds raw file-level dependency graph"""
    
    def __init__(self):
        """Initialize raw graph builder"""
        pass
    
    def build(
        self,
        scanned_files: List,
        analyzer_results: List[AnalyzerResult],
    ) -> RawGraph:
        """
        Build raw dependency graph.
        
        Args:
            scanned_files: List of scanned files
            analyzer_results: List of analyzer results
        
        Returns:
            Raw dependency graph
        """
        logger.info("Building raw dependency graph...")
        
        graph = RawGraph()
        
        # Create nodes for all files
        for file in scanned_files:
            # Normalize path (forward slashes)
            normalized_path = file.relative_path.replace("\\", "/")
            node_id = self._generate_node_id(normalized_path)
            node = RawNode(
                id=node_id,
                path=file.path,
                relative_path=normalized_path,
                label=self._get_file_label(normalized_path),
                language=file.language.value if file.language else "unknown",
                role=file.role.value,
                importance_score=file.importance_score,
            )
            
            graph.add_node(node)
        
        # Create edges from analyzer results
        for result in analyzer_results:
            # Normalize path
            from_path = result.file.replace("\\", "/")
            from_node_id = self._generate_node_id(from_path)
            
            # Import edges
            for import_rel in result.imports:
                # Normalize target path
                to_path = import_rel.to_file.replace("\\", "/")
                to_node_id = self._generate_node_id(to_path)
                
                # Only create edge if target node exists
                if to_node_id in graph.nodes:
                    edge = RawEdge(
                        id=f"{from_node_id}_{to_node_id}_{import_rel.import_type.value}",
                        from_node=from_node_id,
                        to_node=to_node_id,
                        edge_type=import_rel.import_type.value,
                        confidence=import_rel.confidence,
                        evidence=[
                            Evidence(
                                file=from_path,
                                line=import_rel.line_number,
                                reason=f"Import from {to_path}",
                                confidence=import_rel.confidence,
                                type=EvidenceType.EXPLICIT_IMPORT,
                            )
                        ],
                    )
                    graph.add_edge(edge)
        
        logger.info(
            f"Raw graph built: {len(graph.nodes)} nodes, {len(graph.edges)} edges"
        )
        
        return graph
    
    @staticmethod
    def _generate_node_id(file_path: str) -> str:
        """Generate deterministic node ID from file path"""
        return hashlib.sha1(file_path.encode()).hexdigest()[:12]
    
    @staticmethod
    def _get_file_label(file_path: str) -> str:
        """Get display label for file"""
        from pathlib import Path
        return Path(file_path).name
