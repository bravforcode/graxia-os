# Repository Intelligence Hooks

## Pre-commit Hook (Security Check)
Scans staged Python files for credential leaks and forbidden order API imports. Exits 1 to block the commit on findings.

### Install
```bash
cp repo_intelligence/hooks/pre_commit_security_check.py .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

### Standalone Usage
```bash
python repo_intelligence/hooks/pre_commit_security_check.py <file.py>
```

## Pre-commit Hook (Manifest Check)
Validates manifest consistency before allowing commits.

## Registry Check
```bash
python repo_intelligence/hooks/registry_check.py
```

## What These Hooks Do
- **pre_commit_security_check.py**: Blocks credential literals (password, api_key), MT5 env var reads in gold_bot/, and order_send/TRADE_ACTION_DEAL outside execution/demo_canary/
- **pre_commit_check.py**: Validates manifest entries have required fields and no tier violations
- **registry_check.py**: Validates registry YAML structure and required fields
