"""
Result store — DuckDB-backed storage for campaign results + ranking queries.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .campaign import CampaignConfig

RESULTS_DIR = Path(__file__).resolve().parent.parent / "reports" / "paper_engine"

# Try DuckDB; fall back to JSON files
_HAVE_DUCKDB = False
try:
    import duckdb

    _HAVE_DUCKDB = True
except ImportError:
    pass


class ResultStore:
    """Persistent result store backed by DuckDB or JSON files."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path) if path else RESULTS_DIR
        os.makedirs(self.path, exist_ok=True)

        self._db_path = self.path / "campaign_results.duckdb"
        self._con = None
        if _HAVE_DUCKDB:
            try:
                self._con = duckdb.connect(str(self._db_path))
                self._init_schema()
            except Exception:
                pass

    def _init_schema(self) -> None:
        """Create tables if they don't exist."""
        if not self._con:
            return
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS campaigns (
                campaign_id VARCHAR PRIMARY KEY,
                strategy_id VARCHAR,
                symbol VARCHAR,
                timeframe VARCHAR,
                run_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                total_trades INTEGER,
                total_pnl DOUBLE,
                sharpe DOUBLE,
                win_rate_pct DOUBLE,
                profit_factor DOUBLE,
                max_drawdown_pct DOUBLE,
                avg_confidence DOUBLE,
                data_bars INTEGER,
                error VARCHAR,
                params_json VARCHAR,
                trades_json VARCHAR
            )
        """)

    def save_result(self, result) -> None:
        """Save a single CampaignResult."""
        from .engine import CampaignResult

        if not isinstance(result, CampaignResult):
            return

        m = result.metrics
        if self._con:
            try:
                self._con.execute("""
                    INSERT OR REPLACE INTO campaigns
                    (campaign_id, strategy_id, symbol, timeframe, run_at,
                     total_trades, total_pnl, sharpe, win_rate_pct, profit_factor,
                     max_drawdown_pct, avg_confidence, data_bars, error,
                     params_json, trades_json)
                    VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP,
                            ?, ?, ?, ?, ?,
                            ?, ?, ?, ?,
                            ?, ?)
                """, [
                    result.config.campaign_id,
                    result.config.strategy_id,
                    result.config.symbol,
                    result.config.timeframe,
                    m.get("total_trades", 0),
                    m.get("total_pnl", 0),
                    m.get("sharpe", 0),
                    m.get("win_rate_pct", 0),
                    m.get("profit_factor", 0),
                    m.get("max_drawdown_pct", 0),
                    m.get("avg_confidence", 0),
                    m.get("data_bars", 0),
                    result.error,
                    json.dumps(result.config.params),
                    json.dumps([t.to_dict() for t in result.trades]),
                ])
            except Exception:
                pass

        # Always save individual JSON
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        cid = result.config.campaign_id
        path = self.path / f"{cid}_{ts}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2, default=str)

    def save_batch(self, results: list) -> None:
        """Save multiple results."""
        for r in results:
            self.save_result(r)
        if self._con:
            try:
                self._con.commit()
            except Exception:
                pass

    def get_ranking(self, top_n: int = 40) -> list[dict]:
        """Get top-N campaigns by Sharpe ratio."""
        if self._con:
            try:
                rows = self._con.execute("""
                    SELECT campaign_id, strategy_id, symbol, timeframe,
                           total_trades, total_pnl, sharpe, win_rate_pct,
                           profit_factor, max_drawdown_pct
                    FROM campaigns
                    WHERE error IS NULL
                      AND total_trades >= 100
                      AND sharpe IS NOT NULL
                    ORDER BY sharpe DESC
                    LIMIT ?
                """, [top_n]).fetchall()

                return [
                    {
                        "campaign_id": r[0],
                        "strategy": r[1],
                        "symbol": r[2],
                        "timeframe": r[3],
                        "trades": r[4],
                        "pnl": r[5],
                        "sharpe": r[6],
                        "win_rate": r[7],
                        "profit_factor": r[8],
                        "max_dd": r[9],
                    }
                    for r in rows
                ]
            except Exception:
                pass

        # Fallback: read from JSON
        return self._ranking_from_json(top_n)

    def _ranking_from_json(self, top_n: int) -> list[dict]:
        """Read all JSON result files and build ranking."""
        rankings = []
        for f in sorted(self.path.glob("camp_*.json")):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                m = data.get("metrics", {})
                if m.get("total_trades", 0) >= 100 and m.get("sharpe") is not None:
                    rankings.append({
                        "campaign_id": data.get("campaign_id", ""),
                        "strategy": m.get("strategy", ""),
                        "symbol": m.get("symbol", ""),
                        "timeframe": m.get("timeframe", ""),
                        "trades": m.get("total_trades", 0),
                        "pnl": m.get("total_pnl", 0),
                        "sharpe": m.get("sharpe", 0),
                        "win_rate": m.get("win_rate_pct", 0),
                        "profit_factor": m.get("profit_factor", 0),
                        "max_dd": m.get("max_drawdown_pct", 0),
                    })
            except Exception:
                continue

        rankings.sort(key=lambda r: r["sharpe"], reverse=True)
        return rankings[:top_n]

    def save_ranking(self, rankings: list[dict]) -> str | None:
        """Save ranking report as JSON + Markdown."""
        if not rankings:
            return None

        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        json_path = self.path / f"ranking_{ts}.json"
        with open(json_path, "w") as f:
            json.dump(rankings, f, indent=2)

        # Markdown report
        md_path = self.path / f"ranking_{ts}.md"
        lines = [
            "# Campaign Ranking Report",
            f"Generated: {datetime.now(UTC).isoformat()}",
            "",
            f"Top {len(rankings)} campaigns by Sharpe ratio (min 100 trades)",
            "",
            "| Rank | Campaign | Strategy | Symbol | TF | Trades | P&L | Sharpe | WR% | PF | MaxDD% |",
            "|------|----------|----------|-------|-----|--------|-----|--------|-----|-----|--------|",
        ]
        for i, r in enumerate(rankings, 1):
            lines.append(
                f"| {i} | {r['campaign_id']} | {r['strategy']} | {r['symbol']} | {r['timeframe']} "
                f"| {r['trades']} | ${r['pnl']:+.0f} | {r['sharpe']:.3f} | {r['win_rate']:.1f}% "
                f"| {r['profit_factor']:.2f} | {r['max_dd']:.1f}% |"
            )

        md_path.write_text("\n".join(lines), encoding="utf-8")
        return str(md_path)

    def get_trades_json(self, campaign_id: str) -> str | None:
        """Fetch trades_json for a specific campaign from DuckDB."""
        if self._con:
            try:
                row = self._con.execute(
                    "SELECT trades_json FROM campaigns WHERE campaign_id = ?",
                    [campaign_id]
                ).fetchone()
                if row and row[0] and len(row[0]) > 2:  # more than "[]"
                    return row[0]
            except Exception:
                pass
        # Fallback: read from JSON file
        for f in sorted(self.path.glob(f"{campaign_id}_*.json")):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                trades = data.get("trades", [])
                if trades:
                    return json.dumps(trades)
            except Exception:
                continue
        return None

    def get_stats(self) -> dict:
        """Get overall campaign statistics."""
        if self._con:
            try:
                row = self._con.execute("""
                    SELECT
                        COUNT(*) as total,
                        COUNT(*) FILTER (WHERE error IS NULL) as success,
                        COUNT(*) FILTER (WHERE error IS NOT NULL) as failed,
                        COUNT(*) FILTER (WHERE total_trades >= 100) as viable,
                        AVG(sharpe) FILTER (WHERE sharpe IS NOT NULL) as avg_sharpe,
                        MAX(sharpe) as best_sharpe,
                        COUNT(*) FILTER (WHERE sharpe > 1.0) as sharpe_gt_1,
                        COUNT(*) FILTER (WHERE sharpe > 2.0) as sharpe_gt_2
                    FROM campaigns
                """).fetchone()
                if row:
                    return {
                        "total": row[0],
                        "success": row[1],
                        "failed": row[2],
                        "viable": row[3],
                        "avg_sharpe": round(row[4], 3) if row[4] else 0,
                        "best_sharpe": round(row[5], 3) if row[5] else 0,
                        "sharpe_gt_1": row[6],
                        "sharpe_gt_2": row[7],
                    }
            except Exception:
                pass
        return {"total": 0}

    def close(self) -> None:
        if self._con:
            try:
                self._con.close()
            except Exception:
                pass
