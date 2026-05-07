import { execFile } from "node:child_process";
import { promisify } from "node:util";
import * as fs from "node:fs/promises";
import { existsSync } from "node:fs";
import * as path from "node:path";
import * as vscode from "vscode";
import {
  XiArchitectRawGraph,
  XiArchitectScanReport,
  XiArchitectSnapshot,
  XiArchitectStackSummary,
} from "../core/types";

const execFileAsync = promisify(execFile);

export class XiArchitectService {
  private readonly outputChannel = vscode.window.createOutputChannel("xiarchitect");

  public constructor(private readonly context: vscode.ExtensionContext) {}

  public async generateFullArchitecture(
    workspaceFolder: vscode.WorkspaceFolder,
  ): Promise<XiArchitectSnapshot> {
    const outputDir = this.getOutputDir(workspaceFolder);

    await this.runCliCommand("scan", workspaceFolder, outputDir);
    await this.runCliCommand("analyze", workspaceFolder, outputDir);
    await this.runCliCommand("diagram", workspaceFolder, outputDir, ["--type", "all"]);

    return this.loadSnapshot(workspaceFolder);
  }

  public async loadSnapshot(
    workspaceFolder: vscode.WorkspaceFolder,
  ): Promise<XiArchitectSnapshot> {
    const outputDir = this.getOutputDir(workspaceFolder);
    const absoluteOutputDir = path.join(workspaceFolder.uri.fsPath, outputDir);

    const scanReport = await this.readJsonFile<XiArchitectScanReport>(
      path.join(absoluteOutputDir, "scan-report.json"),
    );
    const stackSummary = await this.readJsonFile<XiArchitectStackSummary>(
      path.join(absoluteOutputDir, "stack-summary.json"),
    );
    const rawGraph = await this.readJsonFile<XiArchitectRawGraph>(
      path.join(absoluteOutputDir, "raw-dependency-graph.json"),
    );
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

  private async runCliCommand(
    command: "scan" | "analyze" | "diagram",
    workspaceFolder: vscode.WorkspaceFolder,
    outputDir: string,
    extraArgs: string[] = [],
  ): Promise<void> {
    const pythonPath =
      vscode.workspace.getConfiguration("xiarchitect").get<string>("pythonPath") ?? "python";
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
    } catch (error) {
      const message =
        error instanceof Error ? error.message : "Unknown xiarchitect engine failure";
      this.outputChannel.appendLine(message);
      this.outputChannel.show(true);
      throw new Error(`xiarchitect ${command} failed: ${message}`);
    }
  }

  private resolveEngineRoot(workspaceFolder: vscode.WorkspaceFolder): string {
    const candidates = [
      path.resolve(this.context.extensionPath, ".."),
      path.resolve(this.context.extensionPath, "..", ".."),
      workspaceFolder.uri.fsPath,
    ];

    for (const candidate of candidates) {
      const moduleEntry = path.join(candidate, "xiarchitect", "__main__.py");
      if (existsSync(moduleEntry)) {
        return candidate;
      }
    }

    throw new Error(
      "Unable to locate xiarchitect engine root. Expected xiarchitect/__main__.py near the extension or workspace.",
    );
  }

  private getOutputDir(workspaceFolder: vscode.WorkspaceFolder): string {
    const configured =
      vscode.workspace.getConfiguration("xiarchitect", workspaceFolder).get<string>("outputDir") ??
      "docs/xiarchitect";
    return configured.replaceAll("/", path.sep);
  }

  private async readJsonFile<T>(filePath: string): Promise<T | null> {
    try {
      const raw = await fs.readFile(filePath, "utf8");
      return JSON.parse(raw) as T;
    } catch {
      return null;
    }
  }

  private async listDiagramFiles(diagramDir: string): Promise<string[]> {
    try {
      const entries = await fs.readdir(diagramDir, { withFileTypes: true });
      return entries
        .filter((entry) => entry.isFile())
        .map((entry) => path.join(diagramDir, entry.name))
        .sort();
    } catch {
      return [];
    }
  }
}
