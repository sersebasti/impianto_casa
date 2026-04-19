"""
utility.py

Utility condivise del progetto.

Cosa fa:
- configura un logger unico
- scrive log sia su console che su file
- fornisce funzioni helper per masking dati sensibili
"""

import logging
import os
import sys
from pathlib import Path


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "solar_app.log"


def get_logger(name: str = "solar_app") -> logging.Logger:
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    logger.setLevel(level)
    logger.propagate = False

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        fmt="[%(asctime)s] %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(formatter)
    logger.addHandler(stream_handler)

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    return logger


def mask_token(token: str | None, left: int = 6, right: int = 4) -> str:
    if not token:
        return "<none>"

    if len(token) <= left + right:
        return token

    return f"{token[:left]}...{token[-right:]}"