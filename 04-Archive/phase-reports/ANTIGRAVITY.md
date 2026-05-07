# Antigravity Instructions

Use the local Obsidian skills hub when the user asks for a skill or the task clearly matches one:

`C:\Users\menum\OneDrive\Documents\Gracia\Second Brain\brain\skills-universal`

Skill routing policy:

1. Read `skills-router.md` first.
2. Search `skills-registry-compact.json`.
3. Load only the chosen `<skill-id>\SKILL.md` files.
4. Use 1 skill by default and no more than 3 unless explicitly requested.
5. Prefer this repo's live code, tests, `AGENTS.md`, and `CLAUDE.md` over generic skill guidance.

No daemon is needed. Skills are available through the local filesystem links:

- `skills\`
- `.vscode\skills\`
- `.claude\skills-universal\`

Important boundary: this works only when Antigravity has filesystem access to this workspace and the Obsidian hub path.
