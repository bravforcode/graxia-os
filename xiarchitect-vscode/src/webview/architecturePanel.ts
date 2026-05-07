import * as path from "node:path";
import * as vscode from "vscode";
import { XiArchitectSnapshot } from "../core/types";

export class ArchitecturePanel {
  private static currentPanel: ArchitecturePanel | undefined;

  public static createOrShow(
    context: vscode.ExtensionContext,
    snapshot: XiArchitectSnapshot | null,
  ): ArchitecturePanel {
    const column = vscode.window.activeTextEditor?.viewColumn;

    if (ArchitecturePanel.currentPanel) {
      ArchitecturePanel.currentPanel.panel.reveal(column);
      ArchitecturePanel.currentPanel.update(snapshot);
      return ArchitecturePanel.currentPanel;
    }

    const panel = vscode.window.createWebviewPanel(
      "xiarchitectExplorer",
      "xiarchitect Explorer",
      column ?? vscode.ViewColumn.One,
      {
        enableScripts: false,
        retainContextWhenHidden: true,
      },
    );

    ArchitecturePanel.currentPanel = new ArchitecturePanel(panel, context, snapshot);
    return ArchitecturePanel.currentPanel;
  }

  private constructor(
    private readonly panel: vscode.WebviewPanel,
    private readonly context: vscode.ExtensionContext,
    snapshot: XiArchitectSnapshot | null,
  ) {
    this.update(snapshot);
    this.panel.onDidDispose(() => {
      ArchitecturePanel.currentPanel = undefined;
    });
  }

  public update(snapshot: XiArchitectSnapshot | null): void {
    this.panel.webview.html = this.render(snapshot);
  }

  private render(snapshot: XiArchitectSnapshot | null): string {
    if (!snapshot) {
      return `<!DOCTYPE html>
<html lang="en">
<body>
  <h2>xiarchitect</h2>
  <p>No architecture snapshot loaded yet.</p>
  <p>Run <strong>xiarchitect: Generate Full Architecture</strong> first.</p>
</body>
</html>`;
    }

    const stackBlocks = this.renderStack(snapshot);
    const diagrams = snapshot.diagrams
      .map((diagram) => `<li>${path.basename(diagram)}</li>`)
      .join("");

    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <style>
    body {
      font-family: var(--vscode-font-family);
      color: var(--vscode-editor-foreground);
      background: var(--vscode-editor-background);
      padding: 16px;
      line-height: 1.5;
    }
    .card {
      border: 1px solid var(--vscode-editorGroup-border);
      background: var(--vscode-editorWidget-background);
      border-radius: 8px;
      padding: 12px 14px;
      margin-bottom: 12px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }
    h1, h2, h3 {
      margin: 0 0 10px;
    }
    ul {
      margin: 0;
      padding-left: 18px;
    }
    code {
      font-family: var(--vscode-editor-font-family);
    }
  </style>
</head>
<body>
  <h1>xiarchitect Explorer</h1>
  <div class="card">
    <h2>Workspace</h2>
    <div><strong>Root:</strong> <code>${snapshot.workspaceRoot}</code></div>
    <div><strong>Output:</strong> <code>${snapshot.outputDir}</code></div>
    <div><strong>Files scanned:</strong> ${snapshot.scanReport?.total_files ?? 0}</div>
    <div><strong>Graph:</strong> ${snapshot.rawGraph?.nodes.length ?? 0} nodes, ${snapshot.rawGraph?.edges.length ?? 0} edges</div>
  </div>
  <div class="card">
    <h2>Detected Stack</h2>
    <div class="grid">${stackBlocks}</div>
  </div>
  <div class="card">
    <h2>Generated Diagrams</h2>
    <ul>${diagrams || "<li>No diagrams generated</li>"}</ul>
  </div>
</body>
</html>`;
  }

  private renderStack(snapshot: XiArchitectSnapshot): string {
    const sections = [
      ["Languages", snapshot.stackSummary?.languages ?? []],
      ["Backend", snapshot.stackSummary?.backend ?? []],
      ["Frontend", snapshot.stackSummary?.frontend ?? []],
      ["Database", snapshot.stackSummary?.database ?? []],
      ["Cache", snapshot.stackSummary?.cache ?? []],
      ["Workers", snapshot.stackSummary?.workers ?? []],
    ] as const;

    return sections
      .map(([title, technologies]) => {
        const items = technologies
          .map((technology) => {
            const version = technology.version ? ` ${technology.version}` : "";
            return `<li>${technology.name}${version}</li>`;
          })
          .join("");

        return `<section class="card">
  <h3>${title}</h3>
  <ul>${items || "<li>None detected</li>"}</ul>
</section>`;
      })
      .join("");
  }
}
