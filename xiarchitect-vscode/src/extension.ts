import * as vscode from "vscode";
import { ArchitectureTreeProvider } from "./sidebar/architectureTreeProvider";
import { XiArchitectService } from "./services/xiarchitectService";
import { ArchitecturePanel } from "./webview/architecturePanel";

function getActiveWorkspaceFolder(): vscode.WorkspaceFolder {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) {
    throw new Error("xiarchitect requires an open workspace folder.");
  }
  return folder;
}

export function activate(context: vscode.ExtensionContext): void {
  const service = new XiArchitectService(context);
  const treeProvider = new ArchitectureTreeProvider();

  context.subscriptions.push(
    vscode.window.registerTreeDataProvider("xiarchitect.architecture", treeProvider),
  );

  const generateCommand = vscode.commands.registerCommand(
    "xiarchitect.generateFullArchitecture",
    async () => {
      const workspaceFolder = getActiveWorkspaceFolder();

      await vscode.window.withProgress(
        {
          location: vscode.ProgressLocation.Notification,
          title: "xiarchitect: generating architecture",
          cancellable: false,
        },
        async () => {
          const snapshot = await service.generateFullArchitecture(workspaceFolder);
          treeProvider.setSnapshot(snapshot);
          ArchitecturePanel.createOrShow(context, snapshot);
        },
      );
    },
  );

  const openExplorerCommand = vscode.commands.registerCommand(
    "xiarchitect.openArchitectureExplorer",
    async () => {
      const workspaceFolder = getActiveWorkspaceFolder();
      const snapshot = await service.loadSnapshot(workspaceFolder);
      treeProvider.setSnapshot(snapshot);
      ArchitecturePanel.createOrShow(context, snapshot);
    },
  );

  const rescanCommand = vscode.commands.registerCommand(
    "xiarchitect.rescanWorkspace",
    async () => {
      await vscode.commands.executeCommand("xiarchitect.generateFullArchitecture");
    },
  );

  context.subscriptions.push(generateCommand, openExplorerCommand, rescanCommand);
}

export function deactivate(): void {}
