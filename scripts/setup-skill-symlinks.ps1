#!/usr/bin/env pwsh
<#
.SYNOPSIS
Setup symlinks from .claude/skills to Obsidian vault
Allows backward compatibility while centralizing in Obsidian
#>

param(
    [switch]$Force
)

$ObsidianSkillsDir = "$env:USERPROFILE\Documents\ObsidianVault\Second Brain\brain\skills"
$ClaudeSkillsDir = "$env:USERPROFILE\.claude\skills"

Write-Host "🔗 Setting up skill symlinks..." -ForegroundColor Cyan
Write-Host "  Source: $ObsidianSkillsDir"
Write-Host "  Target: $ClaudeSkillsDir"
Write-Host ""

if (-not (Test-Path $ObsidianSkillsDir)) {
    Write-Host "❌ ERROR: Obsidian skills directory not found: $ObsidianSkillsDir" -ForegroundColor Red
    exit 1
}

if (-not (Test-Path $ClaudeSkillsDir)) {
    New-Item -ItemType Directory -Path $ClaudeSkillsDir -Force | Out-Null
    Write-Host "✓ Created .claude/skills directory"
}

# Get all skill files from Obsidian
$skillFiles = @(Get-ChildItem -Path $ObsidianSkillsDir -Filter "*.md" -ErrorAction SilentlyContinue)

if ($skillFiles.Count -eq 0) {
    Write-Host "⚠️  No skill files found in Obsidian" -ForegroundColor Yellow
    exit 0
}

$created = 0
$skipped = 0
$linked = 0

foreach ($skillFile in $skillFiles) {
    $skillName = $skillFile.BaseName
    $targetSkillDir = Join-Path $ClaudeSkillsDir $skillName
    $targetSkillFile = Join-Path $targetSkillDir "SKILL.md"
    
    # Check if already linked
    if ((Test-Path $targetSkillFile) -and (Get-Item $targetSkillFile -Force).LinkType -eq "SymbolicLink") {
        Write-Host "  → $skillName (already linked)" -ForegroundColor Gray
        $linked++
        continue
    }
    
    # Create symlink
    try {
        # Create directory if needed
        if (-not (Test-Path $targetSkillDir)) {
            New-Item -ItemType Directory -Path $targetSkillDir -Force | Out-Null
        }
        
        # Check if SKILL.md already exists as regular file
        if (Test-Path $targetSkillFile) {
            if ($Force) {
                Remove-Item $targetSkillFile -Force
                Write-Host "  ✓ Replaced: $skillName" -ForegroundColor Green
            } else {
                Write-Host "  ⊗ Skipped: $skillName (file exists, use -Force to replace)" -ForegroundColor Yellow
                $skipped++
                continue
            }
        }
        
        # Create symlink
        New-Item -ItemType SymbolicLink -Path $targetSkillFile -Target $skillFile.FullName -Force | Out-Null
        Write-Host "  ✓ Linked: $skillName" -ForegroundColor Green
        $created++
    }
    catch {
        Write-Host "  ✗ Failed: $skillName - $($_.Exception.Message)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "📊 Summary" -ForegroundColor Cyan
Write-Host "  Created: $created symlinks"
Write-Host "  Linked:  $linked (already)"
Write-Host "  Skipped: $skipped"
Write-Host ""
Write-Host "✅ Symlink setup complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📝 Note: Skills in .claude/skills are now linked to Obsidian vault"
Write-Host "   Any AI tool can access them from either location"
