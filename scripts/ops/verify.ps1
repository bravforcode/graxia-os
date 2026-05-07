$ErrorActionPreference = "Stop"

function Invoke-Step {
    param(
        [string]$Label,
        [scriptblock]$Action
    )

    Write-Host "==> $Label"
    & $Action
}

function Assert-Success {
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code $LASTEXITCODE"
    }
}

function Get-BashExecutable {
    $preferredCandidates = @(
        (Join-Path $env:ProgramFiles "Git\bin\bash.exe"),
        (Join-Path $env:ProgramFiles "Git\usr\bin\bash.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Git\bin\bash.exe"),
        (Join-Path ${env:ProgramFiles(x86)} "Git\usr\bin\bash.exe")
    ) | Where-Object { $_ -and (Test-Path $_) }

    if ($preferredCandidates.Count -gt 0) {
        return $preferredCandidates[0]
    }

    $command = Get-Command bash -ErrorAction SilentlyContinue
    if (-not $command) {
        return $null
    }

    if ($command.Source -match 'Windows\\System32\\bash\.exe$' -or $command.Source -match 'WindowsApps\\bash\.exe$') {
        return $null
    }

    return $command.Source
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$bash = Get-BashExecutable

Push-Location $repoRoot
try {
    Invoke-Step "Backend tests" {
        Push-Location "backend"
        try {
            python -m pytest tests -q
            Assert-Success
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "OpenAPI export" {
        Push-Location "backend"
        try {
            python scripts/export_openapi.py --output openapi.json
            Assert-Success
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Frontend lint" {
        Push-Location "frontend"
        try {
            bun run lint
            Assert-Success
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Frontend tests" {
        Push-Location "frontend"
        try {
            bun run test
            Assert-Success
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Frontend build" {
        Push-Location "frontend"
        try {
            bun run build
            Assert-Success
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Frontend browser E2E" {
        Push-Location "frontend"
        try {
            bunx playwright install chromium
            Assert-Success
            bun run test:e2e
            Assert-Success
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Frontend Storybook build" {
        Push-Location "frontend"
        try {
            bun run build-storybook
            Assert-Success
        }
        finally {
            Pop-Location
        }
    }

    if (-not $bash) {
        throw "A Git Bash executable is required to validate shell scripts on Windows"
    }

    Invoke-Step "Shell script syntax" {
        & $bash -n setup.sh
        Assert-Success
        & $bash -n backend/scripts/backup_database.sh
        Assert-Success
        & $bash -n backend/scripts/restore_database.sh
        Assert-Success
        & $bash -n backend/scripts/smoke_tests.sh
        Assert-Success
    }

    Write-Host ""
    Write-Host "Verification completed successfully."
}
finally {
    Pop-Location
}
