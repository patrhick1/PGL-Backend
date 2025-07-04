# config/__init__.py
"""Configuration module for podcast outreach application."""

# Import all constants from the parent config.py file
# We need to be careful to avoid circular imports
import importlib.util
import os

# Get the path to the parent config.py file
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_path = os.path.join(parent_dir, 'config.py')

# Load config.py as a module
spec = importlib.util.spec_from_file_location("parent_config", config_path)
parent_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parent_config)

# Export all the constants from parent config
ENABLE_LLM_TEST_DASHBOARD = parent_config.ENABLE_LLM_TEST_DASHBOARD
PORT = parent_config.PORT
FRONTEND_ORIGIN = parent_config.FRONTEND_ORIGIN
IS_PRODUCTION = parent_config.IS_PRODUCTION
FREE_PLAN_DAILY_DISCOVERY_LIMIT = parent_config.FREE_PLAN_DAILY_DISCOVERY_LIMIT
FREE_PLAN_WEEKLY_DISCOVERY_LIMIT = parent_config.FREE_PLAN_WEEKLY_DISCOVERY_LIMIT
PAID_PLAN_DAILY_DISCOVERY_LIMIT = parent_config.PAID_PLAN_DAILY_DISCOVERY_LIMIT
PAID_PLAN_WEEKLY_DISCOVERY_LIMIT = parent_config.PAID_PLAN_WEEKLY_DISCOVERY_LIMIT
LISTENNOTES_PAGE_SIZE = parent_config.LISTENNOTES_PAGE_SIZE
PODSCAN_PAGE_SIZE = parent_config.PODSCAN_PAGE_SIZE
API_CALL_DELAY = parent_config.API_CALL_DELAY
ORCHESTRATOR_CONFIG = parent_config.ORCHESTRATOR_CONFIG
FFMPEG_PATH = parent_config.FFMPEG_PATH
FFPROBE_PATH = parent_config.FFPROBE_PATH

# Import discovery config
from .discovery_config import *