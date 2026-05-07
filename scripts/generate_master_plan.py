import os
import re

GRAXIA_DIR = r"C:\Users\menum\graxia os"
OBSIDIAN_DIR = r"C:\Users\menum\Documents\ObsidianVault\Second Brain"
PLAN_FILE = os.path.join(GRAXIA_DIR, "docs", "superpowers", "plans", "2026-05-06-master-cleanup-plan.md")

os.makedirs(os.path.dirname(PLAN_FILE), exist_ok=True)

lines = []
lines.append("# Graxia OS & Obsidian Master Cleanup Plan")
lines.append("> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.\n")
lines.append("**Goal:** Enterprise-grade cleanup, removing all dead code, fixing specific UI/Scraping bugs, and hardening production. No fake data.")
lines.append("**Architecture:** Multi-agent orchestration, FastAPI, React, Supabase.")
lines.append("**Tech Stack:** Python, TypeScript, Redis, PostgreSQL.\n")
lines.append("---\n")

# Phase 1
lines.append("## Phase 1: High-Priority User Directives (From Root Notes)\n")

lines.append("### Task 1: UI Asset Button & LINE URL Shortener")
lines.append("**Files:**")
lines.append("- Modify: `frontend/src/pages/assets/index.tsx` (Asset UI Page)")
lines.append("- Modify: `backend/app/agents/social/line_agent.py`")
lines.append("\n- [ ] **Step 1: Clone UI for Asset Button**")
lines.append("```tsx\n// Implement exact clone code based on target page to make the status button clickable\n```")
lines.append("- [ ] **Step 2: LINE URL Shortening**")
lines.append("```python\n# Shorten URL before sending to LINE to avoid long links\n```")
lines.append("- [ ] **Step 3: Commit**\n```bash\ngit add .\ngit commit -m \"fix(ui): asset button and line url shortener\"\n```\n")

lines.append("### Task 2: Facebook Scraping Optimization (10 Groups & Strict Filters)")
lines.append("**Files:**")
lines.append("- Modify: `backend/app/agents/social/facebook_agent.py`")
lines.append("\n- [ ] **Step 1: Limit to 10 Target Groups**")
lines.append("```python\nTARGET_GROUPS = [\n  'https://www.facebook.com/share/g/1LVFMct7hR/',\n  'https://www.facebook.com/share/g/18SE6B254K/',\n  'https://www.facebook.com/share/g/1DLXSAT8W7/',\n  'https://www.facebook.com/share/g/1CrX8Zp8xb/',\n  'https://www.facebook.com/share/g/1B8mjvuG4Q/',\n  'https://www.facebook.com/share/g/1HhAToUqQW/',\n  # Add remaining\n]\n```")
lines.append("- [ ] **Step 2: Two-Condition Keyword Filter & Contact Check**")
lines.append("```python\n# Cond 1: Owner post, เจ้าของปล่อยเช่า, รับเอเจ้น, Accept Agent, etc.\n# Cond 2: เช่า OR Rent\n# Filter: Must include Phone number or LINE ID, drop duplicates.\n```")
lines.append("- [ ] **Step 3: Commit**\n```bash\ngit add backend/app/agents/social/facebook_agent.py\ngit commit -m \"feat(facebook): optimize scraping logic with strict conditions\"\n```\n")

# Phase 2
lines.append("## Phase 2: Codebase Dead Code & Tech Debt Audit\n")
task_counter = 3

for root, dirs, files in os.walk(GRAXIA_DIR):
    if any(x in root for x in ['node_modules', '.venv', '.git', '.next', 'dist', 'build', '__pycache__', 'output']):
        continue
    for file in files:
        if file.endswith(('.py', '.ts', '.tsx')):
            filepath = os.path.join(root, file)
            rel_path = os.path.relpath(filepath, GRAXIA_DIR).replace('\\', '/')
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    todos = re.findall(r'(?i)#\s*todo:?\s*(.*)|//\s*todo:?\s*(.*)', content)
                    todos = [t[0] or t[1] for t in todos if t[0] or t[1]]
                    
                    line_count = len(content.splitlines())
                    
                    if todos or line_count > 250:
                        lines.append(f"### Task {task_counter}: Refactor `{rel_path}`")
                        lines.append(f"**Files:**\n- Modify: `{rel_path}`")
                        lines.append("\n- [ ] **Step 1: Address Tech Debt & Optimize**")
                        for t in todos:
                            lines.append(f"  - RESOLVE TODO: {t}")
                        if line_count > 250:
                            lines.append(f"  - File length is {line_count} lines. Analyze for Dead Code, remove unused imports, and split into smaller modules if responsibility is mixed.")
                        lines.append("- [ ] **Step 2: Verify Typing & Structure**")
                        lines.append("```bash\n# Run lint/type check\n```")
                        lines.append("- [ ] **Step 3: Commit**\n```bash\ngit add \"{rel_path}\"\ngit commit -m \"refactor: clean up and optimize {file}\"\n```\n")
                        task_counter += 1
            except Exception:
                pass

# Phase 3
lines.append("## Phase 3: Obsidian Vault Health & Standardization\n")
if os.path.exists(OBSIDIAN_DIR):
    for root, dirs, files in os.walk(OBSIDIAN_DIR):
        if any(x in root for x in ['.obsidian', '.git', '.smart-env']):
            continue
        for file in files:
            if file.endswith('.md'):
                filepath = os.path.join(root, file)
                rel_path = os.path.relpath(filepath, OBSIDIAN_DIR).replace('\\', '/')
                lines.append(f"### Task {task_counter}: Audit Vault Note `{rel_path}`")
                lines.append(f"**Files:**\n- Modify: ObsidianVault/Second Brain/{rel_path}")
                lines.append("\n- [ ] **Step 1: Check Frontmatter & Metadata**")
                lines.append("- [ ] **Step 2: Clean Orphaned/Broken Links**")
                lines.append("- [ ] **Step 3: Commit Vault Changes**\n```bash\ngit commit -m \"docs(vault): standardize {file}\"\n```\n")
                task_counter += 1

with open(PLAN_FILE, 'w', encoding='utf-8') as f:
    f.write("\n".join(lines))

print(f"SUCCESS: Generated {len(lines)} lines of actionable tasks.")
print(f"Total Tasks: {task_counter - 1}")
print(f"Saved to: {PLAN_FILE}")
