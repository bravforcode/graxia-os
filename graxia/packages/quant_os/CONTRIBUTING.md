# Contributing to quant_os

## Getting Started

1. Clone the monorepo:
   ```bash
   git clone <repo-url> graxia
   cd graxia
   ```

2. Create a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate  # Linux/macOS
   .venv\Scripts\Activate.ps1  # Windows
   ```

3. Install the package in editable mode:
   ```bash
   pip install -e graxia/packages/quant_os/
   ```

## Running Tests

```bash
make test               # full suite
make test-one file=<path>  # single test file
```

## Linting & Formatting

```bash
make lint    # ruff check
make format  # ruff format
```

## Pre-commit Hooks

```bash
make install-precommit
```

Hooks run automatically on commit. Configured hooks: trailing-whitespace, end-of-file-fixer, check-yaml, check-added-large-files, check-merge-conflict, detect-private-key, ruff (lint + format).

## Development Approach

quant_os follows a **phase-based** development model. Each phase targets a specific subsystem and delivers a self-contained increment. Current phase info is tracked in project documentation.

## Branch Naming & Commits

Use Conventional Commits with these prefixes:

| Prefix      | Purpose                     |
|-------------|-----------------------------|
| `feat/`     | New feature                 |
| `fix/`      | Bug fix                     |
| `security/` | Security fix                |
| `chore/`    | Maintenance / tooling       |

Commit messages follow the format:
```
<type>(<scope>): <description>
```

Examples:
```
feat(strategy): add momentum filter
fix(core): correct position sizing overflow
security(api): sanitize user input
chore(dx): add pre-commit config
```

## Pull Request Process

1. Create a branch with the appropriate prefix
2. Make your changes with focused, atomic commits
3. Run `make test` and `make lint` before pushing
4. Open a PR targeting the main branch
5. Ensure CI passes and all tests are green
6. Request review from a maintainer

## Git Safety Rules

**After any rebase or force push:**

1. **Verify branch state** before pushing:
   ```bash
   git status          # Check for uncommitted changes
   git log --oneline -5  # Verify commit history looks correct
   git diff HEAD~1     # Review the last commit's changes
   ```

2. **Never force push to `main`** — only allowed on feature branches
3. **Always run tests after rebase** before pushing:
   ```bash
   make test
   make lint
   ```
4. **If something looks wrong after push**, do NOT force push again. Create a new commit to fix it.

5. **Before merging PR**, verify:
   - All CI checks pass
   - No merge conflicts
   - Commit history is clean (no "fix fix fix" chains)
