import logging
import os
import sys
from logging.config import dictConfig

# Change this to "INFO" for less verbose logs, "DEBUG" for detailed development logs
FORCED_LOG_LEVEL = "INFO"

# Get log level from environment variable, fallback to the forced level
LOG_LEVEL = os.environ.get("LOG_LEVEL", FORCED_LOG_LEVEL).upper()

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False, # Ensure other loggers (like uvicorn) aren't disabled
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s" # Added module and lineno
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "default",
            "stream": sys.stdout # Explicitly stdout
        }
    },
    "root": {
        "level": FORCED_LOG_LEVEL, # Use the forced level
        "handlers": ["console"]
    },
    # Optional: Make uvicorn logs more verbose too, if they are also missing
    "loggers": {
        "uvicorn": {
            "handlers": ["console"],
            "level": FORCED_LOG_LEVEL,
            "propagate": False
        },
        "uvicorn.error": {
            "handlers": ["console"],
            "level": FORCED_LOG_LEVEL,
            "propagate": False
        },
        "uvicorn.access": {
            "handlers": ["console"],
            "level": FORCED_LOG_LEVEL,
            "propagate": False
        }
    }
}

def setup_logging() -> None:
    """Apply logging configuration using LOGGING_CONFIG."""
    print("DEBUG: Attempting to configure logging...") # Basic print
    dictConfig(LOGGING_CONFIG)
    # Test logger immediately after setup
    test_logger = logging.getLogger("logging_config_test")
    test_logger.debug("DEBUG: Logging configured from logging_config.py.")
    test_logger.info("INFO: Logging configured from logging_config.py.")


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper to get a named logger."""
    return logging.getLogger(name)