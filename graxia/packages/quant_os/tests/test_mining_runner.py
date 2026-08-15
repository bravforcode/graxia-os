# tests/test_mining_runner.py
"""P1 mining runner tests — ingestion gatekeeping, dedup, A7 absorb, prompts."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research import catalog_schema  # noqa: E402
from research.mining_runner import (  # noqa: E402
    absorb_prior_research,
    absorb_retail_forex_eas,
    ingest_mining_output,
)


def _entry(**overrides) -> dict:
    entry = {
        "name": "Test EA",
        "source_url": "https://www.mql5.com/en/code/11111",
        "mechanism": "breakout_momentum",
        "params": {"period": 20},
        "claimed_perf": "+10% in 3 months (source claim)",
        "evidence_tier": "PRACTITIONER_LORE",
        "symbol": "XAUUSD",
        "timeframe": "M15",
    }
    entry.update(overrides)
    return entry


def test_ingest_accepts_valid_entries(tmp_path):
    result = ingest_mining_output("S1", [_entry()], catalog_dir=tmp_path)
    assert result["accepted"] == 1
    assert result["rejected"] == 0
    assert result["written"] == 1
    out = json.loads((tmp_path / "raw_S1.json").read_text(encoding="utf-8"))
    assert out["count"] == 1
    assert out["entries"][0]["source_url"].startswith("https://")


def test_ingest_rejects_fabricated_entries(tmp_path):
    result = ingest_mining_output("S1", [_entry(source_url=""), _entry(source_url="tbd")], catalog_dir=tmp_path)
    assert result["accepted"] == 0
    assert result["rejected"] == 2
    assert "rejected_errors" in result
    # nothing written
    assert not (tmp_path / "raw_S1.json").exists()


def test_ingest_dedups_identical_entries(tmp_path):
    result1 = ingest_mining_output("S1", [_entry()], catalog_dir=tmp_path)
    result2 = ingest_mining_output("S1", [_entry()], catalog_dir=tmp_path)
    assert result1["accepted"] == 1
    # same hash -> not re-added
    out = json.loads((tmp_path / "raw_S1.json").read_text(encoding="utf-8"))
    assert out["count"] == 1


def test_ingest_appends_distinct_entries(tmp_path):
    ingest_mining_output("S1", [_entry()], catalog_dir=tmp_path)
    ingest_mining_output(
        "S1", [_entry(name="Other EA", source_url="https://www.mql5.com/en/code/22222")], catalog_dir=tmp_path
    )
    out = json.loads((tmp_path / "raw_S1.json").read_text(encoding="utf-8"))
    assert out["count"] == 2


def test_catalog_stats_counts_per_source(tmp_path):
    ingest_mining_output("S1", [_entry()], catalog_dir=tmp_path)
    ingest_mining_output("S3", [_entry(source_url="https://www.myfxbook.com/members/x/y/1")], catalog_dir=tmp_path)
    stats = catalog_schema.catalog_stats(tmp_path)
    assert stats["total"] == 2
    assert stats["per_source"]["S1"] == 1
    assert stats["per_source"]["S3"] == 1


def test_absorb_retail_forex_eas_converts_table_rows(tmp_path):
    md = tmp_path / "research_retail_forex_eas_20260804.md"
    md.write_text(
        "| EA | Price USD | License model | Strategy type | Timeframe/Pairs | Martingale/grid/recovery flag | Min deposit | Price source URL |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| TestEA | $99 | One-time | Grid | M15; EURUSD | **YES** | $100 | https://example.com/testea |\n"
        "| GhostEA | Not found | — | — | — | Unknown | — | No review page found |\n"
        "| UnknownRiskEA | $50 | One-time | Scalp | M5; GBPUSD | Not mentioned in review | $200 | https://example.com/unkrisk |\n",
        encoding="utf-8",
    )
    entries = absorb_retail_forex_eas(md)
    # only URL-bearing rows are absorbed; "Not found" row has no URL
    assert len(entries) == 2
    assert entries[0]["source_url"] == "https://example.com/testea"
    assert entries[0]["mechanism"].startswith("retail_ea_")
    assert entries[0]["attribution"].startswith("A7 absorb")
    # "Not mentioned" risk flag is mapped to not-stated, not a placeholder
    assert entries[1]["params"]["risk_flag"] == "not stated"
    assert entries[1]["claimed_perf"] == "not stated"


def test_absorb_prior_research_writes_catalog(tmp_path):
    reports = tmp_path / "reports"
    reports.mkdir()
    (reports / "research_retail_forex_eas_20260804.md").write_text(
        "| EA | Price USD | License model | Strategy type | Timeframe/Pairs | Martingale/grid/recovery flag | Min deposit | Price source URL |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| TestEA | $99 | One-time | Grid | M15; EURUSD | **YES** | $100 | https://example.com/testea |\n",
        encoding="utf-8",
    )
    result = absorb_prior_research(reports, catalog_dir=tmp_path / "catalog_i")
    assert result["accepted"] == 1
    assert result["rejected"] == 0
    assert (tmp_path / "catalog_i" / "raw_S2.json").exists()


def test_mining_prompts_are_contract_shaped():
    sys.path.insert(0, str(ROOT / "scripts"))
    from mining_agent_prompts import SOURCES, build_all_prompts, build_prompt

    assert set(SOURCES) == {"S1", "S2", "S3", "S4", "S5", "S6"}
    prompts = build_all_prompts()
    assert len(prompts) == 6
    p = build_prompt("S1")
    assert "source_url" in p
    assert "NO FABRICATION" in p
    assert "MQL5" in p
