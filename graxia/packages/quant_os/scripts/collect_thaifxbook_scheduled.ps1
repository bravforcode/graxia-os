# Scheduled-task wrapper for the Thaifxbook collector.
# Scheduled tasks do NOT inherit shell env or cwd, so this wrapper pins the
# project root and invokes the collector the same way as manual runs.
param(
    [string]$PythonPath = "C:\Users\menum\AppData\Local\Programs\Python\Python312\python.exe"
)

$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectRoot = Resolve-Path "$scriptDir\.."
Set-Location $projectRoot

Write-Host "[thaifxbook-scheduled] starting: $PythonPath scripts/collect_thaifxbook.py $args"
& $PythonPath -u scripts/collect_thaifxbook.py @args
exit $LASTEXITCODE
