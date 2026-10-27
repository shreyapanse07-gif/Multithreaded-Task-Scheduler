"""
logger.py
One logging setup for the whole project (File Handling + Logging topic).
logging module is already thread-safe, so no extra lock needed.
"""
import logging
import os
from logging.handlers import RotatingFileHandler

import config

_configured = False   # so handlers aren't added twice


def setup_logging(level=logging.INFO):
    global _configured
    if _configured:
        return
    os.makedirs(config.LOG_DIR, exist_ok=True)

    formatter = logging.Formatter(
        "%(asctime)s | %(threadName)-10s | %(levelname)-7s | %(name)s | %(message)s"
    )

    file_handler = RotatingFileHandler(config.LOG_FILE, maxBytes=1_000_000, backupCount=3)
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    _configured = True


def get_logger(name):
    setup_logging()
    return logging.getLogger(name)