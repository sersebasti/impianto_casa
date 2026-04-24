"""
logger.py

Configura un logger unico per il progetto, con rotazione giornaliera e mantenimento degli ultimi N giorni di log.
"""

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from logging.handlers import TimedRotatingFileHandler

LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "solar_app.log"
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "7"))  # Numero di giorni da mantenere

class RomeFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, ZoneInfo("Europe/Rome"))
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()

def get_logger(name: str = "solar_app") -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logger.setLevel(level)
    logger.propagate = False

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = RomeFormatter(
        fmt="[%(asctime)s] %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = TimedRotatingFileHandler(
        LOG_FILE, when="midnight", backupCount=LOG_BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger
