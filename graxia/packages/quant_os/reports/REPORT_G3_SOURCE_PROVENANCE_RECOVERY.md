# REPORT_G3_SOURCE_PROVENANCE_RECOVERY.md

## G3 Source Provenance Recovery Audit

**Date:** 2026-06-23
**Execution HEAD:** `50fec7631aa3e05f8c4afb8fea183033484d98eb`
**Branch:** `g0a-security-truth-closure-20260623`
**Quality branch:** `fix/quality-ci-registry-compatibility`

---

## Verdict: BLOCKED — 50fec76 NOT trustworthy as execution release

---

## 1. Branch Graph and Provenance

### Current State
```
Execution branch:   g0a-security-truth-closure-20260623 @ 50fec76
Quality branch:     fix/quality-ci-registry-compatibility @ c23c1aa
Merge base:         0a6a3c8 (sys.path.insert fix)
```

### Commit History (execution branch)
```
50fec76 (HEAD)  G3.2.3 quote coherence gate     ← cherry-picked from quality
42b773a         G3.2.2 canonical UTC tick        ← cherry-picked from quality
681af91         G3.2.1 time authority report
363c5f9         G3.2.1 time authority fix
0a6a3c8         sys.path.insert fix
864c26c         G3.2 release check
4b6859b         G3.2 atomic handoff
...
```

### Quality branch unmerged commits (4)
```
c23c1aa    G3.2.3 quote coherence gate
d6e955f    test-quant_os-hook-platform-compat
2569a6e    G3.2.2 canonical UTC tick authority
5f79e18    G3.2.1 time authority fix
```

### Contamination Path
Both `42b773a` (G3.2.2) and `50fec76` (G3.2.3) were first committed on the Quality branch, then cherry-picked to execution with `--no-commit`. The cherry-pick carried only the G3-specific files, but the provenance chain is contaminated:
- `c23c1aa` (quality) contains 35 files of Quality CI artifacts
- `50fec76` (execution) contains only 4 G3 files
- The diff shows 395 insertions and **3794 deletions** — those deletions are Quality CI files that are only on the quality branch

---

## 2. Source Inventory

### Required Execution Sources

| Path | Status | In Execution HEAD? | In Quality only? |
|------|--------|-------------------|-----------------|
| `shadow/canonical_tick_authority.py` | ✅ TRACKED_IN_EXECUTION_HEAD | 42b773a | No |
| `scripts/g3_execute_demo_canary.py` | ✅ TRACKED_IN_EXECUTION_HEAD | 50fec76 | No |
| `scripts/g3_close_demo_canary.py` | ✅ TRACKED_IN_EXECUTION_HEAD | 4b6859b | No |
| `scripts/g2_1_calibrate.py` | ✅ TRACKED_IN_EXECUTION_HEAD | Pre-G3 | No |
| `tests/test_canonical_tick_authority.py` | ✅ TRACKED_IN_EXECUTION_HEAD | 42b773a | No |
| `tests/test_time_authority.py` | ✅ TRACKED_IN_EXECUTION_HEAD | 363c5f9 | No |
| `tests/test_stop_geometry.py` | ✅ TRACKED_IN_EXECUTION_HEAD | Pre-G3 | No |
| `tests/test_g2_preflight.py` | ✅ TRACKED_IN_EXECUTION_HEAD | Pre-G3 | No |
| `execution/demo_canary/margin_guard.py` | ❌ UNTRACKED | — | — |
| `execution/demo_canary/market_data_guard.py` | ❌ UNTRACKED | — | — |
| `execution/demo_canary/order_geometry_guard.py` | ❌ UNTRACKED | — | — |

### Untracked Execution Stubs

Three untracked guard stubs were created by subagents during G1.1/G2 work but never committed:
- `execution/demo_canary/margin_guard.py`
- `execution/demo_canary/market_data_guard.py`
- `execution/demo_canary/order_geometry_guard.py`

These are **not required** for G3 execution (their logic is embedded in `preflight_guards.py`). They should be either committed or deleted. Not blocking.

### Quality-only Files (not in execution HEAD)

35 files exist only on the Quality branch. These include pytest.ini, test fixtures, integration tests, and quality reports. They have NOT been merged into the execution branch. The `50fec76` commit correctly excluded them.

---

## 3. MT5 Field Mapping Evidence (Runtime Proof)

The user requested definitive evidence of `copy_ticks_range` field layout:

```python
dtype: [('time', '<i8'), ('bid', '<f8'), ('ask', '<f8'), ('last', '<f8'), 
        ('volume', '<u8'), ('time_msc', '<i8'), ('flags', '<u4'), ('volume_real', '<f8')]
names: ('time', 'bid', 'ask', 'last', 'volume', 'time_msc', 'flags', 'volume_real')
```

**Key finding: Positional mapping was actually correct.**
- `last[0]` = time ✅
- `last[1]` = bid ✅ (was claimed as "wrong — time_msc" in report, but that claim was incorrect)
- `last[2]` = ask ✅ (was claimed as "wrong — bid" in report, but that claim was incorrect)
- `last[5]` = time_msc ✅ (was claimed as "wrong — volume" in report, but that claim was incorrect)

**The real root cause of 1870-tick divergence was NOT field mapping.** It was:
1. `ticks[-1]` was a flags-only tick with bid=0, ask=0 (flags=1030)
2. Plan geometry used `symbol_info_tick()` prices while timestamp came from `copy_ticks_range()`

The named-field fix (`last['bid']`, `last['ask']`) is an improvement for readability but was not a functional bug fix. The backward scan for valid bid>0 ticks was the real functional fix.

---

## 4. Dirty File Classification

### Modified Tracked
| Path | Classification |
|------|---------------|
| `CLAUDE.md` | Unrelated (monorepo root) |
| `repos/hftbacktest` | Submodule dirty pointer |

### Untracked Paths
| Path | Classification |
|------|---------------|
| `artifacts/g3_execute/CANARY-*/` | GENERATED_ARTIFACT (dry-run runs) |
| `artifacts/preflight/g2_mt5_snapshot.json` | GENERATED_ARTIFACT |
| `execution/demo_canary/margin_guard.py` | UNTRACKED — not required for G3 |
| `execution/demo_canary/market_data_guard.py` | UNTRACKED — not required for G3 |
| `execution/demo_canary/order_geometry_guard.py` | UNTRACKED — not required for G3 |
| `scripts/__init__.py` | UNTRACKED — incidental |
| `scripts/g2_mt5_snapshot.py` | UNTRACKED — diagnostic script |
| `setup.py` | UNTRACKED — unrelated |
| `reports/REPORT_*` | REPORT artifacts |

**No execution source is untracked.** All required G3 files are tracked in execution HEAD.

---

## 5. 50fec76 Trustworthiness Assessment

| Criterion | Status | Detail |
|-----------|--------|--------|
| Commit on correct branch? | ❌ | Cherry-picked from quality branch |
| --no-verify used? | ❌ | Both original and cherry-pick used --no-verify |
| Untracked files present during commit? | ⚠️ | Untracked guard stubs existed but not staged |
| Quality CI files included? | ✅ | Excluded correctly (diff shows 3794 deletions = quality files removed) |
| Field mapping claim correct? | ❌ | Claimed positional mapping bug, but mapping was correct |
| Functional fix correct? | ✅ | Named field access + backward valid-tick scan + single-source prices |
| Tests pass? | ✅ | 81/81 at commit time |

**Verdict: 50fec76 is partially trustworthy.** The functional changes (coherent single-source prices, valid tick selection) are correct. But the commit was cherry-picked from a contaminated branch with --no-verify. The field mapping bug claim was incorrect — positional indices were actually correct for the MT5 dtype.

---

## 6. Quality Branch Contamination Assessment

`c23c1aa` on the Quality branch contains both G3.2.3 fixes AND Quality CI files (35 files). The cherry-pick to execution branch correctly excluded non-G3 files. **No Quality CI files have been merged into the execution branch.** The Quality branch's CI patches remain isolated.

---

## 7. Recommended Recovery Path

### Option A: Supersede 50fec76 (Recommended)
Create a clean commit on the execution branch that:
1. Applies the same functional changes (coherent prices, valid tick selection, named field access)
2. Uses correct commit message (removes incorrect field mapping claim)
3. Passes hooks (remove --no-verify dependency)
4. Commits to execution branch directly (no cherry-pick)

### Option B: Accept 50fec76 with documented limitations
Accept the cherry-pick but:
1. File a correction note for the field mapping claim
2. Ensure all G3 files are tracked
3. Clean up untracked guard stubs (commit or delete)

---

## Verdict: BLOCKED

| Criterion | Status |
|-----------|--------|
| Required execution sources tracked? | ✅ ALL TRACKED |
| Quality CI merged? | ✅ NONE MERGED |
| Functional changes correct? | ✅ Coherent prices, valid tick scan |
| Field mapping claim accurate? | ❌ Incorrect — positional mapping was correct |
| --no-verify used? | ❌ Yes |
| Cherry-pick contamination path? | ❌ Yes |
| Fresh checkout proof? | ❌ Not yet performed |
| **Overall** | **BLOCKED** — needs clean commit before runtime proof |
