"""Report inherited Python findings and fail CI on new findings or scan errors."""

import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys


def findings(scanner: str, root: Path) -> Counter[tuple[str, str, str]]:
    if scanner == "ruff":
        arguments = ["check", "--isolated", "--output-format", "json", "backend/app", "automation"]
    else:
        arguments = ["-r", "graxia/packages/quant_os", "-ll", "-f", "json", "-q"]

    result = subprocess.run(
        [sys.executable, "-m", scanner, *arguments],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(f"{scanner} exited with {result.returncode}: {result.stderr.strip()}")

    report = json.loads(result.stdout)
    if scanner == "bandit":
        if report["errors"]:
            paths = ", ".join(error["filename"] for error in report["errors"])
            raise RuntimeError(f"Bandit could not scan {paths}")
        rows = ((item["filename"], item["test_id"], item["issue_text"]) for item in report["results"])
    else:
        rows = ((item["filename"], item["code"], item["message"]) for item in report)

    return Counter(
        ((root / file).resolve().relative_to(root).as_posix(), rule, detail)
        for file, rule, detail in rows
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scanner", choices=("ruff", "bandit"))
    parser.add_argument("base", type=Path)
    args = parser.parse_args()

    base = findings(args.scanner, args.base.resolve())
    current = findings(args.scanner, Path.cwd().resolve())
    added = current - base
    print(f"{args.scanner}: {base.total()} base findings, {current.total()} current, {added.total()} new")
    for (file, rule, detail), count in sorted(added.items()):
        print(f"{file}: {rule}: {detail} ({count} new)")
    return int(bool(added))


if __name__ == "__main__":
    raise SystemExit(main())
