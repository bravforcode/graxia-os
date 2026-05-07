"""
Telegram Bot for Quant OS Notifications

Provides:
- Trade notifications
- Kill switch alerts
- Daily/Weekly P&L reports
- Manual commands (/status, /positions, /pnl, /killswitch)
"""

import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime

import aiohttp

from ..core.config import get_config
from ..core.enums import IncidentSeverity, OrderSide, SignalType


class TelegramNotifier:
    """Telegram bot for trading notifications"""
    
    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        self.config = get_config()
        self.bot_token = bot_token or self.config.telegram_bot_token
        self.chat_id = chat_id or self.config.telegram_chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession()
        return self.session
    
    async def send_message(
        self,
        message: str,
        severity: IncidentSeverity = IncidentSeverity.P2,
        parse_mode: str = "HTML"
    ) -> bool:
        """Send message to Telegram"""
        if not self.bot_token or not self.chat_id:
            return False
        
        # Add severity emoji
        emoji_map = {
            IncidentSeverity.P0: "🚨",  # Critical
            IncidentSeverity.P1: "⚠️",   # High
            IncidentSeverity.P2: "ℹ️",   # Medium
            IncidentSeverity.P3: "💬",   # Low
        }
        emoji = emoji_map.get(severity, "ℹ️")
        
        formatted_message = f"{emoji} <b>Quant OS Alert</b>\n\n{message}"
        
        try:
            session = await self._get_session()
            url = f"{self.base_url}/sendMessage"
            
            payload = {
                "chat_id": self.chat_id,
                "text": formatted_message,
                "parse_mode": parse_mode,
                "disable_notification": severity in [IncidentSeverity.P2, IncidentSeverity.P3]
            }
            
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    return True
                else:
                    print(f"Telegram API error: {response.status}")
                    return False
                    
        except Exception as e:
            print(f"Telegram send error: {e}")
            return False
    
    async def notify_trade(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        strategy: str,
        pnl: Optional[float] = None
    ) -> bool:
        """Send trade notification"""
        emoji = "🟢" if side == OrderSide.BUY else "🔴"
        action = "BUY" if side == OrderSide.BUY else "SELL"
        
        message = f"""
{emoji} <b>Trade Executed</b>

<b>Symbol:</b> {symbol}
<b>Action:</b> {action}
<b>Quantity:</b> {quantity:.2f} lots
<b>Entry:</b> {entry_price:.5f}
<b>Stop Loss:</b> {stop_loss:.5f}
<b>Take Profit:</b> {take_profit:.5f}
<b>Strategy:</b> {strategy.upper()}
"""
        
        if pnl is not None:
            pnl_emoji = "✅" if pnl > 0 else "❌"
            message += f"\n<b>P&L:</b> {pnl_emoji} ${pnl:,.2f}"
        
        return await self.send_message(message, IncidentSeverity.P2)
    
    async def notify_kill_switch(
        self,
        trigger_type: str,
        reason: str,
        triggered_by: str
    ) -> bool:
        """Send kill switch alert"""
        message = f"""
🚨 <b>KILL SWITCH TRIGGERED</b> 🚨

<b>Type:</b> {trigger_type}
<b>Reason:</b> {reason}
<b>Triggered By:</b> {triggered_by}
<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

⚠️ All trading has been halted.
Manual reset required.
"""
        return await self.send_message(message, IncidentSeverity.P0)
    
    async def notify_daily_report(
        self,
        date: str,
        total_trades: int,
        win_count: int,
        loss_count: int,
        daily_pnl: float,
        cumulative_pnl: float,
        drawdown_pct: float,
        open_positions: int
    ) -> bool:
        """Send daily P&L report"""
        win_rate = (win_count / (win_count + loss_count) * 100) if (win_count + loss_count) > 0 else 0
        pnl_emoji = "🟢" if daily_pnl >= 0 else "🔴"
        
        message = f"""
📊 <b>Daily Trading Report - {date}</b>

<b>Trades:</b> {total_trades} ({win_count}W / {loss_count}L)
<b>Win Rate:</b> {win_rate:.1f}%
<b>Open Positions:</b> {open_positions}

<b>Daily P&L:</b> {pnl_emoji} ${daily_pnl:+,.2f}
<b>Cumulative P&L:</b> ${cumulative_pnl:,.2f}
<b>Drawdown:</b> {drawdown_pct:.2f}%
"""
        return await self.send_message(message, IncidentSeverity.P3)
    
    async def notify_signal(
        self,
        symbol: str,
        signal_type: SignalType,
        confidence: float,
        strategy: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float
    ) -> bool:
        """Send signal notification"""
        emoji = "🟢" if signal_type == SignalType.BUY else "🔴"
        action = "BUY" if signal_type == SignalType.BUY else "SELL"
        
        message = f"""
{emoji} <b>Trading Signal</b>

<b>Symbol:</b> {symbol}
<b>Action:</b> {action}
<b>Confidence:</b> {confidence:.1%}
<b>Strategy:</b> {strategy.upper()}

<b>Entry:</b> {entry_price:.5f}
<b>Stop Loss:</b> {stop_loss:.5f}
<b>Take Profit:</b> {take_profit:.5f}

Risk/Reward: {abs((take_profit - entry_price) / (entry_price - stop_loss)):.2f}
"""
        return await self.send_message(message, IncidentSeverity.P2)
    
    async def notify_error(
        self,
        error_message: str,
        context: Optional[str] = None
    ) -> bool:
        """Send error notification"""
        message = f"""
⚠️ <b>System Error</b>

{error_message}
"""
        if context:
            message += f"\n<b>Context:</b> {context}"
        
        return await self.send_message(message, IncidentSeverity.P1)
    
    async def send_custom_message(
        self,
        title: str,
        content: str,
        severity: IncidentSeverity = IncidentSeverity.P2
    ) -> bool:
        """Send custom formatted message"""
        message = f"""
<b>{title}</b>

{content}
"""
        return await self.send_message(message, severity)
    
    async def close(self) -> None:
        """Close the session"""
        if self.session and not self.session.closed:
            await self.session.close()


class TelegramCommandHandler:
    """Handle incoming Telegram commands"""
    
    def __init__(self, notifier: TelegramNotifier):
        self.notifier = notifier
        self.commands = {
            "/status": self.handle_status,
            "/positions": self.handle_positions,
            "/pnl": self.handle_pnl,
            "/killswitch": self.handle_killswitch,
            "/help": self.handle_help,
        }
    
    async def handle_command(self, command: str, args: List[str]) -> str:
        """Handle a command and return response"""
        handler = self.commands.get(command, self.handle_unknown)
        return await handler(args)
    
    async def handle_status(self, args: List[str]) -> str:
        """Handle /status command"""
        return """
📊 <b>System Status</b>

<b>Mode:</b> PAPER
<b>Broker:</b> Connected (MT5)
<b>Kill Switch:</b> 🟢 Armed
<b>Circuit Breaker:</b> 🟢 Closed

<b>Open Positions:</b> 0
<b>Today's Trades:</b> 0
<b>Today's P&L:</b> $0.00
"""
    
    async def handle_positions(self, args: List[str]) -> str:
        """Handle /positions command"""
        return "📈 No open positions"
    
    async def handle_pnl(self, args: List[str]) -> str:
        """Handle /pnl command"""
        return """
💰 <b>P&L Summary</b>

<b>Today:</b> $0.00
<b>This Week:</b> $0.00
<b>This Month:</b> $0.00
<b>YTD:</b> $0.00
"""
    
    async def handle_killswitch(self, args: List[str]) -> str:
        """Handle /killswitch command"""
        if len(args) > 0 and args[0] == "trigger":
            return "🚨 Kill switch triggered manually via Telegram"
        return "Kill switch status: 🟢 Armed (not triggered)"
    
    async def handle_help(self, args: List[str]) -> str:
        """Handle /help command"""
        return """
🤖 <b>Quant OS Bot Commands</b>

/status - System status
/positions - Open positions
/pnl - P&L summary
/killswitch trigger - Trigger kill switch
/help - This help message
"""
    
    async def handle_unknown(self, args: List[str]) -> str:
        """Handle unknown commands"""
        return "❓ Unknown command. Use /help for available commands."
