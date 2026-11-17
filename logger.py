"""Sistema de logging para SOCGuard."""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from config import LOGS_DIR, LOG_LEVEL

def setup_logger(name: str = "SOCGuard") -> logging.Logger:
    """Configura y retorna un logger con salida a consola y archivo rotativo."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logger.setLevel(level)

    # Formato profesional
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Handler de archivo rotativo (10 MB x 5 archivos)
    log_file = LOGS_DIR / "socguard.log"
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(level)
    logger.addHandler(file_handler)

    # Handler de consola con codificación tolerante
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(level)
    logger.addHandler(console_handler)

    return logger

logger = setup_logger("SOCGuard")
