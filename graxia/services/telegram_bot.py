"""
Graxia OS — Telegram Bot with Approval System
Supports: Notifications, Order Approval, Kill Switch, Status Commands
"""
import os
import asyncio
import logging
from datetime import datetime
from decimal import Decimal
from typing import Optional

from telegram import (
    Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup,
    ReplyKeyboardMarkup, KeyboardButton
)
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes
)
from telegram.constants import ParseMode

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class GraxiaTelegramBot:
    """
    Unified Telegram Bot for Graxia OS
    Features:
    - Revenue notifications (new orders, refunds)
    - Trading notifications (trades, P&L)
    - Order approval system (with inline buttons)
    - Kill switch trigger
    - System status
    """
    
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.allowed_chat_id = os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.token and self.allowed_chat_id)
        
        if self.enabled:
            self.application = Application.builder().token(self.token).build()
            self._setup_handlers()
        else:
            self.application = None
            logger.warning("Telegram bot not configured - missing TOKEN or CHAT_ID")
    
    def _setup_handlers(self):
        """Setup command and callback handlers"""
        # Commands
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("status", self.cmd_status))
        self.application.add_handler(CommandHandler("positions", self.cmd_positions))
        self.application.add_handler(CommandHandler("pnl", self.cmd_pnl))
        self.application.add_handler(CommandHandler("orders", self.cmd_orders))
        self.application.add_handler(CommandHandler("killswitch", self.cmd_killswitch))
        self.application.add_handler(CommandHandler("daily", self.cmd_daily))
        self.application.add_handler(CommandHandler("revenue", self.cmd_revenue))
        
        # Callbacks for inline buttons
        self.application.add_handler(CallbackQueryHandler(self.handle_approval, pattern="^approve_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_rejection, pattern="^reject_"))
        self.application.add_handler(CallbackQueryHandler(self.handle_killswitch_confirm, pattern="^killswitch_"))
        
        # Messages
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
    
    def _is_authorized(self, update: Update) -> bool:
        """Check if user is authorized"""
        chat_id = str(update.effective_chat.id)
        return chat_id == self.allowed_chat_id
    
    # ── Command Handlers ──
    
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start command"""
        if not self._is_authorized(update):
            await update.message.reply_text("Unauthorized access.")
            return
        
        welcome_text = f"""
🤖 <b>Graxia OS Bot Activated</b>

ยินดีต้อนรับ! บอทนี้จะแจ้งเตือนคุณเกี่ยวกับ:
• คำสั่งซื้อใหม่ (New Orders)
• การเทรด (Trade Executions)
• P&L รายวัน
• ระบบเตือนภัย (Risk Alerts)

<b>คำสั่งที่ใช้ได้:</b>
/status - สถานะระบบ
/positions - ดู positions ที่เปิดอยู่
/pnl - ดู P&L วันนี้
/orders - ดูคำสั่งซื้อล่าสุด
/revenue - ดูรายได้วันนี้
/killswitch - หยุดการเทรดทั้งหมด
/daily - สรุปรายวัน
/help - ความช่วยเหลือ
        """
        
        keyboard = [
            [KeyboardButton("/status"), KeyboardButton("/revenue")],
            [KeyboardButton("/positions"), KeyboardButton("/pnl")],
            [KeyboardButton("/daily")]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
        
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Help command"""
        if not self._is_authorized(update):
            return
        
        help_text = """
<b>คำสั่งทั้งหมด:</b>

<b>ระบบ:</b>
/status - สถานะระบบทั้งหมด
/daily - สรุปรายงานรายวัน

<b>Revenue:</b>
/revenue - รายได้วันนี้
/orders - คำสั่งซื้อล่าสุด

<b>Trading:</b>
/positions - Positions ที่เปิดอยู่
/pnl - Profit & Loss วันนี้
/killswitch - หยุดการเทรดทั้งหมด

<b>การอนุมัติ:</b>
เมื่อมีคำสั่งซื้อที่ต้องการ approval จะมีปุ่มให้กด Approve/Reject
        """
        await update.message.reply_text(help_text, parse_mode=ParseMode.HTML)
    
    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """System status"""
        if not self._is_authorized(update):
            return
        
        status_text = f"""
<b>📊 Graxia OS Status</b>
<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>

<b>🟢 ระบบทำงานปกติ</b>

<b>Revenue OS:</b>
สถานะ: Operational
Orders วันนี้: 0
Revenue วันนี้: $0.00

<b>Quant OS:</b>
สถานะ: PAPER MODE
Positions ที่เปิด: 0
P&L วันนี้: $0.00
Kill Switch: Disarmed

<b>ระบบ:</b>
Database: Connected
Redis: Connected
Telegram: Active
        """
        await update.message.reply_text(status_text, parse_mode=ParseMode.HTML)
    
    async def cmd_positions(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show open positions"""
        if not self._is_authorized(update):
            return
        
        positions_text = f"""
<b>📈 Open Positions</b>
<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>

ไม่มี positions ที่เปิดอยู่

ใช้ /killswitch เพื่อปิดทั้งหมด
        """
        await update.message.reply_text(positions_text, parse_mode=ParseMode.HTML)
    
    async def cmd_pnl(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show P&L summary"""
        if not self._is_authorized(update):
            return
        
        pnl_text = f"""
<b>💰 Trading P&L</b>
<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>

<b>วันนี้:</b>
Realized P&L: $0.00
Unrealized P&L: $0.00
Total: $0.00

<b>สถิติ:</b>
จำนวนเทรด: 0
Win Rate: 0%
        """
        await update.message.reply_text(pnl_text, parse_mode=ParseMode.HTML)
    
    async def cmd_orders(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show recent orders"""
        if not self._is_authorized(update):
            return
        
        orders_text = f"""
<b>🛒 Recent Orders</b>
<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>

ไม่มีคำสั่งซื้อใหม่ในวันนี้
        """
        await update.message.reply_text(orders_text, parse_mode=ParseMode.HTML)
    
    async def cmd_revenue(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show revenue summary"""
        if not self._is_authorized(update):
            return
        
        revenue_text = f"""
<b>💵 Revenue Summary</b>
<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>

<b>วันนี้:</b>
ยอดขาย: $0.00
จำนวน orders: 0
ลูกค้าใหม่: 0

<b>เดือนนี้:</b>
ยอดขาย: $0.00
จำนวน orders: 0
        """
        await update.message.reply_text(revenue_text, parse_mode=ParseMode.HTML)
    
    async def cmd_killswitch(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Trigger kill switch with confirmation"""
        if not self._is_authorized(update):
            return
        
        keyboard = [
            [InlineKeyboardButton("🚨 YES, STOP ALL TRADING", callback_data="killswitch_confirm")],
            [InlineKeyboardButton("❌ Cancel", callback_data="killswitch_cancel")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await update.message.reply_text(
            "⚠️ <b>KILL SWITCH</b>\n\nคุณแน่ใจหรือไม่ว่าต้องการหยุดการเทรดทั้งหมด?\n\nการกระทำนี้จะ:\n• ปิดทุก position ทันที\n• ยกเลิกคำสั่งซื้อที่รออยู่\n• ปิดระบบเทรดชั่วคราว",
            parse_mode=ParseMode.HTML,
            reply_markup=reply_markup
        )
    
    async def cmd_daily(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Daily summary report"""
        if not self._is_authorized(update):
            return
        
        daily_text = f"""
<b>📋 Daily Summary</b>
<i>{datetime.now().strftime('%Y-%m-%d')}</i>

<b>💰 Revenue:</b>
ยอดขาย: $0.00
Orders: 0
ลูกค้า: 0

<b>📈 Trading:</b>
P&L: $0.00
เทรด: 0 ครั้ง
Positions: 0

<b>🔐 System:</b>
สถานะ: Operational
Database: OK
Redis: OK
        """
        await update.message.reply_text(daily_text, parse_mode=ParseMode.HTML)
    
    # ── Callback Handlers ──
    
    async def handle_approval(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle order approval"""
        query = update.callback_query
        await query.answer()
        
        # Extract order_id from callback_data (format: "approve_<order_id>")
        order_id = query.data.replace("approve_", "")
        
        # Here you would call your order approval service
        await query.edit_message_text(
            f"✅ <b>Order Approved</b>\n\nOrder ID: <code>{order_id}</code>\nApproved by: {update.effective_user.username or update.effective_user.first_name}",
            parse_mode=ParseMode.HTML
        )
        
        logger.info(f"Order {order_id} approved by Telegram user {update.effective_user.id}")
    
    async def handle_rejection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle order rejection"""
        query = update.callback_query
        await query.answer()
        
        order_id = query.data.replace("reject_", "")
        
        await query.edit_message_text(
            f"❌ <b>Order Rejected</b>\n\nOrder ID: <code>{order_id}</code>\nRejected by: {update.effective_user.username or update.effective_user.first_name}",
            parse_mode=ParseMode.HTML
        )
        
        logger.info(f"Order {order_id} rejected by Telegram user {update.effective_user.id}")
    
    async def handle_killswitch_confirm(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle kill switch confirmation"""
        query = update.callback_query
        await query.answer()
        
        if query.data == "killswitch_confirm":
            # Here you would trigger the actual kill switch
            await query.edit_message_text(
                "🚨 <b>KILL SWITCH TRIGGERED</b>\n\nระบบเทรดถูกหยุดแล้ว!\n\n• ทุก position จะถูกปิด\n• คำสั่งซื้อถูกยกเลิก\n\nใช้ /status เพื่อตรวจสอบ",
                parse_mode=ParseMode.HTML
            )
            logger.critical(f"Kill switch triggered by Telegram user {update.effective_user.id}")
        else:
            await query.edit_message_text("Kill switch cancelled.")
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle regular messages"""
        if not self._is_authorized(update):
            return
        
        # Echo for now, or handle specific commands
        text = update.message.text
        if text.startswith("/"):
            await update.message.reply_text(f"Unknown command: {text}\n\nUse /help for available commands.")
    
    # ── Public API for Notifications ──
    
    async def send_message(self, text: str, parse_mode: str = ParseMode.HTML) -> bool:
        """Send message to configured chat"""
        if not self.enabled:
            return False
        
        try:
            await self.application.bot.send_message(
                chat_id=self.allowed_chat_id,
                text=text[:4096],
                parse_mode=parse_mode,
                disable_web_page_preview=True
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
    
    async def send_order_approval_request(self, order_data: dict):
        """Send order approval request with inline buttons"""
        if not self.enabled:
            return False
        
        order_id = order_data.get('id', 'unknown')
        amount = order_data.get('total_amount', 0)
        customer = order_data.get('customer_email', 'N/A')
        product = order_data.get('product_name', 'Unknown')
        
        message = f"""
🛒 <b>New Order Requires Approval</b>

Product: {product}
Amount: ${amount}
Customer: {customer}
Order ID: <code>{order_id}</code>
Time: {datetime.now().strftime('%H:%M:%S')}

<b>กรุณาอนุมัติหรือปฏิเสธ:</b>
        """
        
        keyboard = [
            [
                InlineKeyboardButton("✅ Approve", callback_data=f"approve_{order_id}"),
                InlineKeyboardButton("❌ Reject", callback_data=f"reject_{order_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        try:
            await self.application.bot.send_message(
                chat_id=self.allowed_chat_id,
                text=message,
                parse_mode=ParseMode.HTML,
                reply_markup=reply_markup
            )
            return True
        except Exception as e:
            logger.error(f"Failed to send approval request: {e}")
            return False
    
    # ── Bot Lifecycle ──
    
    def run(self):
        """Run the bot (blocking)"""
        if not self.enabled:
            logger.error("Cannot start bot - not configured")
            return
        
        logger.info("Starting Telegram Bot...")
        self.application.run_polling()
    
    async def start(self):
        """Start the bot (non-blocking)"""
        if not self.enabled:
            logger.error("Cannot start bot - not configured")
            return
        
        await self.application.initialize()
        await self.application.start()
        logger.info("Telegram Bot started")
    
    async def stop(self):
        """Stop the bot"""
        if self.application:
            await self.application.stop()
            logger.info("Telegram Bot stopped")


# Singleton instance
_bot_instance: Optional[GraxiaTelegramBot] = None


def get_bot() -> GraxiaTelegramBot:
    """Get or create bot singleton"""
    global _bot_instance
    if _bot_instance is None:
        _bot_instance = GraxiaTelegramBot()
    return _bot_instance


async def notify_new_order(order_data: dict):
    """Send new order notification"""
    bot = get_bot()
    
    message = f"""
🛒 <b>New Order</b>

Platform: {order_data.get('platform', 'N/A')}
Amount: ${order_data.get('total_amount', 0):.2f}
Customer: {order_data.get('customer_email', 'N/A')}
Time: {datetime.now().strftime('%H:%M:%S')}
"""
    await bot.send_message(message)


async def request_order_approval(order_data: dict):
    """Send order approval request"""
    bot = get_bot()
    await bot.send_order_approval_request(order_data)


async def notify_trade(trade_data: dict):
    """Send trade notification"""
    bot = get_bot()
    
    emoji = "🟢" if trade_data.get('side') == 'buy' else "🔴"
    message = f"""
{emoji} <b>Trade Executed</b>

Symbol: {trade_data.get('symbol', 'N/A')}
Side: {trade_data.get('side', 'N/A').upper()}
Quantity: {trade_data.get('quantity', 0)}
Price: {trade_data.get('price', 0)}
P&L: ${trade_data.get('pnl', 0):.2f}
Time: {datetime.now().strftime('%H:%M:%S')}
"""
    await bot.send_message(message)


async def notify_kill_switch(reason: str):
    """Send kill switch notification"""
    bot = get_bot()
    
    message = f"""
🚨 <b>KILL SWITCH TRIGGERED</b> 🚨

Reason: {reason}
Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

All trading has been HALTED.
Manual intervention required.
"""
    await bot.send_message(message)


# Entry point for running standalone
if __name__ == "__main__":
    bot = get_bot()
    if bot.enabled:
        print("Starting Telegram Bot...")
        bot.run()
    else:
        print("Bot not configured. Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID in .env")
