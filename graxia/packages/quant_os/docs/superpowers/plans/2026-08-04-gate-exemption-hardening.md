# Implementation Plan: Release Gate Exemption Hardening (2-Tier)

Date: 2026-08-04
Spec: `docs/superpowers/specs/2026-08-04-gate-exemption-hardening-design.md` (v2, approved)
Branch: `feat/execution-risk-clean`

## Scope

Replace the reactive file-level `GATE_DIRTY_EXEMPT` tuple in
`scripts/run_release_gate.py` with a 2-tier policy:

- **Tier A** — untrack runtime artifacts (`git rm --cached`) + delete stray `1350)` file.
- **Tier B** — hardened `is_file_exempted()` (path-normalized, `.py` hard-reject,
  file-level + narrow data-extension patterns).
- **Tier C** — `test_massive_sentiment.py` moves from quarantine to
  `approved_runtime_skips` via `pytest.mark.skipif`.
- **Tier D** — playbook `docs/superpowers/playbooks/gate-verification.md`.
- **Verify** — dual gate runs (live tree + pinned worktree) both GREEN, A==B.

## Requirements (verbatim from spec)

- `.py` files are NEVER exempted (hard rejection, `return False` first).
- Path normalization: `filepath.replace("\\", "/")` before matching (Windows parity).
- Exemptions scoped to exact files OR narrow regex on `.json`/`.md`/`.txt` only.
- `1350)` is DELETED, never whitelisted.
- Stale-entry drift: gate warns when an `ALLOWED_DIRTY_FILES` entry no longer exists.
- massive_sentiment: skipif when no provider API keys; `--ignore` removed;
  quarantine entry (QOS-RB-017) removed; `approved_runtime_skips` += count 1.
- Playbook covers pinned-worktree protocol + exemption policy summary.
- Gate thresholds (required_collected/passed) UNCHANGED.

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `scripts/run_release_gate.py` | Modify | Replace `GATE_DIRTY_EXEMPT` with `ALLOWED_DIRTY_FILES`/`ALLOWED_DIRTY_PATTERNS`/`is_file_exempted()` + stale-warning in `check_git_clean()` |
| `quarantine_manifest.json` | Modify | Remove QOS-RB-017; add approved_runtime_skips entry (count 1) |
| `tests/test_massive_sentiment.py` | Modify | Module-level `pytest.mark.skipif` (no provider keys → skip) |
| `graxia/packages/quant_os/1350)` | Delete | Stray 0-byte accident |
| `.gitignore` (quant_os) | Verify | Already covers artifacts/, state/, Meta/states/, tests/.test_tmp/ (no change expected) |
| `docs/superpowers/playbooks/gate-verification.md` | Create | Pinned-worktree protocol + exemption policy |
| `docs/superpowers/plans/2026-08-04-gate-exemption-hardening.md` | Create | This plan |

## Environment / Repo Facts (implementer must know)

- Gate script: `graxia/packages/quant_os/scripts/run_release_gate.py`; run from
  repo root `C:\Users\menum\graxia os` with `python graxia/packages/quant_os/scripts/run_release_gate.py`.
- `GATE_DIRTY_EXEMPT` currently at lines 284-307; `check_git_clean()` at 310-330
  uses `filepath == ex or filepath.startswith(ex)`.
- `git status --porcelain` paths are repo-root-relative; gate parses `line[3:].strip()`.
- Manifest: `quarantine_manifest.json` — `quarantined_tests[]` (23 entries),
  `approved_runtime_skips = {total: 60, reasons: [{count, where, reason}]}`.
- massive_sentiment: uses `PROVIDERS` list with `.env_key` per provider; reads
  `Path(__file__).parent.parent / ".env"`; asserts `len(available) >= 1`.
- Pre-commit hooks run on commit (ruff, ruff-format, mypy) — expect them to
  auto-fix and require re-stage; tool output may truncate — verify with
  `git log --oneline -1`.
- Parallel session is ACTIVE — do NOT commit their files; use pathspec `git add`;
  verify staged set with `git status --porcelain` before commit.

---

## Task 1: Tier A — Untrack runtime artifacts + delete stray file

**Files:**
- Delete: `graxia/packages/quant_os/1350)`
- Index: `git rm --cached` for 5 paths
- Verify: `.gitignore` coverage (no change expected)

**Interfaces:**
- Produces: clean index for these paths; `git status --porcelain` shows no
  entries for them.

- [ ] **Step 1: Confirm `.gitignore` coverage**

```bash
python -c "t=open(r'C:\Users\menum\graxia os\graxia\packages\quant_os\.gitignore').read(); print('artifacts/' in t, 'state/' in t, 'Meta/states/' in t, 'tests/.test_tmp/' in t)"
# Expected: True True True True
```

- [ ] **Step 2: Delete stray file**

```bash
Remove-Item -LiteralPath 'C:\Users\menum\graxia os\graxia\packages\quant_os\1350)'
# verify: Test-Path -> False
```

- [ ] **Step 3: Untrack runtime artifacts**

```bash
git rm --cached -r graxia/packages/quant_os/artifacts/release_gate/
git rm --cached graxia/packages/quant_os/state/audit_log.jsonl
git rm --cached graxia/packages/quant_os/state/autonomous_state.json
git rm --cached graxia/packages/quant_os/state/system_state.json
git rm --cached graxia/packages/quant_os/validation/.experiment_registry.json
```

- [ ] **Step 4: Verify index clean for those paths**

```bash
git status --porcelain -- graxia/packages/quant_os/artifacts/ graxia/packages/quant_os/state/ graxia/packages/quant_os/validation/.experiment_registry.json
# Expected: no output (paths absent or ignored-only; files still on disk)
# NOTE: other parallel-session dirty files may still appear — scope check to the 5 paths only.
```

- [ ] **Step 5: Commit (pathspec'd)**

```bash
git add -A -- graxia/packages/quant_os/artifacts/release_gate graxia/packages/quant_os/state graxia/packages/quant_os/validation/.experiment_registry.json
git commit -m "chore(quant_os): untrack runtime artifacts (gate outputs, state, registry); delete stray 1350) file"
```

Expected: commit lands; `git log --oneline -1` shows it; pre-commit may auto-fix
and require one re-add (retry pattern: `git add <same paths> && git commit -m <same msg>`).

---

## Task 2: Tier B — Hardened is_file_exempted() in gate script

**Files:**
- Modify: `scripts/run_release_gate.py:284-330`

**Interfaces:**
- Consumes: existing `get_git_status()` (returns porcelain string), `check_git_clean()` caller.
- Produces:
  - `ALLOWED_DIRTY_FILES: frozenset[str]` (4 entries — see code below)
  - `ALLOWED_DIRTY_PATTERNS: tuple[re.Pattern, ...]` (6 patterns)
  - `def is_file_exempted(filepath: str) -> bool`
  - `check_git_clean()` now uses `is_file_exempted()` + stale-entry warning.

- [ ] **Step 1: Write failing unit checks (inline script first)**

```python
# temp file: C:\Users\menum\AppData\Local\Temp\opencode\tier_b_checks.py
import sys
sys.path.insert(0, r'C:\Users\menum\graxia os\graxia\packages\quant_os\scripts')
from run_release_gate import is_file_exempted

cases = [
    (r"graxia/packages/quant_os/reports/capacity_ceiling.py", False),
    (r"graxia/packages/quant_os/research/pipeline.py", False),
    (r"graxia\packages\quant_os\reports\research_backed_pipeline.json", True),
    (r"graxia/packages/quant_os/reports/research_backed_pipeline.json", True),
    (r"Meta/states/researcher-forexroasted.md", True),
    (r"graxia/packages/quant_os/1350)", False),
    (r"graxia/packages/quant_os/state/audit_log.jsonl", True),
    (r"graxia/packages/quant_os/tests/test_config_unified.py", False),
]
for path, expected in cases:
    got = is_file_exempted(path)
    assert got == expected, f"{path}: got {got}, expected {expected}"
print("ALL TIER B CHECKS PASS")
```

- [ ] **Step 2: Implement replacement (lines 284-307 + 310-330)**

```python
import re  # add to existing imports if absent
from typing import FrozenSet, Tuple  # already has typing imports? verify

ALLOWED_DIRTY_FILES: FrozenSet[str] = frozenset({
    "data/heartbeat.txt",
    "graxia/packages/quant_os/data/heartbeat.txt",
    "graxia/packages/quant_os/tests/.test_tmp/list.json",
    "graxia/packages/quant_os/quarantine_manifest.json",  # gate itself writes it
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
    normalized_path = filepath.replace("\\", "/")
    if normalized_path.endswith(".py"):
        return False
    if normalized_path in ALLOWED_DIRTY_FILES:
        return True
    return any(p.match(normalized_path) for p in ALLOWED_DIRTY_PATTERNS)
```

Then update `check_git_clean()`:

```python
    for line in status.split("\n"):
        if len(line) < 4:
            continue
        filepath = line[3:].strip()
        if is_file_exempted(filepath):
            continue
        dirty_files.append(filepath)
```

And add the stale-entry drift warning (after computing dirty_files, before
return): warn for each `ALLOWED_DIRTY_FILES` entry whose path does not exist
on disk (relative to REPO_ROOT), but do NOT fail. Use `logger.warning` or a
printed `[WARNING]` line consistent with existing gate output style.

- [ ] **Step 3: Run tier B checks + ruff/mypy**

```bash
python C:\Users\menum\AppData\Local\Temp\opencode\tier_b_checks.py
# Expected: ALL TIER B CHECKS PASS
cd graxia\packages\quant_os && ruff check scripts\run_release_gate.py && ruff format --check scripts\run_release_gate.py
cd "C:\Users\menum\graxia os" && mypy --ignore-missing-imports graxia/packages/quant_os/scripts/run_release_gate.py
```

- [ ] **Step 4: Commit**

```bash
git add graxia/packages/quant_os/scripts/run_release_gate.py
git commit -m "fix(quant_os): hardened dirty-tree exemption — path-normalized, .py hard-reject, stale-entry warning"
```

---

## Task 3: Tier C — massive_sentiment skipif + manifest

**Files:**
- Modify: `tests/test_massive_sentiment.py` (module top, after PROVIDERS)
- Modify: `quarantine_manifest.json`
- Modify: `scripts/run_release_gate.py` (remove `--ignore=...test_massive_sentiment.py`)

**Interfaces:**
- Produces: `approved_runtime_skips.total` 60 → 61; quarantine 23 → 22;
  SUITE_CMD ignore count 23 → 22; consistency still holds (ignore-set == manifest-set).

- [ ] **Step 1: Add skipif to test_massive_sentiment.py**

```python
# After PROVIDERS definition, before HEADLINES or right after imports:
_has_any_provider_key = any(
    os.environ.get(cfg.env_key)
    for cfg in PROVIDERS
    if hasattr(cfg, "env_key")
)

@pytest.mark.skipif(
    not _has_any_provider_key,
    reason="live provider API keys not configured in gate env",
)
```

Place directly above `def test_massive_sentiment_all_providers(...)` (the only
test in the file). Verify `PROVIDERS` and `env_key` attribute names by reading
the file first (the module also reads `.env` at test time — the skipif must be
evaluated at collection; if keys are only loaded inside the test function body,
the skipif check must replicate the env-file loading or gate on
`os.environ` + the same `.env` parse).

- [ ] **Step 2: Standalone verify skip**

```bash
python -m pytest graxia/packages/quant_os/tests/test_massive_sentiment.py -v
# Expected: 1 skipped (no provider keys in env) — OR skipped if .env has no keys
```

- [ ] **Step 3: Remove --ignore line + manifest entry; add approved skip**

```bash
# 1) Remove from SUITE_CMD (single unique line)
# 2) Remove quarantine entry QOS-RB-017 from quarantined_tests[]; total 23 -> 22
# 3) Append to approved_runtime_skips.reasons:
#    {"count": 1, "where": "test_massive_sentiment.py",
#     "reason": "live provider API keys not configured in gate env"}
#    total 60 -> 61
```

- [ ] **Step 4: Consistency check**

```bash
python C:\Users\menum\AppData\Local\Temp\opencode\consistency_check.py
# Expected: ignored == manifest: True; counts: 22 22
```

- [ ] **Step 5: Commit pair**

```bash
git add graxia/packages/quant_os/scripts/run_release_gate.py graxia/packages/quant_os/quarantine_manifest.json graxia/packages/quant_os/tests/test_massive_sentiment.py
git commit -m "test(quant_os): move massive_sentiment to approved_runtime_skips (env-gated skipif)"
```

---

## Task 4: Tier D — gate-verification playbook

**Files:**
- Create: `docs/superpowers/playbooks/gate-verification.md`

- [ ] **Step 1: Write playbook**

Sections:
1. **When to use pinned worktree** — parallel session mutating shared tree,
   run_a/run_b capture different commits, git_clean false on their files.
2. **Pinned-worktree protocol**:
   - `git worktree add --detach <path> <sha>` (sha = target commit)
   - copy gitignored `config/` data files from live tree for parity:
     `Copy-Item` the 17 files (or `git status`-driven diff)
   - commit copies in worktree with `--no-verify` (throwaway)
   - run gate from worktree root; verify `git_commit.txt` + `pytest_command.txt`
     identical across run_a/run_b
   - copy evidence to `artifacts/release_gate/batchN/`
   - `git worktree remove <path>` after review
3. **Exemption policy summary** — 2-tier: Tier A untrack, Tier B file-level
   patterns, `.py` never exempt, stale-entry warnings.
4. **E1 protocol reference** — poll <= 30 min, then ask (plan section).
5. **Verification checklist** — dual runs both PASS, A==B stats, consistency.

- [ ] **Step 2: Commit**

```bash
git add graxia/packages/quant_os/docs/superpowers/playbooks/gate-verification.md
git commit -m "docs(quant_os): gate-verification playbook — pinned-worktree protocol + exemption policy"
```

---

## Task 5: Verify — dual gate runs (live tree + pinned worktree)

**Files:**
- Read: gate artifacts (`summary.json`, `run_*/pytest_output.txt`,
  `run_*/git_commit.txt`, `run_*/pytest_command.txt`)

- [ ] **Step 1: Live-tree gate run**

```bash
python graxia/packages/quant_os/scripts/run_release_gate.py
# Expected: GATE_EXIT=0, verdict PASS, all 10 checks true, run_a == run_b
# If RED on git_clean only from parallel-session NEW files: re-check exemption
# patterns cover them (Tier B) or log as contamination (do NOT exempt .py).
```

- [ ] **Step 2: Pinned-worktree gate run**

```bash
# pin at the commit after Task 4 (HEAD of this work)
git worktree add --detach C:\Users\menum\AppData\Local\Temp\opencode\gate_worktree_hardening <sha>
# copy config/ parity files (playbook step), commit --no-verify in worktree
python <worktree>/graxia/packages/quant_os/scripts/run_release_gate.py
# Expected: same as live tree: PASS, A==B
```

- [ ] **Step 3: Copy evidence**

```bash
# copy summary.json + run_a/* + run_b/* + gate stdout to artifacts/release_gate/hardening/
```

- [ ] **Step 4: Report**

Summarize: verdicts, stats, A==B equality, any contamination logged,
checklist from user review (Tier A clean status, ruff/mypy pass,
massive_sentiment skipped, dual PASS).

---

## Verification Checklist (from approved spec review)

- [ ] Tier A: `git status --porcelain` shows no tracked dirty entries for
      artifacts/, state/, validation/.experiment_registry.json
- [ ] Tier B: ruff + mypy zero errors on `scripts/run_release_gate.py`
- [ ] Tier B: `is_file_exempted()` rejects `.py`, accepts backslash-normalized
      runtime artifacts, rejects `1350)`
- [ ] Tier C: massive_sentiment reported SKIPPED in suite, no gate failure
- [ ] Tier D: playbook exists
- [ ] Final: live + worktree gate runs both PASS with identical A==B stats
- [ ] Consistency: ignore-set == manifest-set (22 == 22)

## Risks / Mitigations

- **Parallel-session commits during verify** → use pinned worktree as official
  record; log live-tree contamination; never exempt `.py`.
- **Pre-commit hook auto-fix loops** → re-add + re-commit pattern; verify
  `git log --oneline -1` after each commit.
- **skipif collection-time env** → if `.env` loading happens inside the test,
  replicate the parse in the skipif guard so collection sees keys correctly.
- **`.gitignore` gaps** → verify coverage before `git rm --cached` (Task 1
  Step 1) so untracked files don't reappear via `git add .`.
