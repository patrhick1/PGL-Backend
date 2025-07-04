#!/usr/bin/env python3
"""
Test the conversation state management fixes
"""

import asyncio
import json
from uuid import uuid4
from datetime import datetime
from podcast_outreach.services.chatbot.conversation_engine import ConversationEngine
from podcast_outreach.services.chatbot.enhanced_nlp_processor import EnhancedNLPProcessor

async def test_state_management_fixes():
    """Test that the conversation state fixes prevent duplicate questions"""
    
    print("\n" + "="*80)
    print("TESTING CONVERSATION STATE MANAGEMENT FIXES")
    print("="*80)
    
    # Initialize engine
    engine = ConversationEngine()
    conversation_id = str(uuid4())
    
    # Test 1: Metrics question should not be asked twice
    print("\n[TEST 1] Preventing duplicate metrics question")
    print("-" * 40)
    
    # Simulate extracted data with metrics already present
    extracted_data = {
        "stories": [{
            "subject": "Startup Exit",
            "result": "Co-founded a startup that raised $1.5M and successfully exited"
        }],
        "linkedin_analysis": {
            "analysis_complete": True,
            "success_stories": [{"title": "Founded company"}]
        }
    }
    
    # Check if metrics exist
    has_metrics = engine._check_if_data_exists(extracted_data, "metrics")
    print(f"Has metrics in story: {has_metrics}")
    
    # Generate question - should not ask for metrics again
    question = await engine._generate_next_question(
        conversation_id,
        "core_discovery",
        [],
        extracted_data,
        {},
        "Test User"
    )
    print(f"Next question: {question[0][:100]}...")
    assert "metrics" not in question[0].lower(), "Should not ask for metrics when already have them"
    
    # Test 2: Confirmation phase summary should only show once
    print("\n\n[TEST 2] Confirmation phase summary shown only once")
    print("-" * 40)
    
    # First time in confirmation phase
    question1 = await engine._generate_next_question(
        conversation_id,
        "confirmation",
        [],
        extracted_data,
        {},
        "Test User"
    )
    print(f"First confirmation message: {question1[0][:50]}...")
    assert "summary of what I've learned" in question1[0], "Should show summary first time"
    
    # Second time in confirmation phase (simulate user response)
    extracted_data['recent_responses'] = ["Looks good"]
    question2 = await engine._generate_next_question(
        conversation_id,
        "confirmation",
        [{"type": "bot", "phase": "confirmation"}],
        extracted_data,
        {},
        "Test User"
    )
    print(f"Second confirmation message: {question2[0][:50]}...")
    assert "summary of what I've learned" not in question2[0], "Should NOT show summary again"
    
    # Test 3: Promotion question answered detection
    print("\n\n[TEST 3] Detecting promotion answer")
    print("-" * 40)
    
    # User says "Let's leave it at this" - should be recognized as promotion answered
    extracted_data['recent_responses'] = ["Let's leave it at this", "None for now"]
    
    # Mark promotion as asked
    engine._mark_question_asked(conversation_id, "promotion q", "promotion")
    
    # Should not ask about promotion again
    has_promotion = engine._check_if_data_exists(extracted_data, "promotion")
    print(f"Has promotion info: {has_promotion}")
    
    # Test 4: Contact preference detection
    print("\n\n[TEST 4] Detecting calendly link")
    print("-" * 40)
    
    extracted_data['recent_responses'] = ["https://calendly.com/jakeguso/rig-hut-demo"]
    has_contact_pref = engine._check_if_data_exists(extracted_data, "contact_preference")
    print(f"Has contact preference: {has_contact_pref}")
    assert has_contact_pref, "Should detect calendly link as contact preference"
    
    # Test 5: Complete conversation flow
    print("\n\n[TEST 5] Complete confirmation phase flow")
    print("-" * 40)
    
    # Reset for clean test
    conversation_id2 = str(uuid4())
    clean_data = {"stories": [], "recent_responses": []}
    
    # First: Show summary
    q1 = await engine._generate_next_question(conversation_id2, "confirmation", [], clean_data, {}, "Test")
    print("1. " + q1[0][:80] + "...")
    
    # User responds to summary
    clean_data['recent_responses'] = ["That's all"]
    
    # Second: Ask about promotion
    q2 = await engine._generate_next_question(conversation_id2, "confirmation", 
        [{"type": "bot", "phase": "confirmation"}], clean_data, {}, "Test")
    print("2. " + q2[0][:80] + "...")
    
    # User responds about promotion
    clean_data['recent_responses'].append("No promotion")
    
    # Third: Ask about contact
    q3 = await engine._generate_next_question(conversation_id2, "confirmation", 
        [{"type": "bot", "phase": "confirmation"}, {"type": "bot", "phase": "confirmation"}], 
        clean_data, {}, "Test")
    print("3. " + q3[0][:80] + "...")
    
    # User provides contact
    clean_data['recent_responses'].append("email me at test@example.com")
    
    # Fourth: Should complete
    q4 = await engine._generate_next_question(conversation_id2, "confirmation", 
        [{"type": "bot", "phase": "confirmation"}, {"type": "bot", "phase": "confirmation"}, 
         {"type": "bot", "phase": "confirmation"}], 
        clean_data, {}, "Test")
    print("4. " + q4[0][:80] + "...")
    assert "everything needed" in q4[0].lower(), "Should indicate completion"
    
    print("\n" + "="*80)
    print("ALL TESTS PASSED!")
    print("="*80)

if __name__ == "__main__":
    print("Starting State Management Tests...")
    asyncio.run(test_state_management_fixes())