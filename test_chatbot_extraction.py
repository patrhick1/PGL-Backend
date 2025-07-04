#!/usr/bin/env python3
"""Test script for chatbot data extraction"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from podcast_outreach.services.chatbot.enhanced_nlp_processor import EnhancedNLPProcessor
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

async def test_extraction():
    """Test the enhanced NLP processor extraction"""
    
    processor = EnhancedNLPProcessor()
    
    # Test message
    test_message = "Hi! My name is John Smith and I'm the founder and CEO of TechStartup Inc. You can reach me at john@techstartup.com"
    
    # Mock conversation history
    conversation_history = [
        {
            "type": "bot",
            "content": "Hi there! I'm excited to help you create an amazing media kit. To get started, what's your full name and email address?"
        },
        {
            "type": "user", 
            "content": test_message
        }
    ]
    
    # Test extraction
    logger.info("Testing extraction with message: %s", test_message)
    
    try:
        result = await processor.process(
            message=test_message,
            conversation_history=conversation_history,
            extracted_data={},
            existing_keywords=[]
        )
        
        logger.info("Extraction successful!")
        logger.info("Result: %s", result)
        
        # Check specific fields
        contact_info = result.get("contact_info", {})
        logger.info("Extracted name: %s", contact_info.get("fullName"))
        logger.info("Extracted email: %s", contact_info.get("email"))
        logger.info("Extracted company: %s", contact_info.get("company"))
        logger.info("Extracted role: %s", contact_info.get("role"))
        
    except Exception as e:
        logger.error("Extraction failed: %s", e)
        raise

if __name__ == "__main__":
    asyncio.run(test_extraction())