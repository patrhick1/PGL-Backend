#!/usr/bin/env python3
"""
Test the exact scenario from the user's conversation
"""

import asyncio
import json
from datetime import datetime
from podcast_outreach.services.chatbot.enhanced_nlp_processor import EnhancedNLPProcessor
from podcast_outreach.services.chatbot.improved_conversation_flows import ImprovedConversationFlowManager
from podcast_outreach.services.chatbot.conversation_engine import ConversationEngine

async def test_real_scenario():
    """Test the exact flow from user's conversation"""
    
    print("\n" + "="*80)
    print("TESTING REAL USER SCENARIO")
    print("="*80)
    
    # Initialize components
    flow_manager = ImprovedConversationFlowManager()
    nlp_processor = EnhancedNLPProcessor()
    engine = ConversationEngine()
    
    # Simulate the exact conversation
    conversation_flow = [
        {
            "user_says": "Yes I am",
            "expected_bot_response_contains": ["full name", "email", "LinkedIn"]
        },
        {
            "user_says": "Paschal David, pnzumah@gmail.com, https://www.linkedin.com/in/paschal-david",
            "expected_bot_response_contains": ["LinkedIn profile", "analyzing"]
        }
    ]
    
    # Start conversation
    messages = []
    extracted_data = {}
    metadata = {}
    current_phase = "introduction"
    
    print("\n[BOT INITIAL]: Hi Paschal! I'm excited to help you create an amazing media kit...")
    print("              Ready to get started?")
    
    for i, step in enumerate(conversation_flow):
        print(f"\n{'-'*60}")
        print(f"STEP {i+1}:")
        print(f"[USER]: {step['user_says']}")
        
        # Process user message
        nlp_results = await nlp_processor.process(
            step['user_says'],
            messages[-5:] if messages else [],
            extracted_data,
            []
        )
        
        # Update extracted data
        if 'contact_info' in nlp_results:
            extracted_data.setdefault('contact_info', {}).update(nlp_results['contact_info'])
        if 'keywords' in nlp_results:
            extracted_data.setdefault('keywords', {}).update(nlp_results['keywords'])
        
        # Check completeness
        completeness = await nlp_processor.check_data_completeness(extracted_data)
        missing_data = flow_manager.get_missing_critical_data(completeness)
        
        # Get bot response
        messages_in_phase = len([m for m in messages if m.get('phase') == current_phase and m['type'] == 'bot'])
        next_question = flow_manager.get_next_question(
            current_phase,
            messages_in_phase,
            extracted_data,
            missing_data
        )
        
        print(f"\n[BOT]: {next_question}")
        
        # Check if response meets expectations
        for expected in step['expected_bot_response_contains']:
            if expected.lower() in next_question.lower():
                print(f"  [PASS] Contains '{expected}'")
            else:
                print(f"  [FAIL] Missing '{expected}'")
        
        # Check for LinkedIn URL
        linkedin_url = engine._extract_linkedin_from_social(nlp_results)
        if linkedin_url:
            print(f"\n[SYSTEM]: LinkedIn URL detected: {linkedin_url}")
            print("[SYSTEM]: Would trigger LinkedIn analysis here...")
            
            # Simulate LinkedIn analysis completion
            extracted_data['linkedin_analysis'] = {
                'analysis_complete': True,
                'professional_bio': 'Extracted from LinkedIn',
                'expertise_keywords': ['keyword1', 'keyword2'],
                'success_stories': [{'title': 'Story from LinkedIn'}],
                'podcast_topics': ['topic1', 'topic2']
            }
            metadata['linkedin_analyzed'] = True
        
        # Add messages for next iteration
        messages.append({
            "type": "user",
            "content": step['user_says'],
            "timestamp": datetime.utcnow().isoformat(),
            "phase": current_phase
        })
        messages.append({
            "type": "bot",
            "content": next_question,
            "timestamp": datetime.utcnow().isoformat(),
            "phase": current_phase
        })
    
    print(f"\n{'='*80}")
    print("SCENARIO TEST COMPLETE")
    print(f"{'='*80}")
    
    # Show final state
    print("\n[FINAL STATE]:")
    print(f"  Name extracted: {extracted_data.get('contact_info', {}).get('fullName', 'Not found')}")
    print(f"  Email extracted: {extracted_data.get('contact_info', {}).get('email', 'Not found')}")
    print(f"  LinkedIn analyzed: {metadata.get('linkedin_analyzed', False)}")
    print(f"  Has professional bio: {completeness.get('has_professional_bio', False)}")
    print(f"  Has expertise keywords: {completeness.get('has_expertise_keywords', False)}")

if __name__ == "__main__":
    print("Starting Real Scenario Test...")
    asyncio.run(test_real_scenario())