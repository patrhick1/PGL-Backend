#!/usr/bin/env python3
"""Test the specific scenario from Paschal's conversation"""

import asyncio
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from podcast_outreach.services.chatbot.enhanced_nlp_processor import EnhancedNLPProcessor
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

async def test_paschal_scenario():
    """Test the exact scenario that was causing issues"""
    
    processor = EnhancedNLPProcessor()
    
    # Paschal's exact message
    test_message = "pokonkwo@g.emporia.edu"
    
    logger.info("Testing Paschal's scenario...")
    logger.info(f"Input message: {test_message}")
    
    # Process the message
    result = await processor.process(
        message=test_message,
        conversation_history=[
            {
                "type": "bot",
                "content": "I'll need your email address to include in the media kit. What's the best email for podcast hosts to reach you?"
            },
            {
                "type": "user",
                "content": test_message
            }
        ],
        extracted_data={},
        existing_keywords=[]
    )
    
    # Check results
    contact_info = result.get("contact_info", {})
    
    logger.info("\nExtracted data:")
    logger.info(f"  Email: {contact_info.get('email')}")
    logger.info(f"  Website: {contact_info.get('website')}")
    logger.info(f"  Social Media: {contact_info.get('socialMedia', [])}")
    
    # Verify no fake URLs were created
    assert contact_info.get('email') == "pokonkwo@g.emporia.edu", "Email not extracted correctly"
    assert contact_info.get('website') is None or contact_info.get('website') == "", f"Fake website created: {contact_info.get('website')}"
    assert len(contact_info.get('socialMedia', [])) == 0, f"Fake social media created: {contact_info.get('socialMedia')}"
    
    logger.info("\n✓ Test passed! No fake URLs were created from the email address.")
    
    # Test a proper website mention
    logger.info("\n\nTesting with explicit website mention...")
    test_message2 = "My website is www.thirdbrain.ai"
    
    result2 = await processor.process(
        message=test_message2,
        conversation_history=[],
        extracted_data=result,  # Use previous extracted data
        existing_keywords=[]
    )
    
    contact_info2 = result2.get("contact_info", {})
    logger.info(f"Website extracted: {contact_info2.get('website')}")
    assert contact_info2.get('website') == "https://www.thirdbrain.ai", "Website not extracted correctly"
    logger.info("✓ Website correctly extracted when explicitly mentioned!")

if __name__ == "__main__":
    asyncio.run(test_paschal_scenario())