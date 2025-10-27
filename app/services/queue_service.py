# -*- coding: utf-8 -*-
import asyncio
import logging
from datetime import datetime, timedelta

from app.db.database import create_bot_connection
from app.db import repository
from app.services.signal_service import signal_service
from app.services.telegram_service import telegram_service

logger = logging.getLogger(__name__)

# --- Configuration for the retry mechanism ---
MAX_RETRIES = 5  # Max number of times to retry a signal
RETRY_DELAY = 10  # seconds to wait between retries
SIGNAL_EXPIRY_MINUTES = 3  # Discard signals older than this

class QueueService:
    def __init__(self):
        self._queue = asyncio.Queue()
        self._worker_task = None

    async def start_worker(self):
        """Starts the background worker task."""
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._process_queue())
            logger.info("Retry queue worker has been started.")

    async def stop_worker(self):
        """Stops the background worker task gracefully."""
        if self._worker_task:
            self._queue.put_nowait(None)  # Sentinel to stop the worker
            await self._worker_task
            self._worker_task = None
            logger.info("Retry queue worker has been stopped.")

    async def add_to_queue(self, signal_data: dict):
        """
        Adds a failed signal to the queue for a retry attempt.
        The signal data is augmented with retry metadata.
        """
        retry_item = {
            "data": signal_data,
            "timestamp": datetime.utcnow(),
            "retry_count": 1
        }
        await self._queue.put(retry_item)
        logger.info(f"Signal for {signal_data.get('symbol')} added to retry queue.")

    async def _process_queue(self):
        """The main loop for the background worker."""
        while True:
            try:
                item = await self._queue.get()
                if item is None:  # Sentinel value to stop the loop
                    break

                data = item["data"]
                timestamp = item["timestamp"]
                retry_count = item["retry_count"]

                # 1. Check if the signal is stale
                if datetime.utcnow() - timestamp > timedelta(minutes=SIGNAL_EXPIRY_MINUTES):
                    report_details = f"Signal {data} discarded as stale after {SIGNAL_EXPIRY_MINUTES} minutes."
                    # We need a new connection here as we are in a separate path
                    conn = await asyncio.to_thread(create_bot_connection)
                    await asyncio.to_thread(repository.create_report, conn, 'STALE_SIGNAL', report_details)
                    await asyncio.to_thread(conn.close)
                    await telegram_service.notify_admins(f"A stale signal for {data.get('symbol')} was discarded. Use /reports to view details.")
                    logger.warning(f"Discarding stale signal for {data.get('symbol')} after {SIGNAL_EXPIRY_MINUTES} minutes.")
                    self._queue.task_done()
                    continue

                # 2. Attempt to re-process the signal
                logger.info(f"Retrying signal for {data.get('symbol')} (Attempt #{retry_count}).")
                try:
                    await self._execute_signal(data)
                    logger.info(f"Successfully processed signal for {data.get('symbol')} from retry queue.")
                    self._queue.task_done()
                except Exception as e:
                    logger.error(f"Retry attempt #{retry_count} failed for {data.get('symbol')}: {e}")
                    # 3. If it fails again, decide whether to re-queue or discard
                    if retry_count >= MAX_RETRIES:
                        report_details = f"Signal {data} discarded after {MAX_RETRIES} failed retry attempts."
                        await asyncio.to_thread(repository.create_report, conn, 'RETRY_FAILURE', report_details)
                        await telegram_service.notify_admins("A signal failed to process after multiple retries. Use /reports to view details.")
                        logger.error(f"Discarding signal for {data.get('symbol')} after {MAX_RETRIES} failed attempts.")
                    else:
                        item["retry_count"] += 1
                        await asyncio.sleep(RETRY_DELAY)
                        await self._queue.put(item)
                    self._queue.task_done()

            except Exception as e:
                logger.error(f"An unexpected error occurred in the queue worker: {e}", exc_info=True)

    async def _execute_signal(self, data: dict):
        """
        The core logic to execute a signal, wrapped to be callable by the worker.
        This contains the logic that might fail (e.g., DB write).
        """
        conn = None
        try:
            conn = await asyncio.to_thread(create_bot_connection)
            action = data.get("action")
            symbol = data.get("symbol")
            price = data.get("price")
            open_signal_id = data.get("open_signal_id")

            if action in ["BUY", "SELL"]:
                # The main blocking operation is saving the signal.
                # The checks are fast and can be re-run.
                can_send, reason = await asyncio.to_thread(signal_service.can_send_signal, conn)
                if not can_send:
                    logger.warning(f"Retry for {symbol} aborted: {reason}")
                    return # Don't retry if conditions are no longer met

                signal_id = await asyncio.to_thread(repository.save_signal, conn, action, symbol, price)
                stats = await asyncio.to_thread(repository.get_today_stats, conn)
                message = signal_service._format_signal_message(action, symbol, price, signal_id, stats)
                await telegram_service.send_alert(message)
                signal_service.update_last_signal_time()

            elif action == "CLOSE":
                pl = await asyncio.to_thread(repository.close_signal, conn, open_signal_id, price)
                stats = await asyncio.to_thread(repository.get_today_stats, conn)
                message = signal_service._format_close_message(symbol, price, open_signal_id, pl, stats)
                await telegram_service.send_alert(message)

        finally:
            if conn:
                await asyncio.to_thread(conn.close)

# Single instance of the queue service
queue_service = QueueService()
