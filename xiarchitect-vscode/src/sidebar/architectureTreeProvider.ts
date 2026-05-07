import * as path from "node:path";
import * as vscode from "vscode";
import { XiArchitectSnapshot, XiArchitectTechnology } from "../core/types";

type TreeNode =
  | { kind: "root"; label: string }
  | { kind: "metric"; label: string; description?: string }
  | { kind: "file"; label: string; filePath: string };

export class ArchitectureTreeProvider
  implements vscode.TreeDataProvider<TreeNode>
{
  private readonly onDidChangeTreeDataEmitter = new vscode.EventEmitter<
    TreeNode | undefined | null | void
  >();

  private snapshot: XiArchitectSnapshot | null = null;

  public readonly onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;

  public setSnapshot(snapshot: XiArchitectSnapshot | null): void {
    this.snapshot = snapshot;
    this.onDidChangeTreeDataEmitter.fire();
  }

  public getTreeItem(element: TreeNode): vscode.TreeItem {
    if (element.kind === "root") {
      const item = new vscode.TreeItem(
        element.label,
        vscode.TreeItemCollapsibleState.Expanded,
      );
      item.contextValue = "root";
      return item;
    }

    if (element.kind === "file") {
      const item = new vscode.TreeItem(
        element.label,
        vscode.TreeItemCollapsibleState.None,
      );
      item.command = {
        command: "vscode.open",
        title: "Open File",
        arguments: [vscode.Uri.file(element.filePath)],
      };
      item.description = path.basename(element.filePath);
      item.contextValue = "artifactFile";
      return item;
    }

    const item = new vscode.TreeItem(
      element.label,
      vscode.TreeItemCollapsibleState.None,
    );
    item.description = element.description;
    item.contextValue = "metric";
    return item;
  }

  public getChildren(element?: TreeNode): Thenable<TreeNode[]> {
    if (!this.snapshot) {
      return Promise.resolve([
        {
          kind: "metric",
          label: "No architecture snapshot yet",
          description: "Run xiarchitect: Generate Full Architecture",
        },
      ]);
    }

    if (!element) {
      return Promise.resolve([
        { kind: "root", label: "Workspace" },
        { kind: "root", label: "Stack" },
        { kind: "root", label: "Graph" },
        { kind: "root", label: "Diagrams" },
      ]);
    }

    switch (element.label) {
      case "Workspace":
        return Promise.resolve(this.workspaceNodes());
      case "Stack":
        return Promise.resolve(this.stackNodes());
      case "Graph":
        return Promise.resolve(this.graphNodes());
      case "Diagrams":
        return Promise.resolve(this.diagramNodes());
      default:
        return Promise.resolve([]);
    }
  }

  private workspaceNodes(): TreeNode[] {
    if (!this.snapshot) {
      return [];
    }

    return [
      {
        kind: "metric",
        label: path.basename(this.snapshot.workspaceRoot),
        description: this.snapshot.workspaceRoot,
      },
      {
        kind: "metric",
        label: "Output",
        description: this.snapshot.outputDir,
      },
      {
        kind: "metric",
        label: "Files scanned",
        description: String(this.snapshot.scanReport?.total_files ?? 0),
      },
    ];
  }

  private stackNodes(): TreeNode[] {
    if (!this.snapshot?.stackSummary) {
      return [{ kind: "metric", label: "No stack summary", description: "" }];
    }

    return [
      ...this.technologySection("Language", this.snapshot.stackSummary.languages),
      ...this.technologySection("Backend", this.snapshot.stackSummary.backend),
      ...this.technologySection("Frontend", this.snapshot.stackSummary.frontend),
      ...this.technologySection("Database", this.snapshot.stackSummary.database),
      ...this.technologySection("Cache", this.snapshot.stackSummary.cache),
      ...this.technologySection("Workers", this.snapshot.stackSummary.workers),
    ];
  }

  private graphNodes(): TreeNode[] {
    if (!this.snapshot?.rawGraph) {
      return [{ kind: "metric", label: "No graph yet", description: "" }];
    }

    return [
      {
        kind: "metric",
        label: "Nodes",
        description: String(this.snapshot.rawGraph.nodes.length),
      },
      {
        kind: "metric",
        label: "Edges",
        description: String(this.snapshot.rawGraph.edges.length),
      },
    ];
  }

  private diagramNodes(): TreeNode[] {
    if (!this.snapshot?.diagrams.length) {
      return [{ kind: "metric", label: "No diagrams yet", description: "" }];
    }

    return this.snapshot.diagrams.map((diagram) => ({
      kind: "file",
      label: path.basename(diagram),
      filePath: diagram,
    }));
  }

  private technologySection(
    category: string,
    technologies: XiArchitectTechnology[],
  ): TreeNode[] {
    if (!technologies.length) {
      return [];
    }

    return technologies.map((technology) => ({
      kind: "metric",
      label: `${category}: ${technology.name}`,
      description: technology.version ?? `${Math.round(technology.confidence * 100)}%`,
    }));
  }
}
