# Direction I Phase 0 — Governance + Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up Direction I's governance skeleton (ledgers, stopping rule, N accounting, screening registry, partition registry, writer-lock enforcement) and close all Phase 0 closure items from the approved spec, so funnel phases P1-P7 have a fail-closed foundation.

**Architecture:** Mirror existing Direction G governance patterns (per-direction ledger + registry, `validation/n_trials.py` N source-of-truth, `registry_schema.stamp_trial_entry` provenance) with Direction I parameters (cap 40, no deadline, 400h). Add three new small modules: writer-lock pre-commit enforcement (A18), screening config registry with hash dedup (A6), and H/I scope partition check (A17). All changes are additive — zero edits to Direction H files (citations-only policy).

**Tech Stack:** Python 3.11+, JSON ledgers (no new deps), pytest, pre-commit local hook, ctypes (Windows pid liveness check).

## Global Constraints

- Trial range I = 10000-10999 (TRIAL_ID_RANGES.md rule: next free 1000-block; ranges follow creation order, not alphabetical — A13)
- Max Total Trials (I) = 40 hard cap; deadline REMOVED; 400 research-hours; 3 consecutive fails = §4.4 review (spec §2)
- Ledgers: `research/trial_ledger_i.json`, `research/hypothesis_registry_i.json`, `research/screening_log_i.json` — NONE may already exist (checked at start)
- N_I = 1050 (baseline) + |distinct configs in screening_log_i| + |trials in trial_ledger_i|; hash = `(mechanism, symbol, timeframe, params, data_range)` (spec §3, A6)
- DO NOT touch any Direction H file (`research/trial_ledger_h.json`, `hypothesis_registry_g/h`, `research/pre_registration/trial_900*`, `reports/stopping_rule_2026_08_06_direction_h.md`, `TRIAL_ID_RANGES.md` H row) — citations-only (A16/A17)
- Writer lock: acquire `scripts/acquire_writer_lock.py --owner "direction-i-funnel-design"` before any write; stale locks (dead pid) cleared only with `--hours <age> --force` after human approval
- `check_trial_uniqueness.py` must pass after every ledger/registry edit
- Every verdict/screening entry stamped via `research/registry_schema.stamp_trial_entry()` (existing API)
- Pre-commit hook suite must stay green; no new dependencies

## Scope Check

The Direction I spec (2026-08-06-direction-i-ea-funnel-design.md) spans 8 phases with external dependencies (Tier0 Sweep C0 output, Sub-project B/C1 decisions — not yet delivered). Per writing-plans scope rule, **this plan covers only Phase 0** (fully executable now, produces working governance). Follow-on roadmap in §Follow-on Plans.

## File Structure

| File | Responsibility |
|---|---|
| `scripts/check_writer_lock.py` (NEW) | Pre-commit local hook: refuse commit while a LIVE foreign `.writer.lock` exists (A18) |
| `.pre-commit-config.yaml` (MODIFY) | Add `repo: local` hook running `check_writer_lock.py` |
| `tests/test_check_writer_lock.py` (NEW) | Tests for hook logic (pid liveness, env override) |
| `research/trial_ledger_i.json` (NEW) | Direction I ledger (mirror `trial_ledger_g.json`, cap 40) |
| `research/hypothesis_registry_i.json` (NEW) | Direction I hypothesis registry (mirror `hypothesis_registry_g.json`) |
| `research/screening_log_i.json` (NEW) | Screening config log (hash-dedup N accounting) |
| `reports/stopping_rule_2026_08_06_direction_i.md` (NEW) | Direction I stopping-rule doc (SHA-256 locked) |
| `TRIAL_ID_RANGES.md` (MODIFY) | Add Direction I row 10000-10999 + creation-order note |
| `validation/n_trials_i.py` (NEW) | `get_n_i()` — N_I source of truth (pattern: `validation/n_trials.py`) |
| `tests/test_n_trials_i.py` (NEW) | N_I computation tests |
| `research/screening_registry.py` (NEW) | `config_hash()`, `register_config()` — hash-dedup registration |
| `tests/test_screening_registry.py` (NEW) | Registration + dedup tests |
| `research/partition_registry.py` (NEW) | `check_partition()` — H/I scope partition (A17) |
| `tests/test_partition_registry.py` (NEW) | Partition classification tests |
| `scripts/screening_guard.py` (NEW) | `assert_no_guard_violations()`, `attr_scan()` — A11 supplement |
| `tests/test_screening_guard.py` (NEW) | Guard assertion tests |
| `scripts/rerun_tsm_jackknife.py` (NEW) | Closure item 1: TSM jackknife re-run from current data |
| `reports/tsm_portfolio_jackknife_rerun_20260806.json` (NEW, generated) | Closure evidence output |

---

### Task 1: Writer-lock enforcement hook (A18)

**Files:**
- Create: `scripts/check_writer_lock.py`
- Modify: `.pre-commit-config.yaml`
- Test: `tests/test_check_writer_lock.py`

**Interfaces:**
- Consumes: `.writer.lock` JSON `{owner, pid, timestamp}` at monorepo root (parents[4]); env `WRITER_LOCK_ROOT` override (same convention as `scripts/acquire_writer_lock.py`)
- Produces: `check_writer_lock.main() -> int` (0 = allow commit, 1 = refuse); `check_writer_lock.pid_alive(pid: int) -> bool`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_check_writer_lock.py
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import check_writer_lock as cwl


@pytest.fixture
def lock_root(tmp_path):
    (tmp_path / ".writer.lock").write_text(
        json.dumps({"owner": "someone", "pid": 999999, "timestamp": 0.0}),
        encoding="utf-8",
    )
    return tmp_path


def test_pid_alive_false_for_dead_pid():
    assert cwl.pid_alive(999999) is False


def test_pid_alive_true_for_own_pid():
    assert cwl.pid_alive(os.getpid()) is True


def test_main_returns_0_when_no_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITER_LOCK_ROOT", str(tmp_path))
    assert cwl.main() == 0


def test_main_returns_1_for_live_foreign_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITER_LOCK_ROOT", str(tmp_path))
    (tmp_path / ".writer.lock").write_text(
        json.dumps({"owner": "other", "pid": os.getpid(), "timestamp": 0.0}),
        encoding="utf-8",
    )
    assert cwl.main() == 1


def test_main_returns_0_for_stale_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITER_LOCK_ROOT", str(tmp_path))
    (tmp_path / ".writer.lock").write_text(
        json.dumps({"owner": "other", "pid": 999999, "timestamp": 0.0}),
        encoding="utf-8",
    )
    assert cwl.main() == 0


def test_main_returns_0_when_own_owner_env_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITER_LOCK_ROOT", str(tmp_path))
    monkeypatch.setenv("WRITER_LOCK_OWNER", "my-session")
    (tmp_path / ".writer.lock").write_text(
        json.dumps({"owner": "my-session", "pid": os.getpid(), "timestamp": 0.0}),
        encoding="utf-8",
    )
    assert cwl.main() == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_check_writer_lock.py -v`
Expected: FAIL with `ModuleNotFoundError` / `AttributeError` (module/function absent)

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/check_writer_lock.py
"""Pre-commit hook: refuse commits while a LIVE foreign writer lock exists.

Closes the A18 advisory-lock gap: `.writer.lock` was previously enforced
only by run_release_gate.py. This hook makes it load-bearing for git commits.
Exit 0 = allow commit; exit 1 = refuse.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]  # monorepo root (same as acquire script)
if os.environ.get("WRITER_LOCK_ROOT"):
    REPO_ROOT = Path(os.environ["WRITER_LOCK_ROOT"])
LOCK_PATH = REPO_ROOT / ".writer.lock"


def pid_alive(pid: int) -> bool:
    """Return True if a process with ``pid`` exists on this host."""
    if pid is None or pid <= 0:
        return False
    if os.name == "nt":
        import ctypes

        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(
            PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid)
        )
        if not handle:
            return False
        ctypes.windll.kernel32.CloseHandle(handle)
        return True
    try:
        os.kill(int(pid), 0)
        return True
    except (ProcessLookupError, PermissionError, OSError):
        return False


def main() -> int:
    if not LOCK_PATH.exists():
        return 0
    try:
        data = json.loads(LOCK_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        print(f"writer-lock: unreadable {LOCK_PATH} — remove manually or fix; refusing commit.")
        return 1
    owner = data.get("owner", "unknown")
    pid = data.get("pid", -1)
    if not pid_alive(pid):
        print(f"writer-lock: stale (owner={owner}, pid={pid} dead) — commit allowed; "
              f"clear with acquire --force after review.")
        return 0
    env_owner = os.environ.get("WRITER_LOCK_OWNER")
    if env_owner and data.get("owner") == env_owner:
        return 0  # committing session holds the lock
    print(f"writer-lock: LIVE foreign lock (owner={owner}, pid={pid}) — refusing commit per F26. "
          f"Set WRITER_LOCK_OWNER=<owner> if you are that session, or wait for release.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_check_writer_lock.py -v`
Expected: 6 passed

- [ ] **Step 5: Wire the pre-commit hook**

Append to `.pre-commit-config.yaml`:

```yaml
  - repo: local
    hooks:
      - id: writer-lock-check
        name: refuse commits while a live foreign writer lock is held
        entry: python scripts/check_writer_lock.py
        language: system
        always_run: true
        pass_filenames: false
```

- [ ] **Step 6: Verify hook wiring**

Run: `pre-commit run writer-lock-check --all-files`
Expected: PASS (no lock file present)

- [ ] **Step 7: Commit**

```bash
git add scripts/check_writer_lock.py tests/test_check_writer_lock.py .pre-commit-config.yaml
git commit -m "feat(quant_os): writer-lock enforcement pre-commit hook (Direction I A18)"
```

---

### Task 2: Direction I ledgers + stopping rule + ranges table

**Files:**
- Create: `research/trial_ledger_i.json`
- Create: `research/hypothesis_registry_i.json`
- Create: `research/screening_log_i.json`
- Create: `reports/stopping_rule_2026_08_06_direction_i.md`
- Modify: `TRIAL_ID_RANGES.md`

**Interfaces:**
- Consumes: schema of `research/trial_ledger_g.json` (verified 2026-08-06), `research/hypothesis_registry_g.json`, existing `TRIAL_ID_RANGES.md` table
- Produces: `research/trial_ledger_i.json` — must contain `cumulative_trial_cap: 40`, `next_available_trial_number: 10001`, `trial_range: "10000-10999"`, `lock_doc_path: "reports/stopping_rule_2026_08_06_direction_i.md"`, `lock_doc_sha256` (set in Step 4 after doc written); `research/screening_log_i.json` — schema `{"schema_version": "1.0", "direction": "I", "configs": [], "count": 0}`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_direction_i_ledgers.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_ledger_i_exists_and_matches_governance():
    ledger = json.loads((ROOT / "research" / "trial_ledger_i.json").read_text(encoding="utf-8"))
    assert ledger["direction"] == "I"
    assert ledger["trial_range"] == "10000-10999"
    assert ledger["cumulative_trial_cap"] == 40
    assert ledger["next_available_trial_number"] == 10001
    assert ledger["stopping_rule"]["deadline"] is None  # user override: no time limit
    assert ledger["stopping_rule"]["hours_cap"] == 400
    assert ledger["stopping_rule"]["consecutive_fail_gate_threshold"] == 3
    assert ledger["sacred_holdout"]["status"] == "LOCKED"
    assert len(ledger["lock_doc_sha256"]) == 64


def test_registry_i_exists():
    reg = json.loads((ROOT / "research" / "hypothesis_registry_i.json").read_text(encoding="utf-8"))
    assert reg["direction"] == "I"
    assert reg["cumulative_trial_count_at_creation"] == 0


def test_screening_log_i_schema():
    log = json.loads((ROOT / "research" / "screening_log_i.json").read_text(encoding="utf-8"))
    assert log["schema_version"] == "1.0"
    assert log["direction"] == "I"
    assert log["configs"] == []
    assert log["count"] == 0


def test_ranges_table_has_direction_i():
    text = (ROOT / "TRIAL_ID_RANGES.md").read_text(encoding="utf-8")
    assert "| Direction I" in text
    assert "10000–10999" in text or "10000-10999" in text


def test_ranges_table_notes_creation_order():
    text = (ROOT / "TRIAL_ID_RANGES.md").read_text(encoding="utf-8")
    assert "creation order" in text.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_direction_i_ledgers.py -v`
Expected: FAIL (files missing)

- [ ] **Step 3: Create `research/trial_ledger_i.json`**

```json
{
  "schema_version": "1.0",
  "direction": "I",
  "lock_date": "2026-08-06",
  "lock_doc_path": "reports/stopping_rule_2026_08_06_direction_i.md",
  "lock_doc_sha256": "",
  "description": "Direction I: EA Deep-Mine Funnel. Opened 2026-08-06 per docs/superpowers/specs/2026-08-06-direction-i-ea-funnel-design.md. Separate ledger per Path-B precedent; parallel Direction H (9000-9999) is citations-only. User override: no deadline; 400 research-hours; 40-trial hard cap across all cycles and sub-programs.",
  "cumulative_trial_count": 0,
  "cumulative_trial_cap": 40,
  "next_available_trial_number": 10001,
  "new_hypotheses_used": 0,
  "new_hypotheses_remaining": 40,
  "trial_range": "10000-10999",
  "stopping_rule": {
    "type": "budget_or_hours_or_consecutive_fail",
    "budget": 40,
    "deadline": null,
    "hours_cap": 400,
    "consecutive_fail_gate_threshold": 3,
    "description": "Stop when any: 40 hypotheses used, 400 research-hours logged, or 3 consecutive hypotheses fail at the same gate. Deadline removed by user override 2026-08-06. Per stopping_rule_2026_08_06_direction_i.md §4."
  },
  "sacred_holdout": {
    "path": "data/sacred_holdout/",
    "status": "LOCKED",
    "use_count": 0,
    "max_use_count": 1,
    "unlock_phase": "4.5 — final confirmation gate only (P7)",
    "open_policy": "Opening this file and running any backtest against it counts as 1 trial. Cannot be reopened."
  }
}
```

- [ ] **Step 4: Create stopping-rule doc + fill SHA-256**

Create `reports/stopping_rule_2026_08_06_direction_i.md` (mirror `reports/stopping_rule_2026_08_05.md` structure: scope, instruments I-funnel, methodology, §4 stopping conditions — budget 40 / hours 400 / 3-consecutive-fail, decision tree per spec §2.1, acknowledgment). Then:

```bash
python - <<'PY'
import hashlib
from pathlib import Path
p = Path("reports/stopping_rule_2026_08_06_direction_i.md")
h = hashlib.sha256(p.read_bytes()).hexdigest()
import json
led = Path("research/trial_ledger_i.json")
d = json.loads(led.read_text(encoding="utf-8"))
d["lock_doc_sha256"] = h
led.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
print(h)
PY
```

- [ ] **Step 5: Create `research/hypothesis_registry_i.json` and `research/screening_log_i.json`**

```json
{
  "schema_version": "1.0",
  "direction": "I",
  "description": "Direction I: EA Deep-Mine Funnel (see docs/superpowers/specs/2026-08-06-direction-i-ea-funnel-design.md).",
  "last_updated": "2026-08-06T00:00:00+00:00",
  "cumulative_trial_count_at_creation": 0,
  "stopping_rule_doc": "reports/stopping_rule_2026_08_06_direction_i.md — budget 40, no deadline, hours 400, 3-consecutive-fail gate",
  "entries": []
}
```

```json
{
  "schema_version": "1.0",
  "direction": "I",
  "description": "Screening config log — every executed screening config registered BEFORE run (spec §3, A6). hash = sha256(mechanism|symbol|timeframe|params_json|data_range).",
  "configs": [],
  "count": 0
}
```

- [ ] **Step 6: Update `TRIAL_ID_RANGES.md`**

Add row to the table: `| Direction I | 10000–10999 | (pre-registration starts 2026-08-06) | trial_ledger_i.json, hypothesis_registry_i.json, screening_log_i.json |`
Add rule note under "Rules": `- Ranges follow DIRECTION CREATION ORDER, not alphabetical order (e.g., C=7xxx predates D=4xxx). Derive the next block from the highest allocated block, never from the letter.`

- [ ] **Step 7: Run test + uniqueness check**

Run: `python -m pytest tests/test_direction_i_ledgers.py -v`
Expected: 5 passed
Run: `python scripts/check_trial_uniqueness.py`
Expected: PASS (63+ entries, 0 collisions)

- [ ] **Step 8: Commit**

```bash
git add research/trial_ledger_i.json research/hypothesis_registry_i.json research/screening_log_i.json reports/stopping_rule_2026_08_06_direction_i.md TRIAL_ID_RANGES.md tests/test_direction_i_ledgers.py
git commit -m "feat(quant_os): Direction I governance — ledgers, stopping rule, ranges table"
```

---

### Task 3: N accounting source of truth (`validation/n_trials_i.py`)

**Files:**
- Create: `validation/n_trials_i.py`
- Test: `tests/test_n_trials_i.py`

**Interfaces:**
- Consumes: `research/screening_log_i.json` (Task 2), `research/trial_ledger_i.json` (Task 2), baseline 1050 (`validation/n_trials.get_reconciled_n_trials()`)
- Produces: `get_n_i(screening_log_path=None, trial_ledger_path=None, baseline=None) -> int` — N_I for DSR; `count_distinct_configs(log_data: dict) -> int` (hash-dedup count)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_n_trials_i.py
import json

from validation.n_trials_i import count_distinct_configs, get_n_i


def _log(configs):
    return {"schema_version": "1.0", "direction": "I", "configs": configs, "count": len(configs)}


CFG_A = {"config_id": "a1", "hash": "h1", "status": "done"}
CFG_A_DUP = {"config_id": "a2", "hash": "h1", "status": "done"}  # same hash = same config
CFG_B = {"config_id": "b1", "hash": "h2", "status": "done"}
CFG_VOID = {"config_id": "c1", "hash": "h3", "status": "VOID"}


def test_count_distinct_configs_dedups_by_hash():
    assert count_distinct_configs(_log([CFG_A, CFG_A_DUP, CFG_B, CFG_VOID])) == 3


def test_count_distinct_configs_empty():
    assert count_distinct_configs(_log([])) == 0


def test_get_n_i_empty_logs_uses_baseline(tmp_path, monkeypatch):
    monkeypatch.setenv("WRITER_LOCK_ROOT", str(tmp_path))  # irrelevant; kept for parity
    assert get_n_i(baseline=1050) == 1050


def test_get_n_i_adds_configs_and_trials(tmp_path):
    screening = tmp_path / "screening_log_i.json"
    screening.write_text(json.dumps(_log([CFG_A, CFG_B, CFG_VOID])), encoding="utf-8")
    ledger = tmp_path / "trial_ledger_i.json"
    ledger.write_text(json.dumps({"cumulative_trial_count": 2}), encoding="utf-8")
    n = get_n_i(
        screening_log_path=str(screening),
        trial_ledger_path=str(ledger),
        baseline=1050,
    )
    # 1050 + 3 distinct configs (VOID still counts) + 2 trials = 1055
    assert n == 1055
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_n_trials_i.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

```python
# validation/n_trials_i.py
"""Source of truth for Direction I DSR n_trials (spec §3, A6).

N_I = 1050 (project baseline) + |distinct screening configs| + |trials|.
Distinct = unique ``hash`` field (sha256 of mechanism|symbol|timeframe|params|data_range).
VOID configs still count (they were tried). Direction H configs/trials NEVER enter N_I.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from validation.n_trials import get_reconciled_n_trials

logger = logging.getLogger(__name__)

_DEFAULT_SCREENING_LOG = Path(__file__).resolve().parent.parent / "research" / "screening_log_i.json"
_DEFAULT_TRIAL_LEDGER = Path(__file__).resolve().parent.parent / "research" / "trial_ledger_i.json"


def count_distinct_configs(log_data: dict) -> int:
    """Count configs with distinct ``hash`` values (A6 dedup rule)."""
    seen: set[str] = set()
    for cfg in log_data.get("configs", []):
        h = cfg.get("hash")
        if h:
            seen.add(h)
    return len(seen)


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        logger.warning("Unreadable JSON at %s — treating as empty", path)
        return {}


def get_n_i(
    screening_log_path: Path | str | None = None,
    trial_ledger_path: Path | str | None = None,
    baseline: int | None = None,
) -> int:
    """Return N_I for DSR multiple-testing correction.

    baseline defaults to the project reconciled N (1050 via
    ``validation.n_trials.get_reconciled_n_trials``).
    """
    n = baseline if baseline is not None else get_reconciled_n_trials()
    screening = _read_json(Path(screening_log_path) if screening_log_path else _DEFAULT_SCREENING_LOG)
    ledger = _read_json(Path(trial_ledger_path) if trial_ledger_path else _DEFAULT_TRIAL_LEDGER)
    n += count_distinct_configs(screening)
    n += int(ledger.get("cumulative_trial_count", 0))
    return n
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_n_trials_i.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add validation/n_trials_i.py tests/test_n_trials_i.py
git commit -m "feat(quant_os): N_I multiple-testing source of truth (Direction I spec §3)"
```

---

### Task 4: Screening config registry (`research/screening_registry.py`)

**Files:**
- Create: `research/screening_registry.py`
- Test: `tests/test_screening_registry.py`

**Interfaces:**
- Consumes: `research/screening_log_i.json` (Task 2)
- Produces: `config_hash(mechanism: str, symbol: str, timeframe: str, params: dict, data_range: tuple[str, str]) -> str`; `register_config(log_path, *, mechanism, symbol, timeframe, params, data_range, status="pending") -> dict` (appends config, dedups by hash, returns config entry); `load_configs(log_path) -> list[dict]`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_screening_registry.py
import json
from pathlib import Path

from research.screening_registry import config_hash, load_configs, register_config

PARAMS = {"lookback": 20, "entry": "close_cross"}


def test_config_hash_deterministic():
    a = config_hash("donchian", "BTCUSD", "H1", PARAMS, ("2018-01-01", "2026-07-01"))
    b = config_hash("donchian", "BTCUSD", "H1", PARAMS, ("2018-01-01", "2026-07-01"))
    assert a == b


def test_config_hash_differs_on_data_range():
    a = config_hash("donchian", "BTCUSD", "H1", PARAMS, ("2018-01-01", "2026-07-01"))
    b = config_hash("donchian", "BTCUSD", "H1", PARAMS, ("2019-01-01", "2026-07-01"))
    assert a != b  # A6: data_range change = distinct config


def test_register_config_dedups_by_hash(tmp_path):
    log = tmp_path / "screening_log_i.json"
    log.write_text(json.dumps({"schema_version": "1.0", "direction": "I", "configs": [], "count": 0}), encoding="utf-8")
    e1 = register_config(str(log), mechanism="donchian", symbol="BTCUSD", timeframe="H1", params=PARAMS, data_range=("2018-01-01", "2026-07-01"))
    e2 = register_config(str(log), mechanism="donchian", symbol="BTCUSD", timeframe="H1", params=PARAMS, data_range=("2018-01-01", "2026-07-01"))
    data = json.loads(log.read_text(encoding="utf-8"))
    assert e1["config_id"] == e2["config_id"]
    assert data["count"] == 1  # duplicate hash NOT double-counted


def test_register_config_counts_distinct(tmp_path):
    log = tmp_path / "screening_log_i.json"
    log.write_text(json.dumps({"schema_version": "1.0", "direction": "I", "configs": [], "count": 0}), encoding="utf-8")
    register_config(str(log), mechanism="donchian", symbol="BTCUSD", timeframe="H1", params=PARAMS, data_range=("2018-01-01", "2026-07-01"))
    register_config(str(log), mechanism="rsi_mr", symbol="EURUSD", timeframe="M15", params={"period": 14}, data_range=("2015-01-01", "2026-07-01"))
    data = json.loads(log.read_text(encoding="utf-8"))
    assert data["count"] == 2
    assert len(load_configs(str(log))) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_screening_registry.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

```python
# research/screening_registry.py
"""Screening config registry for Direction I (spec §3, A6).

Every screening config is registered BEFORE it runs. ``hash`` dedups
identical configs so N accounting never double-counts. VOID runs are
registered with status="VOID" and still count toward N.
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from pathlib import Path


def config_hash(mechanism: str, symbol: str, timeframe: str, params: dict, data_range: tuple[str, str]) -> str:
    canonical = "|".join(
        [mechanism, symbol, timeframe, json.dumps(params, sort_keys=True), f"{data_range[0]}..{data_range[1]}"]
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def load_configs(log_path: str | Path) -> list[dict]:
    path = Path(log_path)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("configs", [])
    except (json.JSONDecodeError, OSError):
        return []


def _write_log(path: Path, configs: list[dict]) -> None:
    path.write_text(
        json.dumps(
            {"schema_version": "1.0", "direction": "I", "configs": configs, "count": len(configs)},
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )


def register_config(
    log_path: str | Path,
    *,
    mechanism: str,
    symbol: str,
    timeframe: str,
    params: dict,
    data_range: tuple[str, str],
    status: str = "pending",
) -> dict:
    path = Path(log_path)
    configs = load_configs(path)
    h = config_hash(mechanism, symbol, timeframe, params, data_range)
    for cfg in configs:
        if cfg.get("hash") == h:
            return cfg  # already registered — do not double count
    entry = {
        "config_id": uuid.uuid4().hex[:12],
        "hash": h,
        "mechanism": mechanism,
        "symbol": symbol,
        "timeframe": timeframe,
        "params": params,
        "data_range": list(data_range),
        "status": status,
        "registered_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()),
    }
    configs.append(entry)
    _write_log(path, configs)
    return entry
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_screening_registry.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add research/screening_registry.py tests/test_screening_registry.py
git commit -m "feat(quant_os): screening config registry with hash dedup (Direction I A6)"
```

---

### Task 5: Scope partition registry (`research/partition_registry.py`, A17)

**Files:**
- Create: `research/partition_registry.py`
- Test: `tests/test_partition_registry.py`

**Interfaces:**
- Consumes: Direction H partition facts hardcoded from spec §1.8 (H trial 9001 REJECTED; 9002 FROZEN; EURUSD H4 pending)
- Produces: `check_partition(mechanism: str, symbol: str, timeframe: str) -> dict` — returns `{"status": "CLOSED"|"WATCH"|"FREE", "owner": "H"|"I"|None, "note": str}`; `PARTITION_RULES: list[dict]` (machine-checkable)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_partition_registry.py
from research.partition_registry import PARTITION_RULES, check_partition


def test_forex4_trend_continuity_closed():
    r = check_partition("trend_continuity", "USDCAD", "H1")
    assert r["status"] == "CLOSED"
    assert r["owner"] == "H"


def test_forex4_rsi_mr_watch():
    r = check_partition("rsi_mean_reversion", "AUDUSD", "H1")
    assert r["status"] == "WATCH"
    assert r["owner"] == "H"


def test_eurusd_h4_watch():
    r = check_partition("tf_probe_family", "EURUSD", "H4")
    assert r["status"] == "WATCH"


def test_unrelated_mechanism_free():
    r = check_partition("gold_scalper", "XAUUSD", "M15")
    assert r["status"] == "FREE"
    assert r["owner"] is None


def test_partition_rules_machine_checkable():
    for rule in PARTITION_RULES:
        assert {"status", "owner", "match"} <= set(rule.keys())
        assert rule["status"] in {"CLOSED", "WATCH"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_partition_registry.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

```python
# research/partition_registry.py
"""H/I scope partition for Direction I (spec §1.8, A17).

Mechanism families owned by the parallel Direction H must not be
re-commended by Direction I mining/taxonomy without structural
justification. check_partition() is consumed by P1 ingest and P2
classification.
"""
from __future__ import annotations

PARTITION_RULES: list[dict] = [
    {
        "status": "CLOSED",
        "owner": "H",
        "match": {"mechanism": {"trend_continuity", "breakout_momentum_continuity"},
                  "symbols": {"USDCAD", "USDCHF", "AUDUSD", "NZDUSD"}, "timeframes": {"H1"}},
        "note": "Direction H trial 9001 REJECTED (t=-8.2..-17.4, measured costs). No re-test.",
    },
    {
        "status": "WATCH",
        "owner": "H",
        "match": {"mechanism": {"rsi_mean_reversion", "rsi_mr"}, "symbols": {"USDCAD", "USDCHF", "AUDUSD", "NZDUSD"}, "timeframes": {"H1"}},
        "note": "Direction H trial 9002 FROZEN, in-flight. Absorb verdict as citation when resolved.",
    },
    {
        "status": "WATCH",
        "owner": "H",
        "match": {"mechanism": {"tf_probe_family", "session_breakout", "breakout"}, "symbols": {"EURUSD"}, "timeframes": {"H4"}},
        "note": "EURUSD H4 TF-probe gross Sharpe 3.46 — waits for Sub-project B Direction H decision (tier0 spec §11.3).",
    },
]


def check_partition(mechanism: str, symbol: str, timeframe: str) -> dict:
    m = mechanism.lower().replace(" ", "_")
    s = symbol.upper()
    tf = timeframe.upper()
    for rule in PARTITION_RULES:
        match = rule["match"]
        if m in match.get("mechanism", set()) and s in match.get("symbols", set()) and tf in match.get("timeframes", set()):
            return {"status": rule["status"], "owner": rule["owner"], "note": rule["note"]}
    return {"status": "FREE", "owner": None, "note": ""}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_partition_registry.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add research/partition_registry.py tests/test_partition_registry.py
git commit -m "feat(quant_os): H/I scope partition registry (Direction I A17)"
```

---

### Task 6: Screening guard supplement (`scripts/screening_guard.py`, A11)

**Files:**
- Create: `scripts/screening_guard.py`
- Test: `tests/test_screening_guard.py`

**Interfaces:**
- Consumes: `BacktestEngine`-like object with `.guard` attribute exposing `violations` (list) — per `backtest/engine.py:521-597` pattern; Tier0 Sweep C0 output is consumed at P4 wiring time (this module is the A11 supplement only)
- Produces: `assert_no_guard_violations(engine, *, config_id: str) -> None` (raises `GuardViolationError` if `engine.guard.violations` non-empty — screening run must be VOIDed by caller); `attr_scan(strategy_obj) -> list[str]` (returns mutated attribute names vs snapshot; empty = clean); `GuardViolationError(Exception)`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_screening_guard.py
import pytest

from scripts.screening_guard import GuardViolationError, assert_no_guard_violations, attr_scan


class FakeGuard:
    def __init__(self, violations):
        self.violations = violations


class FakeEngine:
    def __init__(self, violations):
        self.guard = FakeGuard(violations)


class FakeStrategy:
    def __init__(self):
        self.bars = 100


def test_no_violations_passes():
    assert_no_guard_violations(FakeEngine([]), config_id="c1")


def test_violations_raise():
    with pytest.raises(GuardViolationError, match="c1"):
        assert_no_guard_violations(FakeEngine(["leak@bar 5"]), config_id="c1")


def test_attr_scan_clean():
    s = FakeStrategy()
    before = dict(vars(s))
    assert attr_scan(s, before) == []


def test_attr_scan_detects_mutation():
    s = FakeStrategy()
    before = dict(vars(s))
    s.bars = 999
    mutated = attr_scan(s, before)
    assert "bars" in mutated
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_screening_guard.py -v`
Expected: FAIL (`ModuleNotFoundError`)

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/screening_guard.py
"""Post-run guard enforcement for Direction I screening (spec §5 P4, A11).

Supplement to Tier0 Sweep Stream C0 (reused, not re-implemented): the
screening runner MUST assert zero guard violations after every
BacktestEngine.run() — a violation voids the run (still counts N) and
triggers audit. attr_scan() snapshots strategy attributes before a run
and reports mutations after (scan_for_data_leaks()-equivalent channel).
"""
from __future__ import annotations


class GuardViolationError(RuntimeError):
    pass


def assert_no_guard_violations(engine, *, config_id: str) -> None:
    violations = list(getattr(getattr(engine, "guard", None), "violations", []) or [])
    if violations:
        raise GuardViolationError(
            f"config_id={config_id}: {len(violations)} guard violation(s) — run VOID, audit required"
        )


def attr_scan(strategy, before: dict) -> list[str]:
    after = dict(vars(strategy))
    return sorted(k for k in before if before.get(k) != after.get(k))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_screening_guard.py -v`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/screening_guard.py tests/test_screening_guard.py
git commit -m "feat(quant_os): screening guard assertion + attr-scan (Direction I A11 supplement)"
```

---

### Task 7: Closure item 1 — TSM jackknife re-run

**Files:**
- Create: `scripts/rerun_tsm_jackknife.py`
- Create: `reports/tsm_portfolio_jackknife_rerun_20260806.json` (generated)

**Interfaces:**
- Consumes: existing portfolio code used for `reports/tsm_portfolio_jackknife_20260728.json` (locate the generating script at implementation time via `git log --all -S "tsm_portfolio_jackknife"`); current D1 data files under `data/`
- Produces: `reports/tsm_portfolio_jackknife_rerun_20260806.json` with fields `{"baseline_sharpe": float, "per_asset_exclusion": {symbol: {"sharpe": float, "delta": float}}, "concerning_single_asset_dependence": [str], "verdict": "REJECT_CONFIRMED"|"REJECT_FLIPPED"|"INCONCLUSIVE", "data_sources": [str]}`

- [ ] **Step 1: Locate the original jackknife generator**

Run: `git log --all --oneline -S "concerning_single_asset_dependence" | head -5` and `git log --all --oneline -- reports/tsm_portfolio_jackknife_20260728.json`
Expected: identify the script that produced the 07-28 report

- [ ] **Step 2: Write `scripts/rerun_tsm_jackknife.py`**

Reuse the located script's portfolio + jackknife logic (leave-one-asset-out Sharpe delta), adapted to:

```python
# scripts/rerun_tsm_jackknife.py
"""Closure item 1 (spec P0): re-run TSM portfolio jackknife from current data.

Verifies the 2026-07-28 REJECT (mislabeled 2-asset artifact, dependence on
BTC_YF) still holds with data available today. Verdict REJECT_CONFIRMED
closes the ws_b residual; REJECT_FLIPPED / INCONCLUSIVE escalate to user.
"""
import json
import sys
from pathlib import Path

# TODO-REPLACE: import the portfolio/jackknife functions found in Step 1
# (see git log -S "concerning_single_asset_dependence") — reuse, do not rewrite.


def main() -> int:
    raise NotImplementedError("wired in Step 3 after locating original generator")


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 3: Wire the located generator + run**

Replace `TODO-REPLACE`/`NotImplementedError` with imports of the actual functions found in Step 1; run:

Run: `python scripts/rerun_tsm_jackknife.py`
Expected: writes `reports/tsm_portfolio_jackknife_rerun_20260806.json` with `verdict: "REJECT_CONFIRMED"` (baseline dependence on BTC_YF reproduced) — OR escalate to user if flipped/inconclusive

- [ ] **Step 4: Verify report + record**

Run: `python -c "import json; d=json.load(open('reports/tsm_portfolio_jackknife_rerun_20260806.json')); print(d['verdict'], d['concerning_single_asset_dependence'])"`
Expected: `REJECT_CONFIRMED ['BTC_YF']` (or documented escalation)

- [ ] **Step 5: Commit**

```bash
git add scripts/rerun_tsm_jackknife.py reports/tsm_portfolio_jackknife_rerun_20260806.json
git commit -m "feat(quant_os): TSM jackknife re-run closure (Direction I P0 item 1)"
```

---

### Task 8: Closure verification + P0 acceptance

**Files:**
- Create: `reports/direction_i_phase0_closure_20260806.md`

**Interfaces:**
- Consumes: all Task 1-7 outputs
- Produces: closure report — checklist state for P0 items 0-5 (spec §5 P0)

- [ ] **Step 1: Write the closure checklist test**

```python
# tests/test_direction_i_closure.py
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_closure_items_documented():
    report = (ROOT / "reports" / "direction_i_phase0_closure_20260806.md").read_text(encoding="utf-8")
    for marker in [
        "Item 0 writer-lock", "Item 1 TSM jackknife", "Item 2 C0 reuse",
        "Item 3 8001/8002 annotations", "Item 4 Direction H state",
        "Item 5 EURUSD H4 dependency",
    ]:
        assert marker in report


def test_direction_h_files_untouched():
    import subprocess
    out = subprocess.run(
        ["git", "diff", "--name-only", "7fbe921a..HEAD", "--", "research/trial_ledger_h.json"],
        capture_output=True, text=True,
    )
    assert out.stdout.strip() == "", "Direction H ledger must not be modified by Direction I work"


def test_ratchet_still_passes():
    import subprocess
    out = subprocess.run(["python", "scripts/check_trial_uniqueness.py"], capture_output=True, text=True)
    assert out.returncode == 0, out.stdout + out.stderr
```

- [ ] **Step 2: Run full test suite + closure verification**

Run: `python -m pytest tests/ -q --tb=short`
Expected: all pass (including new tests from Tasks 1-7)
Run: `python scripts/check_trial_uniqueness.py`
Expected: PASS

- [ ] **Step 3: Write `reports/direction_i_phase0_closure_20260806.md`**

Document each P0 item with evidence:
- Item 0: hook installed (Task 1) — decision recorded: pre-commit refusal for LIVE foreign locks; stale locks pass with warning
- Item 1: `tsm_portfolio_jackknife_rerun_20260806.json` verdict
- Item 2: C0 output awaited — screening_guard.py (Task 6) staged as the A11 supplement; P4 wiring blocked until C0 delivered
- Item 3: 8001/8002 annotations verified (registry_g lines cited)
- Item 4: Direction H state = 9001 REJECTED, 9002 FROZEN (citations current); git diff proves zero H-file modifications
- Item 5: EURUSD H4 pre-registration BLOCKED on Sub-project B decision (documented, not skipped)

- [ ] **Step 4: Run the closure test**

Run: `python -m pytest tests/test_direction_i_closure.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add reports/direction_i_phase0_closure_20260806.md tests/test_direction_i_closure.py
git commit -m "docs(quant_os): Direction I Phase 0 closure report + acceptance"
```

---

## Follow-on Plans (roadmap — NOT part of this plan)

| Plan | Phases | Blocks on |
|---|---|---|
| Plan 2: Mining infrastructure | P1-P3 (subagent harness, catalog schema, taxonomy, triage) | Phase 0 done (this plan) |
| Plan 3: Screening + data | P4-P5 (screening runner wiring with `screening_guard` + `screening_registry`, 23-symbol calibration) | Tier0 Sweep C0 output (guard wiring), Sub-project C1 commit (universe) |
| Plan 4: Trials + confirmation | P6-P7 (pre-registration docs, full gate harness, shadow/holdout) | Plan 3 survivors; Sub-project B decisions (EURUSD H4); Direction H 9002 verdict (watch item) |

Each follow-on plan will reference this plan's produced interfaces: `get_n_i()`, `register_config()`, `check_partition()`, `assert_no_guard_violations()`, `attr_scan()`.

## Self-Review Notes

- Spec coverage: P0 items 0-5 → Tasks 1-8 (mapped in Task 8 checklist). Spec §2 params (40/no-deadline/400h) → Task 2 test. §3 N accounting → Tasks 3-4. §1.8 partition → Task 5. §5 P0 item 2 → Task 6. Closure item 1 → Task 7. Governance tables → Task 2. No spec section left without a task within Phase 0 scope.
- Placeholder scan: the ONLY deliberate placeholder is Task 7 Step 2's `TODO-REPLACE` marker, which Step 1 resolves by locating the actual generator before wiring (git-log instruction included). All other code blocks are complete.
- Type consistency: `get_n_i(screening_log_path, trial_ledger_path, baseline)` (Task 3) matches `register_config(log_path, mechanism, symbol, timeframe, params, data_range, status)` (Task 4) — both consume `screening_log_i.json` schema from Task 2; `check_partition(mechanism, symbol, timeframe)` (Task 5) matches P2 consumption signature; `assert_no_guard_violations(engine, config_id)` (Task 6) matches P4 wiring signature.
