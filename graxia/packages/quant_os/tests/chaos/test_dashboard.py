"""Tests for dashboard_streamlit.py — import and structure validation."""
import ast
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "dashboard_streamlit.py"


def test_script_imports_without_error():
    """Verify the script can be parsed as valid Python."""
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert tree is not None


def test_file_structure_is_valid_python():
    """Verify the script has expected top-level constructs."""
    source = SCRIPT.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imports = [n for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom))]
    assert len(imports) >= 3, "Expected at least 3 import statements"

    assigns = [n for n in tree.body if isinstance(n, ast.Assign)]
    assert len(assigns) >= 2, "Expected at least 2 top-level assignments"


def test_script_file_exists():
    """Verify the script file exists at expected path."""
    assert SCRIPT.exists(), f"Script not found: {SCRIPT}"
