# Universal Skills Gateway

The cross-AI skills system is now file-based and centered in Obsidian:

`C:\Users\menum\Documents\ObsidianVault\Second Brain\brain\skills-universal`

Generated hub files:

- `skills-router.md` - small routing guide agents should read first
- `skills-registry-compact.json` - token-cheap skill lookup
- `skills-registry.json` - full metadata and aliases
- `<skill-id>\SKILL.md` - actual skill instructions
- `claude-ai-custom-instructions.md` - text for web Claude when no local-file connector exists

## How Agents Should Use It

Agents should not load every skill.

1. Read `skills-router.md`.
2. Search `skills-registry-compact.json`.
3. Select the smallest useful set of skills, usually 1.
4. Load only the selected `<skill-id>\SKILL.md` files.
5. Use no more than 3 skill files unless the user explicitly asks.

This keeps token cost low while still making every indexed skill discoverable.

## Local Bridges

The hub is linked into the local AI surfaces:

- Workspace: `skills\`
- VS Code: `.vscode\skills\`
- Claude project bridge: `.claude\skills-universal\`
- Claude home bridge: `%USERPROFILE%\.claude\skills-all`
- Codex bridge skill: `%USERPROFILE%\.codex\skills\gracia-universal-skills\SKILL.md`
- Copilot instructions: `.github\copilot-instructions.md`
- Agent instructions: `AGENTS.md`
- Claude Code instructions: `CLAUDE.md` and `.instructions.md`

No API server, daemon, watcher, or continuously running script is required.

## Important Boundary

Local agents with filesystem access can read the hub directly.

Web-only AI products such as Claude.ai or Gemini cannot automatically read local Obsidian files unless they have a local-file connector or the relevant skill content is provided in the chat. For those tools, use:

`C:\Users\menum\Documents\ObsidianVault\Second Brain\brain\skills-universal\claude-ai-custom-instructions.md`

## Maintenance

Reindex only when skills are added or removed from the source folders:

```powershell
python scripts\consolidate_all_skills.py
python scripts\verify_skills_hub.py
```

Daily use does not require these commands.
