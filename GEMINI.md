# Gemini CLI Instructions

Use the local Obsidian skills hub when the user asks for a skill or the task clearly matches one:

`C:\Users\menum\Documents\ObsidianVault\Second Brain\brain\skills-universal`

Skill routing policy:

1. Read `skills-router.md` first.
2. Search `skills-registry-compact.json`.
3. Load only the chosen `<skill-id>\SKILL.md` files.
4. Use 1 skill by default and no more than 3 unless explicitly requested.
5. Follow repo code, tests, `AGENTS.md`, and `CLAUDE.md` when they conflict with generic skill guidance.

No background script, API server, or watcher is required. This is a local filesystem hub.

Important boundary: Gemini web cannot read local Obsidian files by itself. Gemini CLI can use this when it has filesystem access to this workspace and the hub path.
