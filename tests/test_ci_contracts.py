import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATHS = (
    REPO_ROOT / ".github" / "workflows" / "ci.yml",
    REPO_ROOT / ".github" / "workflows" / "security-gate.yml",
)
IMMUTABLE_ACTION_REF = re.compile(r"^\s+uses:\s+[^@\s]+@([0-9a-f]{40})\s*$", re.MULTILINE)


def _workflow_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_image_publication_requires_all_ci_quality_jobs_and_main():
    workflow = _workflow_text(WORKFLOW_PATHS[0])
    deploy = re.search(r"(?ms)^  deploy:\n.*?(?=^  \w+:|\Z)", workflow)

    assert deploy is not None
    deploy_body = deploy.group(0)
    needs = re.search(r"^    needs: \[(.*?)\]$", deploy_body, re.MULTILINE)

    assert needs is not None
    assert {
        "security_scan",
        "backend",
        "revenue_os",
        "frontend",
        "ops",
    } <= set(re.findall(r"[a-z_]+", needs.group(1)))
    assert "if: github.ref == 'refs/heads/main'" in deploy_body


def test_owned_ci_workflows_use_immutable_action_refs():
    for path in WORKFLOW_PATHS:
        workflow = _workflow_text(path)
        action_lines = re.findall(r"^\s+uses:.*$", workflow, re.MULTILINE)

        assert action_lines
        assert len(action_lines) == len(IMMUTABLE_ACTION_REF.findall(workflow))


def test_owned_ci_workflows_fail_closed_for_required_gates():
    for path in WORKFLOW_PATHS:
        workflow = _workflow_text(path)

        assert "continue-on-error:" not in workflow
        assert not re.search(r"\|\|\s*(?:true|echo\b)", workflow)


def test_trufflehog_is_pinned_in_each_owned_workflow():
    expected = "trufflesecurity/trufflehog@288a8a8643a2c5a36b81d231c550dccfa0beeb64"

    for path in WORKFLOW_PATHS:
        assert expected in _workflow_text(path)
