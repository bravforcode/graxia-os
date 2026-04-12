# Obsidian Brain System — Design Spec

**Date:** 2026-04-13  
**Status:** Approved  
**Goal:** Replace manual context management with an autonomous system that captures, learns, and injects context — zero extra quota except when the user explicitly runs `/learn`.

---

## Requirements

| Requirement | Detail |
| --- | --- |
| Context persistence | Auto-save project state, decisions, work progress to Obsidian |
| Self-learning | Extract coding patterns + decisions from sessions automatically |
| On-demand patterns | Top-5 relevant patterns auto-injected at session start |
| Learning cadence | Auto (compact) + Manual (`/learn`) |
| Quota constraint | Zero extra API calls from hooks. `/learn` uses current turn only |
| Skills integration | On-Demand Skills (`/use`) already built — patterns can reference skills |

---

## Architecture

Three layers, all zero-quota except manual `/learn`:

```
LAYER 1: CAPTURE
  Stop hook ──────────► delta JSON  (files, commands, errors, last task)
  PostCompact hook ────► session summary .md + keyword pattern extract

LAYER 2: OBSIDIAN KNOWLEDGE GRAPH
  brain/patterns.json          scored + ranked patterns
  brain/latest.md              lean context (existing, enhanced)
  projects/{name}/context.md   rich project state
  projects/{name}/decisions.md why we chose X over Y
  projects/{name}/work-log.md  TODO / IN_PROGRESS / DONE / BLOCKED
  projects/{name}/sessions/    compact summaries per date
  projects/{name}/delta/       structured tool logs per turn

LAYER 3: INJECT
  SessionStart ────► Python ranks patterns → top-5 → inject latest.md
  On-Demand ──────► /use-pattern <name> for archived patterns
```

---

## Data Schema

### `brain/patterns.json`

```json
{
  "version": 1,
  "patterns": [
    {
      "id": "pat_001",
      "text": "Human-readable actionable pattern",
      "project": "brav-os",
      "scope": "project | global",
      "confidence": 0.92,
      "seen_count": 14,
      "last_seen": "2026-04-13",
      "source_sessions": ["2026-04-10"],
      "linked_decision": "decisions.md#anchor",
      "tags": ["python", "db", "async"],
      "status": "CANDIDATE | ACTIVE | CORE | GLOBAL | ARCHIVED"
    }
  ]
}
```

**Confidence lifecycle:**

| Status | Confidence | Trigger |
| --- | --- | --- |
| CANDIDATE | 0.3 | First seen |
| ACTIVE | 0.6+ | seen_count ≥ 5 |
| CORE | 0.9+ | seen_count ≥ 15, no conflicts |
| GLOBAL | any | Appears in 2+ projects |
| ARCHIVED | any | Not seen for 60 days |

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

Skip delta write if: no tool calls, session < 30s, or identical to previous delta.

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

## Hook Pipeline

### Stop Hook — `~/.claude/hooks/stop-context-saver.py`

```
trigger:  every Claude response end
quota:    ZERO
async:    true (non-blocking)
timeout:  10s

algorithm:
  1. Read ~/.claude/history.jsonl (last 20 entries for session)
  2. Parse tool calls:
       Write/Edit → files_modified
       Bash       → commands_run
       PostToolUseFailure → errors_resolved
  3. Detect last_task from most recent user message
  4. Write delta JSON → Obsidian/projects/{project}/delta/{ts}.json
  5. Update work-log.md:
       - detect DONE: "✓", "done", "fixed", "merged" in last message
       - detect BLOCKED: "waiting", "blocked", "depends on"
       - update IN_PROGRESS with last_task if new
```

### PostCompact Hook — `~/.claude/hooks/postcompact-saver.py`

```
trigger:  after Claude Code auto-compact
quota:    ZERO
async:    true
timeout:  15s

algorithm:
  1. Read compact_summary from stdin JSON
  2. Save → Obsidian/projects/{project}/sessions/{date}.md (append if exists)
  3. Keyword-extract pattern candidates:
       Positive: "ใช้ X", "use X", "always X", "X is required"
       Negative: "อย่าใช้ Y", "don't use Y", "never Y", "avoid Y"
       Sequence: "ต้องทำ Z ก่อน", "Z before", "first Z then"
       File pattern: file modified in > 30% of recent deltas
  4. Update patterns.json:
       - new candidate → confidence 0.3
       - existing match → confidence += 0.1
       - contradiction → confidence -= 0.2, flag in decisions.md
  5. Update context.md (2-3 lines: what was done, current state)
  6. Cross-project check: if pattern in 2+ projects → promote scope to "global"
```

### SessionStart Injector — `~/.claude/hooks/session-start-injector.py`

```
trigger:  session start (replaces/enhances current brain preflight)
quota:    ZERO
timeout:  5s

algorithm:
  1. Read patterns.json
  2. Detect current project from CWD
  3. Score each ACTIVE/CORE pattern:
       score = confidence × recency_factor × tag_match(project_files)
       recency_factor = 1.0 if last_seen < 7 days, 0.7 if < 30 days, 0.4 else
  4. Take top-5 by score
  5. Read work-log.md (IN_PROGRESS section only)
  6. Write "Auto-injected context" section in brain/latest.md:
       ## Auto-injected (updated {date})
       ### Top patterns
       1. {pattern text} (confidence: {score:.0%})
       ...
       ### In progress
       - {task}
```

### Settings Registration

```json
"Stop": [{
  "hooks": [{
    "type": "command",
    "command": "python3 C:/Users/menum/.claude/hooks/stop-context-saver.py",
    "async": true,
    "timeout": 10
  }]
}],
"PostCompact": [{
  "hooks": [{
    "type": "command",
    "command": "python3 C:/Users/menum/.claude/hooks/postcompact-saver.py",
    "async": true,
    "timeout": 15
  }]
}]
```

SessionStart: replace `brain preflight` command with `session-start-injector.py` (runs `brain preflight` internally as well).

---

## Learning Loop

### Auto-Learning (Zero Quota)

Runs inside `postcompact-saver.py`. Rule-based keyword extraction only. Updates `patterns.json` scores. No semantic understanding — pure frequency + keyword matching.

### Manual `/learn` (Current Turn Only)

```
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

```
CANDIDATE (0.3) ──seen×5──► ACTIVE (0.6) ──seen×15──► CORE (0.9)
    │                                                       │
    │                                          appears in 2+ projects
    │                                                       ▼
    │                                                   GLOBAL
    │
    └── not seen 60 days → ARCHIVED (kept, not injected)
```

---

## On-Demand Integration

```
Archived pattern requested → /use-pattern <name> reads from patterns.json
Archived skill needed → /use <skill-name> reads from commands/archive/
Auto-detect: Claude sees .dart file → loads flutter-tagged patterns + /use flutter-review
```

Both systems share the same auto-detect rules in `~/.claude/CLAUDE.md`.

---

## Obsidian Vault Structure

```
Second Brain/
  brain/
    latest.md              existing + "Auto-injected" section added
    patterns.json          NEW — machine-readable pattern store
    learn-log.md           NEW — human-readable learning history
    skills-catalog.md      existing
  projects/
    brav-os/
      context.md           NEW — rich project state (auto-updated)
      decisions.md         NEW — decision log with wikilinks
      work-log.md          NEW — state machine (TODO/IN/DONE/BLOCKED)
      sessions/            NEW — compact summaries
      delta/               NEW — structured tool logs
```

---

## Implementation Phases

**Phase 1 — Foundation (hooks + vault structure)**
- Create vault folders
- Write `stop-context-saver.py`
- Write `postcompact-saver.py`
- Write `session-start-injector.py`
- Register hooks in settings.json
- Initialize `patterns.json` (empty, version 1)

**Phase 2 — Learning Loop**
- Add keyword extractor to postcompact-saver
- Add pattern scorer/ranker to session-start-injector
- Update `/learn` command to read from Obsidian and write back

**Phase 3 — On-Demand Integration**
- Add tag-based archived pattern detection to CLAUDE.md rules
- Connect `/use-pattern` to patterns.json lookups
- Cross-project promotion logic

---

## Out of Scope

- LLM calls from any hook (hard constraint)
- Real-time summarization of every turn (only on compact or manual)
- Semantic vector similarity (keyword matching only for zero-quota)
- GUI for Obsidian pattern management (Obsidian itself handles this)
