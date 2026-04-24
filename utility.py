"""
utility.py

Utility condivise del progetto.

Cosa fa:
- configura un logger unico
- scrive log sia su console che su file
- usa il fuso orario Europe/Rome nei timestamp dei log
- fornisce funzioni helper per masking dati sensibili
"""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "solar_app.log"


class RomeFormatter(logging.Formatter):
    def formatTime(self, record, datefmt=None):
        dt = datetime.fromtimestamp(record.created, ZoneInfo("Europe/Rome"))
        if datefmt:
            return dt.strftime(datefmt)
        return dt.isoformat()


def mask_token(token: str | None, left: int = 6, right: int = 4) -> str:
    if not token:
        return "<none>"

    if len(token) <= left + right:
        return token

    return f"{token[:left]}...{token[-right:]}"