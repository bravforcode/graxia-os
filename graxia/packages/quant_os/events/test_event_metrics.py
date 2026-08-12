"""Tests for event metrics."""
import tempfile
from graxia.packages.quant_os.events.event_metrics import EventMetrics


def test_metrics_creates():
    m = EventMetrics()
    assert m.get_summary()["events_received"] == 0


def test_metrics_records():
    m = EventMetrics()
    m.record_event_received("NFP", "HIGH")
    m.record_block("NFP", "pre_event", 500)
    s = m.get_summary()
    assert s["events_received"] == 1
    assert s["events_blocked"] == 1
    assert s["block_rate"] == 1.0


def test_metrics_export():
    m = EventMetrics()
    m.record_event_received("NFP", "HIGH")
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        m.export(f.name)
        import json
        data = json.loads(f.read())
        assert data["events_received"] == 1
