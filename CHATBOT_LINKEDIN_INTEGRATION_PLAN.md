# Chatbot LinkedIn Integration Plan

## Overview
This plan outlines how to integrate LinkedIn profile scraping and analysis into the existing chatbot conversation flow to reduce the number of questions asked and improve user experience. The integration leverages existing infrastructure without dramatically changing the current process.

## Current State Analysis

### Existing Infrastructure
1. **Social URL Collection**: The chatbot already collects social media URLs (including LinkedIn) in the introduction phase
2. **URL Detection**: The NLP processor already detects LinkedIn URLs (regex pattern in `enhanced_nlp_processor.py`)
3. **Data Storage**: Social URLs are stored in `extracted_data.contact_info.socialMedia` array
4. **Apify Integration**: `SocialDiscoveryService` already has LinkedIn scraping capability
5. **Gemini Integration**: `GeminiService` is available for AI analysis

### Current Conversation Flow
- **Introduction Phase** (2-4 messages): Collects name, email, work info, and social links
- **Core Discovery Phase** (6-10 messages): Gathers success stories, expertise, achievements
- **Media Focus Phase** (4-6 messages): Identifies podcast topics, audience, unique value
- **Confirmation Phase** (2-3 messages): Final details and wrap-up

## Integration Architecture

### 1. LinkedIn Detection and Processing Pipeline

```python
# In conversation_engine.py after line 109 (NLP processing)
if linkedin_url := self._extract_linkedin_url(nlp_results):
    # Trigger async LinkedIn analysis
    linkedin_data = await self._analyze_linkedin_profile(linkedin_url)
    
    # Merge LinkedIn data into extracted_data
    extracted_data = self._merge_linkedin_data(extracted_data, linkedin_data)
    
    # Mark LinkedIn analysis as complete
    metadata['linkedin_analyzed'] = True
    metadata['linkedin_url'] = linkedin_url
```

### 2. LinkedIn Analysis Service

Create a new service class in `services/chatbot/linkedin_analyzer.py`:

```python
class LinkedInAnalyzer:
    def __init__(self):
        self.social_scraper = SocialDiscoveryService()
        self.gemini_service = GeminiService()
        
    async def analyze_profile(self, linkedin_url: str) -> Dict:
        # 1. Scrape LinkedIn profile
        profile_data = await self._scrape_profile(linkedin_url)
        
        # 2. Analyze with Gemini
        analysis = await self._analyze_with_gemini(profile_data)
        
        # 3. Return structured data
        return self._structure_analysis(analysis)
```

### 3. Data Extraction from LinkedIn

LinkedIn provides the following data that can answer chatbot questions:
- **Professional Bio**: Headline, summary, current position
- **Expertise Keywords**: Skills, endorsements, industry
- **Achievements**: Experience descriptions, education
- **Success Stories**: Can be inferred from experience descriptions
- **Years of Experience**: Calculated from work history
- **Company and Role**: Current position information

#### Data Mapping: LinkedIn → Chatbot Fields

| LinkedIn Data | Maps To | Chatbot Question Skipped |
|--------------|---------|-------------------------|
| Headline + Summary | professional_bio | "Can you tell me briefly what you do professionally?" |
| Skills/Endorsements | expertise_keywords | "What would you say are your top 3-5 areas of expertise?" |
| Current Position | company, role | "What company you work with?" |
| Work History | years_experience | Inferred from experience |
| Summary Content | unique_perspective | "What makes your approach unique?" |
| Experience Descriptions | success_stories | "Can you share ONE specific success story?" |
| Profile Analysis | podcast_topics | "What 2-3 topics are you most passionate about?" |

#### Questions That Can Be Skipped

Based on LinkedIn data availability, these questions can be skipped:

1. **Introduction Phase** (Save 1-2 questions):
   - "Can you tell me briefly what you do professionally and what company you work with?"
   - Professional bio is auto-filled from LinkedIn

2. **Core Discovery Phase** (Save 3-4 questions):
   - "What would you say are your top 3-5 areas of expertise?"
   - "What makes your approach or perspective unique in your field?"
   - "How many years have you been in your field?"
   - Partial data for: "Can you share ONE specific success story?"

3. **Media Focus Phase** (Save 1-2 questions):
   - "What topics would you be excited to discuss on podcasts?"
   - AI can suggest topics based on profile analysis

### 4. Question Skipping Logic

Modify `_generate_next_question` in `conversation_engine.py` to check LinkedIn data:

```python
def _should_skip_question(self, data_point: str, extracted_data: Dict) -> bool:
    """Check if LinkedIn already provided this data"""
    linkedin_data = extracted_data.get('linkedin_analysis', {})
    
    skip_mapping = {
        'professional_bio': linkedin_data.get('has_professional_summary'),
        'expertise_keywords': len(linkedin_data.get('skills', [])) >= 5,
        'years_experience': linkedin_data.get('years_experience') is not None,
        'company': linkedin_data.get('current_company') is not None,
        'achievements': len(linkedin_data.get('experiences', [])) > 0
    }
    
    return skip_mapping.get(data_point, False)
```

### 5. Enhanced Introduction Phase

Update the introduction phase questions in `improved_conversation_flows.py`:

```python
"introduction": {
    "follow_up": [
        "Great! Do you have a LinkedIn profile? If yes, please share your LinkedIn URL - I can analyze it to learn more about your expertise and save us both time!",
        "What about other social media or your website? Please share any Twitter, website, or other professional links you'd like in your media kit.",
        # This question becomes conditional based on LinkedIn data
        "Can you tell me briefly what you do professionally and what company you work with?"
    ]
}
```

## Implementation Steps

### Step 1: Create LinkedIn Analyzer Service
```python
# podcast_outreach/services/chatbot/linkedin_analyzer.py
import json
import asyncio
from typing import Dict, Optional, List
from podcast_outreach.services.enrichment.social_scraper import SocialDiscoveryService
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

class LinkedInAnalyzer:
    def __init__(self):
        self.social_scraper = SocialDiscoveryService()
        self.gemini_service = GeminiService()
        
    async def analyze_profile(self, linkedin_url: str) -> Dict:
        """Analyze LinkedIn profile and extract relevant data for chatbot"""
        try:
            # Scrape LinkedIn profile
            scrape_results = await self.social_scraper.get_linkedin_data_for_urls([linkedin_url])
            profile_data = scrape_results.get(linkedin_url)
            
            if not profile_data:
                logger.warning(f"No LinkedIn data scraped for {linkedin_url}")
                return {}
            
            # Analyze with Gemini for deeper insights
            analysis_prompt = self._create_analysis_prompt(profile_data)
            gemini_response = await self.gemini_service.create_message(
                prompt=analysis_prompt,
                model="gemini-2.0-flash",
                workflow="chatbot_linkedin_analysis"
            )
            
            # Parse Gemini response
            try:
                gemini_analysis = json.loads(gemini_response)
            except json.JSONDecodeError:
                logger.error("Failed to parse Gemini response as JSON")
                gemini_analysis = {}
            
            # Structure the results
            return self._structure_results(profile_data, gemini_analysis)
            
        except Exception as e:
            logger.error(f"Error analyzing LinkedIn profile: {e}")
            return {}
    
    def _create_analysis_prompt(self, profile_data: Dict) -> str:
        """Create a detailed prompt for Gemini to analyze LinkedIn data"""
        return f"""
        Analyze this LinkedIn profile data to extract information for a podcast guest media kit.
        
        Profile Data:
        Headline: {profile_data.get('headline', 'Not provided')}
        Summary: {profile_data.get('summary', 'Not provided')}
        
        Extract and infer the following information. Return ONLY valid JSON:
        {{
            "professional_bio": "A 2-3 sentence bio suitable for podcast introductions",
            "expertise_keywords": ["keyword1", "keyword2", ...], // 5-10 technical skills or areas
            "years_experience": number or null,
            "success_stories": [
                {{
                    "title": "Brief title",
                    "description": "What happened",
                    "impact": "Results or metrics"
                }}
            ],
            "podcast_topics": ["topic1", "topic2", ...], // 3-5 topics they could discuss
            "unique_perspective": "What makes them unique",
            "target_audience": "Who would benefit from their insights",
            "speaking_style": "professional/casual/academic/storyteller",
            "key_achievements": ["achievement1", "achievement2", ...]
        }}
        
        Focus on:
        1. Extracting concrete examples and metrics
        2. Identifying unique expertise areas
        3. Suggesting podcast-friendly topics
        4. Finding compelling stories or case studies
        """
    
    def _structure_results(self, scraped_data: Dict, gemini_analysis: Dict) -> Dict:
        """Structure the combined results for the chatbot"""
        return {
            # Direct data from LinkedIn
            "headline": scraped_data.get("headline"),
            "summary": scraped_data.get("summary"),
            "followers_count": scraped_data.get("followers_count"),
            
            # AI-enhanced data
            "professional_bio": gemini_analysis.get("professional_bio"),
            "expertise_keywords": gemini_analysis.get("expertise_keywords", []),
            "years_experience": gemini_analysis.get("years_experience"),
            "success_stories": gemini_analysis.get("success_stories", []),
            "podcast_topics": gemini_analysis.get("podcast_topics", []),
            "unique_perspective": gemini_analysis.get("unique_perspective"),
            "target_audience": gemini_analysis.get("target_audience"),
            "key_achievements": gemini_analysis.get("key_achievements", []),
            
            # Metadata
            "analysis_complete": True,
            "has_professional_summary": bool(scraped_data.get("summary") or gemini_analysis.get("professional_bio")),
            "has_expertise": len(gemini_analysis.get("expertise_keywords", [])) > 0,
            "has_stories": len(gemini_analysis.get("success_stories", [])) > 0
        }
```

### Step 2: Update Conversation Engine

Add LinkedIn processing to `conversation_engine.py`:

```python
# Add these imports
from podcast_outreach.services.chatbot.linkedin_analyzer import LinkedInAnalyzer

# Add these methods to ConversationEngine class:

def _extract_linkedin_from_social(self, nlp_results: Dict) -> Optional[str]:
    """Extract LinkedIn URL from NLP results"""
    social_media = nlp_results.get('contact_info', {}).get('socialMedia', [])
    for url in social_media:
        if 'linkedin.com/in/' in url.lower():
            return url
    return None

def _merge_linkedin_insights(self, extracted_data: Dict, linkedin_data: Dict) -> Dict:
    """Merge LinkedIn analysis results into extracted data"""
    if not linkedin_data:
        return extracted_data
    
    # Store the full analysis
    extracted_data['linkedin_analysis'] = linkedin_data
    
    # Update specific fields with LinkedIn data
    if linkedin_data.get('professional_bio') and not extracted_data.get('professional_bio', {}).get('about_work'):
        extracted_data.setdefault('professional_bio', {})['about_work'] = linkedin_data['professional_bio']
    
    if linkedin_data.get('expertise_keywords'):
        existing_keywords = extracted_data.get('keywords', {}).get('explicit', [])
        new_keywords = list(set(existing_keywords + linkedin_data['expertise_keywords']))[:20]
        extracted_data.setdefault('keywords', {})['explicit'] = new_keywords
    
    if linkedin_data.get('success_stories'):
        extracted_data.setdefault('stories', []).extend([
            {
                'subject': story.get('title', ''),
                'challenge': story.get('description', ''),
                'result': story.get('impact', ''),
                'confidence': 0.9  # High confidence from LinkedIn
            }
            for story in linkedin_data['success_stories']
        ])
    
    if linkedin_data.get('podcast_topics'):
        extracted_data.setdefault('topics', {})['suggested'] = linkedin_data['podcast_topics']
    
    if linkedin_data.get('target_audience'):
        extracted_data['target_audience'] = linkedin_data['target_audience']
    
    if linkedin_data.get('unique_perspective'):
        extracted_data['unique_value'] = linkedin_data['unique_perspective']
    
    return extracted_data

# Update the process_message method:
async def process_message(self, conversation_id: str, message: str) -> Dict:
    # ... existing code up to line 109 ...
    
    # Process with NLP
    nlp_results = await self.nlp_processor.process(
        message, 
        messages, 
        extracted_data,
        conv.get('campaign_keywords') or []
    )
    
    # Update extracted data
    extracted_data = self._merge_extracted_data(extracted_data, nlp_results)
    
    # Check for LinkedIn URL and analyze if not done yet
    linkedin_url = self._extract_linkedin_from_social(nlp_results)
    
    if linkedin_url and not metadata.get('linkedin_analyzed'):
        # Add a processing message
        processing_message = {
            "type": "bot",
            "content": "I see you've shared your LinkedIn profile! Let me analyze it quickly to learn more about your expertise... This will just take a moment.",
            "timestamp": datetime.utcnow().isoformat(),
            "phase": conv['conversation_phase'],
            "is_processing": True
        }
        messages.append(processing_message)
        
        # Update conversation to show processing
        await conv_queries.update_conversation(
            UUID(conversation_id),
            messages,
            extracted_data,
            metadata,
            conv['conversation_phase'],
            self.nlp_processor.calculate_progress(extracted_data)
        )
        
        try:
            # Analyze LinkedIn profile
            linkedin_analyzer = LinkedInAnalyzer()
            linkedin_data = await linkedin_analyzer.analyze_profile(linkedin_url)
            
            if linkedin_data and linkedin_data.get('analysis_complete'):
                # Remove processing message
                messages = [msg for msg in messages if not msg.get('is_processing')]
                
                # Merge LinkedIn data
                extracted_data = self._merge_linkedin_insights(extracted_data, linkedin_data)
                metadata['linkedin_analyzed'] = True
                metadata['linkedin_analysis_timestamp'] = datetime.utcnow().isoformat()
                
                # Add success message
                success_message = {
                    "type": "bot",
                    "content": "Great! I've analyzed your LinkedIn profile and learned a lot about your expertise. This will help me ask more relevant questions and save us both time. Let me continue with a few specific questions based on what I found...",
                    "timestamp": datetime.utcnow().isoformat(),
                    "phase": conv['conversation_phase']
                }
                messages.append(success_message)
                
        except Exception as e:
            logger.error(f"LinkedIn analysis failed: {e}")
            # Remove processing message and continue normally
            messages = [msg for msg in messages if not msg.get('is_processing')]
            
            # Add a friendly error message
            error_message = {
                "type": "bot",
                "content": "I had trouble accessing your LinkedIn profile, but no worries! Let me continue with a few questions to learn about your expertise.",
                "timestamp": datetime.utcnow().isoformat(),
                "phase": conv['conversation_phase']
            }
            messages.append(error_message)
    
    # Save insights to separate table for analysis
    await self._save_insights(conversation_id, nlp_results)
    
    # Generate next question based on phase and gaps
    next_message, new_phase, progress = await self._generate_next_question(
        conv['conversation_phase'],
        messages,
        extracted_data,
        metadata,
        conv['full_name']
    )
    
    # ... rest of the method ...
```

### Step 3: Implement Smart Question Generation

Update `_generate_next_question` in `conversation_engine.py`:

```python
async def _generate_next_question(self, current_phase: str, messages: List[Dict], 
                                extracted_data: Dict, metadata: Dict, 
                                user_name: str) -> Tuple[str, str, int]:
    """Generate the next question based on conversation state and missing data"""
    
    # Check if LinkedIn data is available
    has_linkedin = bool(extracted_data.get('linkedin_analysis', {}).get('analysis_complete'))
    
    # Check data completeness with LinkedIn bonus
    completeness = await self.nlp_processor.check_data_completeness(extracted_data)
    
    # If we have LinkedIn data, mark certain fields as complete
    if has_linkedin:
        linkedin_data = extracted_data.get('linkedin_analysis', {})
        if linkedin_data.get('professional_bio'):
            completeness['has_professional_bio'] = True
        if linkedin_data.get('expertise_keywords'):
            completeness['has_expertise_keywords'] = True
        if linkedin_data.get('success_stories'):
            completeness['has_success_story'] = True
        if linkedin_data.get('podcast_topics'):
            completeness['has_podcast_topics'] = True
    
    # Check if we should transition phases
    messages_in_phase = self._count_messages_in_phase(messages, current_phase)
    should_transition, next_phase = self.flow_manager.should_transition(
        current_phase, messages_in_phase, extracted_data, completeness
    )
    
    if should_transition:
        current_phase = next_phase
        messages_in_phase = 0
    
    # Calculate progress with LinkedIn bonus
    progress = self.nlp_processor.calculate_progress(extracted_data)
    if has_linkedin:
        progress = min(progress + 15, 95)  # Add 15% bonus for LinkedIn
    
    # Check if we can complete early
    completion_readiness = self.nlp_processor.evaluate_completion_readiness(
        extracted_data, len(messages)
    )
    
    # Lower the message threshold if we have LinkedIn data
    if has_linkedin and len(messages) >= 8:  # Instead of 10
        completion_readiness["can_complete"] = True
    
    if completion_readiness["can_complete"] and current_phase != "confirmation":
        current_phase = "confirmation"
        messages_in_phase = 0
    
    # Get missing data for smart question generation
    missing_data = self.flow_manager.get_missing_critical_data(completeness)
    
    # Filter out data already provided by LinkedIn
    if has_linkedin:
        linkedin_provided = self._get_linkedin_provided_fields(extracted_data)
        missing_data = [item for item in missing_data if item not in linkedin_provided]
    
    # Generate smart question based on phase and missing data
    next_question = self._get_smart_question(
        current_phase, messages_in_phase, extracted_data, missing_data, has_linkedin
    )
    
    return next_question, current_phase, progress

def _get_linkedin_provided_fields(self, extracted_data: Dict) -> List[str]:
    """Get list of fields already provided by LinkedIn"""
    linkedin_data = extracted_data.get('linkedin_analysis', {})
    provided_fields = []
    
    if linkedin_data.get('professional_bio'):
        provided_fields.extend(['professional bio', 'current work'])
    if linkedin_data.get('expertise_keywords'):
        provided_fields.append('expertise keywords')
    if linkedin_data.get('success_stories'):
        provided_fields.append('success story')
    if linkedin_data.get('podcast_topics'):
        provided_fields.append('podcast topics')
    if linkedin_data.get('unique_perspective'):
        provided_fields.append('unique value')
    if linkedin_data.get('target_audience'):
        provided_fields.append('target audience')
    
    return provided_fields

def _get_smart_question(self, phase: str, messages_in_phase: int, 
                       extracted_data: Dict, missing_data: List[str], 
                       has_linkedin: bool) -> str:
    """Generate intelligent questions based on LinkedIn data and gaps"""
    
    # If we have LinkedIn, ask more specific follow-up questions
    if has_linkedin and phase == "core_discovery":
        linkedin_data = extracted_data.get('linkedin_analysis', {})
        
        # Ask for specific metrics or outcomes
        if linkedin_data.get('success_stories') and not any(
            story.get('metrics') for story in extracted_data.get('stories', [])
        ):
            return "I see from your LinkedIn profile that you've had some impressive experiences. Can you share specific metrics or numbers from one of your biggest wins?"
        
        # Ask for deeper insights
        if linkedin_data.get('expertise_keywords') and messages_in_phase < 3:
            keywords = linkedin_data['expertise_keywords'][:3]
            return f"Based on your expertise in {', '.join(keywords)}, what's one counterintuitive insight you've gained that most people miss?"
    
    # Otherwise use the standard flow
    return self.flow_manager.get_next_question(
        phase, messages_in_phase, extracted_data, missing_data
    )
```

### Step 4: Update Progress Calculation

Enhance progress calculation to give bonus for LinkedIn data:

```python
def calculate_progress(self, extracted_data: Dict) -> int:
    base_progress = super().calculate_progress(extracted_data)
    
    # Add LinkedIn bonus
    if extracted_data.get('linkedin_analysis'):
        linkedin_bonus = 15  # Skip approximately 3-4 questions worth of progress
        return min(base_progress + linkedin_bonus, 95)
    
    return base_progress
```

## Data Flow

1. **User provides LinkedIn URL** → Introduction phase
2. **URL Detection** → NLP processor identifies LinkedIn URL
3. **Async Scraping** → SocialDiscoveryService fetches profile data
4. **AI Analysis** → Gemini analyzes profile for insights
5. **Data Merge** → LinkedIn insights merged with conversation data
6. **Smart Questions** → Skip questions already answered by LinkedIn
7. **Reduced Messages** → Complete in 10-15 messages instead of 15-20

## Benefits

1. **Reduced Questions**: Skip 5-8 questions if LinkedIn provides sufficient data
2. **Better Data Quality**: LinkedIn provides verified professional information
3. **Improved UX**: Users don't repeat information already on LinkedIn
4. **Faster Completion**: 30-40% reduction in conversation length
5. **Richer Insights**: AI analysis provides deeper understanding

## UI/UX Considerations

### Processing States
1. **LinkedIn Detection**: Show acknowledgment when URL is detected
2. **Processing Indicator**: Display "Analyzing LinkedIn profile..." message
3. **Success Feedback**: Confirm what was learned from LinkedIn
4. **Error Handling**: Friendly message if scraping fails

### User Experience Flow
```
User: "My LinkedIn is linkedin.com/in/johndoe"
Bot: "I see you've shared your LinkedIn profile! Let me analyze it quickly to learn more about your expertise... This will just take a moment."
[Processing...]
Bot: "Great! I've analyzed your LinkedIn profile and learned a lot about your expertise. This will help me ask more relevant questions and save us both time. Let me continue with a few specific questions based on what I found..."
```

### Visual Indicators (for UI implementation)
- **Loading State**: Show typing indicator or spinner during LinkedIn analysis
- **Progress Jump**: Visual indication when progress increases due to LinkedIn
- **Data Source**: Indicate which data came from LinkedIn vs conversation

## Fallback Handling

1. **No LinkedIn**: Continue normal flow
2. **Scraping Failure**: Log error, continue with questions
3. **Partial Data**: Use what's available, ask for missing info
4. **Invalid URL**: Request correct URL or continue without
5. **Private Profiles**: Handle gracefully with appropriate message

## Database Considerations

No schema changes needed because:
- LinkedIn URL is already stored in `extracted_data.contact_info.socialMedia`
- LinkedIn analysis results stored in `extracted_data.linkedin_analysis`
- All data fits within existing JSONB structure

## Error Handling

```python
try:
    linkedin_data = await analyze_linkedin(url)
except ApifyError:
    logger.error("LinkedIn scraping failed")
    # Continue without LinkedIn data
except GeminiError:
    logger.error("AI analysis failed")
    # Use raw scraped data only
except Exception as e:
    logger.error(f"Unexpected error: {e}")
    # Continue normal flow
```

## Performance Considerations

### Async Processing
- LinkedIn analysis runs asynchronously to avoid blocking the conversation
- Timeout set to 30 seconds for Apify scraping
- Gemini analysis timeout set to 15 seconds
- Total maximum delay: ~45 seconds (usually completes in 10-20 seconds)

### Optimization Strategies
1. **Caching**: Consider caching LinkedIn analysis for 24 hours
2. **Partial Processing**: Start conversation while LinkedIn processes
3. **Batch Analysis**: If multiple social profiles provided, process in parallel
4. **Rate Limiting**: Respect Apify rate limits (typically 100 requests/minute)

## Testing Strategy

1. **Unit Tests**: Test LinkedIn analyzer independently
   - Valid LinkedIn URLs
   - Invalid URLs
   - Empty profile data
   - Gemini parsing errors

2. **Integration Tests**: Test full conversation flow with/without LinkedIn
   - LinkedIn provided early → reduced questions
   - LinkedIn provided late → normal flow
   - No LinkedIn → standard conversation

3. **Edge Cases**: 
   - Invalid URLs (typos, wrong format)
   - Private profiles (no data returned)
   - Scraping failures (network, rate limits)
   - Partial data (incomplete profiles)

4. **Performance Tests**: 
   - Ensure async processing doesn't block
   - Measure time to complete analysis
   - Test with various profile sizes

## Success Metrics

- **Conversation Length**: Target 30-40% reduction for LinkedIn users
- **Data Completeness**: Same or better than manual entry
- **User Satisfaction**: Positive feedback on reduced repetition
- **Error Rate**: < 5% failure rate for LinkedIn processing
- **Processing Time**: 95% complete within 20 seconds
- **Question Reduction**: Average 5-8 fewer questions asked

## Implementation Timeline

### Phase 1: Core Implementation (Week 1)
1. Create LinkedInAnalyzer service
2. Update conversation engine
3. Basic error handling

### Phase 2: Integration & Testing (Week 2)
1. Update question flow logic
2. Add UI/UX enhancements
3. Comprehensive testing

### Phase 3: Optimization & Monitoring (Week 3)
1. Performance optimization
2. Add monitoring/analytics
3. Deploy and monitor

## Conclusion

This plan integrates LinkedIn profile analysis into the chatbot without disrupting the existing flow. By leveraging Apify for scraping and Gemini for intelligent analysis, we can significantly reduce the number of questions needed while maintaining or improving data quality. The asynchronous processing ensures a smooth user experience, and the robust error handling means the system gracefully falls back to the standard flow if needed.

The implementation is designed to be minimally invasive to the existing codebase while providing maximum benefit to users with LinkedIn profiles. No database migrations are required, and all data fits within the existing schema structure.