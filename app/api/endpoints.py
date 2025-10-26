import logging
import sqlite3
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from app.api.models import SignalData, SignalResponse, HealthResponse, StatsResponse
from app.core.config import settings
from app.db.database import get_db_connection
from app.db import repository
from app.services.signal_service import signal_service

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/signal", response_model=SignalResponse)
async def receive_signal(
    signal: SignalData,
    request: Request,
    conn: sqlite3.Connection = Depends(get_db_connection)
):
    """
    Main endpoint to receive trading signals.
    It validates the signal, checks rate limits, and processes it.
    """
    client_ip = request.client.host if request.client else "unknown"
    logger.info(f"Signal received from {client_ip}: {signal.action} {signal.symbol} @ {signal.price}")

    # 1. Authentication
    if signal.secret_key != settings.WEBHOOK_SECRET_KEY:
        logger.warning(f"Unauthorized signal attempt from {client_ip}")
        raise HTTPException(status_code=401, detail="Invalid secret key")

    # 2. Validation
    signal.action = signal.action.upper()
    if signal.action not in ["BUY", "SELL", "CLOSE"]:
        logger.warning(f"Invalid action received: {signal.action}")
        raise HTTPException(status_code=400, detail="Action must be BUY, SELL, or CLOSE")

    # 3. Processing
    try:
        if signal.action in ["BUY", "SELL"]:
            can_send, reason = signal_service.can_send_signal(conn)
            if not can_send:
                logger.warning(f"Signal rejected: {reason}")
                raise HTTPException(status_code=429, detail=reason)

            signal_id = await signal_service.process_new_signal(
                conn, signal.action, signal.symbol, signal.price
            )
            message = f"Signal {signal.action} processed successfully"

        elif signal.action == "CLOSE":
            if not signal.open_signal_id:
                raise HTTPException(status_code=400, detail="open_signal_id is required for CLOSE action")

            await signal_service.process_close_signal(
                conn, signal.symbol, signal.price, signal.open_signal_id
            )
            signal_id = signal.open_signal_id
            message = f"Close signal for #{signal_id} processed successfully"

    except HTTPException as e:
        # Re-raise HTTPException so FastAPI can handle it
        raise e
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"An unexpected error occurred while processing signal: {e}")
        raise HTTPException(status_code=500, detail="An internal server error occurred.")

    # 4. Response
    stats = repository.get_today_stats(conn)
    return SignalResponse(
        status="success",
        message=message,
        signal_id=signal_id,
        signals_today=stats['total_signals']
    )

@router.get("/health", response_model=HealthResponse)
async def health_check(conn: sqlite3.Connection = Depends(get_db_connection)):
    """Health check endpoint to verify service status."""
    return HealthResponse(
        status="healthy",
        bot_active=repository.get_bot_state(conn),
        timestamp=datetime.now().isoformat()
    )

@router.get("/stats", response_model=StatsResponse)
async def get_stats(conn: sqlite3.Connection = Depends(get_db_connection)):
    """Public stats endpoint to get today's trading statistics."""
    stats = repository.get_today_stats(conn)
    return StatsResponse(
        date=datetime.now().strftime('%Y-%m-%d'),
        stats=stats,
        bot_active=repository.get_bot_state(conn),
        limits={
            "max_signals_per_day": settings.MAX_SIGNALS_PER_DAY,
            "min_seconds_between_signals": settings.MIN_SECONDS_BETWEEN_SIGNALS
        }
    )
