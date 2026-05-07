"""
xiarchitect.diagrams.mermaid_generator — Generates Mermaid diagrams
"""

from typing import Dict, List, Set

from ..core.logger import get_logger
from ..graph.raw_graph_builder import RawGraph

logger = get_logger(__name__)


class MermaidGenerator:
    """Generates Mermaid diagrams from architecture graphs"""
    
    def __init__(self):
        """Initialize Mermaid generator"""
        pass
    
    def generate_system_overview(
        self,
        raw_graph: RawGraph,
        stack_summary: dict,
    ) -> str:
        """
        Generate system overview diagram (C4 Level 1 - Context).
        
        Shows the system and its external dependencies.
        
        Args:
            raw_graph: Raw dependency graph
            stack_summary: Technology stack summary
        
        Returns:
            Mermaid diagram as string
        """
        lines = [
            "flowchart TD",
            "    %% System Overview - C4 Context Level",
            "",
        ]
        
        # Group nodes by layer
        layers = self._group_by_layer(raw_graph)
        
        # Add system node
        lines.append("    System[\"Graxia Revenue OS<br/>FastAPI + Celery + SQLAlchemy\"]")
        lines.append("")
        
        # Add external services
        external_services = self._detect_external_services(raw_graph)
        if external_services:
            lines.append("    %% External Services")
            for service in external_services:
                service_id = service.replace(" ", "_").replace(".", "_")
                lines.append(f"    {service_id}[\"{service}\"]")
                lines.append(f"    System --> {service_id}")
            lines.append("")
        
        # Add database
        if "database" in stack_summary:
            lines.append("    %% Database")
            lines.append("    DB[(\"PostgreSQL<br/>Database\")]")
            lines.append("    System --> DB")
            lines.append("")
        
        # Add cache
        if "cache" in stack_summary:
            lines.append("    %% Cache")
            lines.append("    Cache[(\"Redis<br/>Cache & Queue\")]")
            lines.append("    System --> Cache")
            lines.append("")
        
        # Styling
        lines.extend([
            "    %% Styling",
            "    classDef system fill:#4A90E2,stroke:#2E5C8A,color:#fff",
            "    classDef external fill:#E8E8E8,stroke:#999,color:#333",
            "    classDef database fill:#50C878,stroke:#2E7D4E,color:#fff",
            "    class System system",
            "    class DB,Cache database",
        ])
        
        return "\n".join(lines)
    
    def generate_container_diagram(
        self,
        raw_graph: RawGraph,
        stack_summary: dict,
    ) -> str:
        """
        Generate container diagram (C4 Level 2).
        
        Shows the major containers/services in the system.
        
        Args:
            raw_graph: Raw dependency graph
            stack_summary: Technology stack summary
        
        Returns:
            Mermaid diagram as string
        """
        lines = [
            "flowchart TD",
            "    %% Container Diagram - C4 Level 2",
            "",
        ]
        
        # Detect containers from folder structure
        containers = self._detect_containers(raw_graph)
        
        # Add containers
        lines.append("    %% Containers")
        for container_id, container_info in containers.items():
            label = container_info["label"]
            tech = container_info.get("tech", "")
            lines.append(f"    {container_id}[\"{label}<br/>{tech}\"]")
        
        lines.append("")
        
        # Add infrastructure
        lines.append("    %% Infrastructure")
        lines.append("    DB[(\"PostgreSQL\")]")
        lines.append("    Cache[(\"Redis\")]")
        lines.append("")
        
        # Add connections
        lines.append("    %% Connections")
        
        # API -> Services
        if "API" in containers and "Services" in containers:
            lines.append("    API --> Services")
        
        # Services -> Models
        if "Services" in containers and "Models" in containers:
            lines.append("    Services --> Models")
        
        # Models -> DB
        if "Models" in containers:
            lines.append("    Models --> DB")
        
        # Workers -> Services
        if "Workers" in containers and "Services" in containers:
            lines.append("    Workers --> Services")
        
        # Workers -> Cache
        if "Workers" in containers:
            lines.append("    Workers --> Cache")
        
        # API -> Cache
        if "API" in containers:
            lines.append("    API --> Cache")
        
        lines.append("")
        
        # Styling
        lines.extend([
            "    %% Styling",
            "    classDef container fill:#4A90E2,stroke:#2E5C8A,color:#fff",
            "    classDef database fill:#50C878,stroke:#2E7D4E,color:#fff",
            "    class API,Services,Models,Workers,Agents container",
            "    class DB,Cache database",
        ])
        
        return "\n".join(lines)
    
    def generate_component_diagram(
        self,
        raw_graph: RawGraph,
        package: str = "revenue_os",
    ) -> str:
        """
        Generate component diagram (C4 Level 3).
        
        Shows internal components within a container.
        
        Args:
            raw_graph: Raw dependency graph
            package: Package to focus on
        
        Returns:
            Mermaid diagram as string
        """
        lines = [
            "flowchart TD",
            f"    %% Component Diagram - {package}",
            "",
        ]
        
        # Filter nodes for this package
        package_nodes = [
            node for node in raw_graph.nodes.values()
            if package in node.relative_path
        ]
        
        # Group by folder
        components = {}
        for node in package_nodes:
            parts = node.relative_path.split("/")
            if len(parts) >= 3:
                component = parts[2]  # e.g., "services", "models", "agents"
                if component not in components:
                    components[component] = []
                components[component].append(node)
        
        # Add components
        for component_name, nodes in components.items():
            component_id = component_name.replace("_", "").title()
            file_count = len(nodes)
            
            lines.append(f"    {component_id}[\"{component_name}<br/>({file_count} files)\"]")
        
        lines.append("")
        
        # Add connections based on edges
        lines.append("    %% Connections")
        added_connections = set()
        
        for edge in raw_graph.edges:
            from_node = raw_graph.nodes.get(edge.from_node)
            to_node = raw_graph.nodes.get(edge.to_node)
            
            if from_node and to_node:
                from_parts = from_node.relative_path.split("/")
                to_parts = to_node.relative_path.split("/")
                
                if len(from_parts) >= 3 and len(to_parts) >= 3:
                    from_comp = from_parts[2].replace("_", "").title()
                    to_comp = to_parts[2].replace("_", "").title()
                    
                    if from_comp != to_comp:
                        conn_key = f"{from_comp}_{to_comp}"
                        if conn_key not in added_connections:
                            lines.append(f"    {from_comp} --> {to_comp}")
                            added_connections.add(conn_key)
        
        lines.append("")
        
        # Styling
        lines.extend([
            "    %% Styling",
            "    classDef component fill:#4A90E2,stroke:#2E5C8A,color:#fff",
            f"    class {','.join(components.keys())} component",
        ])
        
        return "\n".join(lines)
    
    def generate_dependency_graph(
        self,
        raw_graph: RawGraph,
        max_nodes: int = 20,
    ) -> str:
        """
        Generate file-level dependency graph.
        
        Args:
            raw_graph: Raw dependency graph
            max_nodes: Maximum nodes to show
        
        Returns:
            Mermaid diagram as string
        """
        lines = [
            "flowchart LR",
            "    %% File Dependency Graph",
            "",
        ]
        
        # Get most connected nodes
        node_connections = {}
        for edge in raw_graph.edges:
            node_connections[edge.from_node] = node_connections.get(edge.from_node, 0) + 1
            node_connections[edge.to_node] = node_connections.get(edge.to_node, 0) + 1
        
        top_nodes = sorted(
            node_connections.items(),
            key=lambda x: x[1],
            reverse=True
        )[:max_nodes]
        
        top_node_ids = {node_id for node_id, _ in top_nodes}
        
        # Add nodes
        for node_id in top_node_ids:
            if node_id in raw_graph.nodes:
                node = raw_graph.nodes[node_id]
                safe_id = node_id.replace("-", "")
                label = node.label.replace(".py", "")
                lines.append(f"    {safe_id}[\"{label}\"]")
        
        lines.append("")
        
        # Add edges
        lines.append("    %% Dependencies")
        for edge in raw_graph.edges:
            if edge.from_node in top_node_ids and edge.to_node in top_node_ids:
                from_id = edge.from_node.replace("-", "")
                to_id = edge.to_node.replace("-", "")
                lines.append(f"    {from_id} --> {to_id}")
        
        return "\n".join(lines)
    
    def generate_api_route_map(
        self,
        analyzer_results: List,
    ) -> str:
        """
        Generate API route map.
        
        Args:
            analyzer_results: List of analyzer results
        
        Returns:
            Mermaid diagram as string
        """
        lines = [
            "flowchart TD",
            "    %% API Route Map",
            "",
            "    Client[\"Client\"]",
            "",
        ]
        
        # Collect all routes
        routes = []
        for result in analyzer_results:
            routes.extend(result.routes)
        
        if not routes:
            lines.append("    NoRoutes[\"No API routes detected\"]")
            lines.append("    Client --> NoRoutes")
            return "\n".join(lines)
        
        # Group by method
        routes_by_method = {}
        for route in routes:
            method = route.method
            if method not in routes_by_method:
                routes_by_method[method] = []
            routes_by_method[method].append(route)
        
        # Add routes
        for method, method_routes in routes_by_method.items():
            lines.append(f"    %% {method} Routes")
            for i, route in enumerate(method_routes):
                route_id = f"{method}{i}"
                path = route.path
                handler = route.handler
                lines.append(f"    {route_id}[\"{method} {path}<br/>{handler}\"]")
                lines.append(f"    Client --> {route_id}")
            lines.append("")
        
        return "\n".join(lines)
    
    def _group_by_layer(self, raw_graph: RawGraph) -> Dict[str, List]:
        """Group nodes by architectural layer"""
        layers = {
            "api": [],
            "services": [],
            "models": [],
            "workers": [],
            "agents": [],
            "core": [],
            "other": [],
        }
        
        for node in raw_graph.nodes.values():
            path_lower = node.relative_path.lower()
            
            if "api" in path_lower or "routes" in path_lower:
                layers["api"].append(node)
            elif "service" in path_lower:
                layers["services"].append(node)
            elif "model" in path_lower or "schema" in path_lower:
                layers["models"].append(node)
            elif "worker" in path_lower or "task" in path_lower or "celery" in path_lower:
                layers["workers"].append(node)
            elif "agent" in path_lower:
                layers["agents"].append(node)
            elif "core" in path_lower:
                layers["core"].append(node)
            else:
                layers["other"].append(node)
        
        return layers
    
    def _detect_external_services(self, raw_graph: RawGraph) -> Set[str]:
        """Detect external services from imports"""
        external = set()
        
        # Check for common external services in node metadata
        for node in raw_graph.nodes.values():
            path_lower = node.relative_path.lower()
            
            # These would be detected from imports in actual implementation
            # For now, return empty set
            pass
        
        return external
    
    def _detect_containers(self, raw_graph: RawGraph) -> Dict[str, dict]:
        """Detect containers from folder structure"""
        containers = {}
        
        # Analyze folder structure
        has_api = any("api" in n.relative_path.lower() for n in raw_graph.nodes.values())
        has_services = any("service" in n.relative_path.lower() for n in raw_graph.nodes.values())
        has_models = any("model" in n.relative_path.lower() for n in raw_graph.nodes.values())
        has_workers = any("celery" in n.relative_path.lower() or "task" in n.relative_path.lower() for n in raw_graph.nodes.values())
        has_agents = any("agent" in n.relative_path.lower() for n in raw_graph.nodes.values())
        
        if has_api:
            containers["API"] = {"label": "API Layer", "tech": "FastAPI"}
        
        if has_services:
            containers["Services"] = {"label": "Service Layer", "tech": "Business Logic"}
        
        if has_models:
            containers["Models"] = {"label": "Data Models", "tech": "SQLAlchemy"}
        
        if has_workers:
            containers["Workers"] = {"label": "Background Workers", "tech": "Celery"}
        
        if has_agents:
            containers["Agents"] = {"label": "AI Agents", "tech": "LLM Integration"}
        
        return containers
