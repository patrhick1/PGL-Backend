#!/usr/bin/env python3
"""
Test the LinkedIn feedback and summary features
"""

import asyncio
import json
from datetime import datetime
from podcast_outreach.services.chatbot.conversation_engine import ConversationEngine

async def test_feedback_and_summary():
    """Test LinkedIn feedback and conversation summary"""
    
    print("\n" + "="*80)
    print("TESTING LINKEDIN FEEDBACK AND SUMMARY FEATURES")
    print("="*80)
    
    # Initialize engine
    engine = ConversationEngine()
    
    # Test 1: LinkedIn Insights Formatting
    print("\n[TEST 1] LinkedIn Insights Formatting")
    print("-" * 40)
    
    sample_linkedin_data = {
        "analysis_complete": True,
        "professional_bio": "Experienced startup founder and podcast production expert with 10+ years in tech and media.",
        "expertise_keywords": ["Podcasting", "Startup Growth", "Content Marketing", "Tech Innovation", "Media Production"],
        "years_experience": 10,
        "key_achievements": [
            "Co-founded startup that raised $1.5M and successfully exited",
            "Built podcast agency serving 20+ clients",
            "Achieved 5 placements per client per month on average"
        ],
        "podcast_topics": [
            "Building and scaling podcast production agencies",
            "Startup fundraising and exit strategies",
            "Content marketing for B2B companies"
        ],
        "target_audience": "Entrepreneurs, content creators, and marketing professionals"
    }
    
    insights = engine._format_linkedin_insights(sample_linkedin_data)
    print("LinkedIn Insights Output:")
    print(insights)
    
    # Test 2: Conversation Summary Generation
    print("\n\n[TEST 2] Conversation Summary Generation")
    print("-" * 40)
    
    sample_extracted_data = {
        "contact_info": {
            "fullName": "Michael Greenberg",
            "email": "mgg@modernindustrialist.com",
            "website": "https://modernindustrialist.com",
            "socialMedia": ["https://linkedin.com/in/gentoftech", "https://twitter.com/gentoftech"]
        },
        "professional_bio": {
            "about_work": "I'm a startup founder turned podcast production agency owner. I help B2B companies get featured on relevant podcasts to grow their audience and authority."
        },
        "keywords": {
            "explicit": ["Podcasting", "B2B Marketing", "Content Strategy", "Startup Growth", "Media Production", "Agency Building"]
        },
        "stories": [
            {
                "subject": "Startup Exit",
                "challenge": "Building a tech startup from scratch",
                "result": "Raised $1.5M and successfully exited to start podcast agency"
            }
        ],
        "achievements": [
            {
                "description": "Helping 20+ clients achieve average of 5 podcast placements per month"
            }
        ],
        "topics": {
            "suggested": [
                "How to build a successful podcast production agency",
                "B2B podcast guesting strategies",
                "Transitioning from startup founder to agency owner",
                "Content marketing through podcast appearances"
            ]
        },
        "target_audience": "B2B companies looking to grow through content marketing and podcast guesting",
        "unique_value": "I've been on both sides - as a podcast guest and now helping others get booked. I understand what hosts want and how to position guests for success.",
        "linkedin_analysis": sample_linkedin_data
    }
    
    summary = engine._generate_conversation_summary(sample_extracted_data)
    print("Conversation Summary Output:")
    print(summary)
    
    # Test 3: Show how it appears in conversation flow
    print("\n\n[TEST 3] How it appears in conversation")
    print("-" * 40)
    
    # Simulate LinkedIn processing message
    print("\n[USER]: Here's my LinkedIn: https://linkedin.com/in/gentoftech")
    print("\n[BOT]: I see you've shared your LinkedIn profile! Let me analyze it quickly to learn more about your expertise... This will just take a moment.")
    print("\n[LinkedIn Analysis Complete]")
    print(f"\n[BOT]: Great! I've analyzed your LinkedIn profile. Here's what I learned about you:\n\n{insights}\n\nIf any of this needs updating, just let me know! Otherwise, let me continue with a few more specific questions.\n\n[Next question would go here]")
    
    # Simulate confirmation phase with summary
    print("\n" + "-"*40)
    print("\n[Entering Confirmation Phase]")
    confirmation_message = f"We're almost done! Here's a summary of what I've learned about you for your media kit:\n\n{summary}\n\nIs there anything you'd like to add or change?"
    print(f"\n[BOT]: {confirmation_message}")
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)

if __name__ == "__main__":
    print("Starting Feedback and Summary Test...")
    asyncio.run(test_feedback_and_summary())