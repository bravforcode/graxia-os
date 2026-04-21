#!/usr/bin/env python3
"""
Setup symlinks from .claude/skills to Obsidian vault
Cross-platform compatible (Windows + Unix)
"""

import os
import json
from pathlib import Path
from datetime import datetime

def create_symlink_safe(src: Path, target: Path, force: bool = False) -> bool:
    """Create symlink with error handling"""
    try:
        # Create parent directory
        target.parent.mkdir(parents=True, exist_ok=True)
        
        # Remove existing if force
        if target.exists() and force:
            if target.is_symlink():
                target.unlink()
            else:
                print(f"  ⊗ {target.name}: regular file exists (not replacing)")
                return False
        
        # Skip if already linked
        if target.exists() and target.is_symlink():
            return True
        
        # Create symlink
        if hasattr(os, 'symlink'):
            # Unix-like or Windows 10+
            os.symlink(src, target)
        else:
            # Fallback: copy file
            import shutil
            shutil.copy2(src, target)
            print(f"  (copied instead of symlink on this system)")
        
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def main():
    obs_skills = Path.home() / "Documents" / "ObsidianVault" / "Second Brain" / "brain" / "skills"
    claude_skills = Path.home() / ".claude" / "skills"
    
    print("🔗 Setting up skill symlinks...")
    print(f"  Source: {obs_skills}")
    print(f"  Target: {claude_skills}")
    print()
    
    if not obs_skills.exists():
        print(f"❌ ERROR: Obsidian skills not found at {obs_skills}")
        return False
    
    # Create .claude/skills if needed
    claude_skills.mkdir(parents=True, exist_ok=True)
    
    # Get all markdown files
    skill_files = list(obs_skills.glob("*.md"))
    created = 0
    linked = 0
    
    for skill_file in skill_files:
        skill_name = skill_file.stem
        target_dir = claude_skills / skill_name
        target_file = target_dir / "SKILL.md"
        
        # Check if already linked
        if target_file.exists() and target_file.is_symlink():
            print(f"  → {skill_name} (already linked)")
            linked += 1
            continue
        
        # Create symlink
        target_dir.mkdir(parents=True, exist_ok=True)
        
        try:
            if target_file.exists():
                target_file.unlink()
            
            os.symlink(str(skill_file), str(target_file))
            print(f"  ✓ Linked: {skill_name}")
            created += 1
        except Exception as e:
            print(f"  ✗ Failed {skill_name}: {e}")
    
    print()
    print(f"📊 Summary")
    print(f"  Created: {created} new symlinks")
    print(f"  Already: {linked} linked")
    print()
    
    # Create symlink registry
    registry = {
        "symlinks_created": created,
        "symlinks_existing": linked,
        "total_skills": len(skill_files),
        "created_at": datetime.now().isoformat(),
        "source": str(obs_skills),
        "target": str(claude_skills)
    }
    
    registry_file = claude_skills.parent / ".symlink-registry.json"
    registry_file.write_text(json.dumps(registry, indent=2), encoding='utf-8')
    print(f"📝 Registry saved: {registry_file}")
    print()
    print("✅ Symlink setup complete!")
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
