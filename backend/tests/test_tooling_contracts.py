import os
from pathlib import Path
import subprocess
import sys

import yaml

from app.main import app
from scripts.export_openapi import export_openapi


def test_export_openapi_writes_current_api_surface(tmp_path: Path):
    output_path = tmp_path / "openapi.json"

    written = export_openapi(output_path)

    assert written == output_path
    assert output_path.exists()

    payload = output_path.read_text(encoding="utf-8")
    assert '"openapi"' in payload
    assert "/api/v1/system/health" in payload
    assert "/api/v1/commands/execute" in payload
    assert app.title in payload


def test_export_openapi_skips_google_oauth_when_workspace_credentials_are_placeholders(
    tmp_path: Path,
):
    backend_root = Path(__file__).resolve().parents[1]
    output_path = tmp_path / "openapi.json"
    env = os.environ.copy()
    env.update(
        {
            "GOOGLE_CLIENT_ID": "your_google_client_id",
            "GOOGLE_CLIENT_SECRET": "your_google_client_secret",
            "GOOGLE_REFRESH_TOKEN": "your_google_refresh_token",
            "GOOGLE_WORKSPACE_EMAIL": "your_google_workspace_email",
        }
    )

    result = subprocess.run(
        [sys.executable, "scripts/export_openapi.py", "--output", str(output_path)],
        cwd=backend_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )

    combined_output = f"{result.stdout}\n{result.stderr}"

    assert result.returncode == 0
    assert output_path.exists()
    assert "invalid_client" not in combined_output


def test_smoke_script_uses_curl_timeouts():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "smoke_tests.sh"
    script = script_path.read_text(encoding="utf-8")

    assert "--connect-timeout" in script
    assert "--max-time" in script


def test_setup_script_uses_env_example_and_modern_compose():
    repo_root = Path(__file__).resolve().parents[2]
    script = (repo_root / "setup.sh").read_text(encoding="utf-8")

    assert "cp .env.example .env" in script
    assert "docker compose" in script
    assert "docker-compose" not in script
    assert "http://localhost:3000" not in script


def test_compose_has_backend_healthcheck_and_profile_safe_dependencies():
    repo_root = Path(__file__).resolve().parents[2]
    compose = yaml.safe_load((repo_root / "docker-compose.yml").read_text(encoding="utf-8"))
    services = compose["services"]

    backend = services["backend"]
    frontend = services["frontend"]

    assert "healthcheck" in backend
    assert backend["depends_on"]["postgres"]["required"] is False
    assert backend["depends_on"]["redis"]["condition"] == "service_healthy"
    assert frontend["depends_on"]["backend"]["condition"] == "service_healthy"
