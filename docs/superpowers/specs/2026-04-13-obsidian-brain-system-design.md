# Obsidian Brain System v2 — Comprehensive Design Spec

**Date:** 2026-04-13
**Status:** Draft v2
**Goal:** Autonomous context persistence + self-learning system for Claude Code sessions —
zero extra quota from hooks; `/learn` uses only the current conversation turn.

---

## v1 Analysis

### Critical Bugs

- Stop hook reads `~/.claude/history.jsonl` — **not exposed to hooks**. Use `transcript_path` from stdin JSON.
- PostCompact refers to field `summary` in prose — correct field is `compact_summary`.
- SessionStart spec proposes agent-type hook for injection — **only `type: "command"` is valid for SessionStart**.
- Settings snippets show bare event keys without `"hooks": {}` wrapper nesting.

### Design Flaws

- No shared library → hooks duplicate file-locking and JSON-write logic.
- SessionStart injector writes only to `latest.md` — if brain preflight runs first and reads before injector writes, patterns are missed in that session. Must also send `additionalContext` via stdout.
- `async: true` used on all hooks without noting it removes the ability to return `continue: false`.

### Gaps

- No `brain-config.json` → vault path and thresholds are hardcoded in every script.
- No migration path for patterns.json v1 → v2 schema.
- Slash commands described as CLAUDE.md prose — they must be skill or command `.md` files.
- No security: secrets and tokens could appear in delta JSON from Bash tool calls.
- No concurrency contract for two sessions writing `patterns.json` simultaneously.
- No test plan.

---

## Architecture

Five layers, all zero-quota except manual `/learn`.

```text
L1 — Configuration   brain-config.json         single source of truth
L2 — Shared Library  brain_lib.py              file lock, atomic write, schema validate
L3 — Hooks           3 command scripts         Stop · PostCompact · SessionStart
L4 — Obsidian Vault  knowledge graph           patterns, sessions, decisions, work-log
L5 — Skills          5 slash-command files     /learn · /brain-status · /decide · /use-pattern · /brain-forget
```

### L1 — Configuration: `brain-config.json`

Single source of truth. Read by all hooks and skill scripts.
Location: `C:/Users/menum/.claude/hooks/brain-config.json`

### L2 — Shared Library: `brain_lib.py`

Imported by all hooks. Provides: config loader, file lock, atomic JSON write,
schema validate, pattern factory, health recorder, project resolver.
Location: `C:/Users/menum/.claude/hooks/brain_lib.py`

### L3 — Hooks (3 scripts)

- `stop-context-saver.py` — Stop event
- `postcompact-saver.py` — PostCompact event
- `session-start-injector.py` — SessionStart event

Location: `C:/Users/menum/.claude/hooks/`

### L4 — Obsidian Vault

Persistent knowledge graph. Paths under:
`C:/Users/menum/Documents/ObsidianVault/Second Brain/`

### L5 — Slash-Command Skills (5 files)

Location: `C:/Users/menum/.claude/skills/{name}/SKILL.md`
Skills: `learn` · `brain-status` · `decide` · `use-pattern` · `brain-forget`

---

## Configuration

File: `C:/Users/menum/.claude/hooks/brain-config.json`

```json
{
  "vault_path": "C:/Users/menum/Documents/ObsidianVault/Second Brain",
  "hooks_path": "C:/Users/menum/.claude/hooks",
  "project_overrides": {
    "brav os": "brav-os"
  },
  "retention": {
    "delta_days": 90,
    "sessions_days": 180
  },
  "injection": {
    "top_n_patterns": 5
  },
  "extraction": {
    "min_delta_calls": 2,
    "file_frequency_threshold": 0.30
  },
  "decay": {
    "interval_days": 30,
    "factor": 0.9,
    "archive_after_days": 60
  },
  "features": {
    "stop_hook": true,
    "postcompact_hook": true,
    "session_injector": true
  }
}
```

All scripts call `brain_lib.load_config()` — never hardcode vault path.

---

## Shared Library Contract: `brain_lib.py`

```python
# Public API — implementations kept in the script, not in this spec

def load_config() -> dict: ...
# Reads brain-config.json. Raises on missing file.

def resolve_project(cwd: str, config: dict) -> str: ...
# Maps CWD basename to slug using project_overrides, then kebab-case.

def lock_file(path: str): ...
# Context manager. Uses fcntl.flock on POSIX, msvcrt.locking on Windows.
# Lock file: path + ".lock", not the resource file itself.

def atomic_write_json(path: str, data: dict, schema: dict | None = None) -> None: ...
# 1. Validate data against schema (if provided).
# 2. Write to path + ".tmp" in same directory.
# 3. Backup existing to path + ".bak".
# 4. os.replace(tmp -> path).
# Must be called inside lock_file context.

def make_pattern(text: str, project: str, tags: list[str]) -> dict: ...
# Returns a valid v2 pattern dict with all required fields at default values.
# Avoids mutable-default-argument bugs.

def record_health(hook_name: str, status: str, msg: str = "") -> None: ...
# Appends one line to brain/health.log. Never raises.

def read_patterns(vault_path: str) -> dict: ...
def write_patterns(vault_path: str, data: dict) -> None: ...
# write_patterns calls atomic_write_json inside lock_file.
```

The library is a plain `.py` file, no third-party dependencies.

---

## Hook Specifications

### Stop Hook — `stop-context-saver.py`

**Event:** `Stop`
**Registration:** async command hook, timeout 10s
**Quota:** ZERO

**Stdin JSON (from Claude Code):**

```json
{
  "session_id": "...",
  "transcript_path": "/abs/path/to/session.jsonl",
  "stop_hook_active": false,
  "stop_reason": "end_turn"
}
```

**Transcript JSONL format:**
Each line is a JSON object with at minimum: `type`, `timestamp`, `cwd`, `sessionId`.
Tool calls are in `message.content[]` blocks where `type == "tool_use"`.
Tool results are in user-turn entries containing `toolUseResult`.
Do NOT assume top-level `role` or `name` fields.

**Algorithm:**

```text
1. Parse stdin defensively — exit 0 on any error
2. Skip if stop_hook_active is true (already in a stop hook)
3. Read transcript_path (last 40 lines)
4. Extract from tool_use blocks:
     Write/Edit  → files_modified (basename only, redact .env / secrets)
     Bash        → commands_run   (redact tokens, API keys, passwords)
     Failure     → errors_resolved (type + brief message)
5. Extract last_task from last user message text (first 120 chars)
6. Skip if: no tool_use blocks found, OR identical to last delta
7. Resolve project from cwd
8. atomic_write_json → vault/projects/{project}/delta/{ts}.json
9. Update work-log.md:
     DONE signal:    "done", "fixed", "merged", "✓", "เสร็จ" in user text
     BLOCKED signal: "blocked", "waiting", "รอ", "depends on"
     Only update IN_PROGRESS if last_task differs from current top entry
10. record_health("stop", "ok")
```

**Redaction rules:**

- Commands containing `KEY`, `TOKEN`, `SECRET`, `PASSWORD` → replace value with `[REDACTED]`
- File paths containing `.env` → skip entirely
- `.pem`, `.key`, `.p12` extensions → skip

---

### PostCompact Hook — `postcompact-saver.py`

**Event:** `PostCompact`
**Registration:** async command hook, timeout 15s
**Quota:** ZERO

**Stdin JSON:**

```json
{
  "session_id": "...",
  "trigger": "auto | manual",
  "compact_summary": "Full text of what Claude Code summarized..."
}
```

**Algorithm:**

```text
1. Parse stdin — exit 0 on error
2. Extract compact_summary — exit 0 if empty
3. Resolve project from env CWD
4. Append to vault/projects/{project}/sessions/{date}.md
5. Update vault/projects/{project}/context.md (3 lines: what was done, current state, next)
6. Extract pattern candidates from compact_summary:
     Positive regex:  r"(?:ใช้|use|always|is required)\s+(?P<subject>[^.\n]{4,60})"
     Negative regex:  r"(?:อย่าใช้|don't use|never|avoid)\s+(?P<subject>[^.\n]{4,60})"
     Sequence regex:  r"(?:ก่อน|before|first)\s+(?P<subject>[^.\n]{4,60})"
7. For each candidate:
     Dedup: token overlap Jaccard >= 0.6 with existing → merge, not add
     Conflict: same subject, opposite polarity → set conflict_ids, lower confidence
     New: add via make_pattern(), confidence 0.3
     Existing match: confidence = min(0.99, confidence + 0.1)
8. Cross-project promotion:
     If same pattern text found in 2+ project scopes → set scope = "global"
9. Prune old files:
     delta/ older than retention.delta_days
     sessions/ older than retention.sessions_days
10. write_patterns(vault_path, updated_data)
11. record_health("postcompact", "ok")
```

---

### SessionStart Hook — `session-start-injector.py`

**Event:** `SessionStart`
**Registration:** command hook (NOT agent, NOT async — must write stdout before session opens)
**Quota:** ZERO
**Constraint:** SessionStart only supports `type: "command"`. No async flag, no agent type.

**Stdin JSON:**

```json
{
  "session_id": "...",
  "cwd": "C:/brav os",
  "source": "startup | resume | clear | compact"
}
```

**Output — JSON to stdout:**

```json
{
  "hookSpecificOutput": {
    "hookEventName": "SessionStart",
    "additionalContext": "...injected text..."
  }
}
```

**Algorithm:**

```text
1. Parse stdin — on error, exit 0 with empty stdout (never block session)
2. Resolve project from cwd
3. Apply decay to patterns.json inside lock_file:
     For each pattern where (today - last_seen).days >= decay.interval_days:
       confidence *= decay.factor
       if (today - last_seen).days > archive_after_days → status = "ARCHIVED"
4. Score ACTIVE + CORE patterns:
     score = confidence
           * (1.0 if last_seen < 7d else 0.7 if < 30d else 0.4)
           * (1.3 if project matches else 1.0 if scope == "global" else 0.0)
           * (1.0 + 0.1 * len(tag_intersection(pattern.tags, project_file_extensions)))
5. Filter: status not ARCHIVED, score > 0
6. Take top N by score (N from config injection.top_n_patterns)
7. Read IN_PROGRESS section from work-log.md
8. Format context string:
     "## Auto-context ({date})\n### Patterns\n{numbered list}\n### In progress\n{tasks}"
9. Write same string to latest.md "## Auto-injected" section (for persistence)
10. Print JSON with additionalContext to stdout
11. record_health("session_start", "ok")
```

**Why both stdout and latest.md:** stdout injects into the session immediately;
latest.md persists so the brain-updater agent hook can read it on subsequent turns.

---

### Settings Registration

Add to `C:/Users/menum/.claude/settings.json` under `"hooks"` key:

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python C:/Users/menum/.claude/hooks/stop-context-saver.py",
            "async": true,
            "timeout": 10
          }
        ]
      }
    ],
    "PostCompact": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python C:/Users/menum/.claude/hooks/postcompact-saver.py",
            "async": true,
            "timeout": 15
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "node C:/Users/menum/.claude/hooks/gsd-check-update.js"
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "brain preflight --project-root \"$CWD\""
          }
        ]
      },
      {
        "hooks": [
          {
            "type": "command",
            "command": "python C:/Users/menum/.claude/hooks/session-start-injector.py"
          }
        ]
      },
      {
        "matcher": "brain-updater",
        "hooks": [
          {
            "type": "agent",
            "prompt": "...(existing brain-updater prompt unchanged)...",
            "timeout": 30,
            "model": "claude-haiku-4-5-20251001",
            "statusMessage": "Syncing Obsidian brain..."
          }
        ]
      }
    ]
  }
}
```

**Notes:**

- `async: true` only on `Stop` and `PostCompact` — async hooks cannot return `continue: false`.
- `SessionStart` injector must be synchronous to deliver `additionalContext` before the session opens.
- Use `python` (not `python3`) on Windows.
- Add `"shell": "powershell"` if bash is unavailable.

---

## Slash-Command Skills

Each command is a `SKILL.md` file under `C:/Users/menum/.claude/skills/{name}/SKILL.md`.
Legacy `~/.claude/commands/{name}.md` also works but skill format is preferred.

### /learn

Reads `brain/patterns.json`, `projects/{name}/sessions/*.md` (last 30 days),
`projects/{name}/delta/*.json` (last 30 days). Deduplicates semantically,
assigns confidence, flags conflicts, writes back `patterns.json` and `brain/learn-log.md`.
Reports: N updated, M merged, K new, J archived. Uses current turn only — no extra API calls.

### /brain-status

Reads `patterns.json`, `work-log.md`, `context.md`, `brain/health.log`.
Outputs dashboard: pattern counts by status, recent delta activity, IN_PROGRESS tasks,
last hook run timestamps from health.log.

### /decide

Arguments: `<decision text> [#anchor]`
Appends to `projects/{name}/decisions.md` with date, wikilink to current session.
Links any matching ACTIVE pattern in `patterns.json` via `linked_decision`.

### /use-pattern

Arguments: `<id or keyword>`
Looks up pattern in `patterns.json` (including ARCHIVED).
Prints the pattern text and injects it into the current conversation as context.
Does not change status — ARCHIVED patterns stay archived.

### /brain-forget

Arguments: `<id or keyword>`
Sets pattern status to ARCHIVED, adds `archived_reason: "manual"`.
Reports what was archived.

---

## Data Schema

### `brain/patterns.json` v2

```json
{
  "version": 2,
  "patterns": [
    {
      "id": "pat_001",
      "text": "Short actionable pattern statement",
      "project": "brav-os",
      "scope": "project | global",
      "confidence": 0.72,
      "seen_count": 8,
      "last_seen": "2026-04-13",
      "source_sessions": ["2026-04-10", "2026-04-12"],
      "linked_decision": "decisions.md#sqlalchemy-async",
      "tags": ["python", "db", "async"],
      "status": "ACTIVE",
      "conflict_ids": [],
      "archived_reason": null
    }
  ]
}
```

**Changes from v1:** added `conflict_ids` and `archived_reason` fields.

**Confidence lifecycle:**

| Status | Confidence | Trigger |
| --- | --- | --- |
| CANDIDATE | 0.3 | First seen |
| ACTIVE | 0.6+ | seen_count >= 5 |
| CORE | 0.9+ | seen_count >= 15, no conflicts |
| GLOBAL | any | Appears in 2+ projects |
| ARCHIVED | any | Not seen for 60 days, or manual |

Decay: `confidence × 0.9` per 30 days of no activity.

### `projects/{name}/delta/{timestamp}.json`

```json
{
  "ts": "2026-04-13T14:30:00",
  "project": "brav-os",
  "files_modified": ["backend/app/api/cognitive.py"],
  "commands_run": ["python -m pytest tests/ -q"],
  "errors_resolved": ["ModuleNotFoundError: llm.py line 42"],
  "last_task": "add approval gate for COG evolution"
}
```

Skip delta write if: no tool_use blocks in transcript, session < 30s, or identical to previous delta.

### `projects/{name}/work-log.md`

```markdown
## IN_PROGRESS
- [ ] task name (branch: feat/xyz)

## DONE (last 5)
- [x] task — date

## BLOCKED
- [ ] task — reason
```

### `projects/{name}/decisions.md`

```markdown
## #{anchor} — {date}
Decision text. Why we chose X.
Alternatives considered: Y, Z
[[sessions/{date}]] · tags: tag1, tag2
```

---

## Learning Loop

### Auto-Learning (PostCompact, Zero Quota)

Runs inside `postcompact-saver.py`. Rule-based keyword extraction only. Updates `patterns.json`
scores. No semantic understanding — pure frequency + keyword matching.

Triggers: auto-compact and manual `/compact`.

### Manual `/learn` (Current Turn Only)

```text
User runs: /learn

Claude:
  1. Read brain/patterns.json (current state)
  2. Read projects/{name}/sessions/*.md (last 30 days)
  3. Read projects/{name}/delta/*.json (last 30 days)
  4. Identify patterns: short, actionable, specific
  5. Deduplicate: merge semantically identical patterns
  6. Assign confidence scores based on frequency + recency
  7. Flag conflicts → add note to decisions.md
  8. Write back:
       brain/patterns.json (machine-readable, updated)
       brain/learn-log.md (human-readable summary of what changed)
  9. Report: N patterns updated, M merged, K new, J archived
```

### Pattern Lifecycle

```text
CANDIDATE (0.3) ──seen×5──► ACTIVE (0.6) ──seen×15──► CORE (0.9)
    │                                                       │
    │                                          appears in 2+ projects
    │                                                       ▼
    │                                                   GLOBAL
    │
    └── not seen 60 days → ARCHIVED (kept, not injected)
        manual /brain-forget → ARCHIVED (archived_reason: "manual")
```

---

## On-Demand Integration

```text
Archived pattern requested → /use-pattern <id|keyword> reads from patterns.json
Archived skill needed      → /use <skill-name> reads from commands/archive/
Auto-detect: Claude sees .dart file → loads flutter-tagged patterns + /use flutter-review
```

Both systems share the same auto-detect rules in `~/.claude/CLAUDE.md`.

---

## Obsidian Vault Structure

```text
C:/Users/menum/Documents/ObsidianVault/Second Brain/
  brain/
    latest.md              existing + "## Auto-injected" section added by injector
    patterns.json          machine-readable pattern store (v2)
    learn-log.md           human-readable learning history
    health.log             hook run timestamps + status
    skills-catalog.md      existing
  projects/
    brav-os/
      context.md           rich project state (auto-updated by PostCompact)
      decisions.md         decision log with wikilinks
      work-log.md          state machine (TODO / IN_PROGRESS / DONE / BLOCKED)
      sessions/            compact summaries per date
      delta/               structured tool logs per turn
```

---

## Migration: v1 → v2

Run once before deploying Phase 1 hooks:

1. Back up `brain/patterns.json` → `brain/patterns.json.bak`
2. Read file; if `version == 1`, add `conflict_ids: []` and `archived_reason: null` to each pattern
3. Set `version: 2`
4. Write back with `atomic_write_json`
5. Create missing vault folders: `brain/`, `projects/brav-os/sessions/`, `projects/brav-os/delta/`
6. Initialize `brain/health.log` (empty file)
7. Do NOT delete or rename existing `latest.md`, `decisions.md`, or `work-log.md`

The migration can be run as a one-time CLI script: `python brain_lib.py --migrate`

---

## Implementation Phases

### Phase 1 — Foundation (hooks + vault structure)

- Create vault folders
- Write `brain-config.json`
- Write `brain_lib.py` (shared library)
- Write `stop-context-saver.py`
- Write `postcompact-saver.py`
- Write `session-start-injector.py`
- Register Stop + PostCompact + SessionStart hooks in settings.json
- Initialize `patterns.json` v2 (empty, version 2)
- Run migration script if v1 patterns.json exists

### Phase 2 — Learning Loop

- Add keyword extractor to `postcompact-saver`
- Add pattern scorer/ranker to `session-start-injector`
- Update `/learn` skill to read from Obsidian and write back

### Phase 3 — On-Demand Integration

- Create 5 slash-command skill files (`learn`, `brain-status`, `decide`, `use-pattern`, `brain-forget`)
- Add tag-based archived pattern detection to CLAUDE.md rules
- Connect `/use-pattern` to patterns.json lookups
- Cross-project promotion logic

---

## Verification Checklist

Run these checks after updating the spec file to confirm v1 bugs are gone:

```bash
# 1. No reference to history.jsonl
rg "history\.jsonl" docs/superpowers/specs/2026-04-13-obsidian-brain-system-design.md
# expect: no output

# 2. SessionStart section must not claim agent hooks are supported for injection
rg "agent.*SessionStart|SessionStart.*agent" docs/superpowers/specs/2026-04-13-obsidian-brain-system-design.md
# expect: no output

# 3. PostCompact must use compact_summary
rg "compact_summary" docs/superpowers/specs/2026-04-13-obsidian-brain-system-design.md
# expect: at least 2 matches

# 4. Vault path must include ObsidianVault/Second Brain
rg "ObsidianVault/Second Brain" docs/superpowers/specs/2026-04-13-obsidian-brain-system-design.md
# expect: at least 3 matches

# 5. Slash commands described as skill files, not only CLAUDE.md prose
rg "SKILL\.md" docs/superpowers/specs/2026-04-13-obsidian-brain-system-design.md
# expect: at least 1 match
```

---

## Test Matrix

### Unit Tests (`brain_lib.py`)

- `test_resolve_project`: cwd with spaces, override mapping
- `test_atomic_write_json`: temp file cleanup on failure, backup creation
- `test_lock_file`: Windows (msvcrt) and POSIX (fcntl) paths compile
- `test_schema_validate`: invalid pattern rejected before write
- `test_make_pattern`: no shared mutable state between calls
- `test_record_health`: never raises on any input

### Integration Tests (per hook)

- Stop: feed sample transcript JSONL with Write/Edit/Bash tool_use entries; assert delta JSON written
- PostCompact: feed `{"compact_summary": "...", "trigger": "auto"}`; assert sessions file appended, patterns updated
- SessionStart: feed `{"cwd": "C:/brav os", "source": "startup"}`; assert stdout is valid JSON with `additionalContext`

### Concurrency Test

- Two Python processes write `patterns.json` simultaneously; assert no corruption and both patterns present

### Windows-Specific Tests

- Path with spaces: `C:/brav os` resolves correctly
- Vault path with `ObsidianVault/Second Brain` (space in name) resolves correctly
- `python` (not `python3`) is callable

---

## Out of Scope

- LLM calls from any hook (hard constraint — zero quota)
- Real-time summarization of every turn (only on compact or manual `/learn`)
- Semantic vector similarity (keyword matching only for zero-quota)
- GUI for Obsidian pattern management (Obsidian itself handles this)
