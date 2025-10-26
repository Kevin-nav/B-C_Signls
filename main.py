import logging
import asyncio
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI
import uvicorn

from app.api.endpoints import router as api_router
from app.core.config import settings, reload_settings_from_db
from app.db.database import init_database
from app.services.telegram_service import telegram_service
from app.tcp_server import start_tcp_server

# =====================================================================
# LOGGING SETUP
# =====================================================================

# Ensure log directory exists
Path(settings.LOG_DIR).mkdir(exist_ok=True)

def setup_logging():
    """Configures logging to file and console."""
    log_filename = Path(settings.LOG_DIR) / f"bot_{datetime.now().strftime('%Y-%m-%d')}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        handlers=[
            logging.FileHandler(log_filename),
            logging.StreamHandler()
        ]
    )
    # Suppress noisy logs from libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("telegram").setLevel(logging.WARNING)

# =====================================================================
# FASTAPI LIFESPAN EVENTS
# =====================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Handles application startup and shutdown events.
    """
    # Startup
    logging.info("Starting Trading Signal Bot...")
    init_database()
    reload_settings_from_db()  # Load .env and override with DB settings
    await telegram_service.initialize()
    
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

# Setup logging immediately
setup_logging()

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
