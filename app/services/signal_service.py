import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
import sqlite3
import requests
import asyncio

from app.core.config import settings
from app.db import repository
from .telegram_service import telegram_service

logger = logging.getLogger(__name__)

class SignalService:
    def __init__(self):
        self.last_signal_time: Optional[datetime] = None

    def can_send_signal(self, conn: sqlite3.Connection) -> tuple[bool, str]:
        """
        Check if a signal can be sent based on bot state, trading hours,
        rate limiting, and daily limits.
        """
        # 1. Check if bot is paused
        if not repository.get_bot_state(conn):
            return False, "Bot is currently paused by an admin."

        # 2. Check trading hours
        if settings.TRADING_START_TIME and settings.TRADING_END_TIME:
            now_time = datetime.utcnow().time()
            if not (settings.TRADING_START_TIME <= now_time <= settings.TRADING_END_TIME):
                return False, f"Signal rejected: Outside of trading hours ({settings.TRADING_START_TIME} - {settings.TRADING_END_TIME} UTC)."

        # 3. Check rate limiting (time between signals)
        if self.last_signal_time:
            time_since_last = (datetime.now() - self.last_signal_time).total_seconds()
            if time_since_last < settings.MIN_SECONDS_BETWEEN_SIGNALS:
                remaining = settings.MIN_SECONDS_BETWEEN_SIGNALS - time_since_last
                return False, f"Rate limit active. Please wait {remaining:.0f} more seconds."

        # 4. Check daily signal limit
        # A setting of 0 means unlimited signals.
        if settings.MAX_SIGNALS_PER_DAY > 0:
            count = repository.get_today_signal_count(conn)
            if count >= settings.MAX_SIGNALS_PER_DAY:
                return False, f"Daily signal limit of {settings.MAX_SIGNALS_PER_DAY} has been reached."

        return True, "OK"

    def update_last_signal_time(self):
        """Update the timestamp of the last processed signal."""
        self.last_signal_time = datetime.now()

    async def _forward_signal_to_trader(self, action: str, symbol: str, price: float, sl: float, tp1: float, tp2: float, tp3: float):
        """Forwards the signal to the external trading server via HTTP."""
        if not settings.TRADING_SERVER_URL or not settings.TRADING_SERVER_SECRET_KEY:
            logger.info("Trading server URL or secret key not configured. Skipping forwarding.")
            return

        payload = {
            "action": action,
            "symbol": symbol,
            "price": price,
            "sl": sl,
            "tp1": tp1,
            "tp2": tp2,
            "tp3": tp3,
        }
        headers = {
            "X-Secret-Key": settings.TRADING_SERVER_SECRET_KEY,
            "Content-Type": "application/json"
        }

        try:
            logger.info(f"Forwarding signal to trading server at {settings.TRADING_SERVER_URL}")
            
            def post_request():
                return requests.post(settings.TRADING_SERVER_URL, json=payload, headers=headers, timeout=10)

            response = await asyncio.to_thread(post_request)
            response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)

            logger.info(f"Successfully forwarded signal. Trading server responded with: {response.json()}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to forward signal to trading server: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while forwarding signal: {e}")


    def _format_detailed_message(
        self, action: str, symbol: str, price: float, signal_id: int,
        sl: float | None, tp1: float | None, tp2: float | None, tp3: float | None
    ) -> str:
        """Formats the detailed message for a new signal."""
        action_emoji = "🟢" if action == "BUY" else "🔴"
        
        message = f"{action_emoji} <b>{action} SIGNAL: {symbol}</b>\n\n"

        # Use 5 decimal places for consistency, as in the old format
        message += f"➡️  <b>Entry:</b>   <code>{price:.5f}</code>\n"
        message += f"🔴  <b>Stop:</b>    <code>{sl:.5f}</code>\n"
        message += f"‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐\n"
        message += f"🎯  <b>TP 1:</b>    <code>{tp1:.5f}</code>\n"
        
        if tp2:
            message += f"🎯  <b>TP 2:</b>    <code>{tp2:.5f}</code>\n"
        if tp3:
            message += f"🎯  <b>TP 3:</b>    <code>{tp3:.5f}</code>\n"

        message += f"\n<i>Signal #{signal_id} | {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC</i>\n"
        message += f"‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐\n"
        message += "Set your Stop Loss and Take Profit based on your personal risk tolerance and account size.\n"
        message += "✅ Practice proper risk management for consistent results."
        
        return message

    async def process_new_signal(
        self, conn: sqlite3.Connection, action: str, symbol: str, price: float, 
        sl: float, tp1: float, tp2: Optional[float], tp3: Optional[float]
    ) -> int:
        """
        Process a new BUY or SELL signal with pre-calculated values.
        Saves to DB, formats and sends a detailed Telegram alert, and forwards to trader.
        """
        # 1. Save signal to DB to get an ID. ATR is saved as None.
        signal_id = repository.save_signal(conn, action, symbol, price, None, sl, tp1, tp2, tp3)
        logger.info(f"Signal saved to DB: ID={signal_id}, {action} {symbol} @ {price}, SL={sl}, TP1={tp1}")

        # 2. Choose message style based on settings and send Telegram alert
        if settings.SIGNAL_MESSAGE_STYLE == "classic":
            stats = repository.get_today_stats(conn)
            message = self._format_classic_message(action, symbol, price, signal_id, stats)
        else: # Default to "modern" / "detailed"
            message = self._format_detailed_message(action, symbol, price, signal_id, sl, tp1, tp2, tp3)
        
        await telegram_service.send_alert(message)
        logger.info(f"Sent '{settings.SIGNAL_MESSAGE_STYLE}' style Telegram alert for signal ID={signal_id}")

        # 3. Forward signal to external trading server (if applicable)
        if all([sl, tp1]): # TP2 and TP3 are optional
            await self._forward_signal_to_trader(action, symbol, price, sl, tp1, tp2, tp3)

        # 4. Update rate limiting state
        self.update_last_signal_time()
        return signal_id

    async def process_close_signal(self, conn: sqlite3.Connection, symbol: str, price: float, open_signal_id: int):
        """
        Process a CLOSE signal.
        Updates the existing signal in the DB and sends a notification.
        """
        try:
            pl = repository.close_signal(conn, open_signal_id, price)
            logger.info(f"Signal {open_signal_id} closed: P&L={pl:.5f}")

            stats = repository.get_today_stats(conn)
            message = self._format_close_message(symbol, price, open_signal_id, pl, stats)
            await telegram_service.send_alert(message)
        except ValueError as e:
            logger.error(f"Error closing signal: {e}")
            raise

    def _format_modern_message(
        self, action: str, symbol: str, price: float, signal_id: int,
        stop_loss: float | None, tp1: float | None, tp2: float | None, tp3: float | None
    ) -> str:
        """Formats the message for a new BUY/SELL signal using the 'Compact & Clean' layout."""
        action_emoji = "🟢" if action == "BUY" else "🔴"
        
        # Base message
        message = f"{action_emoji} <b>{action} SIGNAL: {symbol}</b>\n\n"

        # Conditionally build the rest of the message
        if all([stop_loss, tp1, tp2, tp3]):
            message += (
                f"➡️  <b>Entry:</b>   <code>{price:.5f}</code>\n"
                f"🔴  <b>Stop:</b>    <code>{stop_loss:.5f}</code>\n"
                f"‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐\n"
                f"🎯  <b>TP 1:</b>    <code>{tp1:.5f}</code>\n"
                f"🎯  <b>TP 2:</b>    <code>{tp2:.5f}</code>\n"
                f"🎯  <b>TP 3:</b>    <code>{tp3:.5f}</code>\n\n"
                f"<i>Signal #{signal_id} | {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC</i>\n"
                f"‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐‐\n"
                f"Set your Stop Loss and Take Profit based on your personal risk tolerance and account size.\n"
                f"✅ Practice proper risk management for consistent results."
            )
        else:
            # Fallback for signals without SL/TP
            message += (
                f"➡️  <b>Entry:</b>   <code>{price:.5f}</code>\n\n"
                f"<i>Signal #{signal_id} | {datetime.now().strftime('%Y-%m-%d %H:%M')} UTC</i>"
            )

        return message

    def _format_classic_message(
        self, action: str, symbol: str, price: float, signal_id: int, stats: dict
    ) -> str:
        """Formats the message using the classic style with daily stats."""
        action_emoji = "🟢" if action == "BUY" else "🔴"
        daily_limit_str = "Unlimited" if settings.MAX_SIGNALS_PER_DAY == 0 else str(settings.MAX_SIGNALS_PER_DAY)

        message = (
            f"{action_emoji} <b>{action} SIGNAL</b> {action_emoji}\n\n"
            f"📊 <b>Symbol:</b> {symbol}\n"
            f"💲 <b>Price:</b> {price:.5f}\n"
            f"⏰ <b>Time:</b> {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}\n"
            f"📝 <b>Signal ID:</b> #{signal_id}\n\n"
            f"📈 <b>Today's Stats:</b>\n"
            f"   • Signals: {stats['total_signals']}/{daily_limit_str}\n"
            f"   • Buys: {stats['buys']} | Sells: {stats['sells']}\n"
            f"   • Closed: {stats['closed']} (W:{stats['wins']} L:{stats['losses']})"
        )
        return message

    def _format_close_message(self, symbol: str, price: float, signal_id: int, pl: float, stats: dict) -> str:
        """Format the message for a CLOSE signal."""
        emoji = "\u26AA\uFE0F"  # White circle
        pl_emoji = "\u2705" if pl >= 0 else "\u274C"  # Checkmark/Cross
        daily_limit_str = "Unlimited" if settings.MAX_SIGNALS_PER_DAY == 0 else str(settings.MAX_SIGNALS_PER_DAY)
        message = f"""
{emoji} <b>CLOSE SIGNAL</b> {emoji}

\U0001F4CA <b>Symbol:</b> {symbol}
\U0001F4B0 <b>Close Price:</b> {price:.5f}
\U0001F4DD <b>Closed Signal ID:</b> #{signal_id}
{pl_emoji} <b>P&L:</b> {pl:+.5f}

\U0001F4C8 <b>Today's Stats:</b>
   • Signals: {stats['total_signals']}/{daily_limit_str}
   • Closed: {stats['closed']} (W:{stats['wins']} L:{stats['losses']})
   • Total P&L: {stats['total_pl']:+.5f}
"""
        return message

# Single instance of the service
signal_service = SignalService()
