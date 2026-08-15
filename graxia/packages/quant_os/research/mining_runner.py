"""Direction I P1 mining runner — validation + absorb + write pipeline.

Consumed by subagent-driven mining (each source agent S1-S6 returns a JSON
payload of candidate entries). The runner is the single gatekeeper between
a mining agent's output and the catalog: nothing enters `research/catalog_i/`
without passing the P1 contract (spec §P1: source URL mandatory, no
fabrication, evidence tier assigned) and the A17 partition stamp.

A7 absorption: prior uncommitted research artifacts (e.g.
reports/research_retail_forex_eas_20260804.md) are converted to catalog
entries with attribution — never re-mined from scratch.
"""

from __future__ import annotations

import re
from pathlib import Path

from .catalog_schema import CATALOG_DIR, finalize_entry, write_raw

# ---------------------------------------------------------------------------
# A7 absorb — convert existing prior-research markdown tables into catalog rows
# ---------------------------------------------------------------------------

# Header cells in research_retail_forex_eas_20260804.md mapped to catalog fields.
_ABSORB_COLUMN_MAP = {
    "EA": "name",
    "Price USD": "price",
    "License model": "license",
    "Strategy type": "mechanism_desc",
    "Timeframe/Pairs": "tf_pairs",
    "Martingale/grid/recovery flag": "risk_flag",
    "Min deposit": "min_deposit",
    "Price source URL": "source_url",
}


def _table_rows(md_text: str) -> list[list[str]]:
    """Extract markdown table rows (skip header separator row)."""
    rows: list[list[str]] = []
    for line in md_text.splitlines():
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
            continue  # header separator row
        rows.append(cells)
    return rows


def absorb_retail_forex_eas(md_path: str | Path) -> list[dict]:
    """Convert the 2026-08-04 retail-EA research table into catalog entries.

    Only rows with a real source URL are absorbed; rows marked "Not found"
    are skipped (they carry no evidence to catalog).
    """
    text = Path(md_path).read_text(encoding="utf-8")
    rows = _table_rows(text)
    entries: list[dict] = []
    for row in rows:
        if len(row) < 8:
            continue
        name = row[0]
        url = row[7]
        if not url.startswith("http"):
            continue
        mechanism_desc = row[3]
        risk_flag = row[5]
        # A row that explicitly says the review does not mention a risk flag
        # is "not stated", not a fabricated placeholder.
        risk_lower = risk_flag.lower()
        if "not mentioned" in risk_lower or "unknown" in risk_lower or risk_flag in ("", "-", "—"):
            risk_note = "not stated"
        else:
            risk_note = risk_flag
        entries.append(
            {
                "source_id": "S2",  # retail EA vendor/review ecosystem
                "name": name,
                "source_url": url,
                "mechanism": "retail_ea_" + re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_"),
                "params": {
                    "price": row[1],
                    "license": row[2],
                    "strategy_type": mechanism_desc,
                    "timeframe_pairs": row[4],
                    "risk_flag": risk_note,
                    "min_deposit": row[6],
                },
                "claimed_perf": risk_note,
                "evidence_tier": "PRACTITIONER_LORE",  # vendor/review-site claims, unverified live
                "attribution": "A7 absorb from reports/research_retail_forex_eas_20260804.md",
            }
        )
    return entries


# ---------------------------------------------------------------------------
# Mining pipeline
# ---------------------------------------------------------------------------


def ingest_mining_output(
    source_id: str,
    raw_entries: list[dict],
    *,
    catalog_dir: str | Path = CATALOG_DIR,
) -> dict:
    """Validate + stamp + dedup + write a mining agent's output.

    Returns a summary dict: {accepted, rejected, rejected_errors, written,
    total_in_catalog}.

    No fabrication policy: entries failing the contract are REJECTED and
    reported — never silently dropped into the catalog.
    """
    accepted: list[dict] = []
    rejected_errors: dict[int, list[str]] = {}
    for idx, entry in enumerate(raw_entries):
        try:
            accepted.append(finalize_entry(entry, source_id=source_id))
        except ValueError as exc:
            rejected_errors[idx] = str(exc).split("; ")

    written = 0
    if accepted:
        path = write_raw(source_id, accepted, catalog_dir)
        written = len(accepted)
    else:
        path = None

    return {
        "source_id": source_id,
        "accepted": len(accepted),
        "rejected": len(rejected_errors),
        "rejected_errors": rejected_errors,
        "written": written,
        "output_path": str(path) if path else None,
    }


def absorb_prior_research(reports_dir: str | Path, catalog_dir: str | Path = CATALOG_DIR) -> dict:
    """A7 — absorb the uncommitted prior research artifacts into the catalog."""
    reports = Path(reports_dir)
    retail = reports / "research_retail_forex_eas_20260804.md"
    if not retail.exists():
        return {"absorbed": 0, "note": f"missing {retail.name}"}
    entries = absorb_retail_forex_eas(retail)
    if not entries:
        return {"absorbed": 0, "note": "no URL-bearing rows to absorb"}
    return ingest_mining_output("S2", entries, catalog_dir=catalog_dir)
