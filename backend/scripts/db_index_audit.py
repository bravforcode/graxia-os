from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.database import AsyncSessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=25)
    parser.add_argument("--output", default="reports/db_index_audit.json")
    parser.add_argument("--explain", action="store_true")
    return parser.parse_args()


async def table_has_pg_stat_statements(db) -> bool:
    result = await db.execute(
        text("SELECT 1 FROM pg_extension WHERE extname = 'pg_stat_statements' LIMIT 1")
    )
    return result.scalar_one_or_none() is not None


async def pg_stat_columns(db) -> set[str]:
    result = await db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = 'pg_stat_statements'
            """
        )
    )
    return {str(row[0]) for row in result.fetchall()}


def pick_stat_columns(cols: set[str]) -> dict[str, str]:
    total = "total_exec_time" if "total_exec_time" in cols else "total_time"
    mean = "mean_exec_time" if "mean_exec_time" in cols else "mean_time"
    return {"total": total, "mean": mean}


async def fetch_top_queries(db, limit: int) -> list[dict]:
    if not await table_has_pg_stat_statements(db):
        return []

    cols = await pg_stat_columns(db)
    picked = pick_stat_columns(cols)
    total_col = picked["total"]
    mean_col = picked["mean"]

    stmt = text(
        f"""
        SELECT query, calls, {total_col} AS total_ms, {mean_col} AS mean_ms, rows
        FROM pg_stat_statements
        WHERE query NOT ILIKE '%pg_stat_statements%'
        ORDER BY {total_col} DESC
        LIMIT :limit
        """
    )
    result = await db.execute(stmt, {"limit": limit})
    items = []
    for row in result.fetchall():
        items.append(
            {
                "query": row[0],
                "calls": int(row[1] or 0),
                "total_ms": float(row[2] or 0.0),
                "mean_ms": float(row[3] or 0.0),
                "rows": int(row[4] or 0),
            }
        )
    return items


async def fetch_unused_indexes(db, limit: int) -> list[dict]:
    stmt = text(
        """
        SELECT
          schemaname,
          relname AS table_name,
          indexrelname AS index_name,
          idx_scan,
          pg_size_pretty(pg_relation_size(indexrelid)) AS index_size
        FROM pg_stat_user_indexes
        WHERE idx_scan = 0
        ORDER BY pg_relation_size(indexrelid) DESC
        LIMIT :limit
        """
    )
    result = await db.execute(stmt, {"limit": limit})
    items = []
    for row in result.fetchall():
        items.append(
            {
                "schema": row[0],
                "table": row[1],
                "index": row[2],
                "idx_scan": int(row[3] or 0),
                "size": row[4],
            }
        )
    return items


async def explain_query(db, query: str) -> dict | None:
    try:
        explain = await db.execute(
            text(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {query}")
        )
        payload = explain.scalar_one_or_none()
        if payload is None:
            return None
        return {"plan": payload}
    except Exception:
        return None


async def main() -> int:
    args = parse_args()
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    async with AsyncSessionLocal() as db:
        has_pg_stat = await table_has_pg_stat_statements(db)
        top_queries = await fetch_top_queries(db, args.limit)
        unused_indexes = await fetch_unused_indexes(db, args.limit)

        explains: list[dict] = []
        if args.explain and top_queries:
            for item in top_queries[: min(10, len(top_queries))]:
                plan = await explain_query(db, item["query"])
                if plan is not None:
                    explains.append({"query": item["query"], "explain": plan})

        report = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "top_queries": top_queries,
            "unused_indexes": unused_indexes,
            "explains": explains,
            "notes": {
                "pg_stat_statements_enabled": has_pg_stat,
                "explain_limit": 10,
            },
        }
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(str(out_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
