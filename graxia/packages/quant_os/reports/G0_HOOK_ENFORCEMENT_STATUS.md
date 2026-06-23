# G0 Hook Enforcement Status

## Repo-local hook surfaces found
- `.git/hooks/pre-commit`
- `.git/hooks/post-commit`
- `repo_intelligence/hooks/pre_commit_check.py`
- `repo_intelligence/hooks/registry_check.py`

## Repo-local behavior verified now
- `repo_intelligence/hooks/pre_commit_check.py` is fail-closed on missing, invalid, empty, and validation-error manifest inputs.
- `repo_intelligence/hooks/registry_check.py` is fail-closed on missing, invalid, empty, wrong-shape, and missing-field registry inputs.
- `tests/test_repo_hooks.py` now locks those fail-closed behaviors with `8` passing tests.
- `python repo_intelligence/hooks/pre_commit_check.py` currently stops with:
  - `ERROR: required manifest not found: C:\Users\menum\graxia os\graxia\packages\quant_os\repo_intelligence\hooks\..\registry\manifest.yml`
- `python repo_intelligence/hooks/registry_check.py` currently passes with:
  - `Registry check: OK (70 entries)`

## Remaining limits
- `.git/hooks/pre-commit` itself is not versioned inside the repository snapshot.
- During this session, `PreToolUse hook failed` messages were observed outside Git-hook execution.
- No repo-local configuration file was found in this workspace snapshot that directly controls Codex/Claude `PreToolUse` harness hooks.

## Verdict
- Repo-local helper enforcement: `PASS`
- Installed Git-hook wiring proof: `REVIEW REQUIRED`
- External `PreToolUse` fail-closed enforcement: `BLOCKED OUTSIDE REPO CONTROL`
