"""
xiarchitect.cli — Command-line interface
"""

import json
from pathlib import Path
from typing import Optional

import click

from .analyzers import AnalyzerRegistry
from .classifier import FileClassifier, StackDetector
from .core.config import XiArchitectConfig
from .core.types import AnalyzerResult, RouteDeclaration
from .core.logger import get_logger
from .diagrams import MermaidGenerator
from .graph import RawGraphBuilder
from .scanner import WorkspaceScanner

logger = get_logger(__name__)


_OUTPUT_REPLACEMENTS = {
    "—": "-",
    "•": "-",
    "✓": "[ok]",
    "❌": "ERROR",
    "🔍": "",
    "📂": "",
    "🏷️": "",
    "🔧": "",
    "📄": "",
    "📊": "",
    "✅": "",
    "🔬": "",
    "🕸️": "",
    "🎨": "",
}

_ORIGINAL_CLICK_ECHO = click.echo


def _safe_echo(message: Optional[object] = None, **kwargs) -> None:
    """Write CLI output without requiring a UTF-8 console."""
    if isinstance(message, str):
        for source, target in _OUTPUT_REPLACEMENTS.items():
            message = message.replace(source, target)
        message = message.encode("ascii", errors="ignore").decode("ascii")
    _ORIGINAL_CLICK_ECHO(message, **kwargs)


click.echo = _safe_echo


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """xiarchitect — Enterprise Architecture Intelligence System"""
    pass


@cli.command()
@click.option(
    "--workspace",
    "-w",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    help="Workspace root directory",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="docs/xiarchitect",
    help="Output directory for generated files",
)
@click.option(
    "--max-files",
    type=int,
    default=50000,
    help="Maximum number of files to scan",
)
@click.option(
    "--max-file-size",
    type=int,
    default=1024,
    help="Maximum file size in KB",
)
def scan(workspace: str, output: str, max_files: int, max_file_size: int):
    """
    Scan workspace and generate architecture intelligence.
    
    This is the master command that runs the full pipeline:
    - Scan workspace
    - Classify files
    - Detect stack
    - Generate reports
    """
    workspace_path = Path(workspace).resolve()
    output_path = Path(output)
    
    click.echo(f"🔍 xiarchitect — Scanning workspace: {workspace_path}")
    click.echo()
    
    # Create configuration
    config = XiArchitectConfig(
        workspace_root=workspace_path,
        max_files=max_files,
        max_file_size_kb=max_file_size,
        output_dir=str(output_path),
    )
    
    # Step 1: Scan workspace
    click.echo("📂 Step 1/3: Scanning workspace...")
    scanner = WorkspaceScanner(config)
    scanned_files = scanner.scan()
    click.echo(f"   ✓ Scanned {len(scanned_files)} files")
    click.echo()
    
    # Step 2: Classify files
    click.echo("🏷️  Step 2/3: Classifying files...")
    classifier = FileClassifier()
    classified_files = classifier.classify_batch(scanned_files)
    
    # Count by role
    role_counts = {}
    for file in classified_files:
        role = file.role.value
        role_counts[role] = role_counts.get(role, 0) + 1
    
    click.echo(f"   ✓ Classified {len(classified_files)} files")
    click.echo(f"   Top roles:")
    for role, count in sorted(role_counts.items(), key=lambda x: x[1], reverse=True)[:5]:
        click.echo(f"     - {role}: {count}")
    click.echo()
    
    # Step 3: Detect stack
    click.echo("🔧 Step 3/3: Detecting technology stack...")
    stack_detector = StackDetector()
    stack = stack_detector.detect(classified_files)
    
    click.echo(f"   ✓ Detected {len(stack.languages)} languages")
    click.echo(f"   ✓ Detected {len(stack.backend)} backend technologies")
    click.echo(f"   ✓ Detected {len(stack.frontend)} frontend technologies")
    click.echo(f"   ✓ Detected {len(stack.database)} database technologies")
    click.echo()
    
    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Export scan report
    scan_report_path = output_path / "scan-report.json"
    scan_report = {
        "workspace_root": str(workspace_path),
        "total_files": len(scanned_files),
        "classified_files": len(classified_files),
        "role_counts": role_counts,
        "files": [
            {
                "path": f.relative_path,
                "role": f.role.value,
                "language": f.language.value if f.language else None,
                "size_bytes": f.size_bytes,
                "is_sensitive": f.is_sensitive,
            }
            for f in classified_files[:100]  # Limit to first 100 for readability
        ]
    }
    
    with open(scan_report_path, "w", encoding="utf-8") as f:
        json.dump(scan_report, f, indent=2)
    
    click.echo(f"📄 Scan report: {scan_report_path}")
    
    # Export stack summary
    stack_summary_path = output_path / "stack-summary.json"
    stack_summary = {
        "languages": [
            {"name": t.name, "version": t.version, "confidence": t.confidence}
            for t in stack.languages
        ],
        "backend": [
            {"name": t.name, "version": t.version, "confidence": t.confidence}
            for t in stack.backend
        ],
        "frontend": [
            {"name": t.name, "version": t.version, "confidence": t.confidence}
            for t in stack.frontend
        ],
        "database": [
            {"name": t.name, "version": t.version, "confidence": t.confidence}
            for t in stack.database
        ],
        "cache": [
            {"name": t.name, "version": t.version, "confidence": t.confidence}
            for t in stack.cache
        ],
        "workers": [
            {"name": t.name, "version": t.version, "confidence": t.confidence}
            for t in stack.workers
        ],
        "overall_confidence": stack.overall_confidence,
    }
    
    with open(stack_summary_path, "w", encoding="utf-8") as f:
        json.dump(stack_summary, f, indent=2)
    
    click.echo(f"📄 Stack summary: {stack_summary_path}")
    click.echo()
    
    # Display stack summary
    click.echo("📊 Technology Stack Summary:")
    click.echo()
    
    if stack.languages:
        click.echo("  Languages:")
        for tech in stack.languages:
            version_str = f" {tech.version}" if tech.version else ""
            click.echo(f"    • {tech.name}{version_str} ({tech.confidence:.0%} confidence)")
    
    if stack.backend:
        click.echo("  Backend:")
        for tech in stack.backend:
            version_str = f" {tech.version}" if tech.version else ""
            click.echo(f"    • {tech.name}{version_str} ({tech.confidence:.0%} confidence)")
    
    if stack.frontend:
        click.echo("  Frontend:")
        for tech in stack.frontend:
            version_str = f" {tech.version}" if tech.version else ""
            click.echo(f"    • {tech.name}{version_str} ({tech.confidence:.0%} confidence)")
    
    if stack.database:
        click.echo("  Database:")
        for tech in stack.database:
            version_str = f" {tech.version}" if tech.version else ""
            click.echo(f"    • {tech.name}{version_str} ({tech.confidence:.0%} confidence)")
    
    if stack.cache:
        click.echo("  Cache:")
        for tech in stack.cache:
            version_str = f" {tech.version}" if tech.version else ""
            click.echo(f"    • {tech.name}{version_str} ({tech.confidence:.0%} confidence)")
    
    if stack.workers:
        click.echo("  Workers:")
        for tech in stack.workers:
            version_str = f" {tech.version}" if tech.version else ""
            click.echo(f"    • {tech.name}{version_str} ({tech.confidence:.0%} confidence)")
    
    click.echo()
    click.echo(f"✅ Architecture intelligence generated in: {output_path}")
    click.echo()
    click.echo("Next steps:")
    click.echo("  • Review scan-report.json for file classification")
    click.echo("  • Review stack-summary.json for detected technologies")
    click.echo("  • Run 'xiarchitect analyze' to generate architecture graph")


@cli.command()
@click.option(
    "--workspace",
    "-w",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    help="Workspace root directory",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="docs/xiarchitect",
    help="Output directory for generated files",
)
def analyze(workspace: str, output: str):
    """
    Analyze workspace and generate architecture graph.
    
    This command:
    - Scans workspace
    - Analyzes imports and dependencies
    - Builds raw dependency graph
    - Generates architecture-graph.json
    """
    workspace_path = Path(workspace).resolve()
    output_path = Path(output)
    
    click.echo(f"🔍 xiarchitect — Analyzing workspace: {workspace_path}")
    click.echo()
    
    # Create configuration
    config = XiArchitectConfig(
        workspace_root=workspace_path,
        output_dir=str(output_path),
    )
    
    # Step 1: Scan workspace
    click.echo("📂 Step 1/4: Scanning workspace...")
    scanner = WorkspaceScanner(config)
    scanned_files = scanner.scan()
    click.echo(f"   ✓ Scanned {len(scanned_files)} files")
    click.echo()
    
    # Step 2: Classify files
    click.echo("🏷️  Step 2/4: Classifying files...")
    classifier = FileClassifier()
    classified_files = classifier.classify_batch(scanned_files)
    click.echo(f"   ✓ Classified {len(classified_files)} files")
    click.echo()
    
    # Step 3: Analyze files
    click.echo("🔬 Step 3/4: Analyzing imports and dependencies...")
    analyzer_registry = AnalyzerRegistry(workspace_path)
    analyzer_results = analyzer_registry.analyze_batch(classified_files)
    
    total_imports = sum(len(r.imports) for r in analyzer_results)
    total_routes = sum(len(r.routes) for r in analyzer_results)
    total_models = sum(len(r.models) for r in analyzer_results)
    total_tasks = sum(len(r.tasks) for r in analyzer_results)
    
    click.echo(f"   ✓ Found {total_imports} imports")
    click.echo(f"   ✓ Found {total_routes} API routes")
    click.echo(f"   ✓ Found {total_models} database models")
    click.echo(f"   ✓ Found {total_tasks} background tasks")
    click.echo()
    
    # Step 4: Build graph
    click.echo("🕸️  Step 4/4: Building dependency graph...")
    graph_builder = RawGraphBuilder()
    raw_graph = graph_builder.build(classified_files, analyzer_results)
    
    click.echo(f"   ✓ Graph: {len(raw_graph.nodes)} nodes, {len(raw_graph.edges)} edges")
    click.echo()
    
    # Create output directory
    output_path.mkdir(parents=True, exist_ok=True)
    
    # Export raw dependency graph
    graph_path = output_path / "raw-dependency-graph.json"
    with open(graph_path, "w", encoding="utf-8") as f:
        json.dump(raw_graph.to_dict(), f, indent=2)

    analysis_results_path = output_path / "analysis-results.json"
    serialized_results = [
        {
            "file": result.file,
            "routes": [
                {
                    "method": route.method,
                    "path": route.path,
                    "handler": route.handler,
                    "file": route.file,
                    "line_number": route.line_number,
                }
                for route in result.routes
            ],
        }
        for result in analyzer_results
    ]
    with open(analysis_results_path, "w", encoding="utf-8") as f:
        json.dump(serialized_results, f, indent=2)
    
    click.echo(f"📄 Dependency graph: {graph_path}")
    click.echo(f"📄 Analysis results: {analysis_results_path}")
    click.echo()
    
    # Display summary
    click.echo("📊 Dependency Graph Summary:")
    click.echo()
    click.echo(f"  Nodes: {len(raw_graph.nodes)}")
    click.echo(f"  Edges: {len(raw_graph.edges)}")
    click.echo(f"  Imports: {total_imports}")
    click.echo(f"  API Routes: {total_routes}")
    click.echo(f"  Models: {total_models}")
    click.echo(f"  Tasks: {total_tasks}")
    click.echo()
    
    # Show top connected files
    if raw_graph.edges:
        click.echo("  Most Connected Files:")
        
        # Count connections per node
        connections = {}
        for edge in raw_graph.edges:
            connections[edge.from_node] = connections.get(edge.from_node, 0) + 1
            connections[edge.to_node] = connections.get(edge.to_node, 0) + 1
        
        # Get top 5
        top_nodes = sorted(connections.items(), key=lambda x: x[1], reverse=True)[:5]
        for node_id, count in top_nodes:
            if node_id in raw_graph.nodes:
                node = raw_graph.nodes[node_id]
                click.echo(f"    • {node.label} ({count} connections)")
    
    click.echo()
    click.echo(f"✅ Architecture graph generated in: {output_path}")
    click.echo()
    click.echo("Next steps:")
    click.echo("  • Review raw-dependency-graph.json for file dependencies")
    click.echo("  • Run 'xiarchitect diagram' to generate visual diagrams")


@cli.command()
@click.option(
    "--workspace",
    "-w",
    type=click.Path(exists=True, file_okay=False, dir_okay=True),
    default=".",
    help="Workspace root directory",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    default="docs/xiarchitect",
    help="Output directory for generated files",
)
@click.option(
    "--type",
    "-t",
    type=click.Choice(["all", "system", "container", "component", "dependency", "api"]),
    default="all",
    help="Diagram type to generate",
)
def diagram(workspace: str, output: str, type: str):
    """
    Generate architecture diagrams.
    
    This command:
    - Loads existing analysis
    - Generates Mermaid diagrams
    - Exports to .mmd files
    
    Diagram types:
    - system: System overview (C4 Level 1)
    - container: Container diagram (C4 Level 2)
    - component: Component diagram (C4 Level 3)
    - dependency: File dependency graph
    - api: API route map
    - all: Generate all diagrams
    """
    workspace_path = Path(workspace).resolve()
    output_path = Path(output)
    
    click.echo(f"📊 xiarchitect — Generating diagrams: {workspace_path}")
    click.echo()
    
    # Check if analysis exists
    graph_file = output_path / "raw-dependency-graph.json"
    stack_file = output_path / "stack-summary.json"
    
    if not graph_file.exists():
        click.echo("❌ Error: No dependency graph found.")
        click.echo("   Run 'xiarchitect analyze' first.")
        return
    
    # Load graph
    click.echo("📂 Loading dependency graph...")
    with open(graph_file, "r", encoding="utf-8") as f:
        graph_data = json.load(f)
    
    # Load stack
    stack_data = {}
    if stack_file.exists():
        with open(stack_file, "r", encoding="utf-8") as f:
            stack_data = json.load(f)

    analysis_results: list[AnalyzerResult] = []
    analysis_results_file = output_path / "analysis-results.json"
    if analysis_results_file.exists():
        with open(analysis_results_file, "r", encoding="utf-8") as f:
            serialized_results = json.load(f)
        analysis_results = [
            AnalyzerResult(
                file=item["file"],
                routes=[
                    RouteDeclaration(
                        method=route["method"],
                        path=route["path"],
                        handler=route["handler"],
                        file=route["file"],
                        line_number=route.get("line_number"),
                    )
                    for route in item.get("routes", [])
                ],
            )
            for item in serialized_results
        ]
    
    # Reconstruct graph (simplified)
    from .graph.raw_graph_builder import RawGraph, RawNode, RawEdge
    from .core.types import Evidence, EvidenceType
    
    raw_graph = RawGraph()
    
    # Add nodes
    for node_data in graph_data["nodes"]:
        node = RawNode(
            id=node_data["id"],
            path=node_data["path"],
            relative_path=node_data["path"],
            label=node_data["label"],
            language=node_data["language"],
            role=node_data["role"],
            importance_score=node_data.get("importance", 0.0),
        )
        raw_graph.add_node(node)
    
    # Add edges
    for edge_data in graph_data["edges"]:
        edge = RawEdge(
            id=edge_data["id"],
            from_node=edge_data["from"],
            to_node=edge_data["to"],
            edge_type=edge_data["type"],
            confidence=edge_data["confidence"],
            evidence=[],
        )
        raw_graph.add_edge(edge)
    
    click.echo(f"   ✓ Loaded {len(raw_graph.nodes)} nodes, {len(raw_graph.edges)} edges")
    click.echo()
    
    # Initialize generator
    generator = MermaidGenerator()
    
    # Create diagrams directory
    diagrams_path = output_path / "diagrams"
    diagrams_path.mkdir(parents=True, exist_ok=True)
    
    diagrams_generated = []
    
    # Generate diagrams based on type
    if type in ["all", "system"]:
        click.echo("🎨 Generating system overview diagram...")
        diagram_content = generator.generate_system_overview(raw_graph, stack_data)
        diagram_file = diagrams_path / "system-overview.mmd"
        with open(diagram_file, "w", encoding="utf-8") as f:
            f.write(diagram_content)
        diagrams_generated.append(("System Overview", diagram_file))
        click.echo(f"   ✓ {diagram_file}")
    
    if type in ["all", "container"]:
        click.echo("🎨 Generating container diagram...")
        diagram_content = generator.generate_container_diagram(raw_graph, stack_data)
        diagram_file = diagrams_path / "container-diagram.mmd"
        with open(diagram_file, "w", encoding="utf-8") as f:
            f.write(diagram_content)
        diagrams_generated.append(("Container Diagram", diagram_file))
        click.echo(f"   ✓ {diagram_file}")
    
    if type in ["all", "component"]:
        click.echo("🎨 Generating component diagram...")
        diagram_content = generator.generate_component_diagram(raw_graph)
        diagram_file = diagrams_path / "component-diagram.mmd"
        with open(diagram_file, "w", encoding="utf-8") as f:
            f.write(diagram_content)
        diagrams_generated.append(("Component Diagram", diagram_file))
        click.echo(f"   ✓ {diagram_file}")
    
    if type in ["all", "dependency"]:
        click.echo("🎨 Generating dependency graph...")
        diagram_content = generator.generate_dependency_graph(raw_graph)
        diagram_file = diagrams_path / "dependency-graph.mmd"
        with open(diagram_file, "w", encoding="utf-8") as f:
            f.write(diagram_content)
        diagrams_generated.append(("Dependency Graph", diagram_file))
        click.echo(f"   ✓ {diagram_file}")
    
    if type in ["all", "api"]:
        click.echo("🎨 Generating API route map...")
        diagram_content = generator.generate_api_route_map(analysis_results)
        diagram_file = diagrams_path / "api-routes.mmd"
        with open(diagram_file, "w", encoding="utf-8") as f:
            f.write(diagram_content)
        diagrams_generated.append(("API Route Map", diagram_file))
        click.echo(f"   ✓ {diagram_file}")
    
    click.echo()
    click.echo(f"✅ Generated {len(diagrams_generated)} diagrams in: {diagrams_path}")
    click.echo()
    
    # Display summary
    click.echo("📊 Generated Diagrams:")
    for name, path in diagrams_generated:
        click.echo(f"  • {name}: {path.name}")
    
    click.echo()
    click.echo("Next steps:")
    click.echo("  • View .mmd files in Mermaid-compatible viewer")
    click.echo("  • Use VS Code Mermaid extension")
    click.echo("  • Copy to https://mermaid.live for preview")


@cli.command()
def version():
    """Show xiarchitect version"""
    click.echo("xiarchitect v0.1.0")
    click.echo("Enterprise Architecture Intelligence System")


if __name__ == "__main__":
    cli()
