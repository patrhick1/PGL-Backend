#!/usr/bin/env python3
"""
Test script for LinkedIn integration in chatbot
"""

import asyncio
import logging
from podcast_outreach.services.chatbot.linkedin_analyzer import LinkedInAnalyzer

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_linkedin_analyzer():
    """Test the LinkedIn analyzer with a sample URL"""
    
    # Initialize the analyzer
    analyzer = LinkedInAnalyzer()
    
    # Test LinkedIn URL (replace with a real LinkedIn URL for testing)
    test_url = "http://linkedin.com/in/gentoftech/"
    
    print("Testing LinkedIn Analyzer...")
    print(f"URL: {test_url}")
    print("-" * 50)
    
    try:
        # Analyze the profile
        result = await analyzer.analyze_profile(test_url)
        
        if result:
            print("Analysis successful!")
            print(f"Analysis complete: {result.get('analysis_complete', False)}")
            print(f"Professional bio: {result.get('professional_bio', 'Not found')}")
            print(f"Expertise keywords: {result.get('expertise_keywords', [])}")
            print(f"Success stories: {len(result.get('success_stories', []))} found")
            print(f"Podcast topics: {result.get('podcast_topics', [])}")
            print(f"Target audience: {result.get('target_audience', 'Not found')}")
        else:
            print("No results returned from analyzer")
            
    except Exception as e:
        print(f"Error during analysis: {e}")
        logger.exception("Detailed error:")

async def test_conversation_flow():
    """Test the conversation flow with LinkedIn integration"""
    from podcast_outreach.services.chatbot.conversation_engine import ConversationEngine
    
    print("\n\nTesting Conversation Flow with LinkedIn...")
    print("-" * 50)
    
    # Initialize conversation engine
    engine = ConversationEngine()
    
    # Simulate conversation with LinkedIn URL
    test_messages = [
        "John Doe, john@example.com",
        "Yes, my LinkedIn is https://www.linkedin.com/in/johndoe",
        "My website is johndoe.com"
    ]
    
    # This would normally interact with a real conversation
    # For testing, we just verify the methods exist
    print("Conversation engine initialized successfully")
    print("LinkedIn extraction method exists:", hasattr(engine, '_extract_linkedin_from_social'))
    print("LinkedIn merge method exists:", hasattr(engine, '_merge_linkedin_insights'))
    print("Smart question method exists:", hasattr(engine, '_get_smart_question'))
    
if __name__ == "__main__":
    print("LinkedIn Integration Test Script")
    print("=" * 50)
    
    # Run tests
    asyncio.run(test_linkedin_analyzer())
    asyncio.run(test_conversation_flow())