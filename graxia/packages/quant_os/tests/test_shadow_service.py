"""Test shadow service supervisor."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def test_shadow_service_import():
    """shadow_service.py should be importable."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "shadow_service",
        str(Path(__file__).parent.parent / "scripts" / "shadow_service.py"),
    )
    assert spec is not None, "Could not find shadow_service.py"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "run"), "shadow_service should have run() function"
    assert hasattr(mod, "MAX_RESTARTS"), "shadow_service should have MAX_RESTARTS"
    assert hasattr(mod, "RESTART_DELAY"), "shadow_service should have RESTART_DELAY"


def test_shadow_service_config():
    """Shadow service should have sensible defaults."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "shadow_service",
        str(Path(__file__).parent.parent / "scripts" / "shadow_service.py"),
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    assert mod.MAX_RESTARTS >= 10, f"MAX_RESTARTS too low: {mod.MAX_RESTARTS}"
    assert mod.RESTART_DELAY >= 5, f"RESTART_DELAY too low: {mod.RESTART_DELAY}"
    assert mod.RESTART_DELAY <= 60, f"RESTART_DELAY too high: {mod.RESTART_DELAY}"


if __name__ == "__main__":
    test_shadow_service_import()
    print("PASS: import")
    test_shadow_service_config()
    print("PASS: config")
    print("All shadow service tests passed!")
