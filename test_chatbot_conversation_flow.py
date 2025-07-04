#!/usr/bin/env python3
"""
Test the complete chatbot conversation flow with LinkedIn integration
"""

import asyncio
import json
from uuid import uuid4
from datetime import datetime
from podcast_outreach.services.chatbot.conversation_engine import ConversationEngine
from podcast_outreach.services.chatbot.enhanced_nlp_processor import EnhancedNLPProcessor
from podcast_outreach.services.chatbot.improved_conversation_flows import ImprovedConversationFlowManager

class ChatbotFlowTester:
    def __init__(self):
        self.engine = ConversationEngine()
        self.flow_manager = ImprovedConversationFlowManager()
        
    def print_phase_info(self, phase, message_num):
        print(f"\n{'='*60}")
        print(f"PHASE: {phase.upper()} | Message #{message_num}")
        print(f"{'='*60}")
        
    def print_bot_message(self, message):
        print(f"\n🤖 BOT: {message}")
        
    def print_user_message(self, message):
        print(f"\n👤 USER: {message}")
        
    def print_analysis(self, data):
        print(f"\n📊 ANALYSIS:")
        print(f"   - Progress: {data.get('progress', 0)}%")
        print(f"   - Phase: {data.get('phase', 'unknown')}")
        if data.get('keywords_found'):
            print(f"   - Keywords found: {data['keywords_found']}")
        
    async def simulate_conversation_flow(self):
        """Simulate a complete conversation flow"""
        
        print("\n" + "="*80)
        print("CHATBOT CONVERSATION FLOW TEST - WITH LINKEDIN INTEGRATION")
        print("="*80)
        
        # Initialize conversation state
        conversation_id = str(uuid4())
        messages = []
        extracted_data = {}
        metadata = {}
        current_phase = "introduction"
        
        # Test scenarios
        scenarios = [
            {
                "name": "Scenario 1: User provides LinkedIn early",
                "messages": [
                    "John Doe, john@example.com",
                    "Yes, here's my LinkedIn: https://www.linkedin.com/in/johndoe",
                    "My website is www.johndoe.com and Twitter is @johndoe"
                ]
            },
            {
                "name": "Scenario 2: User provides LinkedIn later",
                "messages": [
                    "Jane Smith, jane@example.com",
                    "I don't have a LinkedIn profile",
                    "I'm a marketing consultant at Smith Marketing Co.",
                    "Actually, I do have LinkedIn: https://www.linkedin.com/in/janesmith"
                ]
            },
            {
                "name": "Scenario 3: No LinkedIn provided",
                "messages": [
                    "Bob Johnson, bob@example.com",
                    "No LinkedIn, but my website is bobjohnson.com",
                    "I'm a software engineer at Tech Corp"
                ]
            }
        ]
        
        for scenario in scenarios:
            print(f"\n\n{'*'*80}")
            print(f"TESTING: {scenario['name']}")
            print(f"{'*'*80}")
            
            # Reset for each scenario
            messages = []
            extracted_data = {}
            metadata = {}
            current_phase = "introduction"
            message_count = 0
            
            # Initial message
            initial_msg = self.flow_manager.phase_questions["introduction"]["opener"]
            self.print_phase_info(current_phase, message_count)
            self.print_bot_message(initial_msg.format(name="there"))
            
            # Process user messages
            for user_message in scenario['messages']:
                message_count += 1
                self.print_user_message(user_message)
                
                # Simulate NLP processing
                nlp_processor = EnhancedNLPProcessor()
                nlp_results = await nlp_processor.process(
                    user_message, 
                    messages[-5:], 
                    extracted_data,
                    []
                )
                
                # Check for LinkedIn URL
                linkedin_url = self._extract_linkedin_url(nlp_results)
                
                if linkedin_url and not metadata.get('linkedin_analyzed'):
                    print(f"\n🔍 LINKEDIN DETECTED: {linkedin_url}")
                    print("   ⏳ Analyzing LinkedIn profile...")
                    
                    # Simulate LinkedIn analysis
                    metadata['linkedin_analyzed'] = True
                    extracted_data['linkedin_analysis'] = {
                        'analysis_complete': True,
                        'professional_bio': 'LinkedIn bio extracted',
                        'expertise_keywords': ['keyword1', 'keyword2', 'keyword3'],
                        'success_stories': [{'title': 'Story 1'}],
                        'podcast_topics': ['topic1', 'topic2']
                    }
                    
                    print("   ✅ LinkedIn analysis complete!")
                    self.print_bot_message("Great! I've analyzed your LinkedIn profile and learned a lot about your expertise.")
                
                # Update extracted data
                extracted_data = self._merge_data(extracted_data, nlp_results)
                
                # Check completeness and progress
                completeness = await nlp_processor.check_data_completeness(extracted_data)
                progress = nlp_processor.calculate_progress(extracted_data)
                
                # Add LinkedIn bonus if available
                if extracted_data.get('linkedin_analysis'):
                    progress = min(progress + 15, 95)
                
                # Determine next phase
                messages_in_phase = self._count_phase_messages(messages, current_phase)
                should_transition, next_phase = self.flow_manager.should_transition(
                    current_phase, messages_in_phase, extracted_data, completeness
                )
                
                if should_transition:
                    current_phase = next_phase
                    self.print_phase_info(current_phase, message_count + 1)
                
                # Generate next question
                missing_data = self.flow_manager.get_missing_critical_data(completeness)
                
                # Filter out LinkedIn-provided data
                if extracted_data.get('linkedin_analysis'):
                    linkedin_provided = ['professional bio', 'expertise keywords', 'success story']
                    missing_data = [item for item in missing_data if item not in linkedin_provided]
                
                next_question = self.flow_manager.get_next_question(
                    current_phase, messages_in_phase, extracted_data, missing_data
                )
                
                self.print_bot_message(next_question)
                
                # Print analysis
                self.print_analysis({
                    'progress': progress,
                    'phase': current_phase,
                    'keywords_found': len(extracted_data.get('keywords', {}).get('explicit', []))
                })
                
                # Check if we can complete early
                if progress >= 85 and message_count >= 8 and extracted_data.get('linkedin_analysis'):
                    print(f"\n🎉 EARLY COMPLETION POSSIBLE - LinkedIn data accelerated the process!")
                    break
            
            print(f"\n{'='*60}")
            print(f"SCENARIO COMPLETE - Total messages: {message_count}")
            print(f"Final progress: {progress}%")
            print(f"{'='*60}")
    
    def _extract_linkedin_url(self, nlp_results):
        """Extract LinkedIn URL from NLP results"""
        social_media = nlp_results.get('contact_info', {}).get('socialMedia', [])
        for url in social_media:
            if 'linkedin.com/in/' in url.lower():
                return url
        return None
    
    def _merge_data(self, existing, new_results):
        """Simple data merge"""
        if 'keywords' in new_results:
            existing.setdefault('keywords', {})['explicit'] = new_results['keywords'].get('explicit', [])
        if 'contact_info' in new_results:
            existing.setdefault('contact_info', {}).update(new_results['contact_info'])
        return existing
    
    def _count_phase_messages(self, messages, phase):
        """Count messages in current phase"""
        return len([m for m in messages if m.get('phase') == phase])

async def main():
    tester = ChatbotFlowTester()
    await tester.simulate_conversation_flow()

if __name__ == "__main__":
    print("Starting Chatbot Flow Test...")
    asyncio.run(main())