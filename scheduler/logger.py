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
    # TODO: global _configured; if _configured: return
    # TODO: os.makedirs(config.LOG_DIR, exist_ok=True)
    # TODO: formatter -> "%(asctime)s | %(threadName)-10s | %(levelname)-7s | %(name)s | %(message)s"
    #       ^ threadName is the key one -> you can SEE which worker ran what
    # TODO: file handler  -> RotatingFileHandler(config.LOG_FILE, maxBytes=1_000_000, backupCount=3)
    # TODO: console handler -> logging.StreamHandler()
    # TODO: root = logging.getLogger(); root.setLevel(level); add both handlers
    # TODO: _configured = True
    pass


def get_logger(name):
    # TODO: setup_logging(); return logging.getLogger(name)
    pass
