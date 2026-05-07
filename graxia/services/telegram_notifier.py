"""
Graxia OS — Unified Telegram Notifier
Revenue + Trading notifications in one place
"""
import os
from datetime import datetime
from decimal import Decimal
from typing import Optional

from telegram import Bot
from telegram.constants import ParseMode


class UnifiedTelegramNotifier:
    """
    Unified notification system for Revenue OS and Quant OS
    Sends reports, alerts, and summaries to Telegram
    """
    
    def __init__(self):
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.bot_token and self.chat_id)
        
        if self.enabled:
            self.bot = Bot(token=self.bot_token)
        else:
            self.bot = None
    
    async def send_message(self, text: str, parse_mode: str = ParseMode.HTML) -> bool:
        """Send message to Telegram"""
        if not self.enabled:
            return False
        
        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text[:4096],  # Telegram limit
                parse_mode=parse_mode,
                disable_web_page_preview=True
            )
            return True
        except Exception as e:
            print(f"Telegram send failed: {e}")
            return False
    
    # ── Revenue Notifications ──
    
    async def notify_new_order(self, order_data: dict):
        """Notify new order received"""
        message = f"""
🛒 <b>New Order</b>

Platform: {order_data.get('platform', 'N/A')}
Amount: ${order_data.get('total_amount', 0):.2f}
Customer: {order_data.get('customer_email', 'N/A')}
Time: {datetime.utcnow().strftime('%H:%M:%S UTC')}
"""
        await self.send_message(message)
    
    async def notify_revenue_milestone(self, milestone: str, amount: Decimal):
        """Notify revenue milestone reached"""
        message = f"""
🎯 <b>Revenue Milestone!</b>

Milestone: {milestone}
Amount: ${amount:.2f}
Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}

Great work! 🚀
"""
        await self.send_message(message)
    
    async def send_daily_revenue_report(self, report: dict):
        """Send daily revenue summary"""
        message = f"""
📊 <b>Daily Revenue Report</b>
📅 {report.get('date', datetime.utcnow().strftime('%Y-%m-%d'))}

💰 Total Revenue: ${report.get('total_revenue', 0):.2f}
📦 Orders: {report.get('total_orders', 0)}
📈 Avg Order: ${report.get('average_order_value', 0):.2f}
👥 Unique Customers: {report.get('unique_customers', 0)}

💸 Refunds: ${report.get('refund_amount', 0):.2f}
✅ Net Revenue: ${report.get('net_revenue', 0):.2f}
"""
        await self.send_message(message)
    
    # ── Trading Notifications ──
    
    async def notify_trade_executed(self, trade: dict):
        """Notify trade execution"""
        emoji = "🟢" if trade.get('side') == 'buy' else "🔴"
        message = f"""
{emoji} <b>Trade Executed</b>

Symbol: {trade.get('symbol', 'N/A')}
Side: {trade.get('side', 'N/A').upper()}
Quantity: {trade.get('quantity', 0)}
Price: {trade.get('price', 0)}
P&L: ${trade.get('pnl', 0):.2f}
Time: {datetime.utcnow().strftime('%H:%M:%S UTC')}
"""
        await self.send_message(message)
    
    async def notify_kill_switch_triggered(self, reason: str):
        """URGENT: Kill switch activated"""
        message = f"""
🚨 <b>KILL SWITCH TRIGGERED</b> 🚨

Reason: {reason}
Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

All trading has been HALTED.
Manual intervention required.
"""
        await self.send_message(message)
    
    async def notify_risk_limit_breach(self, metric: str, value: float, limit: float):
        """Notify risk limit breach"""
        message = f"""
⚠️ <b>Risk Limit Breach</b>

Metric: {metric}
Current: {value:.2f}
Limit: {limit:.2f}
Status: EXCEEDED

Action: Kill switch armed
"""
        await self.send_message(message)
    
    async def send_daily_trading_report(self, report: dict):
        """Send daily trading summary"""
        pnl = report.get('total_pnl', 0)
        emoji = "🟢" if pnl >= 0 else "🔴"
        
        message = f"""
📈 <b>Daily Trading Report</b>
📅 {report.get('date', datetime.utcnow().strftime('%Y-%m-%d'))}

{emoji} P&L: ${pnl:+.2f}
📊 Trades: {report.get('total_trades', 0)}
🎯 Win Rate: {report.get('win_rate', 0):.1f}%
📉 Max Drawdown: {report.get('max_drawdown', 0):.2f}%

Positions Open: {report.get('open_positions', 0)}
"""
        await self.send_message(message)
    
    # ── Unified Notifications ──
    
    async def send_unified_daily_summary(self, revenue: dict, trading: dict):
        """Send combined daily summary"""
        today = datetime.utcnow().strftime('%Y-%m-%d')
        
        # Trading status emoji
        trading_emoji = "🟢" if trading.get('pnl', 0) >= 0 else "🔴"
        
        message = f"""
🏢 <b>Graxia OS — Daily Summary</b>
📅 {today}

<b>💰 Revenue OS</b>
   Revenue: ${revenue.get('total_revenue', 0):.2f}
   Orders: {revenue.get('total_orders', 0)}
   
<b>📈 Quant OS</b>
   {trading_emoji} P&L: ${trading.get('pnl', 0):+.2f}
   Mode: {trading.get('mode', 'PAPER')}
   Positions: {trading.get('open_positions', 0)}

<b>🔐 System Status:</b> Operational
"""
        await self.send_message(message)
    
    async def notify_system_alert(self, severity: str, message: str):
        """Send system alert"""
        emojis = {
            "critical": "🔴",
            "warning": "⚠️",
            "info": "ℹ️"
        }
        emoji = emojis.get(severity, "ℹ️")
        
        text = f"""
{emoji} <b>System Alert [{severity.upper()}]</b>

{message}

Time: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        await self.send_message(text)
    
    async def send_weekly_report(self, revenue_summary: dict, trading_summary: dict):
        """Send weekly combined report"""
        message = f"""
📊 <b>Weekly Report</b>
Week of {datetime.utcnow().strftime('%Y-W%U')}

<b>Revenue Performance</b>
💰 Total: ${revenue_summary.get('total', 0):.2f}
📈 vs Last Week: {revenue_summary.get('change_percent', 0):+.1f}%

<b>Trading Performance</b>
📈 P&L: ${trading_summary.get('total_pnl', 0):+.2f}
🎯 Win Rate: {trading_summary.get('win_rate', 0):.1f}%
📉 Max Drawdown: {trading_summary.get('max_drawdown', 0):.2f}%

Overall Health: {'✅ Good' if revenue_summary.get('change_percent', 0) >= 0 else '⚠️ Review Needed'}
"""
        await self.send_message(message)


# Singleton instance
notifier = UnifiedTelegramNotifier()
