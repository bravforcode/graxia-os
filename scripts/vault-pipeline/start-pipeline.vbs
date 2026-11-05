' Silent launcher for Graxia Vault Pipeline (no console popup)
Option Explicit
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.Run """C:\Program Files\PowerShell\7\pwsh.exe"" -NoProfile -ExecutionPolicy Bypass -File ""C:\Users\menum\graxia os\scripts\vault-pipeline\start-pipeline.ps1"" -Daemon", 0, False