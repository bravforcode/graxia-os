# tests/test_run_clis.py
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _run(args):
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=ROOT)


def test_mining_cli_ingests_fixture(tmp_path):
    catalog = tmp_path / "catalog.json"
    r = _run(["scripts/run_mining.py", str(catalog), str(ROOT / "tests" / "fixtures" / "mining_sample.json")])
    assert r.returncode == 0, r.stderr
    assert "added 7" in r.stdout


def test_mining_cli_reports_bad_entries(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"entries": [{"name": "no-url"}]}), encoding="utf-8")
    r = _run(["scripts/run_mining.py", str(tmp_path / "catalog.json"), str(bad)])
    assert r.returncode == 1
    assert "source_url" in r.stderr


def test_taxonomy_cli_produces_canonical(tmp_path):
    catalog = tmp_path / "catalog.json"
    _run(["scripts/run_mining.py", str(catalog), str(ROOT / "tests" / "fixtures" / "mining_sample.json")])
    out = tmp_path / "canonical.json"
    r = _run(["scripts/run_taxonomy.py", str(catalog), str(out)])
    assert r.returncode == 0, r.stderr
    canon = json.loads(out.read_text(encoding="utf-8"))
    # 7 entries - 1 partition-CLOSED (forex4 trend_continuity H1 USDCAD) = 6
    assert len(canon["canonical"]) == 6


def test_triage_cli_produces_shortlist(tmp_path):
    catalog = tmp_path / "catalog.json"
    _run(["scripts/run_mining.py", str(catalog), str(ROOT / "tests" / "fixtures" / "mining_sample.json")])
    canon = tmp_path / "canonical.json"
    _run(["scripts/run_taxonomy.py", str(catalog), str(canon)])
    out = tmp_path / "shortlist.json"
    r = _run(["scripts/run_triage.py", str(canon), str(out)])
    assert r.returncode == 0, r.stderr
    sl = json.loads(out.read_text(encoding="utf-8"))
    # grid_martingale excluded (no gate pass); all survivors sorted literature first
    assert all(e.get("mechanism") != "grid_martingale" for e in sl["shortlist"])
    assert sl["shortlist"][0]["evidence_tier"] == "literature"
