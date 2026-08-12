"""Phase 1R-H integration tests."""
import ast
import json
from pathlib import Path

from graxia.packages.quant_os.repo_intelligence.adapters.vectorbt_oracle import (
    get_engine_name as vbt_name,
    validate_input as vbt_validate,
    normalize_output as vbt_normalize,
    run_oracle as vbt_run,
)
from graxia.packages.quant_os.repo_intelligence.adapters.backtesting_py_oracle import (
    get_engine_name as bt_name,
    validate_input as bt_validate,
    normalize_output as bt_normalize,
    run_oracle as bt_run,
)
from graxia.packages.quant_os.repo_intelligence.adapters.backtrader_oracle import (
    get_engine_name as btr_name,
    validate_input as btr_validate,
    normalize_output as btr_normalize,
    run_oracle as btr_run,
)

REPO_ROOT = Path(r"C:\Users\menum\graxia os")
ADAPTERS_DIR = REPO_ROOT / "graxia/packages/quant_os/repo_intelligence/adapters"
CANONICAL_DIR = REPO_ROOT / "graxia/packages/quant_os"

ADAPTERS = [
    ("vectorbt", vbt_name, vbt_validate, vbt_normalize, vbt_run),
    ("backtesting_py", bt_name, bt_validate, bt_normalize, bt_run),
    ("backtrader", btr_name, btr_validate, btr_normalize, btr_run),
]


# --- 1-4: Adapter interface checks ---

def test_all_adapters_have_get_engine_name():
    for name, engine_fn, *_ in ADAPTERS:
        assert callable(engine_fn), f"{name} get_engine_name not callable"
        assert isinstance(engine_fn(), str), f"{name} get_engine_name must return str"


def test_all_adapters_have_validate_input():
    for name, _, validate_fn, *_ in ADAPTERS:
        assert callable(validate_fn), f"{name} validate_input not callable"


def test_all_adapters_have_normalize_output():
    for name, _, _, normalize_fn, *_ in ADAPTERS:
        assert callable(normalize_fn), f"{name} normalize_output not callable"


def test_all_adapters_have_run_oracle():
    for name, _, _, _, run_fn in ADAPTERS:
        assert callable(run_fn), f"{name} run_oracle not callable"


# --- 5: AST scan — no oracle imports in canonical modules ---

ORACLE_PACKAGES = {"vectorbt", "backtesting", "backtrader"}


def _scan_file_for_oracle_imports(filepath: Path) -> list[str]:
    """Return top-level import names that match oracle packages."""
    tree = ast.parse(filepath.read_text(encoding="utf-8"))
    bad = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in ORACLE_PACKAGES:
                    bad.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                if root in ORACLE_PACKAGES:
                    bad.append(node.module)
    return bad


def test_no_oracle_imports_in_canonical():
    """Canonical modules must not import oracle packages at all."""
    bad_files = {}
    for py in CANONICAL_DIR.rglob("*.py"):
        # skip adapters dir — they're allowed to import oracles
        if ADAPTERS_DIR in py.parents or "tests" in py.parts:
            continue
        imports = _scan_file_for_oracle_imports(py)
        if imports:
            bad_files[str(py.relative_to(CANONICAL_DIR))] = imports
    assert not bad_files, f"Canonical modules import oracles: {bad_files}"


# --- 6: Adapters lazy-import oracle packages ---

ORACLE_IMPORT_NAMES = {"vectorbt", "backtesting", "backtrader", "backtrader"}


def test_adapters_lazy_import():
    """Adapters must not import oracle packages at module level."""
    for py in ADAPTERS_DIR.glob("*.py"):
        if py.name.startswith("__"):
            continue
        tree = ast.parse(py.read_text(encoding="utf-8"))
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    assert root not in ORACLE_IMPORT_NAMES, (
                        f"{py.name} imports {alias.name} at module level"
                    )
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    root = node.module.split(".")[0]
                    assert root not in ORACLE_IMPORT_NAMES, (
                        f"{py.name} imports from {node.module} at module level"
                    )


# --- 7-10: File existence checks ---

def test_oracle_isolation_dirs_exist():
    envs = REPO_ROOT / ".envs"
    assert envs.exists(), ".envs/ directory missing"
    for name in ["canonical", "oracle-vectorbt", "oracle-backtesting-py", "oracle-backtrader"]:
        assert (envs / name).exists(), f"Missing .envs/{name}"


def test_license_records_exist():
    path = REPO_ROOT / "graxia/packages/quant_os/repo_intelligence/registry/license_records.json"
    assert path.exists(), "license_records.json missing"
    data = json.loads(path.read_text())
    assert len(data["licenses"]) >= 3


def test_sbom_template_exists():
    path = REPO_ROOT / "graxia/packages/quant_os/repo_intelligence/registry/sbom_template.json"
    assert path.exists(), "sbom_template.json missing"
    data = json.loads(path.read_text())
    assert data["spdx_version"] == "SPDX-2.3"


def test_quarantine_manifest_exists():
    path = REPO_ROOT / "graxia/packages/quant_os/quarantine_manifest.json"
    assert path.exists(), "quarantine_manifest.json missing"


# --- 11: Canonical runtime map has all oracles ---

def test_canonical_runtime_map_has_all_oracles():
    """Check that approved_references.yml lists all three oracle engines."""
    yml_path = (
        REPO_ROOT
        / "graxia/packages/quant_os/repo_intelligence/registry/approved_references.yml"
    )
    assert yml_path.exists(), "approved_references.yml missing"
    content = yml_path.read_text()
    for repo_id in ["mementum_backtrader", "kernc_backtesting_py", "polakowo_vectorbt"]:
        assert repo_id in content, f"approved_references.yml missing {repo_id}"
