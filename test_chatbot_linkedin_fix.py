#!/usr/bin/env python3
"""
Test the LinkedIn question fix in chatbot conversation flow
This script simulates the exact scenario where the bot wasn't asking for LinkedIn
"""

import asyncio
import json
from datetime import datetime
from podcast_outreach.services.chatbot.enhanced_nlp_processor import EnhancedNLPProcessor
from podcast_outreach.services.chatbot.improved_conversation_flows import ImprovedConversationFlowManager

async def test_linkedin_question_flow():
    """Test that LinkedIn is asked when email is requested"""
    
    print("\n" + "="*80)
    print("TESTING LINKEDIN QUESTION FIX")
    print("="*80)
    
    # Initialize components
    flow_manager = ImprovedConversationFlowManager()
    nlp_processor = EnhancedNLPProcessor()
    
    # Simulate conversation state after "Yes I am"
    messages = [
        {
            "type": "bot",
            "content": "Hi there! I'm excited to help you create an amazing media kit...",
            "timestamp": datetime.utcnow().isoformat(),
            "phase": "introduction"
        },
        {
            "type": "user", 
            "content": "Yes I am",
            "timestamp": datetime.utcnow().isoformat(),
            "phase": "introduction"
        }
    ]
    
    # Initial extracted data (empty)
    extracted_data = {}
    
    # Process the "Yes I am" message
    nlp_results = await nlp_processor.process(
        "Yes I am",
        messages,
        extracted_data,
        []
    )
    
    # Check data completeness
    completeness = await nlp_processor.check_data_completeness(extracted_data)
    
    # Get missing data
    missing_data = flow_manager.get_missing_critical_data(completeness)
    
    print("\n[ANALYSIS] After 'Yes I am':")
    print(f"   Missing data: {missing_data}")
    print(f"   Has name: {completeness.get('has_name', False)}")
    print(f"   Has email: {completeness.get('has_email', False)}")
    
    # Get next question
    next_question = flow_manager.get_next_question(
        phase="introduction",
        message_count_in_phase=0,  # First bot message in phase
        extracted_data=extracted_data,
        missing_data=missing_data
    )
    
    print(f"\n[BOT RESPONSE]: {next_question}")
    
    # Check if LinkedIn is mentioned
    if "LinkedIn" in next_question:
        print("\n[SUCCESS]: LinkedIn question is included!")
    else:
        print("\n[ISSUE]: LinkedIn not mentioned in the response")
        
        # Try the targeted question approach
        print("\n[TESTING] targeted question for 'email':")
        targeted_q = flow_manager._create_targeted_question("email", extracted_data)
        print(f"   {targeted_q}")
        
        if "LinkedIn" in targeted_q:
            print("\n[SUCCESS]: LinkedIn is in the targeted email question!")
    
    # Simulate user providing name and email
    print("\n" + "-"*60)
    print("[SIMULATING] user response with name and email...")
    
    user_response = "John Doe, john@example.com"
    messages.append({
        "type": "bot",
        "content": next_question,
        "timestamp": datetime.utcnow().isoformat(),
        "phase": "introduction"
    })
    messages.append({
        "type": "user",
        "content": user_response,
        "timestamp": datetime.utcnow().isoformat(),
        "phase": "introduction"
    })
    
    # Process user response
    nlp_results = await nlp_processor.process(
        user_response,
        messages,
        extracted_data,
        []
    )
    
    # Update extracted data
    if 'contact_info' in nlp_results:
        extracted_data.setdefault('contact_info', {}).update(nlp_results['contact_info'])
    
    # Check completeness again
    completeness = await nlp_processor.check_data_completeness(extracted_data)
    missing_data = flow_manager.get_missing_critical_data(completeness)
    
    print(f"\n[ANALYSIS] After providing name and email:")
    print(f"   Extracted name: {extracted_data.get('contact_info', {}).get('fullName', 'Not found')}")
    print(f"   Extracted email: {extracted_data.get('contact_info', {}).get('email', 'Not found')}")
    print(f"   Has name: {completeness.get('has_name', False)}")
    print(f"   Has email: {completeness.get('has_email', False)}")
    print(f"   Missing data: {missing_data}")
    
    # Get next question (should be about LinkedIn/social media)
    next_question = flow_manager.get_next_question(
        phase="introduction",
        message_count_in_phase=1,  # Second bot message in phase
        extracted_data=extracted_data,
        missing_data=missing_data
    )
    
    print(f"\n[NEXT BOT RESPONSE]: {next_question}")
    
    # Check follow-up questions
    print("\n[INFO] Introduction phase follow-up questions:")
    for i, q in enumerate(flow_manager.phase_questions["introduction"]["follow_up"]):
        print(f"   {i}: {q}")
    
    print("\n" + "="*80)
    print("TEST COMPLETE")
    print("="*80)

if __name__ == "__main__":
    print("Starting LinkedIn Question Fix Test...")
    asyncio.run(test_linkedin_question_flow())