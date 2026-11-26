"""
Central logging configuration.

Call setup_logging() once at application startup (in main.py lifespan).
All other modules should use:  logger = logging.getLogger(__name__)
"""

import logging
import logging.config

from backend.core.config import settings

LOG_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "level": settings.log_level.upper(),
        "handlers": ["console"],
    },
}


def setup_logging() -> None:
    """Apply the logging configuration. Safe to call multiple times."""
    logging.config.dictConfig(LOG_CONFIG)
