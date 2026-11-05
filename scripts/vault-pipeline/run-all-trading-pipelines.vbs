' Silent launcher for Graxia trading pipelines (no console popup)
Option Explicit
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.Run """C:\Program Files\PowerShell\7\pwsh.exe"" -NoProfile -ExecutionPolicy Bypass -File ""C:\Users\menum\graxia os\scripts\vault-pipeline\run-all-trading-pipelines.ps1""", 0, False