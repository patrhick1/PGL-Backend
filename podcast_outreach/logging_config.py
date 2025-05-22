import logging
import sys
from podcast_outreach.config import LOG_LEVEL # Assuming LOG_LEVEL is defined in config.py

logging.basicConfig(
    level=LOG_LEVEL,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)

def get_logger(name):
    return logging.getLogger(name) 