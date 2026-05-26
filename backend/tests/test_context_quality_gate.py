from __future__ import annotations

import tempfile
from pathlib import Path

from app.context_engine.context_pack import ContextPackBuilder
from app.context_engine.quality_gate import evaluate_context_pack
from app.context_engine.schemas import ContextPack, ContextPackFile


def test_critical_files_never_aggressive_compressed() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        auth_dir = root / "backend" / "app" / "auth"
        auth_dir.mkdir(parents=True)
        (auth_dir / "context.py").write_text("class AuthContext:\n    pass\n", encoding="utf-8")

        builder = ContextPackBuilder()
        pack = builder.build_context_pack(
            root_path=str(root),
            task_type="security_review",
            goal="review auth context",
            token_budget=2000,
        )
        auth_file = next(file for file in pack.included_files if file.path.endswith("auth/context.py"))
        assert auth_file.content_mode == "full"


def test_quality_gate_catches_missing_required_path() -> None:
    pack = ContextPack(
        context_pack_id="ctx_test",
        included_files=[ContextPackFile(path="backend/app/api/health.py", content_mode="full")],
    )
    result = evaluate_context_pack(pack, required_paths=["backend/app/api/readiness.py"])
    assert not result.passed
    assert any(finding.code == "MISSING_REQUIRED_PATH" for finding in result.findings)


def test_quality_gate_catches_missing_error_message() -> None:
    pack = ContextPack(
        context_pack_id="ctx_test",
        included_files=[ContextPackFile(path="backend/tests/test_health.py", content="assert True", content_mode="full")],
    )
    result = evaluate_context_pack(pack, expected_error_text="TypeError: broken")
    assert not result.passed
    assert any(finding.code == "MISSING_ERROR_MESSAGE" for finding in result.findings)


def test_quality_gate_blocks_env_path() -> None:
    pack = ContextPack(
        context_pack_id="ctx_test",
        included_files=[ContextPackFile(path=".env", content_mode="full")],
    )
    result = evaluate_context_pack(pack)
    assert not result.passed
    assert any(finding.code == "SECRET_PATH_INCLUDED" for finding in result.findings)
