# Rename folder from 'graxia os' to 'graxiaos'
# Run this script when the IDE is closed

$oldPath = "C:\Users\menum\graxia os"
$newPath = "C:\Users\menum\graxiaos"

if (Test-Path $oldPath) {
    Rename-Item -Path $oldPath -NewName "graxiaos"
    Write-Host "Renamed: $oldPath -> $newPath" -ForegroundColor Green
} else {
    Write-Host "Source folder not found: $oldPath" -ForegroundColor Red
}
