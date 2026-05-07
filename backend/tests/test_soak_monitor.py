from app.core.soak_monitor import parse_system_health_payload


def test_parse_system_health_payload_full_ok():
    payload = {"status": "full", "readiness": {"mode": "full", "issues": []}}
    snapshot = parse_system_health_payload(payload, 200)
    assert snapshot.ok is True
    assert snapshot.mode == "full"
    assert snapshot.issues == []


def test_parse_system_health_payload_degraded_ok():
    payload = {
        "status": "degraded",
        "readiness": {"mode": "degraded", "issues": ["redis unavailable"]},
    }
    snapshot = parse_system_health_payload(payload, 200)
    assert snapshot.ok is True
    assert snapshot.mode == "degraded"
    assert snapshot.issues == ["redis unavailable"]


def test_parse_system_health_payload_blocked_not_ok():
    payload = {
        "status": "blocked",
        "readiness": {"mode": "blocked", "issues": ["Database: cannot connect"]},
    }
    snapshot = parse_system_health_payload(payload, 200)
    assert snapshot.ok is False
    assert snapshot.mode == "blocked"
    assert snapshot.issues == ["Database: cannot connect"]


def test_parse_system_health_payload_non_200_not_ok():
    payload = {"readiness": {"mode": "full", "issues": []}}
    snapshot = parse_system_health_payload(payload, 503)
    assert snapshot.ok is False
    assert snapshot.mode == "full"


def test_parse_system_health_payload_missing_readiness():
    payload = {"status": "ok"}
    snapshot = parse_system_health_payload(payload, 200)
    assert snapshot.ok is False
    assert snapshot.mode == "unknown"
