import logging
import os
import sys
from logging.config import dictConfig

# Change this to "INFO" for less verbose logs, "DEBUG" for detailed development logs
FORCED_LOG_LEVEL = "INFO"

# Get log level from environment variable, fallback to the forced level
LOG_LEVEL = os.environ.get("LOG_LEVEL", FORCED_LOG_LEVEL).upper()

class CompactFormatter(logging.Formatter):
    """Custom formatter for cleaner, more compact logs"""
    def format(self, record):
        # Rename uvicorn.error to just uvicorn for cleaner output
        if record.name == 'uvicorn.error':
            record.name = 'uvicorn'
        
        # Shorten long module names for common services
        name_parts = record.name.split('.')
        if len(name_parts) > 2 and name_parts[0] == 'podcast_outreach':
            if name_parts[1] == 'services':
                # Shorten services.x.y to just x.y
                record.name = '.'.join(name_parts[2:])
            elif name_parts[1] == 'integrations':
                # Shorten integrations.x to just x
                record.name = name_parts[-1]
        
        return super().format(record)

LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": False, # Ensure other loggers (like uvicorn) aren't disabled
    "formatters": {
        "default": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",  # Simplified format
            "()": CompactFormatter  # Use our custom formatter
        },
        "detailed": {
            "format": "%(asctime)s - %(name)s - %(levelname)s - %(module)s:%(lineno)d - %(message)s",
            "()": CompactFormatter
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
    # Configure specific loggers to reduce noise
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
            "level": "WARNING",  # Reduce access log noise
            "propagate": False
        },
        # Reduce noise from service initialization
        "podcast_outreach.services.ai.gemini_client": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False
        },
        "podcast_outreach.services.ai.openai_client": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False
        },
        "podcast_outreach.integrations": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False
        },
        "podcast_outreach.services.enrichment": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False
        },
        "podcast_outreach.services.media": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False
        },
        "podcast_outreach.services.tasks.manager": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False
        },
        "podcast_outreach.services.scheduler": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False
        },
        "podcast_outreach.services.events": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False
        },
        "googleapiclient.discovery_cache": {
            "handlers": ["console"],
            "level": "ERROR",  # These are particularly noisy
            "propagate": False
        },
        # Keep important logs at INFO level
        "podcast_outreach.main": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False
        },
        "podcast_outreach.api": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False
        },
        "podcast_outreach.services.chatbot": {
            "handlers": ["console"],
            "level": "INFO",
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