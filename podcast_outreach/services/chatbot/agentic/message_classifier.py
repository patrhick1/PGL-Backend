# podcast_outreach/services/chatbot/agentic/message_classifier.py

from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import json
import re

from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.logging_config import get_logger
from .bucket_definitions import INFORMATION_BUCKETS, BucketDefinition
from .state_manager import StateManager

logger = get_logger(__name__)

@dataclass
class ClassificationResult:
    """Result of message classification"""
    bucket_updates: Dict[str, Tuple[Any, float]]  # bucket_id -> (value, confidence)
    user_intent: str  # 'provide_info', 'correction', 'completion', 'review', 'question'
    intent_confidence: float
    ambiguous: bool
    needs_clarification: Optional[str] = None
    detected_entities: Dict[str, Any] = None

class MessageClassifier:
    """AI-powered message classifier for bucket routing and intent detection"""
    
    def __init__(self, gemini_service: Optional[GeminiService] = None):
        self.gemini_service = gemini_service or GeminiService()
        self.model_name = "gemini-2.0-flash"
        
        # Entity extractors for objective patterns (emails, URLs, etc)
        # These are kept because they extract specific formatted data
        self.entity_extractors = {
            'email': re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b'),
            'phone': re.compile(r'(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})'),
            'linkedin': re.compile(r'linkedin\.com/in/[\w-]+'),
            'website': re.compile(r'https?://(?:www\.)?[\w.-]+\.[a-zA-Z]{2,}(?:/[\w.-]*)*'),
            'years': re.compile(r'\b(\d+)\s*(?:years?|yrs?)\b', re.I)
        }
    
    async def classify_message(
        self, 
        message: str, 
        state: StateManager,
        context_window: int = 5
    ) -> ClassificationResult:
        """
        Classify a user message to determine bucket updates and intent
        
        Args:
            message: The user's message
            state: Current conversation state
            context_window: Number of recent messages to include for context
            
        Returns:
            ClassificationResult with bucket updates and intent
        """
        # Extract entities (emails, phone numbers, etc) - these are objective
        entities = self._extract_entities(message)
        
        # Use AI for all intent classification and bucket mapping
        try:
            ai_result = await self._ai_classification(message, state, context_window, entities)
            return ai_result
            
        except Exception as e:
            logger.error(f"AI classification failed: {e}", exc_info=True)
            # Fallback: if we at least extracted entities, use them
            bucket_updates = {}
            if entities.get('email'):
                bucket_updates['email'] = (entities['email'], 0.95)
            if entities.get('phone'):
                bucket_updates['phone'] = (entities['phone'], 0.9)
            if entities.get('linkedin'):
                bucket_updates['linkedin_url'] = (entities['linkedin'], 0.95)
            
            return ClassificationResult(
                bucket_updates=bucket_updates,
                user_intent='provide_info',
                intent_confidence=0.5,
                ambiguous=True,
                needs_clarification="Could you please rephrase that?",
                detected_entities=entities
            )
    
    
    def _extract_entities(self, message: str) -> Dict[str, Any]:
        """Extract common entities from message"""
        entities = {}
        
        for entity_type, pattern in self.entity_extractors.items():
            match = pattern.search(message)
            if match:
                if entity_type == 'phone':
                    # Format phone number
                    entities['phone'] = f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
                elif entity_type == 'years':
                    entities['years'] = int(match.group(1))
                else:
                    entities[entity_type] = match.group(0)
        
        return entities
    
    
    async def _ai_classification(
        self, 
        message: str, 
        state: StateManager,
        context_window: int,
        extracted_entities: Optional[Dict[str, Any]] = None
    ) -> ClassificationResult:
        """Use AI to classify the message"""
        
        try:
            # Prepare context
            recent_messages = state.get_recent_messages(context_window)
            filled_buckets = state.get_filled_buckets()
            empty_required = state.get_empty_required_buckets()
        except Exception as e:
            logger.error(f"Error getting state data: {e}", exc_info=True)
            raise
        
        try:
            # Build bucket descriptions for AI
            bucket_info = self._prepare_bucket_info()
        except Exception as e:
            logger.error(f"Error preparing bucket info: {e}", exc_info=True)
            raise
        
        try:
            # Create classification prompt
            prompt = self._build_classification_prompt(
                message, 
                recent_messages, 
                filled_buckets,
                empty_required,
                bucket_info
            )
        except Exception as e:
            logger.error(f"Error building classification prompt: {e}", exc_info=True)
            raise
        
        try:
            # Call AI service
            response = await self.gemini_service.create_message(
                prompt=prompt,
                model=self.model_name,
                workflow="chatbot_classification"
            )
            
            # Log the raw response for debugging
            logger.debug(f"Raw AI response: {response}")
            
            # Parse AI response
            if not response or not response.strip():
                logger.error("Empty response from AI service")
                raise ValueError("Empty AI response")
            
            # Clean the response - sometimes AI returns markdown code blocks
            cleaned_response = response.strip()
            if cleaned_response.startswith("```json"):
                cleaned_response = cleaned_response[7:]  # Remove ```json
            if cleaned_response.startswith("```"):
                cleaned_response = cleaned_response[3:]  # Remove ```
            if cleaned_response.endswith("```"):
                cleaned_response = cleaned_response[:-3]  # Remove ```
            cleaned_response = cleaned_response.strip()
            
            result_data = json.loads(cleaned_response)
            
            # Add extracted entities to the result
            if extracted_entities:
                result_data['entities'] = extracted_entities
            
            # Convert to ClassificationResult
            return self._parse_ai_response(result_data)
            
        except Exception as e:
            logger.error(f"Error in AI classification: {e}")
            raise
    
    def _prepare_bucket_info(self) -> str:
        """Prepare bucket information for AI context"""
        bucket_lines = []
        
        try:
            for bucket_id, bucket_def in INFORMATION_BUCKETS.items():
                if hasattr(bucket_def, 'example_inputs') and bucket_def.example_inputs:
                    examples = " | ".join(bucket_def.example_inputs[:2])
                else:
                    examples = "No examples available"
                
                if hasattr(bucket_def, 'description'):
                    description = bucket_def.description
                else:
                    description = f"Information about {bucket_id}"
                
                bucket_lines.append(
                    f"- {bucket_id}: {description} (Examples: {examples})"
                )
        except Exception as e:
            logger.error(f"Error preparing bucket info: {e}")
            raise
        
        return "\n".join(bucket_lines)
    
    def _build_classification_prompt(
        self,
        message: str,
        recent_messages: List[Any],
        filled_buckets: Dict[str, Any],
        empty_required: List[str],
        bucket_info: str
    ) -> str:
        """Build the classification prompt for AI"""
        
        # Format conversation history
        history = []
        for msg in recent_messages[-5:]:  # Last 5 messages
            if isinstance(msg, dict):
                role = "User" if msg.get('role') == "user" else "Assistant"
                content = msg.get('content', '')
            else:
                role = "User" if msg.role == "user" else "Assistant"
                content = msg.content
            history.append(f"{role}: {content}")
        history_text = "\n".join(history)
        
        # Format filled buckets
        filled_text = "\n".join([
            f"- {bucket_id}: {value}"
            for bucket_id, value in filled_buckets.items()
        ])
        
        # Format empty required buckets
        empty_text = ", ".join(empty_required) if empty_required else "None"
        
        prompt = f"""You are a message classifier for a chatbot that collects information in buckets.

AVAILABLE BUCKETS:
{bucket_info}

CURRENT STATE:
Filled buckets:
{filled_text if filled_text else "None"}

Empty required buckets: {empty_text}

RECENT CONVERSATION:
{history_text}

NEW MESSAGE TO CLASSIFY:
User: {message}

TASK:
1. Identify which buckets this message provides information for
2. Extract the values with confidence scores (0.0-1.0)
3. Determine the user's intent
4. Check if the message is ambiguous or needs clarification

INTENTS:
- provide_info: User is providing new information
- acknowledgment: User is acknowledging without providing new info
- correction: User is correcting previously provided information  
- completion: User explicitly wants to complete/submit
- review: User wants to see collected data
- question: User is asking a question
- hint_linkedin: User is hinting about LinkedIn

Return JSON in this format:
{{
    "bucket_updates": {{
        "bucket_id": {{
            "value": "extracted value or array for multi-value buckets",
            "confidence": 0.95
        }}
    }},
    "user_intent": "provide_info",
    "intent_confidence": 0.9,
    "ambiguous": false,
    "needs_clarification": null,
    "reasoning": "Brief explanation"
}}

IMPORTANT:
- Only extract information explicitly stated in the message
- Use high confidence (>0.8) only when extraction is clear
- Let the AI understand context naturally without rigid rules

HANDLING NEGATIVE RESPONSES FOR OPTIONAL FIELDS:
- When a user indicates they DON'T have something for an OPTIONAL field, DO NOT extract any value
- Examples of negative responses: "I don't have a website", "no website", "don't have one", "none", "not applicable"
- For these cases, DO NOT include the bucket in bucket_updates at all
- Example: User says "I don't have a website" → DO NOT include 'website' in bucket_updates
- Example: User says "I don't have a phone number" → DO NOT include 'phone' in bucket_updates

- For buckets that allow multiple values (social_media, expertise_keywords, success_stories, achievements, podcast_topics, speaking_experience, promotion_items):
  * If the user provides multiple items separated by newlines, commas, or bullets, extract as an array
  * Example: "Twitter: @john\nLinkedIn: john-doe" → value: ["Twitter: @john", "LinkedIn: john-doe"]
  * Example: "AI, Machine Learning, Data Science" → value: ["AI", "Machine Learning", "Data Science"]
  * If user says they don't have any (e.g., "I don't have any", "none", "no experience"), extract as empty array: value: []
  * Example: "I don't have any speaking experience" → value: [] for speaking_experience bucket

SPECIAL HANDLING FOR SOCIAL MEDIA:
- Extract social media information exactly as the user provides it
- Include platform names, handles, URLs - whatever format they use
- Examples of valid social media extractions:
  * "Instagram: @myhandle" → value: ["Instagram: @myhandle"]
  * "https://twitter.com/john" → value: ["https://twitter.com/john"]
  * "I'm on LinkedIn at linkedin.com/in/jane" → value: ["LinkedIn at linkedin.com/in/jane"]
  * Multi-line: "Instagram: @user\nTwitter: @handle" → value: ["Instagram: @user", "Twitter: @handle"]
- The system will intelligently parse and normalize these later

SPECIAL HANDLING FOR YEARS_EXPERIENCE:
- Extract ONLY the numeric value from years of experience
- Examples:
  * "4 years" → value: "4"
  * "10 years of experience" → value: "10"
  * "I have 5 years" → value: "5"
  * "15+ years" → value: "15"
  * Just "7" → value: "7"
- The bucket expects a numeric string or integer"""

        return prompt
    
    def _parse_ai_response(self, response_data: Dict[str, Any]) -> ClassificationResult:
        """Parse AI response into ClassificationResult"""
        
        # Convert bucket updates to expected format
        bucket_updates = {}
        for bucket_id, update_info in response_data.get('bucket_updates', {}).items():
            if isinstance(update_info, dict):
                value = update_info.get('value')
                confidence = update_info.get('confidence', 0.5)
                bucket_updates[bucket_id] = (value, confidence)
        
        return ClassificationResult(
            bucket_updates=bucket_updates,
            user_intent=response_data.get('user_intent', 'provide_info'),
            intent_confidence=response_data.get('intent_confidence', 0.5),
            ambiguous=response_data.get('ambiguous', False),
            needs_clarification=response_data.get('needs_clarification'),
            detected_entities=response_data.get('entities', {})
        )
    
    
    
    def create_clarification_message(self, result: ClassificationResult) -> str:
        """Create a clarification message for ambiguous input"""
        
        if result.needs_clarification:
            return result.needs_clarification
        
        if result.ambiguous and result.bucket_updates:
            # Multiple possible interpretations
            bucket_names = [
                INFORMATION_BUCKETS[bid].name 
                for bid in result.bucket_updates.keys()
                if bid in INFORMATION_BUCKETS
            ]
            
            if len(bucket_names) == 1:
                return f"Just to confirm, is this your {bucket_names[0].lower()}?"
            else:
                names_text = ", ".join(bucket_names[:-1]) + f" and {bucket_names[-1]}"
                return f"I detected information about {names_text}. Could you clarify which you're providing?"
        
        return "I'm not sure I understood that correctly. Could you please rephrase?"