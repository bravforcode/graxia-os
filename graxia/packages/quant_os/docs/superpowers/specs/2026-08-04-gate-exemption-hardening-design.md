# Release Gate Exemption Hardening — 2-Tier Design

Date: 2026-08-04
Status: Approved (brainstorming + deep research)
Plan context: `2026-08-03-release-gate-pass.md` (Tasks 5-8 hardening follow-up)

## 1. Problem Statement

`GATE_DIRTY_EXEMPT` in `scripts/run_release_gate.py` has grown to ~14 file-level
entries, one per parallel-session runtime artifact, added reactively during
batches 1-3. Two structural defects:

1. **Maintenance trap**: every new runtime file the parallel session produces
   requires a new hardcoded exemption entry.
2. **Code-leak risk (if "fixed" naively)**: a directory-wide exemption for
   `reports/` or `research/` would exempt real source code from the dirty-tree
   check — `reports/capacity_ceiling.py`, `research/__init__.py`,
   `research/pipeline.py`, `research/auto_increment_trial.py`,
   `research/ledger_invalidation.py` (verified present). Modified uncommitted
   `.py` files in those directories would silently pass the gate.

## 2. Research Basis (industry practice)

- **Google (2016/2017)**: no per-file/path exemption policy exists in their
  gates. Flaky/env-gated tests are handled by auto-retry → "mark flaky"
  (3-strike) → automatic quarantine (off critical path + filed bug). Environment-
  dependent tests are skipped, not silently exempted. "A test that fails
  reliably is far better than a flaky test."
- **GitHub docs (Ignoring files)**: "If you want to ignore a file that is
  already checked in, you must untrack the file first" (`git rm --cached`).
  Runtime artifacts should be untracked + gitignored — they then never appear
  dirty in `git status` at all.
- **Gates run on clean snapshots**: industry CI runs on fresh checkouts; a
  dirty-tree check is only meaningful in a live dev tree. This validates the
  pinned-detached-worktree method adopted for batch 3 as the standard protocol.

## 3. Design: 2-Tier Exemption Policy

### Tier A — Untrack + gitignore (root-cause fix, GitHub practice)

Files the gate/other sessions regenerate at runtime should NOT be tracked.
Remove them from the index and rely on existing `.gitignore` rules:

```
git rm --cached -r graxia/packages/quant_os/artifacts/release_gate/   # 15 files
git rm --cached graxia/packages/quant_os/state/audit_log.jsonl
git rm --cached graxia/packages/quant_os/state/autonomous_state.json
git rm --cached graxia/packages/quant_os/state/system_state.json
git rm --cached graxia/packages/quant_os/validation/.experiment_registry.json
rm -f graxia/packages/quant_os/1350)   # stray 0-byte fat-finger redirect accident — DELETE, never whitelist
```

`.gitignore` coverage verified (2026-08-04):
- `artifacts/` — covered (root + quant_os .gitignore)
- `state/` — covered
- `Meta/states/` — covered (both root + quant_os)
- `tests/.test_tmp/` — covered
- `1350)` — NOT covered by design: the file is deleted, not ignored (see below)

**Review fix: `1350)` is deleted, NOT whitelisted.** A stray file from a
fat-finger redirect must never appear in a security whitelist — deleting it
from disk + index removes the class of problem entirely. The gate must also
contain a stale-entry guard: if an entry in `ALLOWED_DIRTY_FILES` refers to a
path that no longer exists, the gate warns (drift detection) instead of
silently carrying dead config.

Result: `git status` no longer reports these → `check_git_clean()` passes
without any exemption entry. Files remain on disk (untracked, ignored).

Safety check: verify no file listed is a `.py` or otherwise source — all are
`.json`/`.txt` runtime state.

### Tier B — File-level/pattern-level exemption (fail-closed)

Keep a small, explicit allowlist in the gate script. Rules:

1. **`.py` files are NEVER exempted** — hard rejection regardless of path.
2. Entries are exact paths OR narrow regex patterns scoped to data extensions
   (`.json`, `.md`, `.txt`) — never whole directories.
3. Directory-wide exemption is forbidden for any directory containing `.py`.

```python
import os
import re
from typing import FrozenSet, Tuple

ALLOWED_DIRTY_FILES: FrozenSet[str] = frozenset({
    "data/heartbeat.txt",
    "graxia/packages/quant_os/data/heartbeat.txt",
    "graxia/packages/quant_os/tests/.test_tmp/list.json",
    "graxia/packages/quant_os/quarantine_manifest.json",  # gate itself writes it
    # NOTE: 1350) is NOT whitelisted — deleted in Tier A (review fix)
})

ALLOWED_DIRTY_PATTERNS: Tuple[re.Pattern, ...] = (
    re.compile(r"^graxia/packages/quant_os/research/trial_ledger.*\.json$"),
    re.compile(r"^graxia/packages/quant_os/research/hypothesis_registry.*\.json$"),
    re.compile(r"^graxia/packages/quant_os/reports/.*\.(json|md)$"),
    re.compile(r"^Meta/states/.*\.md$"),
    re.compile(r"^graxia/packages/quant_os/Meta/states/.*\.md$"),
    re.compile(r"^graxia/packages/quant_os/state/.*\.jsonl$"),
)

def is_file_exempted(filepath: str) -> bool:
    """Return True if a dirty file is an allowed runtime artifact.

    Cross-platform: git status --porcelain may emit backslash separators on
    Windows; normalize before matching so Linux CI and Windows dev agree.
    """
    # 1. Normalize OS path separators (Windows \\ vs POSIX /)
    normalized_path = filepath.replace("\\", "/")

    # 2. Hard security rule: source code is NEVER exempted
    if normalized_path.endswith(".py"):
        return False

    # 3. Exact file match
    if normalized_path in ALLOWED_DIRTY_FILES:
        return True

    # 4. Pattern match
    return any(p.match(normalized_path) for p in ALLOWED_DIRTY_PATTERNS)
```

Replaces the current `GATE_DIRTY_EXEMPT` tuple + prefix `startswith` logic.

**Review fixes applied here:**
1. **OS path normalization** — `filepath.replace("\\", "/")` before matching;
   `git status --porcelain` on Windows can emit `\` separators, which would
   make POSIX regexes fail to match → false gate failures. Normalization makes
   behavior identical on Linux (CI/worktree) and Windows (local dev).
2. **`1350)` removed from the whitelist** — the file is deleted in Tier A; a
   fat-finger accident must not become permanent security config.
3. **Future guardrail (not in v1 scope, noted for follow-up)**: size check on
   exempted files — warn when an exempted `.json`/`.md` exceeds a threshold
   (e.g. 50 MB) to catch accidental dumps / credential blobs in artifact dirs.
   Implementation: in `check_git_clean()`, after `is_file_exempted()` returns
   True, stat the file and emit a warning (not a failure) above the threshold.

### Tier C (process, not code) — massive_sentiment → approved_runtime_skips

`tests/test_massive_sentiment.py` requires live provider API keys (asserts
>=1 provider, real httpx calls). It is env-gated, not buggy.

1. Add module-level `pytest.mark.skipif` — skip when no provider keys in env.
2. Remove its `--ignore=` line from SUITE_CMD.
3. Remove its quarantine entry (QOS-RB-017); add to `approved_runtime_skips`
   (count = 1, reason "live provider API keys not configured in gate env").
4. Verify suite: test collected + skipped, gate counts still consistent.

### Tier D (process, not code) — Pinned-worktree protocol playbook

Write `docs/superpowers/playbooks/gate-verification.md`:
- When to use pinned worktree (parallel session mutating shared tree).
- Steps: `git worktree add --detach <path> <sha>` → copy gitignored `config/`
  data files for parity → run gate from worktree root → verify
  `git_commit.txt` + `pytest_command.txt` identical across run_a/run_b →
  copy evidence to `artifacts/release_gate/batchN/`.
- Exemption policy summary (this spec) + E1 wait protocol reference.

## 4. Implementation Steps

1. **Tier A**: delete `1350)` from disk; run `git rm --cached` for the 5
   tracked runtime paths; verify `git status --porcelain` shows zero entries
   for those paths (files remain on disk but untracked+ignored); commit.
2. **Tier B**: replace `GATE_DIRTY_EXEMPT` with `ALLOWED_DIRTY_FILES` +
   `ALLOWED_DIRTY_PATTERNS` + `is_file_exempted()` (path-normalized, `.py`-hard-
   rejection) in `run_release_gate.py`; add stale-entry drift warning; verify
   function against known dirty-path samples (incl. backslash variants);
   ruff/mypy via pre-commit; commit.
3. **Tier C**: edit `test_massive_sentiment.py` (skipif), SUITE_CMD, manifest
   (QOS-RB-017 → approved_runtime_skips count=1); standalone verify skip;
   commit.
4. **Tier D**: write playbook `docs/superpowers/playbooks/gate-verification.md`;
   commit.
5. **Verification**: run gate once on live tree AND once in pinned worktree;
   both must be GREEN with zero failures and identical A==B stats.

## 5. Testing / Verification Criteria

- `is_file_exempted("graxia/packages/quant_os/reports/capacity_ceiling.py") == False`
- `is_file_exempted("graxia/packages/quant_os/research/pipeline.py") == False`
- `is_file_exempted("graxia\\packages\\quant_os\\reports\\research_backed_pipeline.json") == True`  (backslash Windows form)
- `is_file_exempted("graxia/packages/quant_os/reports/research_backed_pipeline.json") == True`
- `is_file_exempted("Meta/states/researcher-forexroasted.md") == True`
- `is_file_exempted("graxia/packages/quant_os/1350)") == False`  (no longer whitelisted; file deleted)
- `git status --porcelain` shows zero entries for Tier-A paths after untrack
- Full gate: verdict PASS, all 10 checks true, run_a == run_b
- massive_sentiment: collected + skipped in suite (not ignored, not failed)

## 6. Out of Scope / Future

- Flaky-test auto-quarantine tooling (Google-style 3-strike) — future.
- Test-size reduction (Google's biggest flakiness lever) — future.
- **Exempted-file size guardrail** — warn (not fail) when an exempted
  `.json`/`.md` exceeds ~50 MB, to surface accidental dumps / credential
  blobs in artifact dirs — future follow-up.
- **Automated clean-checkout runner** — move gate execution to an isolated
  container / temp worktree automatically (100% hermetic), eliminating local
  dirty-tree issues entirely — future.
- Changing gate pass thresholds (required_collected/passed stay).
- Touching `.py` exemption for ANY path — permanently forbidden.
