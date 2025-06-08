# podcast_outreach/services/enrichment/quality_score.py

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
import statistics
from dateutil import parser # For robust date parsing if needed

# Corrected import path for EnrichedPodcastProfile
from podcast_outreach.database.models.media_models import EnrichedPodcastProfile

# We won't need LLMQualityVettingOutput as per decision (if it was used)
# from podcast_outreach.database.models.llm_outputs import LLMQualityVettingOutput # Removed as per previous discussion

from podcast_outreach.logging_config import get_logger # Use new logging config

logger = get_logger(__name__) # Use the new get_logger function

# Configuration for quality score calculation (Moved from old src/enrichment/quality_service.py)
# These thresholds and weights can be tuned.
QUALITY_CONFIG = {
    "recency_max_days_ideal": 30,        # For max score
    "recency_max_days_good": 90,         # For partial score
    "recency_max_days_stale": 180,       # Threshold for very low score
    "frequency_ideal_days": 14,          # e.g., bi-weekly or better
    "frequency_good_days": 35,           # e.g., monthly or better
    "frequency_min_episodes_for_calc": 5,
    "audience_metrics": {
        "listen_score_weight": 0.3,
        "audience_size_weight": 0.3,     # Direct audience size
        "itunes_rating_weight": 0.2,     # Combined iTunes rating and count
        "spotify_rating_weight": 0.2,    # Combined Spotify rating and count
        # Normalization thresholds (examples, need tuning based on typical data ranges)
        "listen_score_norm_max": 90,     # Assume Listen Score rarely exceeds this for normalization
        "audience_size_norm_high": 10000, # Example: 10k listeners is high
        "rating_count_norm_high": 500    # Example: 500 ratings is high
    },
    "social_metrics": {
        "twitter_followers_weight": 0.4,
        "instagram_followers_weight": 0.2,
        "youtube_subscribers_weight": 0.2,
        "tiktok_followers_weight": 0.1,
        "facebook_likes_weight": 0.1,
        # Normalization thresholds (examples)
        "followers_norm_high": 50000     # Example: 50k followers is high for any platform
    },
    "weights": {
        "recency_score": 0.25,
        "frequency_score": 0.25,
        "audience_score": 0.30,
        "social_score": 0.20
    }
}

class QualityService:
    """Service to calculate a quantitative quality score for podcasts."""

    def __init__(self):
        logger.info("QualityService initialized.")

    def _normalize_score(self, value: Optional[float], max_value: float, min_value: float = 0.0) -> float:
        """Normalizes a value to a 0-1 scale given a max_value (and optional min_value)."""
        if value is None or max_value == min_value: # Avoid division by zero
            return 0.0 # Default to 0 if value is missing or range is zero
        
        # Clamp value to be within [min_value, max_value]
        clamped_value = max(min_value, min(value, max_value))
        
        # Normalize
        normalized = (clamped_value - min_value) / (max_value - min_value)
        return normalized

    def _calculate_recency_score(self, profile: EnrichedPodcastProfile) -> Tuple[float, Optional[int]]:
        """Calculates recency score (0-1) and days since last episode."""
        last_episode_date_to_use = profile.latest_episode_date or profile.last_posted_at
        days_since_last: Optional[int] = None

        if last_episode_date_to_use:
            # Ensure naive datetime for comparison with datetime.now()
            if isinstance(last_episode_date_to_use, str):
                try: last_episode_date_to_use = parser.parse(last_episode_date_to_use).replace(tzinfo=None)
                except (ValueError, TypeError): last_episode_date_to_use = None
            elif isinstance(last_episode_date_to_use, datetime) and last_episode_date_to_use.tzinfo:
                last_episode_date_to_use = last_episode_date_to_use.replace(tzinfo=None)
            
            if isinstance(last_episode_date_to_use, datetime):
                days_since_last = (datetime.now() - last_episode_date_to_use).days
                if days_since_last <= QUALITY_CONFIG["recency_max_days_ideal"]:
                    return 1.0, days_since_last
                elif days_since_last <= QUALITY_CONFIG["recency_max_days_good"]:
                    # Linear decay from 1.0 down to (e.g.) 0.5
                    score = 1.0 - 0.5 * ((days_since_last - QUALITY_CONFIG["recency_max_days_ideal"]) / 
                                         (QUALITY_CONFIG["recency_max_days_good"] - QUALITY_CONFIG["recency_max_days_ideal"]))
                    return max(0.5, score), days_since_last # Ensure it doesn't go below 0.5 in this tier
                elif days_since_last <= QUALITY_CONFIG["recency_max_days_stale"]:
                     # Linear decay from 0.5 down to 0.1
                    score = 0.5 - 0.4 * ((days_since_last - QUALITY_CONFIG["recency_max_days_good"]) / 
                                         (QUALITY_CONFIG["recency_max_days_stale"] - QUALITY_CONFIG["recency_max_days_good"]))
                    return max(0.1, score), days_since_last
                else:
                    return 0.0, days_since_last # Very stale
        return 0.0, days_since_last # No date available

    def _calculate_frequency_score(self, profile: EnrichedPodcastProfile) -> Tuple[float, Optional[float]]:
        """Calculates frequency score (0-1) and average frequency in days."""
        avg_freq_days: Optional[float] = None

        if profile.publishing_frequency_days is not None:
            avg_freq_days = profile.publishing_frequency_days
        elif profile.total_episodes and profile.first_episode_date and profile.latest_episode_date and \
             profile.total_episodes >= QUALITY_CONFIG["frequency_min_episodes_for_calc"]:
            
            first_date = profile.first_episode_date
            last_date = profile.latest_episode_date

            if isinstance(first_date, str): first_date = parser.parse(first_date).replace(tzinfo=None)
            if isinstance(last_date, str): last_date = parser.parse(last_date).replace(tzinfo=None)
            if first_date and first_date.tzinfo: first_date = first_date.replace(tzinfo=None)
            if last_date and last_date.tzinfo: last_date = last_date.replace(tzinfo=None)

            if isinstance(first_date, datetime) and isinstance(last_date, datetime) and last_date > first_date:
                duration_days = (last_date - first_date).days
                if duration_days > 0 and profile.total_episodes > 1:
                    avg_freq_days = duration_days / (profile.total_episodes - 1)
        
        if avg_freq_days is not None:
            if avg_freq_days <= QUALITY_CONFIG["frequency_ideal_days"]:
                return 1.0, avg_freq_days
            elif avg_freq_days <= QUALITY_CONFIG["frequency_good_days"]:
                score = 1.0 - 0.5 * ((avg_freq_days - QUALITY_CONFIG["frequency_ideal_days"]) / 
                                     (QUALITY_CONFIG["frequency_good_days"] - QUALITY_CONFIG["frequency_ideal_days"]))
                return max(0.5, score), avg_freq_days
            else:
                # Score decays more sharply for frequencies worse than "good"
                # Max value for this part is (e.g.) 90 days, at which score is 0.1
                stale_frequency_threshold = QUALITY_CONFIG["frequency_good_days"] * 2.5 
                score = 0.5 * (1 - ( (avg_freq_days - QUALITY_CONFIG["frequency_good_days"]) / 
                                      (stale_frequency_threshold - QUALITY_CONFIG["frequency_good_days"]) ))
                return max(0.0, score), avg_freq_days # Allow score to go to 0
        return 0.0, avg_freq_days # No frequency data

    def _calculate_audience_score(self, profile: EnrichedPodcastProfile) -> float:
        """Calculates audience score (0-1) based on listen score, audience size, ratings."""
        cfg = QUALITY_CONFIG["audience_metrics"]
        
        # Listen Score component (if available)
        norm_listen_score = self._normalize_score(profile.listen_score, cfg["listen_score_norm_max"])
        
        # Audience Size component
        norm_audience_size = self._normalize_score(profile.audience_size, cfg["audience_size_norm_high"])

        # iTunes Rating component (combining average rating and count)
        itunes_component_score = 0.0
        if profile.itunes_rating_average is not None and profile.itunes_rating_count is not None:
            norm_rating_avg = self._normalize_score(profile.itunes_rating_average, 5.0) # Assuming 5-star scale
            norm_rating_count = self._normalize_score(profile.itunes_rating_count, cfg["rating_count_norm_high"])
            itunes_component_score = (norm_rating_avg * 0.7) + (norm_rating_count * 0.3) # Weighted average
        
        # Spotify Rating component
        spotify_component_score = 0.0
        if profile.spotify_rating_average is not None and profile.spotify_rating_count is not None:
            norm_spotify_avg = self._normalize_score(profile.spotify_rating_average, 5.0)
            norm_spotify_count = self._normalize_score(profile.spotify_rating_count, cfg["rating_count_norm_high"])
            spotify_component_score = (norm_spotify_avg * 0.7) + (norm_spotify_count * 0.3)
            
        # Weighted sum of components
        total_score = (
            norm_listen_score * cfg["listen_score_weight"] +
            norm_audience_size * cfg["audience_size_weight"] +
            itunes_component_score * cfg["itunes_rating_weight"] +
            spotify_component_score * cfg["spotify_rating_weight"]
        )
        # Ensure total weight doesn't exceed 1 if some components are missing - simple sum for now
        # A more robust approach might re-distribute weights if some data is absent.
        return max(0.0, min(total_score, 1.0)) # Clamp to 0-1

    def _calculate_social_score(self, profile: EnrichedPodcastProfile) -> float:
        """Calculates social media presence score (0-1)."""
        cfg = QUALITY_CONFIG["social_metrics"]
        
        norm_twitter = self._normalize_score(profile.twitter_followers, cfg["followers_norm_high"])
        norm_instagram = self._normalize_score(profile.instagram_followers, cfg["followers_norm_high"])
        norm_youtube = self._normalize_score(profile.youtube_subscribers, cfg["followers_norm_high"])
        norm_tiktok = self._normalize_score(profile.tiktok_followers, cfg["followers_norm_high"])
        norm_facebook = self._normalize_score(profile.facebook_likes, cfg["followers_norm_high"])

        total_score = (
            norm_twitter * cfg["twitter_followers_weight"] +
            norm_instagram * cfg["instagram_followers_weight"] +
            norm_youtube * cfg["youtube_subscribers_weight"] +
            norm_tiktok * cfg["tiktok_followers_weight"] +
            norm_facebook * cfg["facebook_likes_weight"]
        )
        return max(0.0, min(total_score, 1.0))

    def calculate_podcast_quality_score(
        self, 
        profile: EnrichedPodcastProfile
    ) -> Tuple[Optional[float], Dict[str, Any]]:
        """Calculates the overall quantitative quality score (0-100) for a podcast profile.

        Args:
            profile: The EnrichedPodcastProfile of the podcast.

        Returns:
            A tuple: (overall_quality_score, detailed_metrics_dict).
            Score is None if critical data (like profile itself) is missing.
        """
        if not profile:
            logger.warning("Cannot calculate quality score: profile is None.")
            return None, {}

        logger.info(f"Calculating quality score for: {profile.api_id or profile.unified_profile_id} - {profile.title}")

        recency_score, days_since_last = self._calculate_recency_score(profile)
        frequency_score, avg_freq_days = self._calculate_frequency_score(profile)
        audience_score = self._calculate_audience_score(profile)
        social_score = self._calculate_social_score(profile)

        weights = QUALITY_CONFIG["weights"]
        
        overall_score_0_to_1 = (
            recency_score * weights["recency_score"] +
            frequency_score * weights["frequency_score"] +
            audience_score * weights["audience_score"] +
            social_score * weights["social_score"]
        )
        
        # Final score scaled to 0-100, kept as float
        final_quality_score = max(0.0, min(overall_score_0_to_1 * 100, 100))

        detailed_metrics = {
            "quality_score": final_quality_score,
            "quality_score_recency": recency_score,
            "quality_score_frequency": frequency_score,
            "quality_score_audience": audience_score,
            "quality_score_social": social_score,
            "quality_score_last_calculated": datetime.utcnow()
        }
        
        logger.info(f"Quality score for '{profile.title}': {final_quality_score}. Details: {detailed_metrics}")
        # The first element of the tuple is still the final score for convenience
        return final_quality_score, detailed_metrics

# Example Usage (for direct testing of this service module)
if __name__ == '__main__':
    # Import EnrichedPodcastProfile for testing purposes
    # This import is relative to the project root, as this script might be run directly.
    # In a production environment, this would typically be handled by the main app's import system.
    # Ensure `podcast_outreach` is in PYTHONPATH or run from project root.
    try:
        from podcast_outreach.database.models.media_models import EnrichedPodcastProfile
    except ImportError:
        # Fallback if running from a different directory for testing
        import sys
        import os
        sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
        from podcast_outreach.database.models.media_models import EnrichedPodcastProfile


    qs = QualityService()

    # Test case 1: Good, active podcast
    profile1_data = {
        "api_id": "test001",
        "title": "Active & Awesome Podcast",
        "latest_episode_date": datetime.now() - timedelta(days=10),
        "first_episode_date": datetime.now() - timedelta(days=365),
        "total_episodes": 50,
        "listen_score": 85,
        "audience_size": 15000,
        "itunes_rating_average": 4.8,
        "itunes_rating_count": 600,
        "twitter_followers": 20000
    }
    profile1 = EnrichedPodcastProfile(**profile1_data)
    score1, details1 = qs.calculate_podcast_quality_score(profile1)
    print(f"\n--- Profile 1 ({profile1.title}) ---")
    print(f"Overall Quality Score: {score1}")
    # print(f"Details: {json.dumps(details1, indent=2)}") # Requires json import for full print

    # Test case 2: Stale podcast with low engagement
    profile2_data = {
        "api_id": "test002",
        "title": "Old & Quiet Show",
        "latest_episode_date": datetime.now() - timedelta(days=200),
        "first_episode_date": datetime.now() - timedelta(days=700),
        "total_episodes": 20, # Low for the duration
        "listen_score": 30,
        "audience_size": 500,
        "itunes_rating_average": 3.1,
        "itunes_rating_count": 50,
        "twitter_followers": 150
    }
    profile2 = EnrichedPodcastProfile(**profile2_data)
    score2, details2 = qs.calculate_podcast_quality_score(profile2)
    print(f"\n--- Profile 2 ({profile2.title}) ---")
    print(f"Overall Quality Score: {score2}")

    # Test case 3: New podcast, some data missing
    profile3_data = {
        "api_id": "test003",
        "title": "New Kid on the Block",
        "latest_episode_date": datetime.now() - timedelta(days=5),
        "first_episode_date": datetime.now() - timedelta(days=30), # Only 1 month old
        "total_episodes": 4, # Not enough for full frequency calc by default
        "publishing_frequency_days": 7, # But explicitly provided
        "listen_score": None, # Missing
        "audience_size": 1000,
        "itunes_rating_average": None,
        "itunes_rating_count": 5,
        "twitter_followers": 50
    }
    profile3 = EnrichedPodcastProfile(**profile3_data)
    score3, details3 = qs.calculate_podcast_quality_score(profile3)
    print(f"\n--- Profile 3 ({profile3.title}) ---")
    print(f"Overall Quality Score: {score3}")

    # Test case 4: Missing critical date for recency
    profile4_data = {
        "api_id": "test004",
        "title": "Ghost Podcast (No Dates)",
        "latest_episode_date": None,
        "first_episode_date": None,
        "total_episodes": 100,
        "audience_size": 2000
    }
    profile4 = EnrichedPodcastProfile(**profile4_data)
    score4, details4 = qs.calculate_podcast_quality_score(profile4)
    print(f"\n--- Profile 4 ({profile4.title}) ---")
    print(f"Overall Quality Score: {score4}")