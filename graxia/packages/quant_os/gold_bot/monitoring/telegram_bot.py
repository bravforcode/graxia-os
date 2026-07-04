"""
Gold Bot Telegram Notifications
"""

import asyncio
from typing import Optional
from datetime import datetime

from ..core.engine import TradeRecord, AggregatedSignal
from ..core.config import BotConfig


class GoldBotTelegram:
    """Telegram notifications for Gold Bot"""
    
    def __init__(self, config: BotConfig):
        self.config = config
        self.bot_token = config.telegram_bot_token
        self.chat_id = config.telegram_chat_id
        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self.session = None
    
    async def initialize(self):
        """Initialize Telegram connection"""
        if not self.bot_token or not self.chat_id:
            raise ValueError("Telegram bot token or chat ID not configured")
        
        import aiohttp
        self.session = aiohttp.ClientSession()
        
        # Test connection
        async with self.session.get(f"{self.base_url}/getMe") as resp:
            if resp.status != 200:
                raise ConnectionError("Telegram bot connection failed")
    
    async def send_message(self, message: str) -> bool:
        """Send message to Telegram"""
        if not self.session:
            return False
        
        try:
            async with self.session.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                }
            ) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"Telegram send error: {e}")
            return False
    
    async def notify_trade(self, trade: TradeRecord, signal: AggregatedSignal):
        """Send trade notification"""
        emoji = "🟢" if trade.direction.value == "BUY" else "🔴"
        
        # Strategy scores
        top_strategies = sorted(
            signal.signals,
            key=lambda s: s.score,
            reverse=True
        )[:5]
        
        strategy_text = "\n".join(
            f"  {s.strategy_name}: {s.score}%" for s in top_strategies
        )
        
        message = f"""
{emoji} <b>GOLD BOT - Trade Executed</b>

<b>Symbol:</b> XAUUSD
<b>Direction:</b> {trade.direction.value}
<b>Entry:</b> {trade.entry_price:.2f}
<b>Stop Loss:</b> {trade.stop_loss:.2f}
<b>Take Profit:</b> {trade.take_profit:.2f}
<b>Quantity:</b> {trade.quantity:.2f} lots

<b>Score:</b> {signal.total_score}
<b>AI Validated:</b> {"Yes" if trade.ai_validated else "No"}

<b>Top Strategies:</b>
{strategy_text}

<b>Time:</b> {trade.entry_time.strftime('%Y-%m-%d %H:%M:%S UTC')}
"""
        
        await self.send_message(message)
    
    async def notify_daily_report(self, stats: dict):
        """Send daily performance report"""
        message = f"""
📊 <b>GOLD BOT - Daily Report</b>

<b>Date:</b> {datetime.utcnow().strftime('%Y-%m-%d')}

<b>Performance:</b>
  Total Trades: {stats.get('total_trades', 0)}
  Win Rate: {stats.get('win_rate', 0):.1f}%
  Daily P&L: ${stats.get('daily_pnl', 0):+,.2f}
  Total P&L: ${stats.get('total_pnl', 0):+,.2f}

<b>Risk Status:</b>
  Max Drawdown: {stats.get('drawdown', 0):.2f}%
  Open Positions: {stats.get('open_positions', 0)}

<b>League Status:</b>
  Tier S: {', '.join(stats.get('tier_s', []))}
  Tier A: {', '.join(stats.get('tier_a', []))}
  Bench: {', '.join(stats.get('bench', []))}
"""
        
        await self.send_message(message)
    
    async def notify_kill_switch(self, reason: str):
        """Send kill switch alert"""
        message = f"""
🚨 <b>KILL SWITCH TRIGGERED</b>

<b>Reason:</b> {reason}
<b>Time:</b> {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}

All trading has been halted.
Manual reset required.
"""
        
        await self.send_message(message)
    
    async def close(self):
        """Close Telegram session"""
        if self.session and not self.session.closed:
            await self.session.close()
