"""
Kill Switch — Persistent kill switch with Telegram command interface.

Supports three close modes:
  - CLOSE_ALL: Close every open position immediately.
  - CLOSE_RISK_INCREASING_ONLY: Close only positions that would increase risk
    (e.g., losing positions in a drawdown scenario).
  - NO_NEW_ORDERS_ONLY: Block new orders but leave existing positions untouched.
"""

import json
import logging
import os
import time
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

logger = logging.getLogger(__name__)

ASSET_CLASS_COMMANDS: dict[str, list[str]] = {
    "metals": ["XAUUSD", "XAGUSD", "XAUEUR", "XAUJPY"],
    "crypto": ["BTCUSD", "ETHUSD", "SOLUSD", "ADAUSD", "XRPUSD"],
    "forex": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "USDCHF", "NZDUSD", "EURGBP", "EURJPY", "GBPJPY"],
    "indices": ["US30", "NAS100", "SPX500", "GER40", "UK100", "JP225"],
}


class KillSwitchState(str, Enum):
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    INACTIVE = "INACTIVE"


class CloseMode(str, Enum):
    """Defines what the kill switch does with open positions."""

    CLOSE_ALL = "CLOSE_ALL"
    CLOSE_RISK_INCREASING_ONLY = "CLOSE_RISK_INCREASING_ONLY"
    NO_NEW_ORDERS_ONLY = "NO_NEW_ORDERS_ONLY"


class BrokerAdapterLike(Protocol):
    """Minimal broker adapter interface for kill-switch position closing."""

    def get_positions(self) -> list[dict]: ...
    def close_position(self, ticket: int) -> Any: ...


class ReadonlyClientLike(Protocol):
    """Read-only broker client for state reconciliation after close attempts."""

    def get_positions(self) -> list[dict]: ...


class KillSwitch:
    def __init__(
        self,
        state_file: str = "data/kill_switch_state.json",
        broker_adapter: BrokerAdapterLike | None = None,
        close_mode: CloseMode = CloseMode.CLOSE_ALL,
        coordinator: Any | None = None,
    ):
        self._state_file = Path(state_file)
        self._allowed_users: set[int] = self._load_allowed_users()
        self._state: dict[str, Any] = self._load()
        self._last_user_id: int | None = None
        self._broker_adapter = broker_adapter
        self._close_mode = close_mode
        self._coordinator = coordinator
        # Idempotent close tracking: ticket -> closed_at timestamp
        self._closed_tickets: dict[int, str] = self._state.get("closed_tickets", {})

    def is_active(self) -> bool:
        return self._get_state_enum() == KillSwitchState.ACTIVE

    def is_paused(self) -> bool:
        return self._get_state_enum() == KillSwitchState.PAUSED

    def is_class_killed(self, asset_class: str) -> bool:
        if self._get_state_enum() == KillSwitchState.ACTIVE:
            return True
        return asset_class.lower() in self._state.get("killed_classes", [])

    @property
    def is_triggered(self) -> bool:
        return self.is_active() or self.is_paused()

    @property
    def trigger_type(self) -> str:
        return self._state.get("state", KillSwitchState.INACTIVE.value)

    def get_status(self) -> dict[str, Any]:
        return {
            "state": self._state.get("state", KillSwitchState.INACTIVE.value),
            "killed_classes": self._state.get("killed_classes", []),
            "reason": self._state.get("reason", ""),
            "activated_at_utc": self._state.get("activated_at_utc"),
            "authorized_by": self._state.get("authorized_by"),
        }

    def handle_command(self, command: str, user_id: int) -> str:
        if not self._is_authorized(user_id):
            return f"UNAUTHORIZED: user {user_id} not in TELEGRAM_ALLOWED_USERS"
        cmd = command.strip().lower().split()[0]
        self._last_user_id = user_id
        handlers: dict[str, Any] = {
            "/kill_all": self._cmd_kill_all,
            "/kill_metals": lambda: self._cmd_kill_class("metals"),
            "/kill_crypto": lambda: self._cmd_kill_class("crypto"),
            "/kill_forex": lambda: self._cmd_kill_class("forex"),
            "/kill_indices": lambda: self._cmd_kill_class("indices"),
            "/pause": self._cmd_pause,
            "/resume": self._cmd_resume,
        }
        handler = handlers.get(cmd)
        if handler is None:
            return f"UNKNOWN COMMAND: {cmd}"
        return handler()

    def set_coordinator(self, coordinator: Any) -> None:
        """Wire in the StateCoordinator for cross-store sync."""
        self._coordinator = coordinator

    def activate(self, reason: str, source: str = "manual") -> None:
        self._set_state(KillSwitchState.ACTIVE, reason=reason, authorized_by=source)
        self._notify_coordinator(True, reason, source)

    def deactivate(self, reason: str, authorized_by: str = "system") -> None:
        self._set_state(KillSwitchState.INACTIVE, reason=reason, authorized_by=authorized_by)
        self._state["killed_classes"] = []
        self._save()
        self._notify_coordinator(False, reason, authorized_by)

    def _notify_coordinator(self, active: bool, reason: str, source: str) -> None:
        """Propagate state change to coordinator for cross-store sync."""
        if self._coordinator is not None:
            self._coordinator.sync_kill_switch(active, reason, source, triggering_store="kill_switch")

    def _cmd_kill_all(self) -> str:
        source = f"telegram:{self._last_user_id}"
        self._set_state(KillSwitchState.ACTIVE, reason="Telegram /kill_all", authorized_by=source)
        self._notify_coordinator(True, "Telegram /kill_all", source)
        return "KILL SWITCH ACTIVATED — all trading halted."

    def _cmd_kill_class(self, asset_class: str) -> str:
        killed = self._state.get("killed_classes", [])
        if asset_class not in killed:
            killed.append(asset_class)
            self._state["killed_classes"] = killed
        self._append_history(f"/kill_{asset_class}", self._last_user_id)
        self._save()
        return f"KILLED: {asset_class} trading halted. Active kills: {killed}"

    def _cmd_pause(self) -> str:
        source = f"telegram:{self._last_user_id}"
        self._set_state(KillSwitchState.PAUSED, reason="Telegram /pause", authorized_by=source)
        self._notify_coordinator(True, "Telegram /pause", source)
        return "PAUSED — no new entries. Closes still allowed."

    def _cmd_resume(self) -> str:
        source = f"telegram:{self._last_user_id}"
        self._set_state(KillSwitchState.INACTIVE, reason="Telegram /resume", authorized_by=source)
        self._state["killed_classes"] = []
        self._save()
        self._notify_coordinator(False, "Telegram /resume", source)
        return "RESUMED — normal operation."

    # ------------------------------------------------------------------
    # Close-mode enforcement
    # ------------------------------------------------------------------

    def enforce(
        self,
        close_mode: CloseMode,
        broker_adapter: BrokerAdapterLike | None = None,
        readonly_client: ReadonlyClientLike | None = None,
    ) -> dict[str, Any]:
        """Enforce kill-switch close mode against live broker positions.

        Args:
            close_mode: Which positions to close.
            broker_adapter: Adapter with ``get_positions()`` and ``close_position(ticket)``.
            readonly_client: Read-only client for post-close reconciliation.

        Returns:
            Dict with keys: ``closed``, ``failed``, ``remaining``, ``reconciled``.
        """
        result: dict[str, Any] = {
            "closed": [],
            "failed": [],
            "remaining": [],
            "reconciled": False,
        }

        if broker_adapter is None:
            logger.warning("kill_switch.enforce: no broker_adapter — cannot close positions")
            return result

        # Fetch current positions from broker
        try:
            positions = broker_adapter.get_positions()
        except Exception as exc:
            logger.error("kill_switch.enforce: failed to fetch positions: %s", exc)
            return result

        for pos in positions:
            ticket = pos.get("ticket")
            pnl = pos.get("pnl", 0.0)
            should_close = False

            if close_mode == CloseMode.CLOSE_ALL:
                should_close = True
            elif close_mode == CloseMode.CLOSE_RISK_INCREASING_ONLY:
                # Close losing positions (negative PnL = risk-increasing in drawdown)
                should_close = pnl < 0
            elif close_mode == CloseMode.NO_NEW_ORDERS_ONLY:
                # Don't close anything
                should_close = False

            if should_close and ticket is not None:
                # Idempotent check: skip if already closed
                if int(ticket) in self._closed_tickets:
                    logger.info(
                        "kill_switch.enforce: ticket=%s already closed at %s — skipping",
                        ticket,
                        self._closed_tickets[int(ticket)],
                    )
                    result["closed"].append(ticket)
                    continue
                try:
                    broker_adapter.close_position(int(ticket))
                    closed_at = datetime.now(UTC).isoformat()
                    self._closed_tickets[int(ticket)] = closed_at
                    self._state["closed_tickets"] = self._closed_tickets
                    self._save()
                    result["closed"].append(ticket)
                    logger.info("kill_switch.enforce: closed position ticket=%s pnl=%.2f at %s", ticket, pnl, closed_at)
                except Exception as exc:
                    result["failed"].append({"ticket": ticket, "error": str(exc)})
                    logger.error("kill_switch.enforce: failed to close ticket=%s: %s", ticket, exc)
            else:
                result["remaining"].append(ticket)

        # Broker state reconciliation
        result["reconciled"] = self._reconcile_broker_state(readonly_client or broker_adapter, result)

        return result

    def get_closed_tickets(self) -> dict[int, str]:
        """Return dict of ticket -> closed_at timestamp for idempotent tracking."""
        return dict(self._closed_tickets)

    def clear_closed_tickets(self) -> None:
        """Clear the closed tickets tracking (for reset/testing)."""
        self._closed_tickets.clear()
        self._state["closed_tickets"] = {}
        self._save()

    def _reconcile_broker_state(
        self,
        client: BrokerAdapterLike | ReadonlyClientLike,
        close_result: dict[str, Any],
    ) -> bool:
        """Verify broker state matches expected state after close attempts.

        Returns True if reconciliation succeeds (or no positions expected).
        """
        closed_tickets = set(close_result.get("closed", []))

        if not closed_tickets:
            # Nothing was supposed to close — trivially reconciled
            return True

        try:
            broker_positions = client.get_positions()
            broker_tickets = {pos.get("ticket") for pos in broker_positions}

            # Check that closed tickets are no longer open
            still_open = closed_tickets & broker_tickets
            if still_open:
                logger.warning(
                    "kill_switch.reconcile: positions still open after close: %s",
                    still_open,
                )
                return False

            logger.info(
                "kill_switch.reconcile: all %d closed positions verified gone from broker",
                len(closed_tickets),
            )
            return True
        except Exception as exc:
            logger.error("kill_switch.reconcile: broker query failed: %s", exc)
            return False

    def _load_allowed_users(self) -> set[int]:
        raw = os.getenv("TELEGRAM_ALLOWED_USERS", "")
        if not raw:
            return set()
        return {int(uid.strip()) for uid in raw.split(",") if uid.strip().isdigit()}

    def _is_authorized(self, user_id: int) -> bool:
        if not self._allowed_users:
            return False
        return user_id in self._allowed_users

    def _get_state_enum(self) -> KillSwitchState:
        try:
            return KillSwitchState(self._state.get("state", "INACTIVE"))
        except ValueError:
            # Fail-closed: corrupted state cannot be trusted — block all trading
            return KillSwitchState.ACTIVE

    def _set_state(self, state: KillSwitchState, reason: str, authorized_by: str) -> None:
        old_state = self._get_state_enum()
        self._state["state"] = state.value
        self._state["reason"] = reason
        self._state["authorized_by"] = authorized_by
        self._state["activated_at_utc"] = datetime.now(UTC).isoformat()
        self._append_history(f"state={state.value}", authorized_by)
        self._save()

        # Wire enforce: when transitioning to ACTIVE, automatically close positions
        if state == KillSwitchState.ACTIVE and old_state != KillSwitchState.ACTIVE:
            self.enforce(self._close_mode, self._broker_adapter)

    def _append_history(self, action: str, user: Any) -> None:
        history: list[dict[str, str]] = self._state.get("history", [])
        history.append({"action": action, "user": str(user), "timestamp": datetime.now(UTC).isoformat()})
        self._state["history"] = history[-100:]
        self._last_user_id = user

    def _load(self) -> dict[str, Any]:
        if self._state_file.exists():
            try:
                return json.loads(self._state_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, ValueError) as exc:
                logger.critical(
                    "kill_switch: state file corrupted — fail-closed default. " "file=%s error=%s",
                    self._state_file,
                    exc,
                )
                # Best-effort quarantine of the corrupted file for forensics.
                corrupt_name = f"{self._state_file.stem}.corrupt.{int(time.time())}.json"
                corrupt_path = self._state_file.with_name(corrupt_name)
                try:
                    self._state_file.rename(corrupt_path)
                    logger.critical(
                        "kill_switch: corrupted state file quarantined to %s",
                        corrupt_path,
                    )
                except OSError as rename_exc:
                    logger.critical(
                        "kill_switch: failed to quarantine corrupted state file: %s",
                        rename_exc,
                    )
                # Fail-closed: a corrupted kill-switch state cannot be trusted,
                # so default to ACTIVE (block all trading) until manually cleared.
                return {
                    "state": KillSwitchState.ACTIVE.value,
                    "killed_classes": [],
                    "reason": "State file missing or corrupted — fail-closed default",
                    "activated_at_utc": datetime.now(UTC).isoformat(),
                    "authorized_by": "system:fail_closed",
                    "history": [],
                }
        # Normal first-run case: file missing → INACTIVE.
        return {
            "state": KillSwitchState.INACTIVE.value,
            "killed_classes": [],
            "reason": "",
            "activated_at_utc": None,
            "authorized_by": "",
            "history": [],
        }

    def _save(self) -> None:
        """Save state atomically using temp file + rename."""
        import tempfile

        path = self._state_file
        path.parent.mkdir(parents=True, exist_ok=True)

        # Write to temp file first
        fd, tmp_path = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=".kill_switch_",
            suffix=".tmp",
        )
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(self._state, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            # Atomic rename
            os.replace(tmp_path, str(path))
        except Exception:
            # Clean up temp file on failure
            import contextlib

            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
            raise
