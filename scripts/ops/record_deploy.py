#!/usr/bin/env python3
"""Persist production deploy metadata after smoke tests pass."""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database import AsyncSessionLocal
from app.models.deploy_history import DeployHistory


async def record(args: argparse.Namespace) -> None:
    async with AsyncSessionLocal() as session:
        session.add(
            DeployHistory(
                commit_sha=args.commit_sha,
                backend_digest=args.backend_digest,
                frontend_digest=args.frontend_digest,
                operator=args.operator,
                migration_version=args.migration_version,
                smoke_test_result=args.smoke_test_result,
                rollback_limited=args.rollback_limited,
            )
        )
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit-sha", required=True)
    parser.add_argument("--backend-digest", required=True)
    parser.add_argument("--frontend-digest", required=True)
    parser.add_argument("--operator", required=True)
    parser.add_argument("--migration-version", default="")
    parser.add_argument("--smoke-test-result", default="pass")
    parser.add_argument("--rollback-limited", action="store_true")
    args = parser.parse_args()
    asyncio.run(record(args))


if __name__ == "__main__":
    main()
