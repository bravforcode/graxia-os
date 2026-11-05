' Silent launcher for NotebookLM auto-sync (no console popup)
Option Explicit
Dim sh
Set sh = CreateObject("WScript.Shell")
sh.Run "powershell.exe -NoProfile -ExecutionPolicy Bypass -File ""C:\Users\menum\graxia os\scripts\vault-pipeline\notebooklm-auto-sync.ps1""", 0, False