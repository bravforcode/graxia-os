"""
bridge_notebooklm.py — Research Pipeline: Vault ↔ NotebookLM
============================================================
Exports quant_OS research topics from the Obsidian vault into
NotebookLM, runs AI-powered analysis, and captures insights back.

Pre-requisite (one-time):
    notebooklm login    # Opens browser for Google auth

Usage:
  python scripts/bridge_notebooklm.py                # full research pipeline
  python scripts/bridge_notebooklm.py --auth-only    # auth check / login
  python scripts/bridge_notebooklm.py --push-only    # export vault → NotebookLM only
  python scripts/bridge_notebooklm.py --pull-only    # capture insights → vault only
"""

import argparse
import io
import json
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path

# Force UTF-8 on stdout/stderr (Windows cp1252 fix)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# ─── Paths ───────────────────────────────────────────────────────────────
QUANT_OS = Path(__file__).resolve().parent.parent
VAULT = Path(r"C:\Users\menum\quant\quant bot")
VAULT_STATES = VAULT / "Meta" / "states" / "quant_os"
VAULT_INBOX = VAULT / "00-Inbox"
VAULT_RESEARCH = VAULT / "02-areas" / "trading" / "research"
RESEARCH_MANIFEST = QUANT_OS / "Meta" / "notebooklm_manifest.json"

# ─── Notebook name ───────────────────────────────────────────────────────
NOTEBOOK_NAME = "quant_OS Research"

# ══════════════════════════════════════════════════════════════════════════
#  Auth
# ══════════════════════════════════════════════════════════════════════════

_ENCODING = dict(encoding="utf-8")  # Windows cp1252 → utf-8

def _nb_run(args: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Run notebooklm command with utf-8 encoding (fixes cp1252 decode errors)."""
    return subprocess.run(
        ["notebooklm", *args],
        capture_output=True, text=True, timeout=timeout, **_ENCODING,
    )

def check_auth() -> bool:
    """Check if notebooklm-py CLI is authenticated."""
    try:
        result = _nb_run(["auth", "check"])
        return result.returncode == 0 and "SID cookie" in (result.stdout or "")
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def run_login():
    """Run interactive NotebookLM login (opens browser)."""
    print("[nb] Opening browser for Google auth...")
    subprocess.run(["notebooklm", "login"], **_ENCODING)
    print("[nb] After login, re-run this script without --auth-only")


# ══════════════════════════════════════════════════════════════════════════
#  Push: Vault → NotebookLM
# ══════════════════════════════════════════════════════════════════════════

def push_vault_to_notebooklm():
    """Export key vault research notes into a NotebookLM notebook."""
    print("[nb] === Push: Vault -> NotebookLM ===")

    # 1. Gather files to push
    sources = []
    state_files = sorted(VAULT_STATES.glob("*.md"))
    sources.extend(state_files)

    # Also include latest backtest inbox notes
    inbox_files = sorted(VAULT_INBOX.glob("Backtest_*.md"))
    sources.extend(inbox_files[:3])  # cap at 3

    if not sources:
        print("[nb] No files to push.")
        return

    print(f"[nb] Found {len(sources)} files to push.")

    # 2. Find or create notebook via CLI
    nb_id = _resolve_notebook(NOTEBOOK_NAME)
    if not nb_id:
        print("[nb] Creating new notebook...")
        result = _nb_run(["create", NOTEBOOK_NAME])
        if result.returncode != 0:
            print(f"[nb] Failed to create notebook: {result.stderr}")
            return
        nb_id = _extract_notebook_id(result.stdout)
        if not nb_id:
            print("[nb] Could not determine notebook ID. Continuing...")

    # 3. Add sources
    for src in sources:
        print(f"[nb]   Adding: {src.name}")
        try:
            _nb_run(["source", "add", str(src)], timeout=60)
        except Exception as e:
            print(f"[nb]   Warning: {e}")

    # 4. Switch to notebook context
    if nb_id:
        _nb_run(["use", nb_id], timeout=15)

    # 5. Generate research summary via CLI
    print("[nb] Running NotebookLM analysis...")
    VAULT_RESEARCH.mkdir(parents=True, exist_ok=True)
    try:
        result = _nb_run(["ask",
             "Summarize key findings from quant_OS research: "
             "1) Backtest performance metrics 2) Risk parameters "
             "3) Strategy insights 4) Known limitations. "
             "Format as structured markdown with citations."], timeout=120)
        if result.returncode == 0 and result.stdout:
            _save_insight("nb_analysis_summary.md", result.stdout,
                          "NotebookLM", "auto-analysis")
            print("[nb]   ✅ Analysis saved.")
    except Exception as e:
        print(f"[nb]   Warning: analysis failed: {e}")


def _resolve_notebook(name: str) -> str | None:
    """Find notebook ID by name using --json output. Returns None if not found."""
    try:
        result = _nb_run(["list", "--json"])
        if result.returncode != 0 or not result.stdout:
            return None
        data = json.loads(result.stdout)
        for nb in data.get("notebooks", []):
            if name.lower() in nb.get("title", "").lower():
                return nb["id"]
    except Exception:
        pass
    return None


def _extract_notebook_id(output: str) -> str | None:
    """Extract notebook ID from CLI output like 'Created notebook: <uuid> - <name>'."""
    import re
    match = re.search(r'([\da-f]{8}-[\da-f]{4}-[\da-f]{4}-[\da-f]{4}-[\da-f]{12})', output)
    return match.group(1) if match else None


# ══════════════════════════════════════════════════════════════════════════
#  Pull: NotebookLM → Vault
# ══════════════════════════════════════════════════════════════════════════

# Research questions to ask NotebookLM automatically
RESEARCH_QUESTIONS = [
    {
        "id": "risk_factors",
        "question": "What are the top risk factors identified across all trading research? "
                     "List with severity and supporting evidence.",
    },
    {
        "id": "strategy_performance",
        "question": "Summarize strategy performance comparisons. "
                     "Which strategies show consistent edge? Any patterns in drawdowns?",
    },
    {
        "id": "gaps_opportunities",
        "question": "What gaps or contradictions exist in the research? "
                     "What opportunities are suggested by the data that haven't been explored yet?",
    },
    {
        "id": "methodology_issues",
        "question": "What methodology concerns are identified? "
                     "Look for overfitting risks, data quality issues, assumption violations.",
    },
]


def pull_insights_from_notebooklm():
    """Query NotebookLM for research insights and save to vault."""
    print("[nb] === Pull: NotebookLM -> Vault ===")

    VAULT_RESEARCH.mkdir(parents=True, exist_ok=True)

    # Switch to notebook context
    nb_id = _resolve_notebook(NOTEBOOK_NAME)
    if nb_id:
        _nb_run(["use", nb_id], timeout=15)

    for rq in RESEARCH_QUESTIONS:
        qid = rq["id"]
        question = rq["question"]
        print(f"[nb]   Asking: {qid}...")

        try:
            result = _nb_run(["ask", question], timeout=120)
            if result.returncode == 0 and result.stdout:
                _save_insight(f"nb_{qid}.md", result.stdout,
                              "NotebookLM", qid)
                print(f"[nb]     ✅ {qid} saved.")
            else:
                print(f"[nb]     ⚠️ No output for {qid}")

        except subprocess.TimeoutExpired:
            print(f"[nb]     ⏰ Timeout for {qid}")
        except Exception as e:
            print(f"[nb]     ❌ Error: {e}")

    # Generate a consolidated research brief
    _generate_research_brief()


def _save_insight(filename: str, content: str, source: str, category: str):
    """Write an insight note to the research folder."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    header = f"""---
created: {now}
source: {source}
category: {category}
tags: [notebooklm, research, bridge-auto]
---

# Research Insight: {category}

_Generated by NotebookLM at {now}_

"""
    note_path = VAULT_RESEARCH / filename
    note_path.write_text(header + content, encoding="utf-8")
    print(f"[nb]     Wrote: {note_path.relative_to(VAULT)}")


def _generate_research_brief():
    """Synthesize individual findings into a master brief."""
    now = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    research_files = sorted(VAULT_RESEARCH.glob("nb_*.md"))

    if not research_files:
        return

    toc = "\n".join(f"- [{f.stem.replace('nb_', '')}]({f.name})" for f in research_files)
    brief = f"""---
created: {now}
tags: [notebooklm, research-brief, bridge-auto]
---

# quant_OS Research Brief — {now}

Auto-generated from NotebookLM research pipeline.

## Contents

{toc}

## Next Steps

- [ ] Review individual findings for actionability
- [ ] Cross-reference with current trading plan
- [ ] Update strategy parameters based on findings
- [ ] Log decisions in trading log

---

_Research powered by NotebookLM via bridge_notebooklm.py_
"""
    brief_path = VAULT_RESEARCH / "nb_research_brief.md"
    brief_path.write_text(brief, encoding="utf-8")
    print(f"[nb]     Research brief: {brief_path.relative_to(VAULT)}")


# ══════════════════════════════════════════════════════════════════════════
#  Main
# ══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="Bridge: Vault ↔ NotebookLM")
    parser.add_argument("--auth-only", action="store_true", help="Auth check / login")
    parser.add_argument("--push-only", action="store_true", help="Export vault → NotebookLM only")
    parser.add_argument("--pull-only", action="store_true", help="Capture insights → vault only")
    args = parser.parse_args()

    if args.auth_only:
        if check_auth():
            print("[nb] ✅ Already authenticated with NotebookLM.")
        else:
            print("[nb] ❌ Not authenticated.")
            run_login()
        return

    if not check_auth():
        print("[nb] ❌ Not authenticated. Run 'notebooklm login' first or use --auth-only")
        sys.exit(1)

    if args.push_only:
        push_vault_to_notebooklm()
    elif args.pull_only:
        pull_insights_from_notebooklm()
    else:
        # Full pipeline
        print("[nb] === Full Research Pipeline ===")
        push_vault_to_notebooklm()
        pull_insights_from_notebooklm()
        print("[nb] === Done ===")


if __name__ == "__main__":
    main()
