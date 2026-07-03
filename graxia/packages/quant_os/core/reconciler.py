# DEPRECATED: Use execution/reconciler.py instead. Will be removed in Phase 5.
"""
State Reconciler — runs after every MT5 reconnect.

Compares DuckDB open trades vs MT5 actual positions.
Detects Ghost Trades (in DuckDB but not MT5) and Orphan Trades (in MT5 but not DuckDB).

Triggered on: mt5_ingester.reconnected event
"""
import structlog
from typing import List, Dict, Optional
from datetime import datetime, UTC

logger = structlog.get_logger()


class StateReconciler:
    """
    Post-reconnect state reconciliation between DuckDB and MT5.

    Ghost Trade: In DuckDB as OPEN, but not in MT5 → mark CLOSED_BY_DISCONNECT
    Orphan Trade: In MT5 but not in DuckDB → import with SL/TP from MT5
    """

    def __init__(self, duckdb_con, mt5_module=None):
        self._con = duckdb_con
        self._mt5 = mt5_module
        self._reconciliations: List[Dict] = []

    def reconcile(self, mt5_positions: Optional[List[Dict]] = None) -> Dict:
        """
        Run full reconciliation.

        Args:
            mt5_positions: List of dicts from mt5.positions_get().
                           Each dict should have: symbol, volume, ticket, profit, sl, tp.

        Returns:
            Dict with ghost_count, orphan_count, actions taken.
        """
        if mt5_positions is None:
            mt5_positions = self._fetch_mt5_positions()

        # Get open trades from DuckDB
        db_trades = self._get_db_open_trades()

        mt5_by_symbol = {}
        for pos in mt5_positions:
            sym = pos.get("symbol", "")
            if sym not in mt5_by_symbol:
                mt5_by_symbol[sym] = []
            mt5_by_symbol[sym].append(pos)

        ghosts = []
        orphans = []

        # Check Ghost Trades (in DuckDB but not in MT5)
        for trade in db_trades:
            symbol = trade.get("symbol", "")
            trade_id = trade.get("trade_id", "")

            if symbol not in mt5_by_symbol or len(mt5_by_symbol[symbol]) == 0:
                # No MT5 position for this symbol — Ghost Trade
                ghosts.append(trade)
                self._close_ghost(trade_id, "CLOSED_BY_DISCONNECT")

        # Check Orphan Trades (in MT5 but not in DuckDB)
        db_symbols = {t.get("symbol") for t in db_trades}
        for symbol, positions in mt5_by_symbol.items():
            if symbol not in db_symbols:
                for pos in positions:
                    orphans.append(pos)
                    self._import_orphan(pos)

        result = {
            "timestamp": datetime.now(UTC).isoformat(),
            "db_open_trades": len(db_trades),
            "mt5_positions": len(mt5_positions),
            "ghosts_found": len(ghosts),
            "orphans_found": len(orphans),
            "ghosts_closed": len(ghosts),
            "orphans_imported": len(orphans),
        }

        if ghosts or orphans:
            logger.warning(
                "reconciliation_issues_found",
                ghosts=len(ghosts),
                orphans=len(orphans),
            )
        else:
            logger.info("reconciliation_clean", db_trades=len(db_trades), mt5_positions=len(mt5_positions))

        self._reconciliations.append(result)
        return result

    def _fetch_mt5_positions(self) -> List[Dict]:
        """Fetch current positions from MT5."""
        if self._mt5 is None:
            return []
        try:
            positions = self._mt5.positions_get()
            if positions is None:
                return []
            return [
                {
                    "symbol": p.symbol,
                    "volume": p.volume,
                    "ticket": p.ticket,
                    "profit": p.profit,
                    "sl": p.sl,
                    "tp": p.tp,
                    "price_open": p.price_open,
                    "time": p.time,
                }
                for p in positions
            ]
        except Exception as e:
            logger.error("mt5_positions_fetch_failed", error=str(e))
            return []

    def _get_db_open_trades(self) -> List[Dict]:
        """Get all OPEN trades from DuckDB shadow_trades."""
        try:
            result = self._con.execute(
                "SELECT trade_id, symbol, side, entry_price, quantity, status "
                "FROM shadow_trades WHERE status = 'OPEN'"
            ).fetchall()
            return [
                {"trade_id": r[0], "symbol": r[1], "side": r[2],
                 "entry_price": r[3], "quantity": r[4], "status": r[5]}
                for r in result
            ]
        except Exception as e:
            logger.error("db_open_trades_fetch_failed", error=str(e))
            return []

    def _close_ghost(self, trade_id: str, reason: str) -> None:
        """Mark a ghost trade as closed in DuckDB."""
        try:
            self._con.execute(
                "UPDATE shadow_trades SET status = ?, closed_at = ? WHERE trade_id = ?",
                [reason, datetime.now(UTC).isoformat(), trade_id],
            )
            logger.info("ghost_trade_closed", trade_id=trade_id, reason=reason)
        except Exception as e:
            logger.error("ghost_close_failed", trade_id=trade_id, error=str(e))

    def _import_orphan(self, mt5_position: Dict) -> None:
        """Import an orphan trade from MT5 into DuckDB."""
        try:
            self._con.execute(
                "INSERT INTO shadow_trades "
                "(trade_id, symbol, side, entry_price, quantity, status, "
                " stop_loss, take_profit, opened_at, close_reason) "
                "VALUES (?, ?, ?, ?, ?, 'OPEN', ?, ?, ?, 'MT5_IMPORT')",
                [
                    f"ORPHAN_{mt5_position['ticket']}",
                    mt5_position["symbol"],
                    "BUY" if mt5_position["volume"] > 0 else "SELL",
                    mt5_position["price_open"],
                    abs(mt5_position["volume"]),
                    mt5_position.get("sl", 0),
                    mt5_position.get("tp", 0),
                    datetime.fromtimestamp(mt5_position["time"], tz=UTC).isoformat(),
                ],
            )
            logger.info(
                "orphan_trade_imported",
                ticket=mt5_position["ticket"],
                symbol=mt5_position["symbol"],
            )
        except Exception as e:
            logger.error("orphan_import_failed", ticket=mt5_position.get("ticket"), error=str(e))

    def get_reconciliation_history(self) -> List[Dict]:
        """Return history of all reconciliations."""
        return self._reconciliations.copy()
