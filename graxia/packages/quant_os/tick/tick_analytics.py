"""Phase BE-P2 — Tick analytics with DuckDB. Optional, add when needed."""
import json
from pathlib import Path


class TickAnalytics:
    """Analytical queries over tick data. DuckDB optional."""

    def __init__(self, db_path: str = ""):
        self._db_path = db_path
        self._conn = None

    def connect(self) -> bool:
        """Connect to DuckDB. Returns False if unavailable."""
        try:
            import duckdb
            self._conn = duckdb.connect(self._db_path or ":memory:")
            return True
        except ImportError:
            return False

    def query_spread_stats(self, ticks: list[dict]) -> dict:
        """Compute spread stats from tick list (stdlib fallback)."""
        if not ticks:
            return {"p50": 0, "p90": 0, "p99": 0, "max": 0, "count": 0}

        spreads = []
        for t in ticks:
            bid = t.get("bid", 0)
            ask = t.get("ask", 0)
            if bid > 0 and ask > 0:
                spreads.append(ask - bid)

        if not spreads:
            return {"p50": 0, "p90": 0, "p99": 0, "max": 0, "count": 0}

        spreads.sort()
        n = len(spreads)
        return {
            "p50": spreads[n // 2],
            "p90": spreads[int(n * 0.9)],
            "p99": spreads[int(n * 0.99)],
            "max": spreads[-1],
            "count": n,
        }

    def export_parquet(self, ticks: list[dict], output_path: str) -> bool:
        """Export ticks to parquet. Falls back to JSONL if pyarrow unavailable."""
        try:
            import pyarrow as pa
            import pyarrow.parquet as pq

            if not ticks:
                return False

            # Convert to arrow table
            arrays = {}
            for key in ticks[0].keys():
                values = [t.get(key) for t in ticks]
                try:
                    arrays[key] = pa.array(values)
                except Exception:
                    arrays[key] = pa.array([str(v) for v in values])

            table = pa.table(arrays)
            pq.write_table(table, output_path)
            return True
        except ImportError:
            # Fallback: write as JSONL with .parquet extension marker
            path = Path(output_path)
            path.with_suffix(".jsonl").write_text(
                "\n".join(json.dumps(t, default=str) for t in ticks)
            )
            return True

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None
