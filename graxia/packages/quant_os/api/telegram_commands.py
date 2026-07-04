"""
Telegram Command Handler — processes /commands from chat.

Commands:
    /status    — System state (mode, uptime, active sessions)
    /positions — Open positions with unrealized PnL
    /pnl       — Daily/weekly P&L summary
    /kill      — Emergency kill switch (requires confirmation)
    /resume    — Resume trading after kill
    /config    — Current risk limits and config
    /heartbeat — Force heartbeat report
    /help      — List all commands

Safety:
    - Only authorized chat_id can issue commands
    - /kill sends confirmation inline keyboard before activating
    - All commands logged for audit trail
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Command registry decorator
# ---------------------------------------------------------------------------


class _CommandRegistry:
    """Simple registry mapping command names to handler methods."""

    def __init__(self) -> None:
        self._handlers: dict[str, Callable[..., Coroutine[Any, Any, None]]] = {}

    def register(self, *commands: str) -> Callable:
        """Decorator to register a command handler.

        Usage:
            @_registry.register("/status", "status")
            async def _cmd_status(self, chat_id, text):
                ...
        """

        def decorator(fn: Callable[..., Coroutine[Any, Any, None]]) -> Callable:
            for cmd in commands:
                self._handlers[cmd.lower()] = fn
            return fn

        return decorator

    def get(self, command: str) -> Callable[..., Coroutine[Any, Any, None]] | None:
        return self._handlers.get(command.lower())


_registry = _CommandRegistry()


# ---------------------------------------------------------------------------
# TelegramCommandHandler
# ---------------------------------------------------------------------------


class TelegramCommandHandler:
    """Processes /commands from Telegram messages.

    Architecture:
        Telegram webhook → handle_command(message) → parse → dispatch → _send()

    All responses go through _send() which uses httpx.AsyncClient.
    Unauthorized chat_ids get a rejection message and the request is logged.
    """

    TELEGRAM_API = "https://api.telegram.org"

    def __init__(
        self,
        token: str | None = None,
        authorized_chat_id: str | None = None,
        state_store: Any = None,
        ledger: Any = None,
        config: Any = None,
        coordinator: Any = None,
    ) -> None:
        """Initialize the command handler.

        Args:
            token: Telegram bot token (falls back to TELEGRAM_BOT_TOKEN env)
            authorized_chat_id: Allowed chat ID (falls back to TELEGRAM_CHAT_ID env)
            state_store: SystemState store for reading system state
            ledger: TradeLedger for reading positions/PnL
            config: System config object
            coordinator: StateCoordinator for kill switch sync (optional)
        """
        self._token = token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self._authorized_chat_id = authorized_chat_id or os.getenv("TELEGRAM_CHAT_ID", "")
        self._state_store = state_store
        self._ledger = ledger
        self._config = config
        self._coordinator = coordinator
        self._client: httpx.AsyncClient | None = None
        self._start_time = time.monotonic()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def handle_command(self, message: dict) -> None:
        """Process a command from a Telegram message.

        Args:
            message: Telegram Message object dict
        """
        chat_id = str(message.get("chat", {}).get("id", ""))
        text = message.get("text", "").strip()
        user = message.get("from", {})
        username = user.get("username", "unknown")

        # Authorization check
        if chat_id != self._authorized_chat_id:
            logger.warning(
                "telegram.cmd.unauthorized",
                chat_id=chat_id,
                username=username,
                command=text.split()[0] if text else "",
            )
            await self._send(chat_id, "⛔ Unauthorized. This incident has been logged.")
            return

        # Parse command
        if not text.startswith("/"):
            return

        cmd_parts = text.split()
        cmd = cmd_parts[0].lower()

        # Strip bot username suffix (e.g., /status@mybot → /status)
        if "@" in cmd:
            cmd = cmd.split("@")[0]

        logger.info(
            "telegram.cmd.received",
            command=cmd,
            chat_id=chat_id,
            username=username,
        )

        # Dispatch
        handler = _registry.get(cmd)
        if handler:
            await handler(self, chat_id, text)
        else:
            await self._send(chat_id, f"❓ Unknown command: `{cmd}`\nType /help for available commands.")

    async def handle_callback(self, callback_query: dict) -> None:
        """Process inline keyboard callback (e.g., kill confirmation).

        Args:
            callback_query: Telegram CallbackQuery object dict
        """
        data = callback_query.get("data", "")
        chat_id = str(callback_query.get("message", {}).get("chat", {}).get("id", ""))
        cb_id = callback_query.get("id", "")

        if chat_id != self._authorized_chat_id:
            await self._answer_callback(cb_id, "Unauthorized")
            return

        if data == "kill:confirm":
            await self._activate_kill(chat_id)
            await self._answer_callback(cb_id, "Kill switch activated")
            # Edit the confirmation message
            await self._edit_last_message(chat_id, "🔴 KILL SWITCH ACTIVATED — All trading stopped.")
        elif data == "kill:cancel":
            await self._answer_callback(cb_id, "Cancelled")
            await self._edit_last_message(chat_id, "❌ Kill switch cancelled.")
        elif data == "resume:confirm":
            await self._activate_resume(chat_id)
            await self._answer_callback(cb_id, "Trading resumed")
            await self._edit_last_message(chat_id, "🟢 TRADING RESUMED — Kill switch deactivated.")
        elif data == "resume:cancel":
            await self._answer_callback(cb_id, "Cancelled")
            await self._edit_last_message(chat_id, "❌ Resume cancelled.")
        else:
            await self._answer_callback(cb_id, "Unknown action")

    async def shutdown(self) -> None:
        """Close HTTP client on shutdown."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    # ------------------------------------------------------------------
    # Command handlers
    # ------------------------------------------------------------------

    @_registry.register("/status", "status")
    async def _cmd_status(self, chat_id: str, text: str) -> None:
        """Show system status."""
        uptime_s = time.monotonic() - self._start_time
        hours = int(uptime_s // 3600)
        minutes = int((uptime_s % 3600) // 60)

        mode = "unknown"
        kill_active = False
        system_state = "UNKNOWN"

        if self._state_store:
            try:
                state = self._state_store if hasattr(self._state_store, "system_state") else None
                if state:
                    system_state = state.system_state
                    kill_active = state.kill_switch_active
            except Exception:
                pass

        if self._config:
            try:
                mode = getattr(self._config, "trading_mode", None)
                if hasattr(mode, "value"):
                    mode = mode.value
            except Exception:
                pass

        lines = [
            "📊 *System Status*",
            "",
            f"State: `{system_state}`",
            f"Mode: `{mode}`",
            f"Uptime: `{hours}h {minutes}m`",
            f"Kill Switch: `{'🔴 ACTIVE' if kill_active else '🟢 OFF'}`",
        ]
        await self._send(chat_id, "\n".join(lines))

    @_registry.register("/positions", "positions")
    async def _cmd_positions(self, chat_id: str, text: str) -> None:
        """Show open positions."""
        if not self._ledger:
            await self._send(chat_id, "📋 No ledger configured.")
            return

        try:
            positions = self._ledger.get_open_positions()
            if not positions:
                await self._send(chat_id, "📋 No open positions.")
                return

            lines = ["📋 *Open Positions*", ""]
            for pos in positions:
                symbol = pos.get("symbol", "?")
                side = pos.get("side", "?")
                entry = pos.get("entry_price", 0)
                pnl = pos.get("unrealized_pnl", 0)
                emoji = "🟢" if pnl >= 0 else "🔴"
                lines.append(f"{emoji} `{symbol}` {side} @ `{entry:.5f}` | PnL: `${pnl:+.2f}`")
            await self._send(chat_id, "\n".join(lines))
        except Exception as exc:
            logger.warning("telegram.cmd.positions_error", error=str(exc))
            await self._send(chat_id, f"⚠️ Error fetching positions: {exc}")

    @_registry.register("/pnl", "pnl")
    async def _cmd_pnl(self, chat_id: str, text: str) -> None:
        """Show P&L summary."""
        if not self._state_store:
            await self._send(chat_id, "📊 No state store configured.")
            return

        try:
            state = self._state_store if hasattr(self._state_store, "daily_pnl") else None
            if state:
                lines = [
                    "📊 *P&L Summary*",
                    "",
                    f"Daily: `${state.daily_pnl:+.2f}`",
                    f"Weekly: `${state.weekly_pnl:+.2f}`",
                    f"Peak Equity: `${state.peak_equity:,.2f}`",
                    f"Drawdown: `{state.current_drawdown_pct:.2f}%`",
                ]
            else:
                lines = ["📊 *P&L Summary*", "", "No P&L data available."]

            await self._send(chat_id, "\n".join(lines))
        except Exception as exc:
            logger.warning("telegram.cmd.pnl_error", error=str(exc))
            await self._send(chat_id, f"⚠️ Error fetching P&L: {exc}")

    @_registry.register("/kill", "kill")
    async def _cmd_kill(self, chat_id: str, text: str) -> None:
        """Activate kill switch — requires inline keyboard confirmation.

        NEVER activates directly. Always shows confirmation buttons first.
        """
        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "⚠️ CONFIRM KILL", "callback_data": "kill:confirm"},
                    {"text": "❌ Cancel", "callback_data": "kill:cancel"},
                ]
            ]
        }
        await self._send(
            chat_id,
            "⚠️ *Are you sure you want to activate KILL SWITCH?*\n\n"
            "This will stop ALL trading immediately.\n"
            "Open positions will NOT be closed automatically.",
            reply_markup=keyboard,
        )

    @_registry.register("/resume", "resume")
    async def _cmd_resume(self, chat_id: str, text: str) -> None:
        """Resume trading after kill switch — requires confirmation."""
        if self._state_store and hasattr(self._state_store, "kill_switch_active"):
            if not self._state_store.kill_switch_active:
                await self._send(chat_id, "🟢 Kill switch is not active. Trading is running.")
                return

        keyboard = {
            "inline_keyboard": [
                [
                    {"text": "✅ CONFIRM RESUME", "callback_data": "resume:confirm"},
                    {"text": "❌ Cancel", "callback_data": "resume:cancel"},
                ]
            ]
        }
        await self._send(
            chat_id,
            "✅ *Resume trading?*\nThis will reactivate all trading operations.",
            reply_markup=keyboard,
        )

    @_registry.register("/config", "config")
    async def _cmd_config(self, chat_id: str, text: str) -> None:
        """Show current risk limits and config."""
        if not self._config:
            await self._send(chat_id, "⚙️ No config available.")
            return

        try:
            c = self._config
            lines = [
                "⚙️ *Configuration*",
                "",
                f"Mode: `{getattr(c, 'trading_mode', 'N/A')}`",
                f"Max Risk/Trade: `{getattr(c, 'max_risk_per_trade_pct', 'N/A')}%`",
                f"Max Daily Loss: `{getattr(c, 'max_daily_loss_pct', 'N/A')}%`",
                f"Max Drawdown: `{getattr(c, 'max_drawdown_pct', 'N/A')}%`",
                f"Max Positions: `{getattr(c, 'max_positions', 'N/A')}`",
            ]

            weights = getattr(c, "strategy_weights", None)
            if weights:
                lines.append("")
                lines.append("*Strategy Weights:*")
                for name, weight in weights.items():
                    lines.append(f"  `{name}`: {weight:.0%}")

            await self._send(chat_id, "\n".join(lines))
        except Exception as exc:
            logger.warning("telegram.cmd.config_error", error=str(exc))
            await self._send(chat_id, f"⚠️ Error reading config: {exc}")

    @_registry.register("/heartbeat", "heartbeat")
    async def _cmd_heartbeat(self, chat_id: str, text: str) -> None:
        """Force a heartbeat report."""
        uptime_s = time.monotonic() - self._start_time
        now = datetime.now(UTC).isoformat()

        kill_active = False
        if self._state_store and hasattr(self._state_store, "kill_switch_active"):
            kill_active = self._state_store.kill_switch_active

        lines = [
            "💓 *Heartbeat*",
            "",
            f"Time: `{now}`",
            f"Kill Switch: `{'🔴' if kill_active else '🟢'}`",
            f"Uptime: `{int(uptime_s)}s`",
            "Handler: `alive`",
        ]
        await self._send(chat_id, "\n".join(lines))
        logger.info("telegram.cmd.heartbeat", chat_id=chat_id)

    @_registry.register("/help", "help")
    async def _cmd_help(self, chat_id: str, text: str) -> None:
        """List all available commands."""
        lines = [
            "📖 *Available Commands*",
            "",
            "/status — System state, mode, uptime",
            "/positions — Open positions with PnL",
            "/pnl — Daily/weekly P&L summary",
            "/kill — Emergency kill switch (with confirmation)",
            "/resume — Resume trading after kill",
            "/config — Current risk limits and config",
            "/heartbeat — Force heartbeat report",
            "/help — This message",
        ]
        await self._send(chat_id, "\n".join(lines))

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _ensure_client(self) -> httpx.AsyncClient:
        """Lazy-init the async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def _send(
        self,
        chat_id: str,
        text: str,
        reply_markup: dict | None = None,
        parse_mode: str = "Markdown",
    ) -> bool:
        """Send a message to Telegram.

        Args:
            chat_id: Target chat ID
            text: Message text (Markdown formatted)
            reply_markup: Optional inline keyboard markup
            parse_mode: Message parse mode (default: Markdown)

        Returns:
            True if message was sent successfully
        """
        if not self._token:
            logger.warning("telegram.send.no_token")
            return False

        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup

        try:
            client = await self._ensure_client()
            resp = await client.post(
                f"{self.TELEGRAM_API}/bot{self._token}/sendMessage",
                json=payload,
            )

            if resp.status_code == 429:
                retry_after = resp.json().get("parameters", {}).get("retry_after", 5)
                logger.warning("telegram.send.rate_limited", retry_after=retry_after)
                return False

            if resp.status_code != 200:
                logger.warning(
                    "telegram.send.failed",
                    status=resp.status_code,
                    detail=resp.text[:200],
                )
                return False

            return True

        except httpx.TimeoutException:
            logger.warning("telegram.send.timeout", chat_id=chat_id)
            return False
        except Exception as exc:
            logger.warning("telegram.send.error", error=str(exc))
            return False

    async def _answer_callback(self, callback_id: str, text: str = "") -> None:
        """Answer a callback query to remove the loading spinner."""
        if not self._token or not callback_id:
            return
        try:
            client = await self._ensure_client()
            await client.post(
                f"{self.TELEGRAM_API}/bot{self._token}/answerCallbackQuery",
                json={"callback_query_id": callback_id, "text": text},
            )
        except Exception:
            pass

    async def _edit_last_message(self, chat_id: str, text: str) -> None:
        """Edit the last sent message (best-effort).

        Note: This requires storing the last message_id, which we don't
        track in this implementation. A production version would store
        message_ids per chat.
        """
        # Placeholder — in production, store and use message_id
        await self._send(chat_id, text)

    async def _activate_kill(self, chat_id: str) -> None:
        """Activate the kill switch on the state store."""
        if self._coordinator:
            self._coordinator.activate(
                reason="Telegram /kill", source=f"telegram:{chat_id}"
            )
            logger.warning("telegram.cmd.kill_activated", chat_id=chat_id)
        elif self._state_store and hasattr(self._state_store, "kill_switch_active"):
            self._state_store.kill_switch_active = True
            self._state_store.system_state = "HALTED"
            logger.warning("telegram.cmd.kill_activated", chat_id=chat_id)
        else:
            logger.warning("telegram.cmd.kill_no_state_store")

    async def _activate_resume(self, chat_id: str) -> None:
        """Resume trading by deactivating the kill switch."""
        if self._coordinator:
            self._coordinator.deactivate(
                reason="Telegram /resume", source=f"telegram:{chat_id}"
            )
            logger.info("telegram.cmd.resume_activated", chat_id=chat_id)
        elif self._state_store and hasattr(self._state_store, "kill_switch_active"):
            try:
                self._state_store.kill_switch_active = False
                self._state_store.system_state = "RUNNING"
                logger.info("telegram.cmd.resume_activated", chat_id=chat_id)
            except Exception as exc:
                logger.warning("telegram.cmd.resume_error", error=str(exc))
        else:
            logger.warning("telegram.cmd.resume_no_state_store")
