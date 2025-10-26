# -*- coding: utf-8 -*-
import logging
from datetime import datetime, timedelta
import sqlite3
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

    async def process_new_signal(self, conn: sqlite3.Connection, action: str, symbol: str, price: float) -> int:
        """
        Process a new BUY or SELL signal.
        Saves to DB, sends Telegram alert, and updates rate limit state.
        """
        # 1. Save signal to DB to get an ID
        signal_id = repository.save_signal(conn, action, symbol, price)
        logger.info(f"Signal saved to DB: ID={signal_id}, {action} {symbol} @ {price}")

        # 2. Send Telegram alert
        stats = repository.get_today_stats(conn)
        message = self._format_signal_message(action, symbol, price, signal_id, stats)
        await telegram_service.send_alert(message)

        # 3. Update rate limiting state
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

    def _format_signal_message(self, action: str, symbol: str, price: float, signal_id: int, stats: dict) -> str:
        """Format the message for a new BUY/SELL signal."""
        emoji = "\U0001F7E2" if action == "BUY" else "\U0001F534"  # Green/Red circle
        daily_limit_str = "Unlimited" if settings.MAX_SIGNALS_PER_DAY == 0 else str(settings.MAX_SIGNALS_PER_DAY)
        message = f"""
{emoji} <b>{action} SIGNAL</b> {emoji}

\U0001F4CA <b>Symbol:</b> {symbol}
\U0001F4B0 <b>Price:</b> {price:.5f}
\U0001F550 <b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} UTC
\U0001F4DD <b>Signal ID:</b> #{signal_id}

\U0001F4C8 <b>Today's Stats:</b>
   • Signals: {stats['total_signals']}/{daily_limit_str}
   • Buys: {stats['buys']} | Sells: {stats['sells']}
   • Closed: {stats['closed']} (W:{stats['wins']} L:{stats['losses']})
"""
        if stats['total_pl'] != 0:
            message += f"   • Total P&L: {stats['total_pl']:+.5f}\n"
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
