# podcast_outreach/services/campaigns/questionnaire_social_processor.py

import logging
import re
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime

from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.services.ai.openai_client import OpenAIService

logger = logging.getLogger(__name__)

@dataclass
class SocialMediaHandle:
    """Represents a social media handle/profile"""
    platform: str
    handle: str
    url: str
    raw_input: str  # Original input from user

@dataclass
class ClientSocialProfile:
    """Complete social media profile for a client"""
    handles: List[SocialMediaHandle]
    bio_summary: str
    expertise_topics: List[str]
    key_messages: List[str]
    content_themes: List[str]
    engagement_style: str
    follower_insights: Dict[str, Any]

class QuestionnaireSocialProcessor:
    """Processes social media data from questionnaire responses"""
    
    def __init__(self):
        self.gemini_service = GeminiService()
        self.openai_service = OpenAIService()
        
        # Social media URL patterns for validation and extraction
        self.social_patterns = {
            'linkedin': re.compile(
                r'(?:https?://)?(?:www\.)?linkedin\.com/in/([a-zA-Z0-9-]+)/?',
                re.IGNORECASE
            ),
            'twitter': re.compile(
                r'(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/([a-zA-Z0-9_]+)/?',
                re.IGNORECASE
            ),
            'instagram': re.compile(
                r'(?:https?://)?(?:www\.)?instagram\.com/([a-zA-Z0-9._]+)/?',
                re.IGNORECASE
            ),
            'youtube': re.compile(
                r'(?:https?://)?(?:www\.)?youtube\.com/(?:c/|channel/|user/)?([a-zA-Z0-9_-]+)/?',
                re.IGNORECASE
            ),
            'tiktok': re.compile(
                r'(?:https?://)?(?:www\.)?tiktok\.com/@([a-zA-Z0-9_.]+)/?',
                re.IGNORECASE
            ),
            'facebook': re.compile(
                r'(?:https?://)?(?:www\.)?facebook\.com/([a-zA-Z0-9.]+)/?',
                re.IGNORECASE
            )
        }
        
        logger.info("QuestionnaireSocialProcessor initialized")

    async def process_questionnaire_social_data(
        self, 
        questionnaire_data: Dict[str, Any],
        campaign_id: str
    ) -> ClientSocialProfile:
        """
        Main entry point to process social media data from questionnaire
        
        Args:
            questionnaire_data: Full questionnaire response data
            campaign_id: Campaign ID for tracking
            
        Returns:
            ClientSocialProfile: Processed social media profile
        """
        logger.info(f"Processing social media data for campaign {campaign_id}")
        
        try:
            # Extract social media handles from questionnaire
            social_handles = self._extract_social_handles(questionnaire_data)
            logger.info(f"Extracted {len(social_handles)} social media handles")
            
            # Get bio and expertise information
            bio_info = self._extract_bio_information(questionnaire_data)
            
            # Analyze social media content (if we can access it)
            content_analysis = await self._analyze_social_content(social_handles)
            
            # Generate insights and recommendations
            profile_insights = await self._generate_profile_insights(
                bio_info, content_analysis, social_handles
            )
            
            # Create comprehensive profile
            client_profile = ClientSocialProfile(
                handles=social_handles,
                bio_summary=profile_insights.get('bio_summary', ''),
                expertise_topics=profile_insights.get('expertise_topics', []),
                key_messages=profile_insights.get('key_messages', []),
                content_themes=profile_insights.get('content_themes', []),
                engagement_style=profile_insights.get('engagement_style', ''),
                follower_insights=profile_insights.get('follower_insights', {})
            )
            
            logger.info(f"Successfully processed social profile for campaign {campaign_id}")
            return client_profile
            
        except Exception as e:
            logger.error(f"Error processing social media data for campaign {campaign_id}: {e}")
            raise

    def _extract_social_handles(self, questionnaire_data: Dict[str, Any]) -> List[SocialMediaHandle]:
        """Extract and validate social media handles from questionnaire"""
        handles = []
        
        # Extract from contactInfo.socialMedia array
        contact_info = questionnaire_data.get('contactInfo', {})
        social_media = contact_info.get('socialMedia', [])
        
        for social_entry in social_media:
            platform = social_entry.get('platform', '').lower()
            handle_input = social_entry.get('handle', '')
            
            if not handle_input:
                continue
                
            # Validate and normalize the handle
            validated_handle = self._validate_and_normalize_handle(platform, handle_input)
            if validated_handle:
                handles.append(validated_handle)
        
        # Also check other potential locations in questionnaire
        # Look for social media mentions in other fields
        additional_handles = self._extract_handles_from_text_fields(questionnaire_data)
        handles.extend(additional_handles)
        
        # Remove duplicates
        unique_handles = []
        seen_urls = set()
        for handle in handles:
            if handle.url not in seen_urls:
                unique_handles.append(handle)
                seen_urls.add(handle.url)
        
        logger.info(f"Extracted {len(unique_handles)} unique social media handles")
        return unique_handles

    def _validate_and_normalize_handle(self, platform: str, handle_input: str) -> Optional[SocialMediaHandle]:
        """Validate and normalize a social media handle"""
        if not handle_input or not platform:
            return None
            
        # Clean up the input
        handle_input = handle_input.strip()
        
        # Check if we have a pattern for this platform
        if platform not in self.social_patterns:
            logger.warning(f"Unknown social media platform: {platform}")
            return None
            
        pattern = self.social_patterns[platform]
        
        # Try to match the pattern
        match = pattern.search(handle_input)
        if match:
            username = match.group(1)
            # Generate the full URL
            if platform == 'linkedin':
                full_url = f"https://linkedin.com/in/{username}"
            elif platform in ['twitter', 'x']:
                full_url = f"https://twitter.com/{username}"
            elif platform == 'instagram':
                full_url = f"https://instagram.com/{username}"
            elif platform == 'youtube':
                full_url = f"https://youtube.com/c/{username}"
            elif platform == 'tiktok':
                full_url = f"https://tiktok.com/@{username}"
            elif platform == 'facebook':
                full_url = f"https://facebook.com/{username}"
            else:
                full_url = handle_input
                
            return SocialMediaHandle(
                platform=platform,
                handle=username,
                url=full_url,
                raw_input=handle_input
            )
        else:
            logger.warning(f"Could not parse {platform} handle: {handle_input}")
            return None

    def _extract_handles_from_text_fields(self, questionnaire_data: Dict[str, Any]) -> List[SocialMediaHandle]:
        """Extract social media handles from text fields in questionnaire"""
        handles = []
        
        # Fields to search for social media mentions
        text_fields = [
            questionnaire_data.get('professionalBio', {}).get('aboutWork', ''),
            questionnaire_data.get('promotionPrefs', {}).get('itemsToPromote', ''),
            questionnaire_data.get('finalNotes', {}).get('anythingElse', ''),
            questionnaire_data.get('socialProof', {}).get('notableStats', ''),
        ]
        
        # Combine all text fields
        combined_text = ' '.join(text_fields)
        
        # Search for social media URLs in the text
        for platform, pattern in self.social_patterns.items():
            matches = pattern.finditer(combined_text)
            for match in matches:
                handle_input = match.group(0)
                validated_handle = self._validate_and_normalize_handle(platform, handle_input)
                if validated_handle:
                    handles.append(validated_handle)
        
        return handles

    def _extract_bio_information(self, questionnaire_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract biographical and professional information"""
        bio_info = {}
        
        # Professional bio
        professional_bio = questionnaire_data.get('professionalBio', {})
        bio_info['about_work'] = professional_bio.get('aboutWork', '')
        bio_info['achievements'] = professional_bio.get('achievements', '')
        bio_info['expertise_topics'] = professional_bio.get('expertiseTopics', '')
        
        # Contact info
        contact_info = questionnaire_data.get('contactInfo', {})
        bio_info['full_name'] = contact_info.get('fullName', '')
        bio_info['website'] = contact_info.get('website', '')
        
        # Promotion preferences
        promotion_prefs = questionnaire_data.get('promotionPrefs', {})
        bio_info['items_to_promote'] = promotion_prefs.get('itemsToPromote', '')
        bio_info['preferred_intro'] = promotion_prefs.get('preferredIntro', '')
        
        # Social proof
        social_proof = questionnaire_data.get('socialProof', {})
        bio_info['notable_stats'] = social_proof.get('notableStats', '')
        bio_info['testimonials'] = social_proof.get('testimonials', '')
        
        # At a glance stats
        stats = questionnaire_data.get('atAGlanceStats', {})
        bio_info['years_experience'] = stats.get('yearsOfExperience', '')
        bio_info['email_subscribers'] = stats.get('emailSubscribers', '')
        bio_info['keynote_engagements'] = stats.get('keynoteEngagements', '')
        
        return bio_info

    async def _analyze_social_content(self, social_handles: List[SocialMediaHandle]) -> Dict[str, Any]:
        """Analyze social media content (placeholder for now)"""
        # For now, we'll return basic info based on handles
        # In the future, this could integrate with social media APIs
        
        analysis = {
            'platforms': [handle.platform for handle in social_handles],
            'handle_count': len(social_handles),
            'primary_platforms': self._identify_primary_platforms(social_handles)
        }
        
        # Note: Actual content analysis would require API access to social platforms
        # This is a placeholder that could be enhanced with:
        # - LinkedIn API for professional content
        # - Twitter API for tweets and engagement
        # - Instagram API for visual content analysis
        
        return analysis

    def _identify_primary_platforms(self, social_handles: List[SocialMediaHandle]) -> List[str]:
        """Identify the primary social media platforms"""
        platforms = [handle.platform for handle in social_handles]
        
        # Prioritize professional platforms
        priority_order = ['linkedin', 'twitter', 'youtube', 'instagram', 'tiktok', 'facebook']
        
        primary_platforms = []
        for platform in priority_order:
            if platform in platforms:
                primary_platforms.append(platform)
        
        return primary_platforms[:3]  # Return top 3 platforms

    async def _generate_profile_insights(
        self, 
        bio_info: Dict[str, Any], 
        content_analysis: Dict[str, Any],
        social_handles: List[SocialMediaHandle]
    ) -> Dict[str, Any]:
        """Generate insights about the client's profile using AI"""
        
        # Prepare prompt for Gemini
        social_platforms = ", ".join([handle.platform for handle in social_handles])
        
        prompt = f"""
        Analyze the following client profile information and generate insights:
        
        PROFESSIONAL INFORMATION:
        Name: {bio_info.get('full_name', 'N/A')}
        About Work: {bio_info.get('about_work', 'N/A')}
        Achievements: {bio_info.get('achievements', 'N/A')}
        Expertise Topics: {bio_info.get('expertise_topics', 'N/A')}
        Items to Promote: {bio_info.get('items_to_promote', 'N/A')}
        Notable Stats: {bio_info.get('notable_stats', 'N/A')}
        Years of Experience: {bio_info.get('years_experience', 'N/A')}
        
        SOCIAL MEDIA PRESENCE:
        Platforms: {social_platforms}
        
        PREFERRED INTRODUCTION:
        {bio_info.get('preferred_intro', 'N/A')}
        
        Based on this information, provide:
        1. A concise bio summary (2-3 sentences)
        2. 5 key expertise topics
        3. 3 key messages they want to communicate
        4. 3 content themes they likely focus on
        5. Their engagement style (professional, casual, educational, etc.)
        
        Format as JSON with keys: bio_summary, expertise_topics, key_messages, content_themes, engagement_style
        """
        
        try:
            response = await self.gemini_service.generate_content_async(prompt)
            
            # Try to parse as JSON
            import json
            try:
                insights = json.loads(response)
            except json.JSONDecodeError:
                # Fallback parsing if JSON isn't perfect
                insights = self._parse_insights_fallback(response)
            
            # Add follower insights based on stats
            insights['follower_insights'] = self._extract_follower_insights(bio_info)
            
            return insights
            
        except Exception as e:
            logger.error(f"Error generating profile insights: {e}")
            return self._generate_fallback_insights(bio_info, social_handles)

    def _parse_insights_fallback(self, response: str) -> Dict[str, Any]:
        """Fallback parsing when JSON parsing fails"""
        insights = {
            'bio_summary': 'Experienced professional with diverse expertise.',
            'expertise_topics': [],
            'key_messages': [],
            'content_themes': [],
            'engagement_style': 'Professional'
        }
        
        # Try to extract sections from the response
        lines = response.split('\n')
        current_section = None
        
        for line in lines:
            line = line.strip()
            if 'bio_summary' in line.lower():
                current_section = 'bio_summary'
            elif 'expertise_topics' in line.lower():
                current_section = 'expertise_topics'
            elif 'key_messages' in line.lower():
                current_section = 'key_messages'
            elif 'content_themes' in line.lower():
                current_section = 'content_themes'
            elif 'engagement_style' in line.lower():
                current_section = 'engagement_style'
            elif line and current_section:
                # Clean up the line
                line = re.sub(r'^[-•*]\s*', '', line)  # Remove bullet points
                line = re.sub(r'^\d+\.\s*', '', line)  # Remove numbers
                
                if current_section in ['expertise_topics', 'key_messages', 'content_themes']:
                    if line:
                        insights[current_section].append(line)
                else:
                    insights[current_section] = line
        
        return insights

    def _extract_follower_insights(self, bio_info: Dict[str, Any]) -> Dict[str, Any]:
        """Extract insights about follower base from stats"""
        insights = {}
        
        email_subs = bio_info.get('email_subscribers', '')
        if email_subs:
            insights['email_list_size'] = email_subs
        
        keynotes = bio_info.get('keynote_engagements', '')
        if keynotes:
            insights['speaking_experience'] = keynotes
        
        years_exp = bio_info.get('years_experience', '')
        if years_exp:
            insights['experience_level'] = years_exp
        
        return insights

    def _generate_fallback_insights(
        self, 
        bio_info: Dict[str, Any], 
        social_handles: List[SocialMediaHandle]
    ) -> Dict[str, Any]:
        """Generate basic insights when AI analysis fails"""
        
        name = bio_info.get('full_name', 'Professional')
        expertise = bio_info.get('expertise_topics', 'Various topics')
        
        return {
            'bio_summary': f"{name} is an experienced professional specializing in {expertise}.",
            'expertise_topics': [topic.strip() for topic in expertise.split(',')][:5] if expertise else [],
            'key_messages': ['Professional expertise', 'Industry insights', 'Value-driven content'],
            'content_themes': ['Professional development', 'Industry trends', 'Best practices'],
            'engagement_style': 'Professional',
            'follower_insights': self._extract_follower_insights(bio_info)
        }

    async def update_campaign_with_social_data(
        self, 
        campaign_id: str, 
        client_profile: ClientSocialProfile
    ) -> bool:
        """Update campaign record with processed social media data"""
        try:
            # Prepare social media data for storage
            social_data = {
                'social_handles': [
                    {
                        'platform': handle.platform,
                        'handle': handle.handle,
                        'url': handle.url
                    } for handle in client_profile.handles
                ],
                'bio_summary': client_profile.bio_summary,
                'expertise_topics': client_profile.expertise_topics,
                'key_messages': client_profile.key_messages,
                'content_themes': client_profile.content_themes,
                'engagement_style': client_profile.engagement_style,
                'follower_insights': client_profile.follower_insights,
                'processed_at': datetime.utcnow().isoformat()
            }
            
            # This would update the campaign record
            # Implementation depends on your database structure
            logger.info(f"Social media data prepared for campaign {campaign_id}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error updating campaign {campaign_id} with social data: {e}")
            return False

    def extract_ideal_podcast_description(self, questionnaire_data: Dict[str, Any]) -> str:
        """Extract or generate ideal podcast description for vetting
        
        Priority order:
        1. finalNotes.idealPodcastDescription (dedicated field)
        2. finalNotes.anythingElse (if contains 'podcast')
        3. Generated from expertiseTopics and aboutWork
        4. Default fallback text
        """
        
        # Look for the dedicated ideal podcast description field first (new structure)
        final_notes = questionnaire_data.get('finalNotes', {})
        ideal_podcast_desc = final_notes.get('idealPodcastDescription', '').strip()
        
        # If dedicated field exists and has content, use it
        if ideal_podcast_desc:
            logger.debug("Using dedicated idealPodcastDescription field")
            return ideal_podcast_desc
        
        # Fallback to checking anythingElse for podcast mentions (legacy support)
        anything_else = final_notes.get('anythingElse', '')
        if 'podcast' in anything_else.lower():
            logger.debug("Using anythingElse field (contains 'podcast')")
            return anything_else
        
        # Generate based on their expertise and goals as final fallback
        expertise = questionnaire_data.get('professionalBio', {}).get('expertiseTopics', '')
        about_work = questionnaire_data.get('professionalBio', {}).get('aboutWork', '')
        
        if expertise or about_work:
            logger.debug("Generating description from expertise and work background")
            return f"Podcasts focused on {expertise} with audiences interested in {about_work}"
        
        logger.debug("Using default fallback description")
        return "Professional podcasts relevant to their expertise and target audience"