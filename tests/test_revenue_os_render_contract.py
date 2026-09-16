from pathlib import Path

import pytest


yaml = pytest.importorskip("yaml")
ROOT = Path(__file__).parents[1]


def _render():
    return yaml.safe_load((ROOT / "render.yaml").read_text(encoding="utf-8"))


def _service(config, name):
    return next(item for item in config["services"] if item["name"] == name)


def _env_map(service):
    result = {}
    for item in service.get("envVars", []):
        result[item["key"]] = item
    return result


def test_staging_revenue_os_isolated_and_kill_switched():
    config = _render()
    production = _service(config, "graxia-revenue-os")
    staging_names = {
        "graxia-revenue-os-staging",
        "graxia-revenue-os-staging-worker",
        "graxia-revenue-os-staging-beat",
    }
    services = {item["name"]: item for item in config["services"]}
    assert staging_names <= services.keys()
    assert production["dockerfilePath"] == services["graxia-revenue-os-staging"]["dockerfilePath"]

    for name in staging_names:
        service = services[name]
        env = _env_map(service)
        assert service["autoDeploy"] is False
        assert env["APP_ENV"]["value"] == "staging"
        assert env["NO_LIVE_PAYMENT_MODE"]["value"] == "true"
        assert env["KILL_SWITCH_ALL_EXTERNAL_BETA"]["value"] == "true"
        assert env["DATABASE_URL"]["fromDatabase"]["name"] == "graxia-db-staging"
        assert env["CELERY_BROKER_URL"]["fromService"]["name"] == "graxia-redis-staging"
        assert env["CELERY_RESULT_BACKEND"]["fromService"]["name"] == "graxia-redis-staging"


def test_staging_backing_resources_are_distinct():
    config = _render()

    assert {item["name"] for item in config["databases"]} >= {
        "graxia-db",
        "graxia-db-staging",
    }
    assert {item["name"] for item in config["redis"]} >= {
        "graxia-redis",
        "graxia-redis-staging",
    }
