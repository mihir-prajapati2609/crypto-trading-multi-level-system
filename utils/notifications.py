import logging
import asyncio
from typing import Dict, Any, Optional
from telegram import Bot
from telegram.error import TelegramError

from config.settings import get_settings
from data.models import Trade, RegimeState

logger = logging.getLogger(__name__)

class NotificationManager:
    """Manages notifications via Telegram."""
    
    def __init__(self):
        self.settings = get_settings().notifications
        self.bot = None
        if self.settings.enabled:
            try:
                self.bot = Bot(token=self.settings.telegram_bot_token)
            except Exception as e:
                logger.error(f"Failed to initialize Telegram bot: {e}")
                
        self.last_alert_time = 0

    async def _send(self, message: str, critical: bool = False):
        if not self.bot or not self.settings.enabled:
            # Strip emojis for safe logging on Windows cp1252
            safe_message = message.encode('ascii', 'ignore').decode('ascii').replace('\n', ' | ')
            logger.info(f"Notification (disabled): {safe_message}")
            return
            
        import time
        now = time.time()
        
        # Rate limit non-critical messages
        if not critical and (now - self.last_alert_time) < self.settings.rate_limit_seconds:
            return
            
        try:
            await self.bot.send_message(chat_id=self.settings.telegram_chat_id, text=message, parse_mode='HTML')
            if not critical:
                self.last_alert_time = now
        except TelegramError as e:
            logger.error(f"Telegram error: {e}")

    async def send_trade_alert(self, trade: Trade):
        emoji = "🟢" if trade.net_profit_usd > 0 else "🔴"
        msg = f"<b>{emoji} Trade Executed</b>\n"
        msg += f"Pair: {trade.symbol}\n"
        msg += f"Strategy: {trade.strategy.value}\n"
        msg += f"Net P&L: ${trade.net_profit_usd:.2f} ({trade.net_profit_pct:.2f}%)\n"
        await self._send(msg, critical=False)

    async def send_error_alert(self, error_msg: str):
        msg = f"<b>⚠️ System Error</b>\n{error_msg}"
        await self._send(msg, critical=True)

    async def send_daily_summary(self, pnl_data: Dict[str, Any]):
        msg = f"<b>📊 Daily Summary ({pnl_data.get('date', '')})</b>\n"
        msg += f"Net P&L: ${pnl_data.get('net_pnl', 0):.2f}\n"
        msg += f"Trades: {pnl_data.get('trade_count', 0)} (W:{pnl_data.get('win_count',0)} L:{pnl_data.get('loss_count',0)})\n"
        await self._send(msg, critical=False)

    async def send_anomaly_alert(self, details: str):
        msg = f"<b>🚨 Anomaly Detected</b>\n{details}\nTrading paused temporarily."
        await self._send(msg, critical=True)

    async def send_regime_change(self, old_regime: RegimeState, new_regime: RegimeState):
        msg = f"<b>🔄 Regime Change</b>\n{old_regime.value} ➡️ {new_regime.value}"
        await self._send(msg, critical=False)

    async def send_new_listing(self, symbol: str, exchange: str):
        msg = f"<b>🆕 New Listing Detected</b>\nPair: {symbol}\nExchange: {exchange}"
        await self._send(msg, critical=False)
