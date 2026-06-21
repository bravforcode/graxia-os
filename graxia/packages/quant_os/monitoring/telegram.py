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
    """Handle incoming Telegram commands with real data"""
    
    def __init__(self, notifier: TelegramNotifier, db_session=None, kill_switch=None, risk_engine=None):
        self.notifier = notifier
        self.db = db_session
        self.kill_switch = kill_switch
        self.risk_engine = risk_engine
        self.commands = {
            "/status": self.handle_status,
            "/positions": self.handle_positions,
            "/pnl": self.handle_pnl,
            "/killswitch": self.handle_killswitch,
            "/risk": self.handle_risk,
            "/help": self.handle_help,
        }
    
    async def handle_command(self, command: str, args: List[str]) -> str:
        """Handle a command and return response"""
        handler = self.commands.get(command, self.handle_unknown)
        return await handler(args)
    
    async def handle_status(self, args: List[str]) -> str:
        """Handle /status command with real data"""
        from ..core.config import get_config
        from ..core.golden_rules import validate_golden_rules
        
        config = get_config()
        rules_valid = validate_golden_rules()
        
        # Get position count
        position_count = 0
        if self.db:
            try:
                from ..data.models import Position
                position_count = self.db.query(Position).filter(Position.is_open == True).count()
            except Exception:
                pass
        
        # Get today's trade count
        today_trades = 0
        if self.db:
            try:
                from ..data.models import Fill
                from sqlalchemy import func
                from datetime import date
                today_trades = self.db.query(Fill).filter(func.date(Fill.filled_at) == date.today()).count()
            except Exception:
                pass
        
        # Kill switch status
        ks_status = "🟢 Armed"
        if self.kill_switch and self.kill_switch.is_triggered:
            ks_status = f"🔴 Triggered ({self.kill_switch.trigger_type.value})"
        
        return f"""
📊 <b>System Status</b>

<b>Mode:</b> {config.trading_mode.value}
<b>Live Trading:</b> {"✅ Enabled" if config.live_trading_enabled else "❌ Disabled"}
<b>Kill Switch:</b> {ks_status}
<b>Rules Valid:</b> {"✅" if rules_valid["all_checks_passed"] else "❌"}

<b>Open Positions:</b> {position_count}
<b>Today's Trades:</b> {today_trades}
<b>Max Risk/Trade:</b> {config.max_risk_per_trade_pct}%
<b>Max Drawdown:</b> {config.max_drawdown_pct}%
"""
    
    async def handle_positions(self, args: List[str]) -> str:
        """Handle /positions command with real data"""
        if not self.db:
            return "📈 No database connected"
        
        try:
            from ..data.models import Position
            
            positions = self.db.query(Position).filter(
                Position.is_open == True
            ).all()
            
            if not positions:
                return "📈 No open positions"
            
            lines = ["📈 <b>Open Positions</b>\n"]
            for pos in positions:
                pnl_emoji = "🟢" if (pos.unrealized_pnl or 0) >= 0 else "🔴"
                lines.append(
                    f"<b>{pos.symbol}</b> {pos.position_type.value} "
                    f"{pos.quantity} lots @ {pos.avg_entry_price}\n"
                    f"  {pnl_emoji} P&L: ${pos.unrealized_pnl or 0:,.2f}\n"
                    f"  SL: {pos.stop_loss or 'N/A'} | TP: {pos.take_profit or 'N/A'}\n"
                )
            
            return "\n".join(lines)
        except Exception as e:
            return f"📈 Error: {e}"
    
    async def handle_pnl(self, args: List[str]) -> str:
        """Handle /pnl command with real data"""
        if not self.db:
            return "💰 No database connected"
        
        try:
            from ..data.models import Fill, PortfolioSnapshot
            from sqlalchemy import func
            from datetime import date, timedelta
            
            # Today's P&L
            today = date.today()
            today_pnl = self.db.query(
                func.sum(Fill.realized_pnl)
            ).filter(
                func.date(Fill.filled_at) == today
            ).scalar() or 0
            
            # Weekly P&L
            week_start = today - timedelta(days=today.weekday())
            week_pnl = self.db.query(
                func.sum(Fill.realized_pnl)
            ).filter(
                func.date(Fill.filled_at) >= week_start
            ).scalar() or 0
            
            # Monthly P&L
            month_start = today.replace(day=1)
            month_pnl = self.db.query(
                func.sum(Fill.realized_pnl)
            ).filter(
                func.date(Fill.filled_at) >= month_start
            ).scalar() or 0
            
            # Total trades
            total_trades = self.db.query(Fill).count()
            winning = self.db.query(Fill).filter(Fill.realized_pnl > 0).count()
            win_rate = (winning / total_trades * 100) if total_trades > 0 else 0
            
            return f"""
💰 <b>P&L Summary</b>

<b>Today:</b> ${today_pnl:+,.2f}
<b>This Week:</b> ${week_pnl:+,.2f}
<b>This Month:</b> ${month_pnl:+,.2f}

<b>Total Trades:</b> {total_trades}
<b>Win Rate:</b> {win_rate:.1f}%
"""
        except Exception as e:
            return f"💰 Error: {e}"
    
    async def handle_killswitch(self, args: List[str]) -> str:
        """Handle /killswitch command"""
        if len(args) > 0 and args[0] == "trigger":
            if self.kill_switch:
                from ..core.enums import KillSwitchType
                self.kill_switch.trigger(
                    KillSwitchType.MANUAL,
                    "Manual trigger via Telegram",
                    triggered_by="telegram_user"
                )
                return "🚨 Kill switch triggered manually via Telegram"
            return "❌ Kill switch not available"
        
        if self.kill_switch and self.kill_switch.is_triggered:
            return f"🔴 Kill switch TRIGGERED\nType: {self.kill_switch.trigger_type.value}\nReason: {self.kill_switch.state.reason}"
        
        return "🟢 Kill switch status: Armed (not triggered)"
    
    async def handle_risk(self, args: List[str]) -> str:
        """Handle /risk command - show risk metrics"""
        from ..core.config import get_config
        
        config = get_config()
        
        # Get risk metrics from risk engine
        daily_loss = 0.0
        drawdown = 0.0
        exposure = 0.0
        
        if self.risk_engine:
            daily_loss = await self.risk_engine._get_daily_pnl()
            drawdown = await self.risk_engine._get_current_drawdown()
            exposure = await self.risk_engine._get_current_exposure()
        
        return f"""
🛡️ <b>Risk Metrics</b>

<b>Daily P&L:</b> ${daily_loss:+,.2f}
<b>Current Drawdown:</b> {drawdown:.2f}%
<b>Portfolio Exposure:</b> ${exposure:,.2f}

<b>Limits:</b>
  Risk/Trade: {config.max_risk_per_trade_pct}%
  Daily Loss: {config.max_daily_loss_pct}%
  Max DD: {config.max_drawdown_pct}%
  Max Positions: {config.max_positions}
"""
    
    async def handle_help(self, args: List[str]) -> str:
        """Handle /help command"""
        return """
🤖 <b>Quant OS Bot Commands</b>

/status - System status
/positions - Open positions
/pnl - P&L summary
/risk - Risk metrics
/killswitch trigger - Trigger kill switch
/help - This help message
"""
    
    async def handle_unknown(self, args: List[str]) -> str:
        """Handle unknown commands"""
        return "❓ Unknown command. Use /help for available commands."
