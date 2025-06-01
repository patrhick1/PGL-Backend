import logging
import sys
from logging.config import dictConfig

# Force DEBUG level for this debugging session
FORCED_LOG_LEVEL = "DEBUG" # Changed from podcast_outreach.config import LOG_LEVEL

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