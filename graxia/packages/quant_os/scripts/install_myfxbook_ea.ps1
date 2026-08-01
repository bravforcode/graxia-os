<#
.SYNOPSIS
    Copy the Myfxbook publisher EA + DLL into every installed MT5 terminal data folder.

.DESCRIPTION
    Run this AFTER opening MetaTrader 5 and logging in (so the terminal has created its
    %APPDATA%\MetaQuotes\Terminal\<hash> data folder). It drops Myfxbook.ex5 into
    MQL5\Experts and Myfxbook.dll into MQL5\Libraries for every detected terminal.

    Source EA files are expected next to this script's parent (Downloads\MQL5\...) or in
    the same folder as this script. Edit $SrcRoot if your layout differs.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File scripts/install_myfxbook_ea.ps1
#>

$ErrorActionPreference = "Stop"

# Where the extracted EA files live (adjust if you moved them).
$SrcRoot = "C:\Users\menum\Downloads"
$SrcEA  = Join-Path $SrcRoot "MQL5\Experts\Myfxbook.ex5"
$SrcDLL = Join-Path $SrcRoot "MQL5\Libraries\Myfxbook.dll"

if (-not (Test-Path $SrcEA)) { Write-Host "[FAIL] Myfxbook.ex5 not found at $SrcEA"; exit 1 }
if (-not (Test-Path $SrcDLL)) { Write-Host "[FAIL] Myfxbook.dll not found at $SrcDLL"; exit 1 }

# MT5 is 64-bit only and can load ONLY 64-bit DLLs. The Myfxbook EA publisher
# requires Myfxbook.dll; a 32-bit copy fails with "is not 64-bit version" / [193].
# Refuse to deploy a 32-bit DLL so we never silently break every terminal.
function Get-PEMachine([string]$Path) {
    $d = [System.IO.File]::ReadAllBytes($Path)
    if ($d[0..1] -join '' -ne '7790') { return $null }          # not 'MZ'
    $e_lfanew = [BitConverter]::ToInt32($d, 0x3C)
    if ([System.Text.Encoding]::ASCII.GetString($d, $e_lfanew, 2) -ne 'PE') { return $null }
    return [BitConverter]::ToUInt16($d, $e_lfanew + 4)
}
$machine = Get-PEMachine $SrcDLL
if ($machine -ne 0x8664) {
    Write-Host "[FAIL] Myfxbook.dll is 32-bit (machine=0x$($machine.ToString('X'))). MT5 is 64-bit and cannot load it."
    Write-Host "       Fix: obtain the 64-bit Myfxbook EA publisher package, then replace:"
    Write-Host "         $SrcDLL"
    Write-Host "       with the 64-bit Myfxbook.dll, and re-run this script."
    Write-Host "       Get it from: myfxbook.com (log in > your account > Publish/EA download),"
    Write-Host "       or inside MT5: Tools > Code Base > search 'myfxbook' > install."
    exit 1
}

$Base = "C:\Users\menum\AppData\Roaming\MetaQuotes\Terminal"
if (-not (Test-Path $Base)) {
    Write-Host "[FAIL] No MT5 data folder at $Base. Open MT5 and log in first, then re-run."
    exit 1
}

$folders = Get-ChildItem $Base -Force -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -match '^[0-9A-F]{32}$' }

if (-not $folders) {
    Write-Host "[FAIL] No terminal data folders found. Open MT5 and log in first, then re-run."
    exit 1
}

$count = 0
foreach ($f in $folders) {
    $exp = Join-Path $f.FullName "MQL5\Experts"
    $lib = Join-Path $f.FullName "MQL5\Libraries"
    New-Item -ItemType Directory -Force -Path $exp, $lib | Out-Null
    Copy-Item $SrcEA  $exp -Force
    Copy-Item $SrcDLL $lib -Force
    Write-Host ("[OK] {0}: EA={1} DLL={2}" -f $f.Name,
        (Test-Path (Join-Path $exp "Myfxbook.ex5")),
        (Test-Path (Join-Path $lib "Myfxbook.dll")))
    $count++
}

Write-Host ""
Write-Host "[DONE] Copied into $count terminal folder(s)."
Write-Host "Next: in MT5 Navigator, right-click 'Expert Advisors' > Refresh,"
Write-Host "       drag 'Myfxbook' onto a chart, set your myfxbook email/password in inputs,"
Write-Host "       and enable Algo Trading (AutoTrading button)."
