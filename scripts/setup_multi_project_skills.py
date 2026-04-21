#!/usr/bin/env python3
"""
Multi-Project Skills Loader
Connects all projects in .claude/skills to Obsidian central skills hub
"""
import os
import json
from pathlib import Path
from datetime import datetime

# Obsidian paths (central hub)
OBSIDIAN_SKILLS = Path.home() / "Documents" / "ObsidianVault" / "Second Brain" / "brain" / "skills"
OBSIDIAN_REGISTRY = Path.home() / "Documents" / "ObsidianVault" / "Second Brain" / "brain" / "ai-gateway" / "skills-registry.json"

def find_projects():
    """
    Find all projects on machine:
    1. Check projects.yaml in Obsidian
    2. Find by .git, package.json, pyproject.toml
    """
    projects = set()
    
    # Always include main project
    main_project = Path("c:\\brav os")
    if main_project.exists():
        projects.add(main_project)
    
    # Check Obsidian projects.yaml for project list
    projects_yaml = Path.home() / "Documents" / "ObsidianVault" / "Second Brain" / "identity" / "projects.yaml"
    if projects_yaml.exists():
        try:
            import yaml
            data = yaml.safe_load(projects_yaml.read_text(encoding='utf-8'))
            if data and 'projects' in data:
                for proj in data['projects']:
                    if 'github_url' in proj:
                        # Could clone or track references
                        pass
        except ImportError:
            pass  # yaml not installed, skip
        except Exception as e:
            print(f"Warning reading projects.yaml: {e}")
    
    # Find projects by filesystem patterns
    search_dirs = [
        Path("c:\\") / "projects",
        Path("c:\\") / "work",
        Path("c:\\") / "dev",
        Path.home() / "projects",
    ]
    
    for search_dir in search_dirs:
        if not search_dir.exists():
            continue
        try:
            for item in search_dir.iterdir():
                if item.is_dir() and not item.name.startswith("."):
                    # Check if it's a project
                    if (item / ".git").exists() or \
                       (item / "package.json").exists() or \
                       (item / "pyproject.toml").exists() or \
                       (item / "Dockerfile").exists():
                        projects.add(item)
        except PermissionError:
            pass
    
    return sorted(list(projects))

def setup_project_skills(project_path):
    """
    Setup skills access for a single project:
    1. Create .claude/skills/ directory
    2. Create symlinks to Obsidian skills (or copy if symlink fails)
    3. Generate config.json for project
    4. Generate load_skills.py loader script
    """
    try:
        # Create .claude/skills directory
        cli_dir = project_path / ".claude" / "skills"
        cli_dir.mkdir(parents=True, exist_ok=True)
        
        if not OBSIDIAN_SKILLS.exists():
            print(f"⚠️  Obsidian skills not found, skipping {project_path.name}")
            return False
        
        # Create symlinks/copies for each skill
        skill_count = 0
        for skill_file in sorted(OBSIDIAN_SKILLS.glob("*.md")):
            skill_name = skill_file.stem
            target_dir = cli_dir / skill_name
            target_dir.mkdir(exist_ok=True)
            target_skill = target_dir / "SKILL.md"
            
            if not target_skill.exists():
                try:
                    # Try symlink first
                    os.symlink(str(skill_file), str(target_skill))
                except (OSError, NotImplementedError):
                    # Fallback to copy
                    import shutil
                    shutil.copy2(str(skill_file), str(target_skill))
            skill_count += 1
        
        # Create project config
        config = {
            "project_name": project_path.name,
            "project_root": str(project_path.absolute()),
            "skills_source": "obsidian-central",
            "skills_registry": str(OBSIDIAN_REGISTRY.absolute()),
            "skills_directory": str(cli_dir.relative_to(project_path)),
            "skills_count": skill_count,
            "created_at": datetime.now().isoformat(),
            "last_updated": datetime.now().isoformat()
        }
        
        config_file = project_path / ".claude" / "config.json"
        config_file.write_text(json.dumps(config, indent=2, ensure_ascii=False), encoding='utf-8')
        
        # Generate loader script
        create_loader_script(project_path, cli_dir)
        
        return True
    except Exception as e:
        print(f"❌ Error setting up {project_path.name}: {e}")
        return False

def create_loader_script(project_path, cli_dir):
    """Generate .claude/load_skills.py for easy skill access"""
    loader_code = '''#!/usr/bin/env python3
"""Auto-generated skill loader for this project"""
import json
from pathlib import Path

CONFIG_FILE = Path(__file__).parent / "config.json"
SKILLS_DIR = Path(__file__).parent / "skills"

def load_config():
    if CONFIG_FILE.exists():
        return json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    return {}

def list_skills():
    """List all available skills"""
    skills = []
    if SKILLS_DIR.exists():
        for skill_dir in sorted(SKILLS_DIR.glob("*/")):
            skill_file = skill_dir / "SKILL.md"
            if skill_file.exists():
                skills.append(skill_dir.name)
    return skills

def get_skill(skill_name):
    """Get skill markdown content"""
    skill_file = SKILLS_DIR / skill_name / "SKILL.md"
    if skill_file.exists():
        return skill_file.read_text(encoding='utf-8')
    return None

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "list":
            for skill in list_skills():
                print(skill)
        elif cmd == "get" and len(sys.argv) > 2:
            skill = get_skill(sys.argv[2])
            if skill:
                print(skill)
            else:
                print(f"Skill '{sys.argv[2]}' not found")
    else:
        config = load_config()
        print(f"Project: {config.get('project_name', 'Unknown')}")
        print(f"Skills loaded: {len(list_skills())}")
        print(f"Available skills: {', '.join(list_skills())}")
'''
    
    loader_file = project_path / ".claude" / "load_skills.py"
    loader_file.write_text(loader_code, encoding='utf-8')

def create_master_registry(projects):
    """Create master registry of all projects"""
    try:
        registry = {
            "version": "1.0.0",
            "generated": datetime.now().isoformat(),
            "total_projects": len(projects),
            "projects": []
        }
        
        for proj_path in projects:
            config_file = proj_path / ".claude" / "config.json"
            if config_file.exists():
                config = json.loads(config_file.read_text(encoding='utf-8'))
                registry["projects"].append({
                    "name": proj_path.name,
                    "path": str(proj_path.absolute()),
                    "skills_count": config.get("skills_count", 0),
                    "last_updated": config.get("last_updated")
                })
        
        # Save master registry
        registry_dir = Path.home() / ".claude"
        registry_dir.mkdir(parents=True, exist_ok=True)
        registry_file = registry_dir / "projects-registry.json"
        registry_file.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding='utf-8')
        
        return registry_file
    except Exception as e:
        print(f"Warning creating master registry: {e}")
        return None

def main():
    print("🔍 Scanning for projects...\n")
    
    # Find projects
    projects = find_projects()
    
    if not projects:
        print("⚠️  No projects found")
        return False
    
    print(f"📍 Found {len(projects)} project(s):\n")
    
    # Setup each project
    configured = 0
    for proj_path in projects:
        print(f"  ⚙️  {proj_path.name}...", end=" ")
        if setup_project_skills(proj_path):
            configured += 1
            print("✓")
        else:
            print("✗")
    
    print()
    
    # Create master registry
    registry_file = create_master_registry(projects)
    if registry_file:
        print(f"📝 Master registry: {registry_file}")
    
    print()
    print(f"✅ Setup complete! {configured}/{len(projects)} projects configured")
    print()
    print("Next steps:")
    print("  cd your-project")
    print("  python .claude/load_skills.py list")
    
    return True

if __name__ == "__main__":
    import sys
    success = main()
    sys.exit(0 if success else 1)
