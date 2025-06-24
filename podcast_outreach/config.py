import os
from dotenv import load_dotenv

# Load environment variables from a .env file if present
load_dotenv()

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Database connection settings
DB_HOST = os.getenv("PGHOST")
DB_PORT = int(os.getenv("PGPORT"))
DB_NAME = os.getenv("PGDATABASE")
DB_USER = os.getenv("PGUSER")
DB_PASSWORD = os.getenv("PGPASSWORD")

# Third-party API keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API")
LISTEN_NOTES_API_KEY = os.getenv("LISTEN_NOTES_API_KEY")
PODSCAN_API_KEY = os.getenv("PODSCANAPI")
INSTANTLY_API_KEY = os.getenv("INSTANTLY_API_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")

# Google services
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
GOOGLE_PODCAST_INFO_FOLDER_ID = os.getenv("GOOGLE_PODCAST_INFO_FOLDER_ID")
PGL_AI_DRIVE_FOLDER_ID = os.getenv("PGL_AI_DRIVE_FOLDER_ID")

# Feature flags
ENABLE_LLM_TEST_DASHBOARD = os.getenv("ENABLE_LLM_TEST_DASHBOARD", "false").lower() == "true"
IS_PRODUCTION = os.getenv("IS_PRODUCTION", "false").lower() == "true"

# Worker/concurrency settings
EPISODE_SYNC_MAX_CONCURRENT_TASKS = int(os.getenv("EPISODE_SYNC_MAX_CONCURRENT_TASKS", "10"))
GEMINI_TRANSCRIPTION_MAX_RETRIES = int(os.getenv("GEMINI_TRANSCRIPTION_MAX_RETRIES", "3"))
GEMINI_TRANSCRIPTION_RETRY_DELAY = int(os.getenv("GEMINI_TRANSCRIPTION_RETRY_DELAY", "5"))
GEMINI_API_CONCURRENCY = int(os.getenv("GEMINI_API_CONCURRENCY", "10"))
DOWNLOAD_CONCURRENCY = int(os.getenv("DOWNLOAD_CONCURRENCY", "5"))
TRANSCRIBER_MAX_EPISODES_PER_BATCH = int(os.getenv("TRANSCRIBER_MAX_EPISODES_PER_BATCH", "20"))
FFMPEG_PATH = os.getenv("FFMPEG_CUSTOM_PATH")
FFPROBE_PATH = os.getenv("FFPROBE_CUSTOM_PATH")

# Default server port
PORT = int(os.getenv("PORT"))


FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN")

FREE_PLAN_DAILY_DISCOVERY_LIMIT = int(os.getenv("FREE_PLAN_DAILY_DISCOVERY_LIMIT", 10))
FREE_PLAN_WEEKLY_DISCOVERY_LIMIT = int(os.getenv("FREE_PLAN_WEEKLY_DISCOVERY_LIMIT", 50))

PAID_PLAN_DAILY_DISCOVERY_LIMIT = int(os.getenv("PAID_PLAN_DAILY_DISCOVERY_LIMIT", "100")) # Example
PAID_PLAN_WEEKLY_DISCOVERY_LIMIT = int(os.getenv("PAID_PLAN_WEEKLY_DISCOVERY_LIMIT", "500")) # Example

# --- API Client Settings ---
LISTENNOTES_PAGE_SIZE = int(os.getenv("LISTENNOTES_PAGE_SIZE", "10"))
PODSCAN_PAGE_SIZE = int(os.getenv("PODSCAN_PAGE_SIZE", "10"))
API_CALL_DELAY = float(os.getenv("API_CALL_DELAY", "1.0")) # Delay in seconds between API calls for rate limiting

# Configuration for the enrichment orchestrator
ORCHESTRATOR_CONFIG = {
    "media_enrichment_batch_size": 10,
    
    # MULTI-LEVEL ENRICHMENT CONFIGURATION
    "core_enrichment_interval_hours": 24 * 365,  # Core enrichment: rarely re-run (yearly)
    "social_stats_refresh_interval_hours": 24 * 7,  # Social stats: weekly refresh
    "quality_score_update_interval_hours": 24 * 7,  # Quality scores: weekly recalculation
    
    # LEGACY (keeping for backward compatibility)
    "media_enrichment_interval_hours": 24 * 7,  # General enrichment fallback
    "quality_score_update_interval_days": 7, # Legacy field
    
    "quality_score_min_transcribed_episodes": 3,
    "max_transcription_flags_per_media": 4, # Max episodes to flag for transcription per media item
    "main_loop_sleep_seconds": 300 # Sleep duration for the main orchestrator loop if run continuously
}
