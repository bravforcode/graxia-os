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
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = __importStar(require("vscode"));
const architectureTreeProvider_1 = require("./sidebar/architectureTreeProvider");
const xiarchitectService_1 = require("./services/xiarchitectService");
const architecturePanel_1 = require("./webview/architecturePanel");
function getActiveWorkspaceFolder() {
    const folder = vscode.workspace.workspaceFolders?.[0];
    if (!folder) {
        throw new Error("xiarchitect requires an open workspace folder.");
    }
    return folder;
}
function activate(context) {
    const service = new xiarchitectService_1.XiArchitectService(context);
    const treeProvider = new architectureTreeProvider_1.ArchitectureTreeProvider();
    context.subscriptions.push(vscode.window.registerTreeDataProvider("xiarchitect.architecture", treeProvider));
    const generateCommand = vscode.commands.registerCommand("xiarchitect.generateFullArchitecture", async () => {
        const workspaceFolder = getActiveWorkspaceFolder();
        await vscode.window.withProgress({
            location: vscode.ProgressLocation.Notification,
            title: "xiarchitect: generating architecture",
            cancellable: false,
        }, async () => {
            const snapshot = await service.generateFullArchitecture(workspaceFolder);
            treeProvider.setSnapshot(snapshot);
            architecturePanel_1.ArchitecturePanel.createOrShow(context, snapshot);
        });
    });
    const openExplorerCommand = vscode.commands.registerCommand("xiarchitect.openArchitectureExplorer", async () => {
        const workspaceFolder = getActiveWorkspaceFolder();
        const snapshot = await service.loadSnapshot(workspaceFolder);
        treeProvider.setSnapshot(snapshot);
        architecturePanel_1.ArchitecturePanel.createOrShow(context, snapshot);
    });
    const rescanCommand = vscode.commands.registerCommand("xiarchitect.rescanWorkspace", async () => {
        await vscode.commands.executeCommand("xiarchitect.generateFullArchitecture");
    });
    context.subscriptions.push(generateCommand, openExplorerCommand, rescanCommand);
}
function deactivate() { }
//# sourceMappingURL=extension.js.map