"""Direction I P1 — deep-research harness CLI (spec §P1).

Entry point for the massive-mining campaign:
  - absorb:  A7 absorb prior uncommitted research artifacts into the catalog
  - ingest:  validate + dedup + write a subagent's JSON payload (file or stdin)
  - stats:   per-source progress toward the 2,500-entry target
  - prompt:  print the mining contract for a source agent (S1-S6)

Example:
  python scripts/run_p1_mining.py absorb
  python scripts/run_p1_mining.py ingest S1 path/to/payload.json
  python scripts/run_p1_mining.py stats
  python scripts/run_p1_mining.py prompt S5
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from research.catalog_schema import SOURCE_IDS, catalog_stats, load_raw  # noqa: E402
from research.mining_runner import absorb_prior_research, ingest_mining_output  # noqa: E402
from scripts.mining_agent_prompts import build_prompt  # noqa: E402


def _cmd_absorb(args: argparse.Namespace) -> int:
    result = absorb_prior_research(Path(args.reports_dir))
    print(json.dumps(result, indent=2))
    return 0


def _cmd_ingest(args: argparse.Namespace) -> int:
    if args.source_id not in SOURCE_IDS:
        print(f"ERROR: source_id must be one of {SOURCE_IDS}")
        return 2
    payload = sys.stdin.read() if args.payload == "-" else Path(args.payload).read_text(encoding="utf-8")
    data = json.loads(payload)
    entries = data["entries"] if isinstance(data, dict) and "entries" in data else data
    result = ingest_mining_output(args.source_id, entries)
    print(json.dumps(result, indent=2))
    return 0 if result["rejected"] == 0 else 1


def _cmd_stats(args: argparse.Namespace) -> int:
    print(json.dumps(catalog_stats(), indent=2))
    return 0


def _cmd_prompt(args: argparse.Namespace) -> int:
    if args.source_id not in SOURCE_IDS:
        print(f"ERROR: source_id must be one of {SOURCE_IDS}")
        return 2
    print(build_prompt(args.source_id))
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    """Write a P1 progress report to reports/."""
    stats = catalog_stats()
    lines = [
        "# Direction I P1 — Mining Progress Report",
        "",
        f"Generated: {args.timestamp}",
        "",
        f"Total catalog entries: **{stats['total']}** (target 2,500)",
        "",
        "| Source | Entries |",
        "|---|---|",
    ]
    for sid in SOURCE_IDS:
        lines.append(f"| {sid} | {stats['per_source'][sid]} |")
    lines.append("")
    lines.append("Evidence tiers present:")
    tiers: dict[str, int] = {}
    for sid in SOURCE_IDS:
        for e in load_raw(sid):
            tier = str(e.get("evidence_tier", "?"))
            tiers[tier] = tiers.get(tier, 0) + 1
    for tier, count in sorted(tiers.items()):
        lines.append(f"- {tier}: {count}")
    lines.append("")
    lines.append(
        "Notes: no fabrication — every entry carries a real source_url; blocked sources recorded, never guessed."
    )
    lines.append("")
    out = Path(args.reports_dir) / "direction_i_p1_mining_progress.md"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Direction I P1 deep-research harness")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_absorb = sub.add_parser("absorb", help="A7 absorb prior research artifacts")
    p_absorb.add_argument("--reports-dir", default="reports")
    p_absorb.set_defaults(func=_cmd_absorb)

    p_ingest = sub.add_parser("ingest", help="validate + write a mining payload")
    p_ingest.add_argument("source_id", choices=SOURCE_IDS)
    p_ingest.add_argument("payload", help="JSON file path, or '-' for stdin")
    p_ingest.set_defaults(func=_cmd_ingest)

    p_stats = sub.add_parser("stats", help="catalog progress toward 2,500 target")
    p_stats.set_defaults(func=_cmd_stats)

    p_prompt = sub.add_parser("prompt", help="print a source agent's mining contract")
    p_prompt.add_argument("source_id", choices=SOURCE_IDS)
    p_prompt.set_defaults(func=_cmd_prompt)

    p_report = sub.add_parser("report", help="write P1 progress report to reports/")
    p_report.add_argument("--reports-dir", default="reports")
    p_report.add_argument("--timestamp", default="2026-08-06")
    p_report.set_defaults(func=_cmd_report)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
