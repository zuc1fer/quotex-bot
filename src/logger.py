"""Tiny logging helper. Every signal/trade goes through here for audit."""
from __future__ import annotations

import logging
import sys


def get_logger(name: str = "quotex-bot") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    )
    logger.addHandler(handler)
    return logger
