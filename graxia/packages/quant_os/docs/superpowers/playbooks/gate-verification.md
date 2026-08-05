# Release Gate Verification — Playbook

Date: 2026-08-04
Spec: `docs/superpowers/specs/2026-08-04-gate-exemption-hardening-design.md`
Plan: `docs/superpowers/plans/2026-08-04-gate-exemption-hardening.md`

Standard operating procedure for running the release gate
(`scripts/run_release_gate.py`) safely — especially when a parallel session is
actively mutating the shared working tree.

## 1. When to use a pinned worktree

Run the gate on a **pinned detached worktree** instead of the live tree when:

- A parallel session is committing frequently (observed: every 5-10 min).
- run_a / run_b capture different commits → pass-count mismatch
  (`Pass count mismatch: A=... B=...`), `reproducible: false`.
- `git_clean` fails on the parallel session's newest files.

Rationale (industry practice): CI runs gates on fresh clean checkouts. A
dirty-tree check is only meaningful in a live dev tree; when the tree is a
moving target, freeze it at the commit under test.

## 2. Pinned-worktree protocol

```bash
# 1) Pin at the target commit (e.g. HEAD of the batch work)
git worktree add --detach C:\path\to\gate_worktree <commit-sha>

# 2) Copy gitignored config/data files for parity — a fresh checkout lacks
#    gitignored files that tests assert exist (config/*.toml, config/*.json,
#    config/.env.example). Copy them from the live tree:
#    (from repo root)
Copy-Item -Recurse graxia/packages/quant_os/config/* C:\path\to\gate_worktree\graxia\packages\quant_os\config\

# 3) Commit the copied files in the worktree so git_clean is honest
#    (throwaway commit — never leaves the machine)
cd C:\path\to\gate_worktree
git add -A
git commit --no-verify -m "snapshot: parity config data files"

# 4) Run the gate FROM the worktree root
python C:\path\to\gate_worktree\graxia\packages\quant_os\scripts\run_release_gate.py
```

### 2.1 Verify evidence integrity (after every gate run)

Before trusting a PASS, confirm BOTH runs captured the SAME state:

```bash
# git_commit.txt must be identical in run_a and run_b
type artifacts\release_gate\run_a\git_commit.txt
type artifacts\release_gate\run_b\git_commit.txt

# pytest_command.txt must show the expected --ignore set (count matches manifest)
# Compare ignore count: python -c "t=open(r'artifacts\release_gate\run_a\pytest_command.txt').read(); print(t.count('--ignore='))"
```

Red flags: differing git_commit.txt between runs, or a pass-count mismatch —
evidence is contaminated; discard and re-run in a quiet window or pinned tree.

### 2.2 Collect evidence

```bash
# Copy summary + both runs' outputs to the batch evidence dir
# (artifacts are gitignored — evidence lives on disk, not in git)
Copy-Item artifacts\release_gate\summary.json <batchdir>\gate_summary_summary.json
Copy-Item artifacts\release_gate\run_a\* <batchdir>\
Copy-Item artifacts\release_gate\run_b\* <batchdir>\
```

### 2.3 Cleanup

```bash
git worktree remove C:\path\to\gate_worktree
```

## 3. Exemption policy (2-tier, fail-closed)

`check_git_clean()` in `scripts/run_release_gate.py` exempts dirty files only
through `is_file_exempted()`:

- **`.py` files are NEVER exempted** — hard rejection, regardless of path.
- **Exact-file allowlist** `ALLOWED_DIRTY_FILES` (heartbeat, .test_tmp,
  quarantine_manifest.json).
- **Narrow data-extension patterns** `ALLOWED_DIRTY_PATTERNS` — only
  `.json` / `.md` / `.jsonl` under research/, reports/, Meta/states/, state/.
- **Tier A hygiene**: runtime artifacts should be UNTRACKED + gitignored
  (`git rm --cached` + `.gitignore`) so they never appear dirty at all.
- **Stale-entry guard**: the gate warns when an allowed entry no longer
  exists on disk (dead config drift).

Do NOT add whole-directory exemptions for `reports/` or `research/` — they
contain real source (`.py`) and exempting them would let uncommitted code slip
past the gate.

## 4. E1 protocol (parallel-session blockage)

From plan `2026-08-03-release-gate-pass.md`: if the parallel session's source
fixes are still uncommitted, **poll ≤ 30 min; if blocked longer, pause and ask
(E1)**. Never weaken gate criteria to force a pass; use the pinned worktree as
the official record and log live-tree contamination as out-of-scope.

## 5. Verification checklist

- [ ] Live-tree run: PASS, all 10 checks true, run_a == run_b
- [ ] Pinned-worktree run: PASS, all 10 checks true, run_a == run_b
- [ ] `git_commit.txt` + `pytest_command.txt` identical across run_a/run_b
- [ ] Consistency: ignore-set == manifest-set
- [ ] massive_sentiment: collected + skipped (no keys) or passing (keys), never failing
- [ ] Evidence copied to `artifacts/release_gate/<batch>/`
