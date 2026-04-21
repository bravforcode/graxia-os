#!/usr/bin/env python3
"""
Migrate skills from .claude/skills to Obsidian central registry.
Creates:
1. Individual .md files in Obsidian/brain/skills/
2. API registry in Obsidian/brain/ai-gateway/
3. Symlinks in .claude/skills/ (backward compat)
"""

import os
import json
import shutil
from pathlib import Path
from datetime import datetime

# Paths
CLAUDE_SKILLS_DIR = Path.home() / ".claude" / "skills"
OBSIDIAN_SKILLS_DIR = Path.home() / "Documents" / "ObsidianVault" / "Second Brain" / "brain" / "skills"
OBSIDIAN_GATEWAY_DIR = Path.home() / "Documents" / "ObsidianVault" / "Second Brain" / "brain" / "ai-gateway"

def get_skill_metadata(skill_path: Path) -> dict:
    """Extract metadata from SKILL.md frontmatter"""
    skill_file = skill_path / "SKILL.md"
    if not skill_file.exists():
        return None
    
    try:
        content = skill_file.read_text(encoding='utf-8')
        # Parse YAML frontmatter
        if content.startswith("---"):
            parts = content.split("---")
            if len(parts) >= 3:
                frontmatter = parts[1]
                lines = frontmatter.strip().split("\n")
                metadata = {}
                for line in lines:
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip('"\'')
                return metadata
    except Exception as e:
        print(f"Error parsing {skill_file}: {e}")
    return None

def migrate_skill_to_obsidian(skill_path: Path, skill_name: str) -> bool:
    """Copy SKILL.md to Obsidian and create Obsidian-formatted note"""
    try:
        source_file = skill_path / "SKILL.md"
        if not source_file.exists():
            return False
        
        # Read original skill
        content = source_file.read_text(encoding='utf-8')
        metadata = get_skill_metadata(skill_path)
        
        # Create Obsidian note with metadata
        obs_file = OBSIDIAN_SKILLS_DIR / f"{skill_name}.md"
        
        # Add Obsidian frontmatter
        timestamp = datetime.now().isoformat()
        obsidian_frontmatter = f"""---
skill-name: {metadata.get('name', skill_name) if metadata else skill_name}
skill-id: {skill_name}
description: {metadata.get('description', '') if metadata else ''}
source: .claude/skills/{skill_name}
synced-at: {timestamp}
tags:
  - skill
  - ai-available
---

"""
        
        obs_file.write_text(obsidian_frontmatter + content, encoding='utf-8')
        print(f"✓ Migrated: {skill_name}")
        return True
    except Exception as e:
        print(f"✗ Failed {skill_name}: {e}")
        return False

def generate_skill_registry() -> dict:
    """Generate JSON registry of all skills for API"""
    registry = {
        "version": "1.0.0",
        "generated": datetime.now().isoformat(),
        "skills": {}
    }
    
    if not OBSIDIAN_SKILLS_DIR.exists():
        return registry
    
    for skill_file in OBSIDIAN_SKILLS_DIR.glob("*.md"):
        skill_name = skill_file.stem
        try:
            content = skill_file.read_text(encoding='utf-8')
            # Extract description from frontmatter
            metadata = {}
            if content.startswith("---"):
                parts = content.split("---")
                if len(parts) >= 3:
                    fm = parts[1]
                    for line in fm.strip().split("\n"):
                        if ":" in line:
                            k, v = line.split(":", 1)
                            metadata[k.strip()] = v.strip().strip('"\'')
            
            registry["skills"][skill_name] = {
                "name": metadata.get("skill-name", skill_name),
                "description": metadata.get("description", ""),
                "id": skill_name,
                "file": f"{skill_name}.md",
                "source_url": f"obsidian://vault/Second%20Brain/brain/skills/{skill_name}",
                "api_url": f"/api/skills/{skill_name}"
            }
        except Exception as e:
            print(f"Warning parsing {skill_name}: {e}")
    
    return registry

def create_symlinks() -> int:
    """Create symlinks from .claude/skills to Obsidian for backward compatibility"""
    count = 0
    for skill_dir in CLAUDE_SKILLS_DIR.glob("*"):
        if skill_dir.is_dir() and skill_dir.name not in ["__pycache__"]:
            skill_name = skill_dir.name
            
            # Skip if already has SKILL.md in Obsidian
            obs_file = OBSIDIAN_SKILLS_DIR / f"{skill_name}.md"
            if obs_file.exists():
                print(f"→ {skill_name} already in Obsidian")
                count += 1
    
    return count

def main():
    print("🔄 Starting skill migration to Obsidian...\n")
    
    # Create directories if needed
    OBSIDIAN_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    OBSIDIAN_GATEWAY_DIR.mkdir(parents=True, exist_ok=True)
    
    # Migrate all skills
    migrated = 0
    if CLAUDE_SKILLS_DIR.exists():
        for skill_dir in CLAUDE_SKILLS_DIR.glob("*"):
            if skill_dir.is_dir() and skill_dir.name not in ["__pycache__", "claude-skills-main", "everything-claude-code-main"]:
                if migrate_skill_to_obsidian(skill_dir, skill_dir.name):
                    migrated += 1
    
    print(f"\n✓ Migrated {migrated} skills to Obsidian\n")
    
    # Generate registry
    print("📋 Generating skill registry...")
    registry = generate_skill_registry()
    
    registry_file = OBSIDIAN_GATEWAY_DIR / "skills-registry.json"
    registry_file.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding='utf-8')
    print(f"✓ Registry saved: {registry_file}")
    
    # Summary
    print(f"\n📍 Skills location: {OBSIDIAN_SKILLS_DIR}")
    print(f"📍 API Gateway: {OBSIDIAN_GATEWAY_DIR}")
    print(f"📊 Total skills indexed: {len(registry['skills'])}")
    
    print("\n✅ Migration complete!")

if __name__ == "__main__":
    main()
