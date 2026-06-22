from __future__ import annotations

import logging
import os

LOGGER_NAME = "uvt_asist"
DEFAULT_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"

logger = logging.getLogger(LOGGER_NAME)


def setup_logging(level: str | int | None = None) -> logging.Logger:
    configured_level = level or os.getenv("BACKEND_LOG_LEVEL", "INFO")
    numeric_level = logging.getLevelName(str(configured_level).upper()) if isinstance(configured_level, str) else configured_level
    if not isinstance(numeric_level, int):
        numeric_level = logging.INFO

    logging.basicConfig(level=numeric_level, format=DEFAULT_LOG_FORMAT)
    logger.setLevel(numeric_level)
    return logger


def get_logger(name: str | None = None) -> logging.Logger:
    if not name:
        return logger
    short_name = name.rsplit(".", 1)[-1]
    return logging.getLogger(f"{LOGGER_NAME}.{short_name}")
