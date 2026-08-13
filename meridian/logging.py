from __future__ import annotations

import sys

from loguru import logger

from meridian.config import get_settings

_configured = False


def setup_logging() -> None:
    global _configured
    if _configured:
        return
    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level="INFO", format="{time:HH:mm:ss} | {level:<7} | {message}")
    logger.add(
        settings.log_dir / "meridian.log",
        rotation="2 MB",
        retention=8,
        level="DEBUG",
        encoding="utf-8",
    )
    _configured = True
