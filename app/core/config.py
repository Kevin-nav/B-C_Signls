from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import List, Optional, Any, Union, get_origin, get_args
from datetime import time
import logging

class Settings(BaseSettings):
    # Model config
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    # Telegram Configuration
    TELEGRAM_BOT_TOKEN: str
    TELEGRAM_DEFAULT_CHAT_ID: str

    # Security
    WEBHOOK_SECRET_KEY: str
    ADMIN_USER_IDS: List[int]

    # Rate Limiting & Controls
    MAX_SIGNALS_PER_DAY: int = 10
    MIN_SECONDS_BETWEEN_SIGNALS: int = 60

    # Trading Hours (UTC time)
    TRADING_START_TIME: Optional[time] = None
    TRADING_END_TIME: Optional[time] = None

    # Server Configuration
    HOST: str = "0.0.0.0"
    PORT: int = 5000
    RELOAD_UVICORN: bool = False

    # TCP Server Configuration
    TCP_HOST: str = "0.0.0.0"
    TCP_PORT: int = 5200
    SSL_CERT_PATH: str = "cert.pem"
    SSL_KEY_PATH: str = "key.pem"

    # Paths
    DB_PATH: str = "trading_signals.db"
    LOG_DIR: str = "logs"

    # Trading Server
    TRADING_SERVER_URL: Optional[str] = None
    TRADING_SERVER_SECRET_KEY: Optional[str] = None

    # Bot Settings
    SIGNAL_MESSAGE_STYLE: str = "modern"

    @field_validator('ADMIN_USER_IDS', mode='before')
    @classmethod
    def split_values(cls, v: Any) -> List[str]:
        if isinstance(v, (int, float)):
            v = str(v)
        if isinstance(v, str):
            return [item.strip() for item in v.split(',')]
        return v

# Load initial settings from .env file immediately.
# This object will be updated later with values from the DB.
settings = Settings()

def reload_settings_from_db():
    """
    Loads settings from the database and updates the global `settings` object in place.
    """
    from app.db.database import create_bot_connection
    from app.db.repository import load_settings_from_db

    logger = logging.getLogger(__name__)
    
    logger.info("Attempting to load and apply settings from the database...")
    try:
        conn = create_bot_connection()
        db_settings = load_settings_from_db(conn)
        conn.close()

        if not db_settings:
            logger.info("No dynamic settings found in the database. Using existing values.")
            return

        update_count = 0
        for key, value in db_settings.items():
            key_upper = key.upper()
            if hasattr(settings, key_upper):
                field_info = settings.model_fields.get(key_upper)
                if not field_info: continue

                field_type = field_info.annotation
                
                try:
                    # Handle Optional types like Optional[time]
                    if get_origin(field_type) is Union and type(None) in get_args(field_type):
                        if value is None or value == "":
                            setattr(settings, key_upper, None)
                            update_count += 1
                            continue
                        # Get the actual type from the Union, e.g., time
                        field_type = next(t for t in get_args(field_type) if t is not type(None))

                    # Type casting from string stored in DB
                    if field_type is time:
                        parts = list(map(int, value.split(':')))
                        parsed_value = time(parts[0], parts[1])
                    elif field_type is bool:
                        parsed_value = value.lower() in ('true', '1', 't')
                    else: # Works for int, float, str
                        parsed_value = field_type(value)
                        
                    setattr(settings, key_upper, parsed_value)
                    update_count += 1

                except (ValueError, TypeError) as e:
                    logger.error(f"Could not parse setting '{key_upper}' from DB value '{value}'. Error: {e}. Using existing value.")
        
        if update_count > 0:
            logger.info(f"Successfully applied {update_count} settings from the database.")

    except Exception as e:
        logger.error(f"Could not load settings from database: {e}. Using existing settings.")
