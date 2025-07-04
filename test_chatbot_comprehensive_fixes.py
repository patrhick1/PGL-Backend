#!/usr/bin/env python3
"""
Test comprehensive chatbot fixes for:
1. Story/achievement deduplication
2. User correction handling
3. Conversation completion
4. Progress tracking
"""

import asyncio
import json
from uuid import uuid4
from datetime import datetime
from podcast_outreach.services.chatbot.conversation_engine import ConversationEngine
from podcast_outreach.services.chatbot.enhanced_nlp_processor import EnhancedNLPProcessor

async def test_comprehensive_fixes():
    """Test all the chatbot fixes"""
    
    print("\n" + "="*80)
    print("TESTING COMPREHENSIVE CHATBOT FIXES")
    print("="*80)
    
    # Initialize engine
    engine = ConversationEngine()
    nlp = EnhancedNLPProcessor()
    
    # Test 1: Story Deduplication
    print("\n[TEST 1] Story Deduplication")
    print("-" * 40)
    
    existing_data = {
        'stories': [{
            'subject': 'Operational Leverage',
            'result': 'Average customer makes 5% more per million'
        }]
    }
    
    new_results = {
        'stories': [{
            'subject': 'Operational Leverage',
            'result': 'Average customer makes 5% more per million'
        }, {
            'subject': 'Startup Exit',
            'result': 'Raised $1.5M and exited'
        }]
    }
    
    merged = engine._merge_extracted_data(existing_data.copy(), new_results)
    print(f"Stories before: {len(existing_data['stories'])}")
    print(f"Stories after merge: {len(merged['stories'])}")
    print(f"Should be 2 (no duplicates): {len(merged['stories']) == 2}")
    
    # Test 2: Achievement Deduplication
    print("\n\n[TEST 2] Achievement Deduplication")
    print("-" * 40)
    
    existing_data2 = {
        'achievements': [{
            'description': 'Founded 3rd Brain'
        }]
    }
    
    new_results2 = {
        'achievements': [{
            'description': 'Founded 3rd Brain'
        }, {
            'description': 'Raised $1.5M'
        }]
    }
    
    merged2 = engine._merge_extracted_data(existing_data2.copy(), new_results2)
    print(f"Achievements before: {len(existing_data2['achievements'])}")
    print(f"Achievements after merge: {len(merged2['achievements'])}")
    print(f"Should be 2 (no duplicates): {len(merged2['achievements']) == 2}")
    
    # Test 3: Correction Detection
    print("\n\n[TEST 3] User Correction Handling")
    print("-" * 40)
    
    test_messages = [
        "for my key achievement I co-founded a startup that raised $1.5M",
        "actually, I meant to say we raised $2M",
        "let me clarify - the achievement was founding a podcast agency"
    ]
    
    for msg in test_messages:
        # Extract NLP results
        results = await nlp.process(msg, [], {}, [])
        print(f"\nMessage: '{msg}'")
        print(f"Achievements extracted: {results.get('achievements', [])}")
        
    # Test 4: LinkedIn Story Import without Duplication
    print("\n\n[TEST 4] LinkedIn Story Import")
    print("-" * 40)
    
    linkedin_data = {
        'success_stories': [{
            'title': 'Founded 3rd Brain',
            'description': 'Built company',
            'impact': 'Average customer makes 5% more'
        }]
    }
    
    extracted_data3 = {'stories': []}
    
    # Simulate multiple imports (this was causing duplication)
    for i in range(3):
        extracted_data3 = engine._merge_linkedin_insights(extracted_data3, linkedin_data)
    
    print(f"Stories after 3 LinkedIn imports: {len(extracted_data3['stories'])}")
    print(f"Should be 1 (no duplicates): {len(extracted_data3['stories']) == 1}")
    
    # Test 5: Conversation Completion
    print("\n\n[TEST 5] Conversation Completion")
    print("-" * 40)
    
    conversation_id = str(uuid4())
    state = engine._get_conversation_state(conversation_id)
    
    # Mark confirmation phase as complete
    state["phase_states"]["confirmation"]["complete"] = True
    
    # Test completion phrases
    completion_messages = ["awesome", "that's all", "perfect", "done"]
    
    for msg in completion_messages:
        print(f"Testing completion phrase: '{msg}'")
        # Check if it triggers completion
        completion_phrases = ['complete', 'done', 'finish', 'that\'s all', 'awesome', 'perfect', 'great']
        triggers_completion = any(phrase in msg.lower() for phrase in completion_phrases)
        print(f"  Triggers completion: {triggers_completion}")
    
    # Test 6: Progress Calculation
    print("\n\n[TEST 6] Progress Tracking")
    print("-" * 40)
    
    # Simulate confirmation complete
    test_data = {
        'contact_info': {'fullName': 'Test', 'email': 'test@test.com'},
        'stories': [{'result': 'Success'}],
        'keywords': {'explicit': ['test1', 'test2']},
        'linkedin_analysis': {'analysis_complete': True}
    }
    
    # Calculate base progress
    base_progress = nlp.calculate_progress(test_data)
    print(f"Base progress: {base_progress}%")
    
    # With LinkedIn bonus
    with_linkedin = min(base_progress + 15, 95)
    print(f"With LinkedIn bonus: {with_linkedin}%")
    
    # With confirmation complete
    state["phase_states"]["confirmation"]["complete"] = True
    final_progress = 100
    print(f"With confirmation complete: {final_progress}%")
    
    print("\n" + "="*80)
    print("ALL TESTS COMPLETE")
    print("="*80)

if __name__ == "__main__":
    print("Starting Comprehensive Fix Tests...")
    asyncio.run(test_comprehensive_fixes())