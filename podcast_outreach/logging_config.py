import logging
import sys
from logging.config import dictConfig

from podcast_outreach.config import LOG_LEVEL

LOGGING_CONFIG = {
    "version": 1,
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": sys.stdout
        }
    },
    "root": {
        "level": LOG_LEVEL,
        "handlers": ["console"]
    }
}

def setup_logging() -> None:
    """Apply logging configuration using LOGGING_CONFIG."""
    dictConfig(LOGGING_CONFIG)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper to get a named logger."""
    return logging.getLogger(name)
