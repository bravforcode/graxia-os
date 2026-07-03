# Repository Intelligence Hooks

## Pre-commit Hook
Validates manifest consistency before allowing commits.

### Install
```bash
cp repo_intelligence/hooks/pre_commit_check.py .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### Registry Check
```bash
python repo_intelligence/hooks/registry_check.py
```

## What These Hooks Do
- **pre_commit_check.py**: Validates manifest entries have required fields and no tier violations
- **registry_check.py**: Validates registry YAML structure and required fields
