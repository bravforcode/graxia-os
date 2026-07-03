#!/usr/bin/env python3
"""Generate Obsidian notes for all test files in quant_os with source links."""
import ast, os, sys, io
from pathlib import Path
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

VAULT = Path(os.getenv("OBSIDIAN_VAULT_PATH", r"C:\Users\menum\quant\quant bot"))
ROOT = Path(__file__).resolve().parent.parent

DOMAIN_MAP = {
    "tests": "06-Validation", "shadow": "17-Shadow", "canary": "18-Canary",
    "validation": "06-Validation", "ticks": "05-Data", "events": "15-Events",
    "regime": "14-Regime", "oracle": "20-Oracle", "micro_live": "09-Live-Readiness",
    "markets": "08-Markets", "cost": "12-Cost", "expansion": "13-Expansion",
    "runtime": "01-Architecture", "gold_bot": "02-Strategies", "scripts": "01-Architecture",
    "repo_intelligence": "16-Repo-Intelligence", "core": "01-Architecture",
    "execution": "04-Execution", "risk": "03-Risk", "backtest": "19-Backtest",
    "ml": "10-ML", "data": "05-Data", "market_data": "05-Data",
}


def parse_test_file(path, root):
    """Parse a test file to extract functions, imports, and docstrings."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, Exception):
        return None

    rel = str(path.relative_to(root))
    parts = path.relative_to(root).parts
    domain = parts[0] if len(parts) > 1 else "tests"

    imports = []
    test_funcs = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.append(node.module)
        elif isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
            if node.name.startswith("test_"):
                docstring = ast.get_docstring(node) or ""
                test_funcs.append((node.name, docstring))

    # Find source modules being tested
    source_modules = set()
    for imp in imports:
        if imp.startswith("graxia.packages.quant_os.") or imp.startswith("quant_os."):
            mod = imp.split(".")[-1]
            source_modules.add(mod)
        elif imp.startswith(".") and len(imp) > 1:
            source_modules.add(imp.lstrip(".").split(".")[-1])

    return {
        "path": rel,
        "name": path.stem,
        "domain": domain,
        "folder": DOMAIN_MAP.get(domain, "06-Validation"),
        "docstring": ast.get_docstring(tree) or "",
        "test_functions": test_funcs,
        "imports": imports,
        "source_modules": sorted(source_modules),
    }


def generate_notes():
    """Generate test file notes for all test_*.py files."""
    test_files = sorted(ROOT.rglob("test_*.py"))
    test_files = [f for f in test_files if "__pycache__" not in str(f)]

    print(f"[TESTS] Found {len(test_files)} test files")

    notes_dir = VAULT / "Tests"
    notes_dir.mkdir(parents=True, exist_ok=True)

    created = 0
    for tf in test_files:
        info = parse_test_file(tf, ROOT)
        if not info:
            continue

        today = datetime.now().strftime("%Y-%m-%d")
        source_links = ""
        for mod in info["source_modules"]:
            # Try to find the actual note in vault
            source_links += f"- [[{mod}]]\n"
        if not source_links:
            source_links = "- (no source links found)\n"

        test_list = ""
        for fname, fdoc in info["test_functions"]:
            test_list += f"- `{fname}()`"
            if fdoc:
                first_line = fdoc.split("\n")[0]
                test_list += f" -- {first_line}"
            test_list += "\n"

        content = f"""---
title: "{info['name']}"
type: test
module: "{info['path']}"
domain: "{info['domain']}"
tags: [test, {info['domain']}]
created: {today}
---

# {info['name']}

> **Source:** `{info['path']}` | **Domain:** {info['domain']}

## Description

{info['docstring'] or 'No description.'}

## Test Functions ({len(info['test_functions'])})

{test_list or '- (no test functions found)'}

## Source Modules Under Test

{source_links}
## Dependencies

"""
        for imp in info["imports"][:15]:
            content += f"- `{imp}`\n"

        content += f"""
## Relationships

- Domain: [[{info['folder']} MOC]]
- Related: [[Quant-OS-Architecture]]

---
*Auto-generated from `{info['path']}` on {today}*
"""
        note_name = f"{info['name']}.md"
        (notes_dir / note_name).write_text(content, encoding="utf-8")
        created += 1

    print(f"[TESTS] Created {created} test notes in {notes_dir}")
    return created


def generate_test_index():
    """Generate a test index MOC."""
    today = datetime.now().strftime("%Y-%m-%d")
    notes = sorted((VAULT / "Tests").glob("test_*.md"))

    content = f"""---
title: "Test Suite Index"
type: moc
tags: [test, moc]
created: {today}
---

# Test Suite Index

> {len(notes)} test files across all domains

## By Domain

"""
    by_domain = {}
    for n in notes:
        try:
            lines = n.read_text(encoding="utf-8").split("\n")
            for line in lines:
                if line.startswith("domain:"):
                    d = line.split(":")[1].strip().strip('"')
                    if d not in by_domain:
                        by_domain[d] = []
                    by_domain[d].append(n.stem)
                    break
        except Exception:
            pass

    for domain, tests in sorted(by_domain.items(), key=lambda x: -len(x[1])):
        content += f"### {domain} ({len(tests)})\n\n"
        for t in sorted(tests):
            content += f"- [[{t}]]\n"
        content += "\n"

    content += f"---\n*Auto-generated on {today}*\n"
    (VAULT / "00-MOCs" / "Test-Suite-Index.md").write_text(content, encoding="utf-8")
    print(f"[TESTS] Test index created: {len(notes)} notes indexed")


if __name__ == "__main__":
    count = generate_notes()
    generate_test_index()
    print(f"[TESTS] Done! {count} test notes created.")
