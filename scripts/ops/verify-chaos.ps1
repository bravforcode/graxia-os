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

function Assert-DockerEngine {
    docker info *> $null
    if ($LASTEXITCODE -ne 0) {
        throw "Docker engine is not available. Start Docker Desktop (Linux containers) and retry."
    }
}

function Wait-HttpOk {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$Retries = 40,
        [int]$DelaySeconds = 3
    )

    for ($i = 0; $i -lt $Retries; $i++) {
        try {
            $response = Invoke-RestMethod -Uri $Url -TimeoutSec 5 -Method Get
            if ($null -ne $response) {
                return
            }
        }
        catch {
        }
        Start-Sleep -Seconds $DelaySeconds
    }

    throw "HTTP endpoint did not become ready: $Url"
}

function Wait-HttpReachable {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [int]$Retries = 40,
        [int]$DelaySeconds = 3,
        [int[]]$AcceptStatusCodes = @(200, 401, 403, 404)
    )

    for ($i = 0; $i -lt $Retries; $i++) {
        try {
            $response = Invoke-WebRequest -Uri $Url -TimeoutSec 5 -Method Get -SkipHttpErrorCheck
            if ($AcceptStatusCodes -contains $response.StatusCode) {
                return
            }
        }
        catch {
        }
        Start-Sleep -Seconds $DelaySeconds
    }

    throw "HTTP endpoint did not become reachable: $Url"
}

function Wait-PostgresReady {
    param(
        [int]$Retries = 40,
        [int]$DelaySeconds = 2
    )

    for ($i = 0; $i -lt $Retries; $i++) {
        docker exec personal_os_postgres pg_isready -U personal_os *> $null
        if ($LASTEXITCODE -eq 0) {
            return
        }
        Start-Sleep -Seconds $DelaySeconds
    }

    throw "Postgres did not become ready"
}

function Reset-PostgresVolume {
    $containerId = docker ps -a --filter "name=personal_os_postgres" --format "{{.ID}}"
    if (-not $containerId) {
        return
    }

    $volumeName = docker inspect $containerId --format '{{ range .Mounts }}{{ if eq .Destination "/var/lib/postgresql/data" }}{{ .Name }}{{ end }}{{ end }}' 2>$null
    if (-not $volumeName) {
        $volumeName = "bravos_postgres_data"
    }

    docker compose --profile default down
    Assert-Success

    docker volume rm -f $volumeName
    Assert-Success

    docker compose --profile default up -d postgres redis
    Assert-Success
    Wait-PostgresReady
}

$repoRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location $repoRoot
try {
    Invoke-Step "Docker engine availability" {
        Assert-DockerEngine
    }

    Invoke-Step "Start core infrastructure (Postgres + Redis)" {
        docker compose --profile default up -d postgres redis
        Assert-Success
        Wait-PostgresReady
    }

    Invoke-Step "Database migrations (Alembic)" {
        Push-Location "backend"
        try {
            python scripts/alembic_safe.py upgrade head
            if ($LASTEXITCODE -ne 0) {
                Reset-PostgresVolume
                python scripts/alembic_safe.py upgrade head
            }
            Assert-Success
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Start runtime services (API + Celery + Beat)" {
        docker compose --profile default up -d backend celery beat
        Assert-Success
    }

    Invoke-Step "Wait for API readiness" {
        Wait-HttpOk -Url "http://localhost:8000/health"
        Wait-HttpReachable -Url "http://localhost:8000/api/v1/system/health"
    }

    Invoke-Step "Backend system verification (live dependencies)" {
        Push-Location "backend"
        try {
            python scripts/verify_system.py
            Assert-Success
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step "Deployment smoke test (HTTP)" {
        python deploy/scripts/smoke_test.py --target "http://localhost:8000"
        Assert-Success
    }

    Invoke-Step "Chaos: restart Redis then re-check health" {
        docker restart personal_os_redis
        Assert-Success
        Wait-HttpOk -Url "http://localhost:8000/health"
    }

    Invoke-Step "Chaos: restart Postgres then re-check health" {
        docker restart personal_os_postgres
        Assert-Success
        Wait-HttpOk -Url "http://localhost:8000/health"
    }

    Write-Host ""
    Write-Host "Chaos verification completed successfully."
}
finally {
    Pop-Location
}
