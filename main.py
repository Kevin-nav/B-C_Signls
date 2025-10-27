import logging
import asyncio
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn

from app.api.endpoints import router as api_router
from app.core.logging_config import setup_logging
from app.core.config import settings, reload_settings_from_db
from app.db.database import init_database
from app.services.telegram_service import telegram_service
from app.services.queue_service import queue_service
from app.tcp_server import start_tcp_server

# =====================================================================
# FASTAPI LIFESPAN EVENTS
# =====================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events.
    """
    # Startup
    setup_logging() # Setup logging first
    logging.info("Starting Trading Signal Bot...")
    init_database()
    reload_settings_from_db()  # Load .env and override with DB settings
    await telegram_service.initialize()
    await queue_service.start_worker() # Start the retry queue worker
    
    # Start the TCP server in the background
    tcp_server_task = asyncio.create_task(start_tcp_server())
    
    logging.info(f"HTTP server starting on http://{settings.HOST}:{settings.PORT}")
    
    yield
    
    # Shutdown
    logging.info("Server shutting down...")
    
    # Stop the TCP server
    logging.info("Stopping TCP server...")
    tcp_server_task.cancel()
    try:
        await tcp_server_task
    except asyncio.CancelledError:
        logging.info("TCP server stopped successfully.")

    await telegram_service.shutdown()
    logging.info("Shutdown complete.")

# =====================================================================
# FASTAPI APPLICATION
# =====================================================================



# Create FastAPI app
app = FastAPI(
    title="B/C Signals",
    description="Receives trading signals and sends them to Telegram.",
    version="2.0.0",
    lifespan=lifespan
)

# Include the API router
app.include_router(api_router)

# =====================================================================
# MAIN ENTRY POINT
# =====================================================================

if __name__ == "__main__":
    # Uvicorn uses the initial settings from the .env file to start.
    # The application itself will use the DB-overridden settings once the lifespan event completes.
    uvicorn.run(
        "main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.RELOAD_UVICORN,
        log_level="info"
    )
