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
