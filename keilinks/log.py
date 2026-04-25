"""
Logging centralizado da Keilinks.
Substitui todos os print() por logger estruturado com arquivo rotativo.
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from config import LOG_LEVEL, LOG_FILE

# Garante que a pasta de logs existe
os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)

# ─── Formato ──────────────────────────────────────────────────────────────────
_FMT      = "[%(asctime)s] %(levelname)-5s %(name)-14s │ %(message)s"
_DATE_FMT = "%H:%M:%S"

_formatter = logging.Formatter(_FMT, datefmt=_DATE_FMT)

# ─── Handler de arquivo (rotativo, max 5MB x 3 backups) ──────────────────────
_file_handler = RotatingFileHandler(
    LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
)
_file_handler.setFormatter(_formatter)

# ─── Handler de console (colorido simplificado) ──────────────────────────────
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)

# ─── Root config ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    handlers=[_file_handler, _console_handler],
)

# Silencia logs ruidosos de terceiros
for noisy in (
    "httpx", "httpcore", "urllib3", "PIL", "faster_whisper",
    "comtypes", "comtypes.client", "comtypes._post_coinit",
    "comtypes._comobject", "comtypes._vtbl", "comtypes._manage",
    "asyncio", "chromadb", "chromadb.config",
):
    logging.getLogger(noisy).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retorna um logger com o nome do módulo."""
    return logging.getLogger(name)
