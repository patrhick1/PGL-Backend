"""
Discovery Configuration Module
Centralizes all discovery-related settings and thresholds
"""

from typing import Dict, Optional, Any

# Discovery workflow configuration
DISCOVERY_CONFIG = {
    # Vetting configuration
    'vetting': {
        'enabled': True,
        'score_threshold': 50,  # Minimum vetting score to create a match
        'max_retries': 2,
        'timeout_seconds': 60,
    },
    
    # Enrichment configuration
    'enrichment': {
        'enabled': True,
        'batch_size': 5,
        'timeout_seconds': 300,
        'max_retries': 3,
        'social_media_enabled': True,
        'transcription_enabled': True,
        'ai_description_enabled': True,
        'host_verification_enabled': True,
    },
    
    # Discovery limits
    'discovery': {
        'max_results_per_keyword': 10,
        'max_keywords_per_search': 10,
        'sources': ['listennotes', 'podscanfm'],  # Available podcast sources
        'require_contact_email': True,  # Only include podcasts with contact emails
        'max_concurrent_searches': 3,
    },
    
    # Client-specific limits
    'client_limits': {
        'free': {
            'weekly_match_limit': 50,  # Matches where vetting_score >= threshold
            'preview_limit': 15,  # For backwards compatibility
            'max_discoveries_per_request': 100,  # How many podcasts they can discover at once
            'enrichment_enabled': True,
            'vetting_enabled': True,
            'ai_description_enabled': True,
            'pitch_generation_enabled': False,
            'placement_management_enabled': False,
        },
        'paid_basic': {
            'weekly_match_limit': None,  # Unlimited
            'preview_limit': None,
            'max_discoveries_per_request': 500,
            'enrichment_enabled': True,
            'vetting_enabled': True,
            'ai_description_enabled': True,
            'pitch_generation_enabled': True,
            'placement_management_enabled': True,
        },
        'paid_premium': {
            'weekly_match_limit': None,  # Unlimited
            'preview_limit': None,
            'max_discoveries_per_request': 1000,
            'enrichment_enabled': True,
            'vetting_enabled': True,
            'ai_description_enabled': True,
            'pitch_generation_enabled': True,
            'placement_management_enabled': True,
            'priority_support': True,
            'custom_integrations': True,
        }
    },
    
    # Match creation configuration
    'match_creation': {
        'min_vetting_score': 50,  # Minimum score to create a match
        'auto_create_review_task': True,
        'notify_client_on_creation': True,
        'batch_size': 10,  # Create matches in batches
    },
    
    # Background task configuration
    'background_tasks': {
        'discovery_pipeline_timeout': 1800,  # 30 minutes
        'enrichment_worker_timeout': 600,  # 10 minutes per podcast
        'vetting_worker_timeout': 300,  # 5 minutes per podcast
        'max_concurrent_enrichments': 5,
        'max_concurrent_vettings': 3,
    },
    
    # Notification configuration
    'notifications': {
        'websocket_enabled': True,
        'email_enabled': True,
        'progress_update_interval': 10,  # seconds
        'batch_notification_threshold': 5,  # Send batch notifications after N matches
    },
    
    # Cache configuration
    'cache': {
        'enrichment_ttl': 86400,  # 24 hours
        'vetting_ttl': 604800,  # 7 days
        'discovery_ttl': 3600,  # 1 hour
    }
}

def get_plan_limits(plan_type: str) -> Dict[str, Any]:
    """
    Get discovery limits for a specific plan type.
    
    Args:
        plan_type: The subscription plan type (free, paid_basic, paid_premium)
        
    Returns:
        Dictionary of limits for the plan
    """
    return DISCOVERY_CONFIG['client_limits'].get(
        plan_type, 
        DISCOVERY_CONFIG['client_limits']['free']  # Default to free limits
    )

def get_vetting_threshold() -> int:
    """Get the minimum vetting score threshold for creating matches."""
    return DISCOVERY_CONFIG['vetting']['score_threshold']

def get_enrichment_config() -> Dict[str, Any]:
    """Get enrichment configuration settings."""
    return DISCOVERY_CONFIG['enrichment']

def get_discovery_config() -> Dict[str, Any]:
    """Get discovery configuration settings."""
    return DISCOVERY_CONFIG['discovery']

def get_match_creation_config() -> Dict[str, Any]:
    """Get match creation configuration settings."""
    return DISCOVERY_CONFIG['match_creation']

def get_notification_config() -> Dict[str, Any]:
    """Get notification configuration settings."""
    return DISCOVERY_CONFIG['notifications']

def is_feature_enabled_for_plan(plan_type: str, feature: str) -> bool:
    """
    Check if a specific feature is enabled for a plan.
    
    Args:
        plan_type: The subscription plan type
        feature: The feature to check (e.g., 'pitch_generation_enabled')
        
    Returns:
        True if the feature is enabled, False otherwise
    """
    plan_limits = get_plan_limits(plan_type)
    return plan_limits.get(feature, False)

def get_max_discoveries_for_plan(plan_type: str) -> int:
    """Get the maximum number of discoveries allowed per request for a plan."""
    plan_limits = get_plan_limits(plan_type)
    return plan_limits.get('max_discoveries_per_request', 100)

def get_weekly_match_limit(plan_type: str) -> Optional[int]:
    """
    Get the weekly match limit for a plan.
    
    Returns:
        The limit as an integer, or None for unlimited
    """
    plan_limits = get_plan_limits(plan_type)
    return plan_limits.get('weekly_match_limit')

# Environment-specific overrides (can be set via environment variables)
import os

# Allow overriding vetting threshold via environment variable
if os.getenv('VETTING_SCORE_THRESHOLD'):
    try:
        DISCOVERY_CONFIG['vetting']['score_threshold'] = int(os.getenv('VETTING_SCORE_THRESHOLD'))
    except ValueError:
        pass

# Allow overriding free plan match limit via environment variable
if os.getenv('FREE_PLAN_WEEKLY_MATCH_LIMIT'):
    try:
        DISCOVERY_CONFIG['client_limits']['free']['weekly_match_limit'] = int(os.getenv('FREE_PLAN_WEEKLY_MATCH_LIMIT'))
    except ValueError:
        pass