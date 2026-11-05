import ast
from pathlib import Path
from uuid import UUID

from app.config import settings

CONFIG_PATH = Path(__file__).resolve().parents[1] / "app" / "config.py"


def _settings_field_names() -> list[str]:
    tree = ast.parse(CONFIG_PATH.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            return [
                stmt.target.id
                for stmt in node.body
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name)
            ]
    raise AssertionError("class Settings not found in app/config.py")


def test_settings_fields_are_declared_once():
    names = _settings_field_names()
    duplicates = sorted({name for name in names if names.count(name) > 1})
    assert duplicates == [], f"duplicate Settings fields override each other: {duplicates}"


def test_legacy_organization_id_is_uuid():
    assert isinstance(settings.LEGACY_ORGANIZATION_ID, UUID)
