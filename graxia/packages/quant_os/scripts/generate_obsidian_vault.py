#!/usr/bin/env python3
"""
Obsidian Vault Generator for Quant OS
======================================
Scans the quant_os codebase and auto-generates Obsidian-compatible markdown notes
with YAML frontmatter and [[wikilinks]].

Usage:
    python scripts/generate_obsidian_vault.py --vault "C:/Users/menum/quant/quant bot"
"""

import ast
import os
import sys
import io
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Set
from dataclasses import dataclass, field

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Configuration
VAULT_PATH = Path(os.getenv("OBSIDIAN_VAULT_PATH", r"C:\Users\menum\quant\quant bot"))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
# QUANT_OS_ROOT auto-detected: this file lives inside quant_os already
QUANT_OS_ROOT = PROJECT_ROOT

DOMAIN_MAP = {
    "core": ("01-Architecture", "Architecture"),
    "api": ("01-Architecture", "Architecture"),
    "runtime": ("01-Architecture", "Architecture"),
    "strategies": ("02-Strategies", "Strategies"),
    "gold_bot": ("02-Strategies", "Strategies"),
    "risk": ("03-Risk", "Risk"),
    "execution": ("04-Execution", "Execution"),
    "data": ("05-Data", "Data"),
    "market_data": ("05-Data", "Data"),
    "tick": ("05-Data", "Data"),
    "ticks": ("05-Data", "Data"),
    "validation": ("06-Validation", "Validation"),
    "governance": ("07-Governance", "Governance"),
    "markets": ("08-Markets", "Markets"),
    "live_readiness": ("09-Live-Readiness", "Live Readiness"),
    "ml": ("10-ML", "ML"),
    "monitoring": ("11-Monitoring", "Monitoring"),
    "cost": ("12-Cost", "Cost"),
    "expansion": ("13-Expansion", "Expansion"),
    "regime": ("14-Regime", "Regime"),
    "events": ("15-Events", "Events"),
    "repo_intelligence": ("16-Repo-Intelligence", "Repo Intelligence"),
    "shadow": ("17-Shadow", "Shadow"),
    "canary": ("18-Canary", "Canary"),
    "backtest": ("19-Backtest", "Backtest"),
    "oracle": ("20-Oracle", "Oracle"),
    "news_events": ("15-Events", "Events"),
    "micro_live": ("09-Live-Readiness", "Live Readiness"),
    "demo_campaign": ("18-Canary", "Canary"),
    "lancedb": ("10-ML", "ML"),
    "mql5": ("05-Data", "Data"),
    "pine_script": ("02-Strategies", "Strategies"),
    "phases": ("06-Validation", "Validation"),
    "experiments": ("06-Validation", "Validation"),
    "config": ("01-Architecture", "Architecture"),
    "docs": ("01-Architecture", "Architecture"),
}


@dataclass
class ParsedClass:
    name: str
    module_path: str
    package: str
    domain: str
    docstring: str = ""
    bases: List[str] = field(default_factory=list)
    fields: List[Tuple[str, str, str]] = field(default_factory=list)
    methods: List[Tuple[str, str]] = field(default_factory=list)
    is_dataclass: bool = False
    is_frozen: bool = False
    is_abstract: bool = False
    is_sqlalchemy: bool = False
    table_name: str = ""
    source_lines: List[str] = field(default_factory=list)


@dataclass
class ParsedEnum:
    name: str
    module_path: str
    package: str
    domain: str
    values: List[Tuple[str, str]] = field(default_factory=list)
    docstring: str = ""


@dataclass
class ParsedFunction:
    name: str
    module_path: str
    package: str
    domain: str
    docstring: str = ""
    args: List[Tuple[str, str, str]] = field(default_factory=list)
    return_type: str = ""
    source_lines: List[str] = field(default_factory=list)


@dataclass
class ParsedModule:
    name: str
    path: str
    package: str
    domain: str
    docstring: str = ""
    classes: List[ParsedClass] = field(default_factory=list)
    enums: List[ParsedEnum] = field(default_factory=list)
    functions: List[ParsedFunction] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)


class CodebaseParser:
    def __init__(self, root: Path):
        self.root = root
        self.modules: Dict[str, ParsedModule] = {}
        self.all_classes: Dict[str, ParsedClass] = {}
        self.all_enums: Dict[str, ParsedEnum] = {}
        self.all_functions: Dict[str, ParsedFunction] = {}

    def parse_all(self):
        for py_file in sorted(self.root.rglob("*.py")):
            if py_file.name.startswith("test_") or py_file.name == "__init__.py":
                continue
            if "__pycache__" in str(py_file):
                continue
            try:
                self._parse_file(py_file)
            except Exception as e:
                print(f"  [WARN] Failed to parse {py_file}: {e}")

    def _get_domain(self, file_path: Path) -> Tuple[str, str]:
        rel = file_path.relative_to(self.root)
        parts = rel.parts
        if len(parts) > 1:
            top_dir = parts[0]
            if top_dir in DOMAIN_MAP:
                return DOMAIN_MAP[top_dir]
        return ("01-Architecture", "Architecture")

    def _get_package(self, file_path: Path) -> str:
        rel = file_path.relative_to(self.root)
        return ".".join(rel.with_suffix("").parts)

    def _parse_file(self, file_path: Path):
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError:
            return

        _, domain_name = self._get_domain(file_path)
        package = self._get_package(file_path)
        rel_path = str(file_path.relative_to(self.root))

        module = ParsedModule(
            name=file_path.stem, path=rel_path, package=package,
            domain=domain_name, docstring=ast.get_docstring(tree) or "",
        )

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    module.imports.append(node.module)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                cls = self._parse_class(node, rel_path, package, domain_name, source)
                if cls:
                    module.classes.append(cls)
                    self.all_classes[cls.name] = cls
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func = self._parse_function(node, rel_path, package, domain_name, source)
                if func:
                    module.functions.append(func)
                    self.all_functions[func.name] = func

        self.modules[rel_path] = module

    def _parse_class(self, node, rel_path, package, domain, source):
        is_dataclass = False
        is_frozen = False
        for decorator in node.decorator_list:
            dec_name = ""
            if isinstance(decorator, ast.Name):
                dec_name = decorator.id
            elif isinstance(decorator, ast.Attribute):
                dec_name = decorator.attr
            elif isinstance(decorator, ast.Call):
                if isinstance(decorator.func, ast.Name):
                    dec_name = decorator.func.id
                elif isinstance(decorator.func, ast.Attribute):
                    dec_name = decorator.func.attr
                for kw in decorator.keywords:
                    if kw.arg == "frozen" and isinstance(kw.value, ast.Constant):
                        is_frozen = kw.value.value
            if dec_name == "dataclass":
                is_dataclass = True

        bases = []
        for base in node.bases:
            if isinstance(base, ast.Name):
                bases.append(base.id)
            elif isinstance(base, ast.Attribute):
                bases.append(base.attr)

        is_abstract = "ABC" in bases

        is_sqlalchemy = False
        table_name = ""
        for item in ast.walk(node):
            if isinstance(item, ast.Assign):
                for target in item.targets:
                    if isinstance(target, ast.Name) and target.id == "__tablename__":
                        if isinstance(item.value, ast.Constant):
                            table_name = item.value.value
                            is_sqlalchemy = True

        fields = []
        for item in node.body:
            if isinstance(item, ast.AnnAssign) and isinstance(item.target, ast.Name):
                fname = item.target.id
                ftype = ast.unparse(item.annotation) if item.annotation else "Any"
                fdefault = ""
                if item.value:
                    try:
                        fdefault = ast.unparse(item.value)
                    except Exception:
                        fdefault = "..."
                fields.append((fname, ftype, fdefault))

        methods = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if item.name.startswith("_") and item.name != "__init__":
                    continue
                docstring = ast.get_docstring(item) or ""
                methods.append((item.name, docstring))

        source_lines = source.split("\n")
        start = node.lineno - 1
        end = min(start + 30, len(source_lines))
        snippet = "\n".join(source_lines[start:end])

        return ParsedClass(
            name=node.name, module_path=rel_path, package=package, domain=domain,
            docstring=ast.get_docstring(node) or "", bases=bases, fields=fields,
            methods=methods, is_dataclass=is_dataclass, is_frozen=is_frozen,
            is_abstract=is_abstract, is_sqlalchemy=is_sqlalchemy,
            table_name=table_name, source_lines=[snippet],
        )

    def _parse_function(self, node, rel_path, package, domain, source):
        if node.name.startswith("_") and node.name != "__init__":
            return None
        args = []
        for arg in node.args.args:
            atype = ast.unparse(arg.annotation) if arg.annotation else ""
            args.append((arg.arg, atype, ""))
        return_type = ast.unparse(node.returns) if node.returns else ""
        source_lines = source.split("\n")
        start = node.lineno - 1
        end = min(start + 20, len(source_lines))
        snippet = "\n".join(source_lines[start:end])
        return ParsedFunction(
            name=node.name, module_path=rel_path, package=package, domain=domain,
            docstring=ast.get_docstring(node) or "", args=args,
            return_type=return_type, source_lines=[snippet],
        )


class VaultGenerator:
    def __init__(self, vault_path: Path, parser: CodebaseParser):
        self.vault = vault_path
        self.parser = parser
        self.notes_created = 0
        self.links_created = 0

    def generate_all(self):
        print("\n[PHASE 1] Generating MOCs...")
        self._generate_mocs()
        print("[PHASE 2] Generating dataclass notes...")
        self._generate_dataclass_notes()
        print("[PHASE 3] Generating SQLAlchemy model notes...")
        self._generate_model_notes()
        print("[PHASE 4] Generating strategy notes...")
        self._generate_strategy_notes()
        print("[PHASE 5] Generating config notes...")
        self._generate_config_notes()
        print("[PHASE 6] Generating enum notes...")
        self._generate_enum_notes()
        print("[PHASE 7] Generating module notes...")
        self._generate_module_notes()
        print("[PHASE 8] Generating function notes...")
        self._generate_function_notes()
        print("[PHASE 9] Generating architecture overview...")
        self._generate_architecture_overview()
        print("[PHASE 10] Generating relationship map...")
        self._generate_relationship_map()
        print(f"\n[DONE] Created {self.notes_created} notes with {self.links_created} links.")

    def _write_note(self, folder, filename, content):
        note_dir = self.vault / folder
        note_dir.mkdir(parents=True, exist_ok=True)
        (note_dir / filename).write_text(content, encoding="utf-8")
        self.notes_created += 1

    def _link(self, name):
        self.links_created += 1
        return f"[[{name}]]"

    def _get_folder(self, module_path):
        parts = module_path.replace("\\", "/").split("/")
        top = parts[0] if parts else "core"
        return DOMAIN_MAP.get(top, ("01-Architecture", "Architecture"))[0]

    def _generate_mocs(self):
        mocs = {
            "MOC-Architecture.md": {"title": "Architecture MOC", "domain": "Architecture", "tags": ["moc", "architecture"], "desc": "System architecture, configuration, and core infrastructure"},
            "MOC-Strategies.md": {"title": "Strategies MOC", "domain": "Strategies", "tags": ["moc", "strategies"], "desc": "Trading strategies, signal generation, and ensemble logic"},
            "MOC-Risk.md": {"title": "Risk Management MOC", "domain": "Risk", "tags": ["moc", "risk"], "desc": "Risk policy, position sizing, circuit breakers, and kill switches"},
            "MOC-Execution.md": {"title": "Execution MOC", "domain": "Execution", "tags": ["moc", "execution"], "desc": "Order lifecycle, fill models, and execution simulation"},
            "MOC-Data.md": {"title": "Data Pipeline MOC", "domain": "Data", "tags": ["moc", "data"], "desc": "Data models, pipelines, market data, and tick processing"},
            "MOC-Validation.md": {"title": "Validation MOC", "domain": "Validation", "tags": ["moc", "validation"], "desc": "Walk-forward validation, deflated Sharpe, and phase verdicts"},
            "MOC-Governance.md": {"title": "Governance MOC", "domain": "Governance", "tags": ["moc", "governance"], "desc": "Experiment registry, ML policy, and multi-broker policy"},
            "MOC-Live-Readiness.md": {"title": "Live Readiness MOC", "domain": "Live Readiness", "tags": ["moc", "live", "readiness"], "desc": "Shadow trading, canary deployment, and live readiness checks"},
            "MOC-ML.md": {"title": "Machine Learning MOC", "domain": "ML", "tags": ["moc", "ml"], "desc": "ML pipeline, model training, and feature engineering"},
            "MOC-Regime.md": {"title": "Regime Detection MOC", "domain": "Regime", "tags": ["moc", "regime"], "desc": "Market regime detection, monitoring, and risk overlay"},
        }
        today = datetime.now().strftime("%Y-%m-%d")
        for filename, moc in mocs.items():
            domain_classes = [c for c in self.parser.all_classes.values() if moc["domain"].lower() in c.domain.lower()]
            domain_enums = [e for e in self.parser.all_enums.values() if moc["domain"].lower() in e.domain.lower()]
            content = f'---\ntitle: "{moc["title"]}"\ntype: moc\ndomain: "{moc["domain"]}"\ntags: [{", ".join(moc["tags"])}]\ncreated: {today}\n---\n\n# {moc["title"]}\n\n> {moc["desc"]}\n\n## Sections\n\n'
            for s in ["Core", "API", "Config", "Modules"]:
                content += f"- **{s}**\n"
            if domain_classes:
                content += "\n## Classes\n\n"
                for cls in sorted(domain_classes, key=lambda c: c.name):
                    content += f"- {self._link(cls.name)}\n"
            if domain_enums:
                content += "\n## Enums\n\n"
                for e in sorted(domain_enums, key=lambda x: x.name):
                    content += f"- {self._link(e.name)}\n"
            content += f"\n---\n*Auto-generated on {today}*\n"
            self._write_note("00-MOCs", filename, content)

    def _generate_dataclass_notes(self):
        today = datetime.now().strftime("%Y-%m-%d")
        for name, cls in self.parser.all_classes.items():
            if not cls.is_dataclass:
                continue
            folder = self._get_folder(cls.module_path)
            frozen_badge = "Frozen" if cls.is_frozen else "Mutable"
            content = f'---\ntitle: "{cls.name}"\ntype: dataclass\nmodule: "{cls.package}"\ndomain: "{cls.domain}"\nfrozen: {str(cls.is_frozen).lower()}\ntags: [dataclass, {cls.domain.lower()}]\ncreated: {today}\n---\n\n# {cls.name}\n\n> **Module:** `{cls.module_path}` | **{frozen_badge}** | **Domain:** {cls.domain}\n\n'
            if cls.docstring:
                content += f"## Description\n\n{cls.docstring}\n\n"
            if cls.is_sqlalchemy:
                content += f"## Table\n\n`{cls.table_name}`\n\n"
            if cls.bases:
                content += "## Inheritance\n\n"
                for b in cls.bases:
                    content += f"- Parent: {self._link(b)}\n"
                content += "\n"
            if cls.fields:
                content += "## Fields\n\n| Name | Type | Default |\n|------|------|---------|\n"
                for fn, ft, fd in cls.fields:
                    content += f"| `{fn}` | `{ft}` | `{fd or '--'}` |\n"
                content += "\n"
            if cls.methods:
                content += "## Methods\n\n"
                for mn, md in cls.methods:
                    content += f"- `{mn}()`"
                    if md:
                        content += f" -- {md.split(chr(10))[0]}"
                    content += "\n"
                content += "\n"
            content += f"---\n*Auto-generated from `{cls.module_path}`*\n"
            self._write_note(folder, f"{cls.name}.md", content)

    def _generate_model_notes(self):
        today = datetime.now().strftime("%Y-%m-%d")
        for name, cls in self.parser.all_classes.items():
            if not cls.is_sqlalchemy:
                continue
            content = f'---\ntitle: "{cls.name}"\ntype: sqlalchemy-model\ntable: "{cls.table_name}"\ndomain: "{cls.domain}"\ntags: [model, database, {cls.domain.lower()}]\ncreated: {today}\n---\n\n# {cls.name}\n\n> **Table:** `{cls.table_name}` | **Module:** `{cls.module_path}`\n\n'
            if cls.fields:
                content += "## Columns\n\n| Column | Type | Default |\n|--------|------|----------|\n"
                for fn, ft, fd in cls.fields:
                    content += f"| `{fn}` | `{ft}` | `{fd or '--'}` |\n"
                content += "\n"
            content += f"---\n*Auto-generated from `{cls.module_path}`*\n"
            self._write_note("05-Data", f"{cls.name}.md", content)

    def _generate_strategy_notes(self):
        today = datetime.now().strftime("%Y-%m-%d")
        for name, cls in self.parser.all_classes.items():
            is_strategy = ("Strategy" in name and name != "StrategyConfig") or "Strategy" in cls.bases or cls.module_path.startswith("strategies") or cls.module_path.startswith("gold_bot")
            if not is_strategy:
                continue
            content = f'---\ntitle: "{cls.name}"\ntype: strategy\nmodule: "{cls.package}"\ndomain: "{cls.domain}"\ntags: [strategy, {cls.domain.lower()}]\ncreated: {today}\n---\n\n# {cls.name}\n\n> **Module:** `{cls.module_path}` | **Domain:** {cls.domain}\n\n'
            if cls.docstring:
                content += f"## Description\n\n{cls.docstring}\n\n"
            if cls.bases:
                content += "## Inheritance\n\n"
                for b in cls.bases:
                    content += f"- Parent: {self._link(b)}\n"
                content += "\n"
            if cls.fields:
                content += "## Parameters\n\n| Name | Type | Default |\n|------|------|---------|\n"
                for fn, ft, fd in cls.fields:
                    content += f"| `{fn}` | `{ft}` | `{fd or '--'}` |\n"
                content += "\n"
            content += f"---\n*Auto-generated from `{cls.module_path}`*\n"
            self._write_note("02-Strategies", f"{cls.name}.md", content)

    def _generate_config_notes(self):
        today = datetime.now().strftime("%Y-%m-%d")
        for name, cls in self.parser.all_classes.items():
            if not ("Config" in name or "Policy" in name or "Settings" in name):
                continue
            if not (cls.is_dataclass or cls.fields):
                continue
            folder = self._get_folder(cls.module_path)
            content = f'---\ntitle: "{cls.name}"\ntype: config\nmodule: "{cls.package}"\ndomain: "{cls.domain}"\ntags: [config, {cls.domain.lower()}]\ncreated: {today}\n---\n\n# {cls.name}\n\n> **Module:** `{cls.module_path}` | **Domain:** {cls.domain}\n\n'
            if cls.fields:
                content += "## Configuration Fields\n\n| Name | Type | Default |\n|------|------|---------|\n"
                for fn, ft, fd in cls.fields:
                    content += f"| `{fn}` | `{ft}` | `{fd or '--'}` |\n"
                content += "\n"
            content += f"---\n*Auto-generated from `{cls.module_path}`*\n"
            self._write_note(folder, f"{cls.name}.md", content)

    def _generate_enum_notes(self):
        today = datetime.now().strftime("%Y-%m-%d")
        for name, enum in self.parser.all_enums.items():
            folder = self._get_folder(enum.module_path)
            content = f'---\ntitle: "{enum.name}"\ntype: enum\nmodule: "{enum.package}"\ndomain: "{enum.domain}"\ntags: [enum, {enum.domain.lower()}]\ncreated: {today}\n---\n\n# {enum.name}\n\n> **Module:** `{enum.module_path}` | **Domain:** {enum.domain}\n\n'
            if enum.values:
                content += "## Values\n\n| Name | Value |\n|------|-------|\n"
                for vn, vv in enum.values:
                    content += f"| `{vn}` | `{vv}` |\n"
                content += "\n"
            content += f"---\n*Auto-generated from `{enum.module_path}`*\n"
            self._write_note(folder, f"{enum.name}.md", content)

    def _generate_module_notes(self):
        today = datetime.now().strftime("%Y-%m-%d")
        for mod_name, mod in self.parser.modules.items():
            if not mod.classes and not mod.functions:
                continue
            folder = self._get_folder(mod_name)
            content = f'---\ntitle: "{mod.name}"\ntype: module\npackage: "{mod.package}"\ndomain: "{mod.domain}"\ntags: [module, {mod.domain.lower()}]\ncreated: {today}\n---\n\n# {mod.name}\n\n> **Package:** `{mod.package}` | **Path:** `{mod.path}`\n\n'
            if mod.classes:
                content += "## Classes\n\n"
                for cls in mod.classes:
                    content += f"- {self._link(cls.name)}"
                    if cls.docstring:
                        content += f" -- {cls.docstring.split(chr(10))[0]}"
                    content += "\n"
                content += "\n"
            if mod.functions:
                content += "## Functions\n\n"
                for func in mod.functions:
                    content += f"- `{func.name}()`"
                    if func.docstring:
                        content += f" -- {func.docstring.split(chr(10))[0]}"
                    content += "\n"
                content += "\n"
            content += f"---\n*Auto-generated from `{mod.path}`*\n"
            self._write_note(folder, f"{mod.name}.md", content)

    def _generate_function_notes(self):
        today = datetime.now().strftime("%Y-%m-%d")
        skip = {"main", "run", "get", "set", "create", "init", "reset", "validate"}
        for name, func in self.parser.all_functions.items():
            if len(name) < 3 or name.startswith("_") or name in skip:
                continue
            folder = self._get_folder(func.module_path)
            args_str = ", ".join([a[0] for a in func.args if a[0] != "self"])
            ret = f": {func.return_type}" if func.return_type else ""
            content = f'---\ntitle: "{func.name}"\ntype: function\nmodule: "{func.package}"\ndomain: "{func.domain}"\ntags: [function, {func.domain.lower()}]\ncreated: {today}\n---\n\n# {func.name}()\n\n> **Module:** `{func.module_path}` | **Domain:** {func.domain}\n\n'
            if func.docstring:
                content += f"## Description\n\n{func.docstring}\n\n"
            content += f"## Signature\n\n```python\ndef {func.name}({args_str}){ret}\n```\n\n"
            content += f"---\n*Auto-generated from `{func.module_path}`*\n"
            self._write_note(folder, f"fn-{func.name}.md", content)

    def _generate_architecture_overview(self):
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        tc = len(self.parser.all_classes)
        td = sum(1 for c in self.parser.all_classes.values() if c.is_dataclass)
        tm = sum(1 for c in self.parser.all_classes.values() if c.is_sqlalchemy)
        te = len(self.parser.all_enums)
        tf = len(self.parser.all_functions)
        tmo = len(self.parser.modules)

        domains = {}
        for cls in self.parser.all_classes.values():
            if cls.domain not in domains:
                domains[cls.domain] = {"c": 0, "d": 0, "m": 0}
            domains[cls.domain]["c"] += 1
            if cls.is_dataclass:
                domains[cls.domain]["d"] += 1
            if cls.is_sqlalchemy:
                domains[cls.domain]["m"] += 1

        content = f'---\ntitle: "Quant OS Architecture"\ntype: architecture\ntags: [architecture, overview]\ncreated: {today}\n---\n\n# Quant OS Architecture Overview\n\n> Complete knowledge graph of the Quant OS trading system\n\n## Statistics\n\n| Metric | Count |\n|--------|-------|\n| Total Classes | {tc} |\n| Dataclasses | {td} |\n| SQLAlchemy Models | {tm} |\n| Enums | {te} |\n| Functions | {tf} |\n| Modules | {tmo} |\n\n## Domain Map\n\n'
        for dn, stats in sorted(domains.items()):
            content += f"### {dn}\n\n- Classes: {stats['c']} | Dataclasses: {stats['d']} | Models: {stats['m']}\n\n"

        content += f"""## Key Relationships

### Data Flow
```
Signal -> RiskCheck -> Order -> Fill -> Position -> PortfolioSnapshot
```

### Strategy Flow
```
Strategy.generate_signal() -> Signal -> Ensemble -> RiskGate -> Order
```

### Validation Flow
```
Backtest -> WalkForward -> DeflatedSharpe -> PhaseVerdict -> PromotionReview
```

### Live Readiness Flow
```
Shadow -> Canary -> MicroLive -> LimitedLive -> ControlledLive
```

## MOCs

- [[MOC-Architecture]] -- System architecture and core
- [[MOC-Strategies]] -- Trading strategies
- [[MOC-Risk]] -- Risk management
- [[MOC-Execution]] -- Order execution
- [[MOC-Data]] -- Data pipeline
- [[MOC-Validation]] -- Validation framework
- [[MOC-Governance]] -- Governance and policies
- [[MOC-Live-Readiness]] -- Live readiness
- [[MOC-ML]] -- Machine learning
- [[MOC-Regime]] -- Regime detection

---
*Auto-generated on {now}*
"""
        self._write_note("01-Architecture", "Quant-OS-Architecture.md", content)

    def _generate_relationship_map(self):
        today = datetime.now().strftime("%Y-%m-%d")
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        domain_imports: Dict[str, Set[str]] = {}
        for mod_name, mod in self.parser.modules.items():
            domain = mod.domain
            if domain not in domain_imports:
                domain_imports[domain] = set()
            for imp in mod.imports:
                for other_mod in self.parser.modules.values():
                    if imp in other_mod.package or other_mod.name in imp:
                        if other_mod.domain != domain:
                            domain_imports[domain].add(other_mod.domain)
                        break

        content = f'---\ntitle: "Relationship Map"\ntype: graph\ntags: [graph, relationships]\ncreated: {today}\n---\n\n# Relationship Map\n\n> Import and dependency relationships between modules\n\n## Import Graph\n\n'
        for domain, deps in sorted(domain_imports.items()):
            if deps:
                content += f"### {domain}\n\n"
                for dep in sorted(deps):
                    content += f"- -> {dep}\n"
                content += "\n"
        content += f"\n---\n*Auto-generated on {now}*\n"
        self._write_note("Graph", "Relationship-Map.md", content)


def extract_enums_from_source(root):
    enums = {}
    for py_file in sorted(root.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        try:
            source = py_file.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, Exception):
            continue
        rel_path = str(py_file.relative_to(root))
        parts = py_file.relative_to(root).parts
        top_dir = parts[0] if len(parts) > 1 else "core"
        _, domain_name = DOMAIN_MAP.get(top_dir, ("01-Architecture", "Architecture"))
        package = ".".join(py_file.relative_to(root).with_suffix("").parts)
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ClassDef):
                is_enum = any(
                    "Enum" in (b.id if isinstance(b, ast.Name) else b.attr if isinstance(b, ast.Attribute) else "")
                    for b in node.bases
                )
                if is_enum:
                    values = []
                    for item in node.body:
                        if isinstance(item, ast.Assign):
                            for target in item.targets:
                                if isinstance(target, ast.Name):
                                    val = repr(item.value.value) if isinstance(item.value, ast.Constant) else ""
                                    values.append((target.id, val))
                    enums[node.name] = ParsedEnum(
                        name=node.name, module_path=rel_path, package=package,
                        domain=domain_name, values=values,
                        docstring=ast.get_docstring(node) or "",
                    )
    return enums


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Generate Obsidian vault from quant_os codebase")
    parser.add_argument("--vault", default=str(VAULT_PATH))
    parser.add_argument("--source", default=str(QUANT_OS_ROOT))
    args = parser.parse_args()

    vault_path = Path(args.vault)
    source_path = Path(args.source)

    print(f"[SCAN] Scanning: {source_path}")
    print(f"[VAULT] Vault: {vault_path}")

    if not source_path.exists():
        print(f"[ERROR] Source path not found: {source_path}")
        return

    cb = CodebaseParser(source_path)
    print("[PARSE] Parsing codebase...")
    cb.parse_all()

    print("[ENUMS] Extracting enums...")
    enums = extract_enums_from_source(source_path)
    cb.all_enums.update(enums)

    print("\n[STATS] Parsed:")
    print(f"  Modules: {len(cb.modules)}")
    print(f"  Classes: {len(cb.all_classes)}")
    print(f"  Dataclasses: {sum(1 for c in cb.all_classes.values() if c.is_dataclass)}")
    print(f"  SQLAlchemy: {sum(1 for c in cb.all_classes.values() if c.is_sqlalchemy)}")
    print(f"  Enums: {len(cb.all_enums)}")
    print(f"  Functions: {len(cb.all_functions)}")

    gen = VaultGenerator(vault_path, cb)
    gen.generate_all()


if __name__ == "__main__":
    main()
