# G0A: Pre-Commit Security Hook Installation

## Overview

The pre-commit hook (`repo_intelligence/hooks/pre_commit_security_check.py`) scans staged Python files for:

1. **Credential literals** — `password = "realvalue"` or `api_key = "realvalue"` (non-empty, non-placeholder)
2. **MT5 env var reads** — `MT5_LOGIN`, `MT5_PASSWORD`, `MT5_SERVER` usage of `os.environ`/`os.getenv` inside `gold_bot/`
3. **Forbidden order API imports** — `order_send(...)` or `TRADE_ACTION_DEAL` used outside the allowlist (`execution/demo_canary/`)

Exit code 0 = clean, exit code 1 = blocked.

## Installation

```bash
cd graxia/packages/quant_os

# Linux/macOS
cp repo_intelligence/hooks/pre_commit_security_check.py .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit

# Windows (Git Bash)
cp repo_intelligence/hooks/pre_commit_security_check.py .git/hooks/pre-commit
```

### Running as a standalone check (no git required)

```bash
python repo_intelligence/hooks/pre_commit_security_check.py <file.py>
```

## What It Checks

| Category | Pattern | Scope |
|---|---|---|
| Password assignment | `password = "..."` (non-empty) | All staged .py files |
| API key assignment | `api_key = "..."` (non-empty) | All staged .py files |
| MT5 env vars | `MT5_LOGIN/MT5_PASSWORD/MT5_SERVER = os.environ[...]` | `gold_bot/` only |
| Forbidden order API | `order_send(...)` | Outside `execution/demo_canary/` |
| Forbidden order API | `TRADE_ACTION_DEAL` | Outside `execution/demo_canary/` |

Empty strings (`password = ""`) and placeholder patterns are intentionally allowed.

## Bypassing

```bash
git commit --no-verify -m "message"
```

Acceptable reasons to bypass:
- Committing a config template with placeholder credentials (not real values)
- Adding test fixtures that intentionally contain mock credential patterns
- Emergency hotfix where the hook is temporarily broken

When bypassing, document the reason in the commit message or PR description.

## Testing

```bash
python -m pytest tests/test_pre_commit_hook.py -v
```

## Notes

- This hook only operates on **staged** Python files (added or modified).
- External Codex/PreToolUse hooks are outside repository control and not covered by this hook.
- The hook reads staged content via `git show :filepath`, so it checks what would be committed, not the working copy.
