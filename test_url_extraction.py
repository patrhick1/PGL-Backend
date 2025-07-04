#!/usr/bin/env python3
"""Test URL extraction to ensure no fake URLs are created"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from podcast_outreach.services.chatbot.enhanced_nlp_processor import EnhancedNLPProcessor
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

async def test_url_extraction():
    """Test various URL extraction scenarios"""
    
    processor = EnhancedNLPProcessor()
    
    # Test cases
    test_cases = [
        {
            "name": "Email only - should NOT create fake URLs",
            "message": "My email is pokonkwo@g.emporia.edu",
            "expected": {
                "email": "pokonkwo@g.emporia.edu",
                "website": None,
                "social_media": []
            }
        },
        {
            "name": "Email with explicit website",
            "message": "My email is john@example.com and my website is www.johnsmith.com",
            "expected": {
                "email": "john@example.com",
                "website": "https://www.johnsmith.com",
                "social_media": []
            }
        },
        {
            "name": "Email with LinkedIn",
            "message": "Contact me at jane@company.com. My LinkedIn is linkedin.com/in/janesmith",
            "expected": {
                "email": "jane@company.com",
                "website": None,
                "social_media": ["https://linkedin.com/in/janesmith"]
            }
        },
        {
            "name": "Email with Twitter handle",
            "message": "Email: bob@startup.io, Twitter: @bobthebuilder",
            "expected": {
                "email": "bob@startup.io",
                "website": None,
                "social_media": ["https://twitter.com/bobthebuilder"]
            }
        },
        {
            "name": "No social media mentioned",
            "message": "I'm Sarah Johnson, CEO of Tech Corp. You can reach me at sarah@techcorp.com",
            "expected": {
                "email": "sarah@techcorp.com",
                "website": None,
                "social_media": []
            }
        }
    ]
    
    for test in test_cases:
        logger.info(f"\n=== Test: {test['name']} ===")
        logger.info(f"Message: {test['message']}")
        
        # Process with minimal context
        result = await processor.process(
            message=test['message'],
            conversation_history=[],
            extracted_data={},
            existing_keywords=[]
        )
        
        # Check results
        contact_info = result.get("contact_info", {})
        
        logger.info(f"Extracted email: {contact_info.get('email')}")
        logger.info(f"Extracted website: {contact_info.get('website')}")
        logger.info(f"Extracted social media: {contact_info.get('socialMedia', [])}")
        
        # Verify expectations
        if test['expected']['email']:
            assert contact_info.get('email') == test['expected']['email'], f"Email mismatch: {contact_info.get('email')} != {test['expected']['email']}"
        
        if test['expected']['website']:
            assert contact_info.get('website') == test['expected']['website'], f"Website mismatch: {contact_info.get('website')} != {test['expected']['website']}"
        else:
            assert not contact_info.get('website'), f"Unexpected website extracted: {contact_info.get('website')}"
        
        expected_social = set(test['expected']['social_media'])
        actual_social = set(contact_info.get('socialMedia', []))
        assert actual_social == expected_social, f"Social media mismatch: {actual_social} != {expected_social}"
        
        logger.info("✓ Test passed!")

if __name__ == "__main__":
    asyncio.run(test_url_extraction())