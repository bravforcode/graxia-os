# Codex Agent Context

## Brain Context

At the start of any complex session, read:

`C:\Users\menum\Documents\ObsidianVault\Second Brain\brain\latest.md`

Read this once per session only. Do not crawl the vault unless the user asks for a specific vault task.

## Universal Skills Hub

The local cross-AI skills source of truth is:

`C:\Users\menum\Documents\ObsidianVault\Second Brain\brain\skills-universal`

Use this hub when the user asks to use a skill or when a task clearly matches a skill.

Token policy:

1. Read `skills-router.md` first.
2. Search `skills-registry-compact.json` for candidates.
3. Load only the selected `<skill-id>\SKILL.md` files.
4. Use 1 skill by default and no more than 3 unless the user explicitly asks.
5. Never load the full hub or paste the full registry into the conversation.

No background script, API server, watcher, or daemon is required. The hub is connected through local filesystem links:

- `skills\`
- `.vscode\skills\`
- `.claude\skills-universal\`
- `%USERPROFILE%\.claude\skills-all`
- `%USERPROFILE%\.codex\skills\gracia-universal-skills\SKILL.md`

Hard limit: web-only AI products cannot read local Obsidian files unless they have a local-file connector or the user provides the relevant file text. Do not claim Claude.ai, Gemini, or Copilot web can automatically read local files without that access.

## Rules

- Trust internal code and framework guarantees; validate at system boundaries.
- No trailing summaries.
- No emojis unless asked.
- No mock DB in tests; use the real DB.
- Frontend dev server: port 5173, not 3000.
- Preserve user changes in the worktree. Do not revert unrelated edits.

## Stack

FastAPI + SQLAlchemy async, React/TS/Vite/Bun, PostgreSQL/Supabase, Redis/Celery, n8n, Telegram Bot.

## Trusted Projects

- `C:\brav os` - AI outreach/CRM system
- `C:\vibecity.live`
- `C:\TaskAm-main`
