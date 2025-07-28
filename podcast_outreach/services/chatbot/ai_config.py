"""
AI Configuration for Chatbot System

This module provides configuration for Gemini 2.0 Flash and other AI models
used in the chatbot system, including optimized settings for different use cases.
"""

import os
from typing import Dict, Any, Optional, List
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Model configurations for different use cases
GEMINI_CONFIGS = {
    "correction_detection": {
        "model": "gemini-2.0-flash",
        "temperature": 0.2,  # Low for consistency
        "top_p": 0.1,
        "top_k": 1,
        "max_output_tokens": 1000,
        "safety_settings": [
            {
                "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
                "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
            },
        ]
    },
    "phase_analysis": {
        "model": "gemini-2.0-flash",
        "temperature": 0.3,  # Slightly more creative for decision making
        "top_p": 0.2,
        "top_k": 5,
        "max_output_tokens": 1500,
    },
    "question_generation": {
        "model": "gemini-2.0-flash",
        "temperature": 0.7,  # More creative for natural questions
        "top_p": 0.8,
        "top_k": 40,
        "max_output_tokens": 800,
    },
    "data_extraction": {
        "model": "gemini-2.0-flash",
        "temperature": 0.1,  # Very low for accurate extraction
        "top_p": 0.1,
        "top_k": 1,
        "max_output_tokens": 2000,
    },
    "security_validation": {
        "model": "gemini-2.0-flash",
        "temperature": 0.0,  # Deterministic for security
        "top_p": 0.1,
        "top_k": 1,
        "max_output_tokens": 500,
        "safety_settings": [
            {
                "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
                "threshold": HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,  # Stricter for security
            },
            {
                "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                "threshold": HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                "threshold": HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
            },
            {
                "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                "threshold": HarmBlockThreshold.BLOCK_LOW_AND_ABOVE,
            },
        ]
    },
    "completion_analysis": {
        "model": "gemini-2.0-flash",
        "temperature": 0.3,
        "top_p": 0.3,
        "top_k": 10,
        "max_output_tokens": 800,
    }
}

# Default safety settings if not specified in config
DEFAULT_SAFETY_SETTINGS = [
    {
        "category": HarmCategory.HARM_CATEGORY_HARASSMENT,
        "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_HATE_SPEECH,
        "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
        "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    },
    {
        "category": HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
        "threshold": HarmBlockThreshold.BLOCK_MEDIUM_AND_ABOVE,
    },
]

def get_gemini_config(use_case: str) -> Dict[str, Any]:
    """
    Get Gemini configuration for a specific use case.
    
    Args:
        use_case: The use case (e.g., "correction_detection", "phase_analysis")
        
    Returns:
        Dictionary with model configuration
    """
    config = GEMINI_CONFIGS.get(use_case, {}).copy()
    
    # Add default safety settings if not specified
    if "safety_settings" not in config:
        config["safety_settings"] = DEFAULT_SAFETY_SETTINGS
    
    # Ensure we have a model specified
    if "model" not in config:
        config["model"] = "gemini-2.0-flash"
    
    return config

# Prompt engineering best practices
PROMPT_GUIDELINES = {
    "structured_output": {
        "prefix": "You are an AI assistant that ALWAYS responds with valid JSON. Never include explanations outside the JSON structure.",
        "suffix": "Respond ONLY with the JSON object, no additional text.",
    },
    "correction_detection": {
        "prefix": "You are analyzing a conversation to detect if the user is making a correction to previously provided information.",
        "examples": [
            {
                "input": "Actually, my email is john.doe@example.com",
                "output": {"is_correction": True, "field": "email"}
            },
            {
                "input": "That's great, thanks!",
                "output": {"is_correction": False}
            }
        ]
    },
    "phase_analysis": {
        "prefix": "You are analyzing a conversation to determine if it should transition to the next phase based on data completeness and quality.",
        "criteria": [
            "Essential data collected for current phase",
            "User engagement level",
            "Natural conversation flow",
            "LinkedIn data availability"
        ]
    }
}

# Timeout configurations
TIMEOUT_CONFIGS = {
    "correction_detection": 10,  # seconds
    "phase_analysis": 15,
    "question_generation": 20,
    "data_extraction": 30,
    "security_validation": 10,
    "completion_analysis": 15
}

# Retry configurations
RETRY_CONFIGS = {
    "max_retries": 3,
    "initial_delay": 1,  # seconds
    "max_delay": 30,     # seconds
    "exponential_base": 2
}

# Model selection logic
def select_model_for_task(task_type: str, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Select the best model for a given task based on context.
    
    Args:
        task_type: Type of task (e.g., "correction_detection")
        context: Optional context information
        
    Returns:
        Model name to use
    """
    # For now, we're using Gemini 2.0 Flash for everything
    # In the future, this could select different models based on:
    # - Task complexity
    # - Response time requirements
    # - Cost considerations
    # - Context size
    
    return "gemini-2.0-flash"

# Structured output configuration
STRUCTURED_OUTPUT_CONFIG = {
    "response_mime_type": "application/json",
    "enforce_schema": True,
    "retry_on_validation_error": True,
    "max_validation_retries": 2
}

# Cache configuration for common patterns
CACHE_CONFIG = {
    "enabled": True,
    "ttl_seconds": 3600,  # 1 hour
    "max_entries": 1000,
    "cache_types": [
        "correction_patterns",
        "common_questions",
        "phase_decisions"
    ]
}

# Monitoring configuration
MONITORING_CONFIG = {
    "log_all_requests": True,
    "log_all_responses": False,  # Only log on errors
    "track_token_usage": True,
    "alert_on_high_usage": True,
    "usage_threshold": 100000  # tokens per hour
}