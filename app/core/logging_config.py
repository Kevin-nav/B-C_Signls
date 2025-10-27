# -*- coding: utf-8 -*-
import logging
import sys
import json
from pathlib import Path
from datetime import datetime

from app.core.config import settings

class JsonFormatter(logging.Formatter):
    """Formats log records as JSON strings."""
    def format(self, record):
        log_object = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "message": record.getMessage(),
            "name": record.name,
        }
        # Add extra fields if they exist
        if hasattr(record, 'extra_data'):
            log_object.update(record.extra_data)
            
        if record.exc_info:
            log_object['exc_info'] = self.formatException(record.exc_info)
            
        return json.dumps(log_object)

def setup_logging():
    """
    Configures a logger with daily rotating files and structured JSON output.
    """
    log_dir = Path(settings.LOG_DIR)
    log_dir.mkdir(exist_ok=True)
    log_filename = log_dir / f"bot_{datetime.now().strftime('%Y-%m-%d')}.log"

    # Get the root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Clear any existing handlers to avoid duplicate logs
    root_logger.handlers.clear()

    # --- File Handler (JSON) ---
    file_handler = logging.FileHandler(log_filename, mode='a')
    file_handler.setFormatter(JsonFormatter('%Y-%m-%dT%H:%M:%S.%fZ'))
    root_logger.addHandler(file_handler)

    # --- Console Handler (for human-readable output during development) ---
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    root_logger.addHandler(console_handler)

    # Suppress noisy logs from libraries
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info("Structured JSON logging configured.")
