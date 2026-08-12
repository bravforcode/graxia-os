"""Telegram alerting for GRAXIA-OS — sync and async.

Config priority: env vars > toml config file > constructor args.
"""

import os
import pathlib

import requests

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

DEFAULT_CONFIG_PATH = pathlib.Path(__file__).resolve().parent.parent / "scripts" / "telegram_config.toml"


def _load_config(path: pathlib.Path | None = None) -> dict:
    cfg: dict = {}
    p = path or DEFAULT_CONFIG_PATH
    if p.exists():
        with open(p, "rb") as fh:
            cfg = tomllib.load(fh)
    return cfg


def _get_token(config: dict | None = None) -> str:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if token:
        return token
    cfg = config or _load_config()
    return cfg.get("bot_token", "")


def _get_chat_id(config: dict | None = None) -> str:
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if chat_id:
        return chat_id
    cfg = config or _load_config()
    return cfg.get("chat_id", "")


class TelegramNotifier:
    def __init__(self, token: str | None = None, chat_id: str | None = None):
        self.token = token or _get_token()
        self.chat_id = chat_id or _get_chat_id()
        if not self.token or not self.chat_id:
            raise RuntimeError(
                "TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set via env vars or telegram_config.toml"
            )
        self.base = f"https://api.telegram.org/bot{self.token}"

    def send(self, msg: str) -> bool:
        try:
            r = requests.post(
                f"{self.base}/sendMessage",
                json={"chat_id": self.chat_id, "text": msg, "parse_mode": "Markdown"},
                timeout=5,
            )
            return r.status_code == 200
        except Exception as e:
            print(f"Telegram error: {e}")
            return False

    async def send_async(self, msg: str) -> bool:
        """Send message asynchronously using httpx."""
        import httpx

        if not self.token or not self.chat_id:
            return False
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.post(
                    f"{self.base}/sendMessage",
                    json={"chat_id": self.chat_id, "text": msg, "parse_mode": "Markdown"},
                )
                return resp.status_code == 200
        except Exception as exc:
            print(f"Telegram send_async error: {exc}")
            return False

    def trade_opened(
        self,
        direction: str,
        entry: float,
        sl: float,
        tp: float,
        confidence: float,
        lot: float,
        regime: str,
    ):
        emoji = "🟢 LONG" if direction.upper() == "BUY" else "🔴 SHORT"
        self.send(
            f"*GRAXIA-OS | {emoji}*\n"
            f"Entry: `{entry:.2f}` | Lot: `{lot}` | Regime: `{regime}`\n"
            f"SL: `{sl:.2f}` | TP: `{tp:.2f}`\n"
            f"Confidence: `{confidence:.3f}`"
        )

    async def trade_opened_async(
        self,
        direction: str,
        entry: float,
        sl: float,
        tp: float,
        confidence: float,
        lot: float,
        regime: str,
    ):
        emoji = "🟢 LONG" if direction.upper() == "BUY" else "🔴 SHORT"
        await self.send_async(
            f"*GRAXIA-OS | {emoji}*\n"
            f"Entry: `{entry:.2f}` | Lot: `{lot}` | Regime: `{regime}`\n"
            f"SL: `{sl:.2f}` | TP: `{tp:.2f}`\n"
            f"Confidence: `{confidence:.3f}`"
        )

    def trade_closed(
        self,
        direction: str,
        pnl_net: float,
        reason: str,
        daily_pnl: float,
        monthly_pnl: float,
        swap_paid: float = 0.0,
    ):
        emoji = "💚" if pnl_net > 0 else "❤️"
        msg = f"{emoji} *CLOSED | {reason}*\n" f"P&L: `${pnl_net:+.2f}`"
        if swap_paid:
            msg += f" (incl. swap `${swap_paid:+.2f}`)"
        msg += f"\nDaily: `${daily_pnl:+.2f}` | Monthly: `${monthly_pnl:+.2f}`"
        self.send(msg)

    async def trade_closed_async(
        self,
        direction: str,
        pnl_net: float,
        reason: str,
        daily_pnl: float,
        monthly_pnl: float,
        swap_paid: float = 0.0,
    ):
        emoji = "💚" if pnl_net > 0 else "❤️"
        msg = f"{emoji} *CLOSED | {reason}*\n" f"P&L: `${pnl_net:+.2f}`"
        if swap_paid:
            msg += f" (incl. swap `${swap_paid:+.2f}`)"
        msg += f"\nDaily: `${daily_pnl:+.2f}` | Monthly: `${monthly_pnl:+.2f}`"
        await self.send_async(msg)

    def risk_alert(self, reason: str):
        self.send(f"⚠️ *RISK ALERT*\n{reason}")

    async def risk_alert_async(self, reason: str):
        await self.send_async(f"⚠️ *RISK ALERT*\n{reason}")

    def heartbeat(
        self,
        trades_today: int,
        win_rate_7d: float,
        balance: float,
        prob_ruin_at_current_lot: float | None = None,
    ):
        msg = (
            f"💓 *Daily Heartbeat*\n"
            f"Trades today: `{trades_today}`\n"
            f"WR 7d: `{win_rate_7d:.1%}`\n"
            f"Balance: `${balance:,.2f}`"
        )
        if prob_ruin_at_current_lot is not None:
            msg += f"\nMonte Carlo P(ruin), current lot: `{prob_ruin_at_current_lot:.2%}`"
        self.send(msg)

    async def heartbeat_async(
        self,
        trades_today: int,
        win_rate_7d: float,
        balance: float,
        prob_ruin_at_current_lot: float | None = None,
    ):
        msg = (
            f"💓 *Daily Heartbeat*\n"
            f"Trades today: `{trades_today}`\n"
            f"WR 7d: `{win_rate_7d:.1%}`\n"
            f"Balance: `${balance:,.2f}`"
        )
        if prob_ruin_at_current_lot is not None:
            msg += f"\nMonte Carlo P(ruin), current lot: `{prob_ruin_at_current_lot:.2%}`"
        await self.send_async(msg)

    def failover_triggered(self, reason: str):
        self.send(
            f"🚨 *FAILOVER* — standby VPS is taking over.\n"
            f"Reason: {reason}\n"
            f"Verify open positions manually NOW."
        )

    async def failover_triggered_async(self, reason: str):
        await self.send_async(
            f"🚨 *FAILOVER* — standby VPS is taking over.\n"
            f"Reason: {reason}\n"
            f"Verify open positions manually NOW."
        )
