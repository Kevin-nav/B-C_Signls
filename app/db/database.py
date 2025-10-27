import sqlite3
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

def create_bot_connection():
    """Creates a standalone, correctly configured DB connection for background services."""
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def get_db_connection():
    """
    FastAPI dependency to get a database connection.
    This will be called for each request that needs a DB connection.
    """
    conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row  # This allows accessing columns by name
    try:
        yield conn
    finally:
        conn.close()

def init_database():
    """
    Initialize SQLite database with required tables.
    This should be called once on application startup.
    """
    try:
        conn = sqlite3.connect(settings.DB_PATH, check_same_thread=False)
        cursor = conn.cursor()

        # Signals table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS signals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                action TEXT NOT NULL,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                sent_to_telegram BOOLEAN DEFAULT FALSE,
                telegram_message_id INTEGER,
                closed BOOLEAN DEFAULT FALSE,
                close_price REAL,
                close_timestamp DATETIME,
                profit_loss REAL
            )
        """)

        # System state table (for bot pause/resume)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS system_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Initialize system state if it doesn't exist
        cursor.execute("""
            INSERT OR IGNORE INTO system_state (key, value)
            VALUES ('bot_active', 'true')
        """)

        # Managed chats table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS managed_chats (
                chat_id TEXT PRIMARY KEY,
                chat_name TEXT NOT NULL
            )
        """)

        # Settings table for dynamic configuration
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)

        # Reports table for admin notifications
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                report_type TEXT NOT NULL, -- e.g., 'STALE_SIGNAL', 'RETRY_FAILURE'
                details TEXT NOT NULL, -- Full JSON or text details of the report
                is_read BOOLEAN DEFAULT FALSE
            )
        """)

        conn.commit()
        conn.close()
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Error initializing database: {e}")
        raise
