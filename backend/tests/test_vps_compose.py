from pathlib import Path

import pytest
import yaml

VPS_DIR = Path(__file__).resolve().parents[2] / "deploy" / "vps"
SERVICES = ("postgres", "redis", "backend", "frontend", "celery", "beat")


class _Loader(yaml.SafeLoader):
    """SafeLoader that accepts compose-only tags such as !override / !reset."""


def _construct_tagged(loader, suffix, node):
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    if isinstance(node, yaml.MappingNode):
        return loader.construct_mapping(node, deep=True)
    return loader.construct_scalar(node)


for _tag in ("!override", "!reset"):
    _Loader.add_multi_constructor(_tag, _construct_tagged)


def _load(name: str) -> dict:
    return yaml.load((VPS_DIR / name).read_text(encoding="utf-8"), Loader=_Loader)


def _merged_services() -> dict:
    base = _load("docker-compose.base.yml")
    override = _load("docker-compose.production.override.yml")
    services = {name: dict(spec or {}) for name, spec in base.get("services", {}).items()}
    for name, spec in override.get("services", {}).items():
        services.setdefault(name, {}).update(spec or {})
    return services


@pytest.mark.parametrize("service", SERVICES)
def test_service_has_healthcheck(service):
    assert _merged_services()[service].get("healthcheck", {}).get("test"), f"{service} has no healthcheck"


@pytest.mark.parametrize("service", SERVICES)
def test_service_has_log_limit(service):
    options = _merged_services()[service].get("logging", {}).get("options", {})
    assert options.get("max-size"), f"{service} logs grow without limit"


def test_backend_image_tag_comes_from_env():
    for service in ("backend", "celery", "beat"):
        image = _merged_services()[service]["image"]
        assert image.startswith("graxia-backend:${GRAXIA_BACKEND_TAG"), f"{service} pins {image}"
