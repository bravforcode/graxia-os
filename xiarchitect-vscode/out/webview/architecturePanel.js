"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __setModuleDefault = (this && this.__setModuleDefault) || (Object.create ? (function(o, v) {
    Object.defineProperty(o, "default", { enumerable: true, value: v });
}) : function(o, v) {
    o["default"] = v;
});
var __importStar = (this && this.__importStar) || (function () {
    var ownKeys = function(o) {
        ownKeys = Object.getOwnPropertyNames || function (o) {
            var ar = [];
            for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) ar[ar.length] = k;
            return ar;
        };
        return ownKeys(o);
    };
    return function (mod) {
        if (mod && mod.__esModule) return mod;
        var result = {};
        if (mod != null) for (var k = ownKeys(mod), i = 0; i < k.length; i++) if (k[i] !== "default") __createBinding(result, mod, k[i]);
        __setModuleDefault(result, mod);
        return result;
    };
})();
Object.defineProperty(exports, "__esModule", { value: true });
exports.ArchitecturePanel = void 0;
const path = __importStar(require("node:path"));
const vscode = __importStar(require("vscode"));
class ArchitecturePanel {
    panel;
    context;
    static currentPanel;
    static createOrShow(context, snapshot) {
        const column = vscode.window.activeTextEditor?.viewColumn;
        if (ArchitecturePanel.currentPanel) {
            ArchitecturePanel.currentPanel.panel.reveal(column);
            ArchitecturePanel.currentPanel.update(snapshot);
            return ArchitecturePanel.currentPanel;
        }
        const panel = vscode.window.createWebviewPanel("xiarchitectExplorer", "xiarchitect Explorer", column ?? vscode.ViewColumn.One, {
            enableScripts: false,
            retainContextWhenHidden: true,
        });
        ArchitecturePanel.currentPanel = new ArchitecturePanel(panel, context, snapshot);
        return ArchitecturePanel.currentPanel;
    }
    constructor(panel, context, snapshot) {
        this.panel = panel;
        this.context = context;
        this.update(snapshot);
        this.panel.onDidDispose(() => {
            ArchitecturePanel.currentPanel = undefined;
        });
    }
    update(snapshot) {
        this.panel.webview.html = this.render(snapshot);
    }
    render(snapshot) {
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
    renderStack(snapshot) {
        const sections = [
            ["Languages", snapshot.stackSummary?.languages ?? []],
            ["Backend", snapshot.stackSummary?.backend ?? []],
            ["Frontend", snapshot.stackSummary?.frontend ?? []],
            ["Database", snapshot.stackSummary?.database ?? []],
            ["Cache", snapshot.stackSummary?.cache ?? []],
            ["Workers", snapshot.stackSummary?.workers ?? []],
        ];
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
exports.ArchitecturePanel = ArchitecturePanel;
//# sourceMappingURL=architecturePanel.js.map