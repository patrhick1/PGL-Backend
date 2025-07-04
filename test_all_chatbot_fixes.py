#!/usr/bin/env python3
"""
Test all chatbot fixes for the reported bugs
"""

import asyncio
from datetime import datetime
from podcast_outreach.services.chatbot.enhanced_nlp_processor import EnhancedNLPProcessor
from podcast_outreach.services.chatbot.improved_conversation_flows import ImprovedConversationFlowManager

async def test_all_fixes():
    """Test all the bug fixes"""
    
    print("\n" + "="*80)
    print("TESTING ALL CHATBOT FIXES")
    print("="*80)
    
    # Initialize components
    flow_manager = ImprovedConversationFlowManager()
    nlp_processor = EnhancedNLPProcessor()
    
    # Test 1: Name already known scenario
    print("\n[TEST 1] Name already known - should ask for email + LinkedIn")
    extracted_data = {
        "contact_info": {
            "fullName": "Michael Greenberg"
        }
    }
    completeness = await nlp_processor.check_data_completeness(extracted_data)
    missing_data = flow_manager.get_missing_critical_data(completeness)
    
    question = flow_manager.get_next_question(
        phase="introduction",
        message_count_in_phase=0,
        extracted_data=extracted_data,
        missing_data=missing_data
    )
    
    print(f"Question: {question}")
    assert "email" in question.lower(), "Should ask for email"
    assert "linkedin" in question.lower(), "Should ask for LinkedIn"
    
    # Test 2: Email question with LinkedIn already provided
    print("\n[TEST 2] LinkedIn already provided - email question should not ask for LinkedIn again")
    extracted_data = {
        "contact_info": {
            "fullName": "John Doe",
            "socialMedia": ["https://linkedin.com/in/johndoe"]
        }
    }
    
    question = flow_manager._create_targeted_question("email", extracted_data)
    print(f"Question: {question}")
    assert "linkedin" not in question.lower(), "Should NOT ask for LinkedIn again"
    
    # Test 3: Confirmation phase progression
    print("\n[TEST 3] Confirmation phase should progress through questions without looping")
    extracted_data = {"promotion_preferences": {}}
    
    questions = []
    for i in range(5):  # Try 5 messages in confirmation phase
        question = flow_manager.get_next_question(
            phase="confirmation",
            message_count_in_phase=i,
            extracted_data=extracted_data,
            missing_data=[]
        )
        questions.append(question)
        print(f"  Message {i+1}: {question[:50]}...")
    
    # Check no duplicates
    unique_questions = set(questions)
    assert len(unique_questions) == len(questions), "Should not have duplicate questions"
    
    # Test 4: LinkedIn already analyzed
    print("\n[TEST 4] LinkedIn already analyzed - should not ask for it again")
    extracted_data = {
        "contact_info": {
            "fullName": "Jane Smith",
            "socialMedia": ["https://linkedin.com/in/janesmith"]
        },
        "linkedin_analysis": {
            "analysis_complete": True
        }
    }
    
    has_linkedin = flow_manager._has_linkedin(extracted_data)
    print(f"Has LinkedIn: {has_linkedin}")
    assert has_linkedin, "Should recognize LinkedIn is already provided"
    
    question = flow_manager._create_targeted_question("email", extracted_data)
    print(f"Email question: {question}")
    assert "linkedin" not in question.lower(), "Should NOT ask for LinkedIn in email question"
    
    print("\n" + "="*80)
    print("ALL TESTS PASSED!")
    print("="*80)

if __name__ == "__main__":
    print("Starting Chatbot Fix Tests...")
    asyncio.run(test_all_fixes())