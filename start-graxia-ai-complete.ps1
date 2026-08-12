#!/usr/bin/env pwsh
# Graxia OS Complete AI System - Backend + OpenClaude Integration
# Starts: Backend API → Waits for ready → Launches OpenClaude with Graxia as AI provider

param(
    [string]$Model = "kimi-k2.5:cloud",
    [switch]$SkipBackend
)

$ErrorActionPreference = "Stop"

function Write-Header($text) {
    Write-Host "`n╔══════════════════════════════════════════════════════════════╗" -ForegroundColor Cyan
    Write-Host "║ $text" -ForegroundColor Cyan
    Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor Cyan
}

function Write-Success($text) {
    Write-Host "   ✅ $text" -ForegroundColor Green
}

function Write-Error($text) {
    Write-Host "   ❌ $text" -ForegroundColor Red
}

function Write-Info($text) {
    Write-Host "   ℹ️  $text" -ForegroundColor Gray
}

Write-Header "Graxia OS AI - Complete System Startup"

# Configuration
$apiKey = "sk-dbeee8e2e35c4635939848280521f6aa"
$baseUrl = "https://ollama-pay.thaigqsoft.com/api/v1"
$graxiaPath = "C:\graxia os"
if (-not (Test-Path $graxiaPath)) {
    $graxiaPath = "C:\Users\menum\graxia os"
}

Write-Host "`n📁 Graxia Path: $graxiaPath" -ForegroundColor Gray

# Step 1: Start Backend (if not skipped)
if (-not $SkipBackend) {
    Write-Host "`n[Step 1] Starting Graxia Backend..." -ForegroundColor Cyan
    
    # Check if backend already running
    try {
        $health = Invoke-RestMethod -Uri "http://localhost:8000/api/system/health" -TimeoutSec 2 -ErrorAction Stop
        Write-Success "Backend already running (API healthy)"
    } catch {
        Write-Info "Starting new backend instance..."
        
        # Check Python venv
        $venvPython = Join-Path $graxiaPath "backend\venv\Scripts\python.exe"
        if (-not (Test-Path $venvPython)) {
            Write-Error "Python venv not found at: $venvPython"
            Write-Host "   Creating venv..." -ForegroundColor Yellow
            
            Push-Location "$graxiaPath\backend"
            try {
                python -m venv venv 2>&1 | Out-Null
                & .\venv\Scripts\pip.exe install -r requirements.txt -q 2>&1 | Out-Null
                Write-Success "Created and installed venv"
            } catch {
                Write-Error "Failed to create venv: $_"
                exit 1
            } finally { Pop-Location }
        }
        
        # Start Redis
        try {
            $pong = (redis-cli ping 2>$null)
            if ($pong -ne "PONG") {
                Start-Process "redis-server" -ArgumentList "--port 6379" -WindowStyle Hidden
                Start-Sleep -Seconds 2
                Write-Info "Redis started"
            }
        } catch {}
        
        # Start backend using python directly (avoiding uvicorn.exe path issues)
        $backendLog = Join-Path $graxiaPath "logs\backend.log"
        $null = New-Item -ItemType Directory -Force -Path (Split-Path $backendLog)
        
        $env:OLLAMA_PAY_API_KEY = $apiKey
        $env:OLLAMA_PAY_BASE_URL = $baseUrl
        $env:PYTHONPATH = "$graxiaPath\backend"
        
        # Use python -m uvicorn instead of uvicorn.exe
        $backendJob = Start-Process -FilePath $venvPython -ArgumentList @(
            "-m", "uvicorn",
            "app.main:app",
            "--host", "0.0.0.0",
            "--port", "8000",
            "--workers", "1"
        ) -WorkingDirectory "$graxiaPath\backend" -PassThru -WindowStyle Hidden
        
        # Wait for startup
        Write-Info "Waiting for backend to start..."
        $ready = $false
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 1
            try {
                $health = Invoke-RestMethod -Uri "http://localhost:8000/api/system/health" -TimeoutSec 2
                $ready = $true
                break
            } catch {}
        }
        
        if ($ready) {
            Write-Success "Backend started and ready!"
            Write-Info "API: http://localhost:8000"
        } else {
            Write-Error "Backend failed to start in time"
            exit 1
        }
    }
} else {
    Write-Info "Skipping backend start (using existing)"
}

# Step 2: Configure OpenClaude to use Graxia Backend
Write-Host "`n[Step 2] Configuring OpenClaude for Graxia..." -ForegroundColor Cyan

# Create config for Graxia Backend as AI provider
$graxiaConfig = @{
    provider = "openai"
    model = $Model
    base_url = "http://localhost:8000/ai/v1"  # Graxia AI endpoint
    api_key = "graxia-local-key"  # Local key for Graxia
    env = @{
        GRAXIA_MODE = "1"
        OLLAMA_PAY_API_KEY = $apiKey
        OLLAMA_PAY_BASE_URL = $baseUrl
    }
}

# Update settings.json
$settingsPath = "$env:USERPROFILE\.openclaude\settings.json"
$settingsJson = $graxiaConfig | ConvertTo-Json -Depth 3
$settingsJson | Set-Content $settingsPath
Write-Success "Updated OpenClaude settings for Graxia"

# Create .claude.json for Graxia mode
$claudeConfig = @{
    provider = "openai"
    model = $Model
    base_url = "http://localhost:8000/ai/v1"
    api_key = "graxia-local-key"
} | ConvertTo-Json -Depth 3
$claudeConfig | Set-Content "$env:USERPROFILE\.claude.json"
Write-Success "Created .claude.json with Graxia endpoint"

# Step 3: Launch OpenClaude
Write-Host "`n[Step 3] Launching OpenClaude with Graxia Backend..." -ForegroundColor Cyan
Write-Host "   Provider: Graxia Backend (localhost:8000)" -ForegroundColor Gray
Write-Host "   Model: $Model" -ForegroundColor Gray
Write-Host "   AI Endpoint: http://localhost:8000/ai/v1" -ForegroundColor Gray

Write-Host "`n🚀 Starting OpenClaude..." -ForegroundColor Green
Write-Host ""

# Set environment for OpenClaude
$env:OPENAI_API_KEY = "graxia-local-key"
$env:OPENAI_BASE_URL = "http://localhost:8000/ai/v1"
$env:OLLAMA_PAY_API_KEY = $apiKey
$env:OLLAMA_PAY_BASE_URL = $baseUrl
$env:GRAXIA_API_URL = "http://localhost:8000"

# Start OpenClaude
openclaude
