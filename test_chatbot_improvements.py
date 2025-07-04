#!/usr/bin/env python3
"""Test script to verify chatbot improvements"""

import asyncio
import json
import sys
import os
sys.path.insert(0, os.path.abspath('.'))

from podcast_outreach.services.chatbot.enhanced_nlp_processor import EnhancedNLPProcessor
from podcast_outreach.services.chatbot.improved_conversation_flows import ImprovedConversationFlowManager
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

async def test_improvements():
    """Test the chatbot improvements"""
    
    # Initialize components
    nlp_processor = EnhancedNLPProcessor()
    flow_manager = ImprovedConversationFlowManager()
    
    # Test case 1: Professional bio extraction
    logger.info("=== Test 1: Professional Bio Extraction ===")
    
    test_message = """I've been playing the great game of business for about a decade now.
Everything I launched hit scaling roadblocks—constant shifts in people and tools shattered our processes.
After years of struggle, I discovered that relentless change was piling up hidden operational debt, choking our growth and draining cash flow.
Determined, I dove deep into mastering the fusion of operations and technology to scale seamlessly.
Then ChatGPT launched, and everything clicked—AI combined with my operations expertise was the breakthrough I'd been dreaming of.
That's how 3rd Brain was born: integrating people, processes, and technology to build unstoppable operational leverage instead of drowning in debt.
We help businesses do more while spending less using Automation, AI, and Digital Operations. Our average customer makes about 5% more on every million of revenue by partnering with us."""
    
    conversation_history = [
        {"type": "bot", "content": "Can you tell me more about your professional background?"},
        {"type": "user", "content": test_message}
    ]
    
    # Test extraction
    result = await nlp_processor.process(
        message=test_message,
        conversation_history=conversation_history,
        extracted_data={},
        existing_keywords=[]
    )
    
    logger.info("Extracted professional bio: %s", result.get("professional_bio", {}).get("about_work"))
    logger.info("Extracted stories: %d", len(result.get("stories", [])))
    logger.info("Extracted achievements: %d", len(result.get("achievements", [])))
    logger.info("Extracted keywords: %s", result.get("keywords", {}).get("explicit", [])[:5])
    
    # Test case 2: Question generation
    logger.info("\n=== Test 2: Smart Question Generation ===")
    
    # Simulate extracted data
    extracted_data = {
        "contact_info": {
            "fullName": "Paschal Okonkwor",
            "email": "pokonkwo@g.emporia.edu",
            "company": "Third Brain Automation",
            "role": "founder and CEO"
        },
        "professional_bio": {
            "about_work": "integrating people, processes, and technology to build unstoppable operational leverage"
        },
        "stories": [],
        "achievements": []
    }
    
    # Check completeness
    completeness = await nlp_processor.check_data_completeness(extracted_data)
    logger.info("Data completeness: %s", {k: v for k, v in completeness.items() if isinstance(v, bool)})
    
    # Get missing data
    missing_data = flow_manager.get_missing_critical_data(completeness)
    logger.info("Missing data: %s", missing_data[:3])
    
    # Generate next question
    next_question = flow_manager.get_next_question(
        phase="core_discovery",
        message_count_in_phase=1,
        extracted_data=extracted_data,
        missing_data=missing_data
    )
    logger.info("Next question: %s", next_question)
    
    # Test case 3: Progress calculation
    logger.info("\n=== Test 3: Progress Calculation ===")
    
    progress = nlp_processor.calculate_progress(extracted_data)
    logger.info("Current progress: %d%%", progress)
    
    # Add more data and recalculate
    extracted_data["stories"] = [{"challenge": "scaling roadblocks", "result": "5% more revenue per million"}]
    extracted_data["expertise_keywords"] = ["automation", "AI", "digital operations", "operational leverage", "scaling"]
    
    new_progress = nlp_processor.calculate_progress(extracted_data)
    logger.info("Progress after adding data: %d%%", new_progress)
    
    # Test completion readiness
    readiness = nlp_processor.evaluate_completion_readiness(extracted_data, 10)
    logger.info("Completion readiness: %s", readiness["completion_quality"])
    logger.info("Can complete: %s", readiness["can_complete"])

if __name__ == "__main__":
    asyncio.run(test_improvements())