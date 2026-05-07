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
exports.ArchitectureTreeProvider = void 0;
const path = __importStar(require("node:path"));
const vscode = __importStar(require("vscode"));
class ArchitectureTreeProvider {
    onDidChangeTreeDataEmitter = new vscode.EventEmitter();
    snapshot = null;
    onDidChangeTreeData = this.onDidChangeTreeDataEmitter.event;
    setSnapshot(snapshot) {
        this.snapshot = snapshot;
        this.onDidChangeTreeDataEmitter.fire();
    }
    getTreeItem(element) {
        if (element.kind === "root") {
            const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.Expanded);
            item.contextValue = "root";
            return item;
        }
        if (element.kind === "file") {
            const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.None);
            item.command = {
                command: "vscode.open",
                title: "Open File",
                arguments: [vscode.Uri.file(element.filePath)],
            };
            item.description = path.basename(element.filePath);
            item.contextValue = "artifactFile";
            return item;
        }
        const item = new vscode.TreeItem(element.label, vscode.TreeItemCollapsibleState.None);
        item.description = element.description;
        item.contextValue = "metric";
        return item;
    }
    getChildren(element) {
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
    workspaceNodes() {
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
    stackNodes() {
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
    graphNodes() {
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
    diagramNodes() {
        if (!this.snapshot?.diagrams.length) {
            return [{ kind: "metric", label: "No diagrams yet", description: "" }];
        }
        return this.snapshot.diagrams.map((diagram) => ({
            kind: "file",
            label: path.basename(diagram),
            filePath: diagram,
        }));
    }
    technologySection(category, technologies) {
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
exports.ArchitectureTreeProvider = ArchitectureTreeProvider;
//# sourceMappingURL=architectureTreeProvider.js.map