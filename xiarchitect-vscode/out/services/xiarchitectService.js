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
exports.XiArchitectService = void 0;
const node_child_process_1 = require("node:child_process");
const node_util_1 = require("node:util");
const fs = __importStar(require("node:fs/promises"));
const node_fs_1 = require("node:fs");
const path = __importStar(require("node:path"));
const vscode = __importStar(require("vscode"));
const execFileAsync = (0, node_util_1.promisify)(node_child_process_1.execFile);
class XiArchitectService {
    context;
    outputChannel = vscode.window.createOutputChannel("xiarchitect");
    constructor(context) {
        this.context = context;
    }
    async generateFullArchitecture(workspaceFolder) {
        const outputDir = this.getOutputDir(workspaceFolder);
        await this.runCliCommand("scan", workspaceFolder, outputDir);
        await this.runCliCommand("analyze", workspaceFolder, outputDir);
        await this.runCliCommand("diagram", workspaceFolder, outputDir, ["--type", "all"]);
        return this.loadSnapshot(workspaceFolder);
    }
    async loadSnapshot(workspaceFolder) {
        const outputDir = this.getOutputDir(workspaceFolder);
        const absoluteOutputDir = path.join(workspaceFolder.uri.fsPath, outputDir);
        const scanReport = await this.readJsonFile(path.join(absoluteOutputDir, "scan-report.json"));
        const stackSummary = await this.readJsonFile(path.join(absoluteOutputDir, "stack-summary.json"));
        const rawGraph = await this.readJsonFile(path.join(absoluteOutputDir, "raw-dependency-graph.json"));
        const diagrams = await this.listDiagramFiles(path.join(absoluteOutputDir, "diagrams"));
        return {
            workspaceRoot: workspaceFolder.uri.fsPath,
            outputDir: absoluteOutputDir,
            scanReport,
            stackSummary,
            rawGraph,
            diagrams,
        };
    }
    async runCliCommand(command, workspaceFolder, outputDir, extraArgs = []) {
        const pythonPath = vscode.workspace.getConfiguration("xiarchitect").get("pythonPath") ?? "python";
        const engineRoot = this.resolveEngineRoot(workspaceFolder);
        const args = [
            "-m",
            "xiarchitect",
            command,
            "--workspace",
            workspaceFolder.uri.fsPath,
            "--output",
            outputDir,
            ...extraArgs,
        ];
        this.outputChannel.appendLine(`> ${pythonPath} ${args.join(" ")}`);
        try {
            const result = await execFileAsync(pythonPath, args, {
                cwd: engineRoot,
                env: {
                    ...process.env,
                    PYTHONIOENCODING: "utf-8",
                },
                windowsHide: true,
                maxBuffer: 16 * 1024 * 1024,
            });
            if (result.stdout) {
                this.outputChannel.append(result.stdout);
            }
            if (result.stderr) {
                this.outputChannel.append(result.stderr);
            }
        }
        catch (error) {
            const message = error instanceof Error ? error.message : "Unknown xiarchitect engine failure";
            this.outputChannel.appendLine(message);
            this.outputChannel.show(true);
            throw new Error(`xiarchitect ${command} failed: ${message}`);
        }
    }
    resolveEngineRoot(workspaceFolder) {
        const candidates = [
            path.resolve(this.context.extensionPath, ".."),
            path.resolve(this.context.extensionPath, "..", ".."),
            workspaceFolder.uri.fsPath,
        ];
        for (const candidate of candidates) {
            const moduleEntry = path.join(candidate, "xiarchitect", "__main__.py");
            if ((0, node_fs_1.existsSync)(moduleEntry)) {
                return candidate;
            }
        }
        throw new Error("Unable to locate xiarchitect engine root. Expected xiarchitect/__main__.py near the extension or workspace.");
    }
    getOutputDir(workspaceFolder) {
        const configured = vscode.workspace.getConfiguration("xiarchitect", workspaceFolder).get("outputDir") ??
            "docs/xiarchitect";
        return configured.replaceAll("/", path.sep);
    }
    async readJsonFile(filePath) {
        try {
            const raw = await fs.readFile(filePath, "utf8");
            return JSON.parse(raw);
        }
        catch {
            return null;
        }
    }
    async listDiagramFiles(diagramDir) {
        try {
            const entries = await fs.readdir(diagramDir, { withFileTypes: true });
            return entries
                .filter((entry) => entry.isFile())
                .map((entry) => path.join(diagramDir, entry.name))
                .sort();
        }
        catch {
            return [];
        }
    }
}
exports.XiArchitectService = XiArchitectService;
//# sourceMappingURL=xiarchitectService.js.map