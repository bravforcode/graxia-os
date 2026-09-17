import json
from datetime import datetime, timezone
from pathlib import Path

import pytest


SCHEMA_PATH = Path(__file__).parents[1] / "app" / "contracts" / "social_video_analysis.schema.json"


def valid_result():
    stamp = datetime(2026, 9, 16, tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
    return {
        "schema_version": "1.0",
        "consent": {
            "cloud_media_egress": False,
            "transcript_egress": False,
            "granted_at": stamp,
            "granted_by": "operator-1",
        },
        "stages": [{"stage": "fetch", "status": "complete", "evidence_ref": "safe:fetch-1"}],
        "result_hash": "sha256:" + "a" * 64,
        "lease": {"owner": "worker-1", "acquired_at": stamp, "expires_at": stamp},
        "publish_blocked": True,
    }


def test_schema_declares_safety_fields():
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    assert set(schema["required"]) == {
        "schema_version",
        "consent",
        "stages",
        "result_hash",
        "lease",
        "publish_blocked",
    }
    assert schema["properties"]["result_hash"]["pattern"].startswith("^sha256:")


def test_valid_fixture_passes_jsonschema_when_available():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))

    jsonschema.Draft202012Validator(schema).validate(valid_result())


def test_missing_consent_is_rejected_when_jsonschema_available():
    jsonschema = pytest.importorskip("jsonschema")
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    invalid = valid_result()
    del invalid["consent"]

    with pytest.raises(jsonschema.ValidationError):
        jsonschema.Draft202012Validator(schema).validate(invalid)
