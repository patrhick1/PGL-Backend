# podcast_outreach/services/matches/enhanced_vetting_agent.py
import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import episodes as episode_queries

logger = logging.getLogger(__name__)

# --- Pydantic Models for Structured LLM Output ---

class VettingCriterion(BaseModel):
    criterion: str = Field(description="A specific criterion for evaluating the podcast's fit.")
    reasoning: str = Field(description="Why this criterion is important based on the client's goals.")
    weight: int = Field(description="The importance of this criterion on a scale of 1 to 5.", ge=1, le=5)

class VettingChecklist(BaseModel):
    checklist: List[VettingCriterion] = Field(description="A list of vetting criteria.")

class CriterionScore(BaseModel):
    criterion: str = Field(description="The specific criterion being scored.")
    score: int = Field(description="The score from 0 to 100 for this criterion.", ge=0, le=100)
    justification: str = Field(description="The justification for the score, citing specific evidence from the podcast data.")

class VettingAnalysis(BaseModel):
    scores: List[CriterionScore] = Field(description="A list of scores for each criterion.")
    final_summary: str = Field(description="A final summary of the podcast's fit, explaining the overall score.")
    topic_match_analysis: str = Field(description="Specific analysis of how well the podcast topics match the client's expertise areas.")

# --- Enhanced Vetting Agent Service ---

class EnhancedVettingAgent:
    """An intelligent agent to vet podcast opportunities using comprehensive questionnaire data."""

    def __init__(self):
        self.gemini_service = GeminiService()
        logger.info("EnhancedVettingAgent initialized.")

    def _extract_comprehensive_client_profile(self, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract all relevant information from questionnaire responses for vetting."""
        questionnaire = campaign_data.get('questionnaire_responses', {})
        if questionnaire is None:
            questionnaire = {}
        
        # Extract all relevant fields
        profile = {
            'ideal_podcast_description': campaign_data.get('ideal_podcast_description', ''),
            'expertise_topics': [],
            'suggested_topics': [],
            'key_messages': [],
            'audience_requirements': {},
            'media_preferences': {},
            'promotion_items': [],
            'social_proof': {},
            'content_themes': []
        }
        
        # Extract expertise topics from multiple sources
        professional_bio = questionnaire.get('professionalBio', {})
        if isinstance(professional_bio, dict):
            expertise = professional_bio.get('expertiseTopics', '')
            if expertise:
                if isinstance(expertise, list):
                    profile['expertise_topics'].extend(expertise)
                elif isinstance(expertise, str):
                    profile['expertise_topics'].extend([t.strip() for t in expertise.split(',') if t.strip()])
        
        # Extract suggested topics
        suggested_topics = questionnaire.get('suggestedTopics', {})
        if isinstance(suggested_topics, dict):
            topics = suggested_topics.get('topics', '')
            if topics:
                if isinstance(topics, list):
                    profile['suggested_topics'].extend(topics)
                elif isinstance(topics, str):
                    # Parse numbered list or comma-separated topics
                    import re
                    topic_list = re.split(r'\d+\.\s*|\n|,', topics)
                    profile['suggested_topics'].extend([t.strip() for t in topic_list if t.strip()])
            
            key_stories = suggested_topics.get('keyStoriesOrMessages', '')
            if key_stories:
                profile['key_messages'].append(key_stories)
        
        # Extract social enrichment data if available
        social_enrichment = questionnaire.get('social_enrichment', {})
        if social_enrichment:
            if 'expertise_topics' in social_enrichment:
                profile['expertise_topics'].extend(social_enrichment['expertise_topics'])
            if 'key_messages' in social_enrichment:
                profile['key_messages'].extend(social_enrichment['key_messages'])
            if 'content_themes' in social_enrichment:
                profile['content_themes'].extend(social_enrichment['content_themes'])
        
        # Extract audience requirements
        at_a_glance = questionnaire.get('atAGlanceStats', {})
        if isinstance(at_a_glance, dict):
            profile['audience_requirements'] = {
                'email_subscribers': at_a_glance.get('emailSubscribers', ''),
                'years_experience': at_a_glance.get('yearsOfExperience', ''),
                'keynote_engagements': at_a_glance.get('keynoteEngagements', '')
            }
        
        # Extract media preferences
        media_exp = questionnaire.get('mediaExperience', {})
        if isinstance(media_exp, dict):
            previous_shows = media_exp.get('previousAppearances', [])
            if previous_shows:
                profile['media_preferences']['previous_show_types'] = [
                    show.get('showName', '') for show in previous_shows if isinstance(show, dict)
                ]
        
        # Extract promotion items
        promo_prefs = questionnaire.get('promotionPrefs', {})
        if isinstance(promo_prefs, dict):
            items = promo_prefs.get('itemsToPromote', '')
            if items:
                profile['promotion_items'].append(items)
        
        # Extract social proof
        social_proof = questionnaire.get('socialProof', {})
        if isinstance(social_proof, dict):
            profile['social_proof'] = {
                'testimonials': social_proof.get('testimonials', ''),
                'notable_stats': social_proof.get('notableStats', '')
            }
        
        # Remove duplicates and empty values
        profile['expertise_topics'] = list(set(filter(None, profile['expertise_topics'])))
        profile['suggested_topics'] = list(set(filter(None, profile['suggested_topics'])))
        profile['key_messages'] = list(filter(None, profile['key_messages']))
        profile['content_themes'] = list(set(filter(None, profile['content_themes'])))
        
        return profile

    async def _generate_enhanced_vetting_checklist(self, client_profile: Dict[str, Any]) -> Optional[VettingChecklist]:
        """Generate a comprehensive vetting checklist using all questionnaire data."""
        # Create the prompt with properly escaped audience requirements
        # to avoid template variable issues
        audience_req_str = str(client_profile['audience_requirements']).replace('"', "'")
        
        prompt_template = """
        Based on the following comprehensive client profile, create a prioritized checklist of 7-10 specific, measurable criteria to evaluate potential podcasts. Consider all aspects of the client's expertise, preferences, and requirements.

        Client Profile:
        {user_query}

        Create criteria that:
        1. Assess topic alignment with the client's expertise areas
        2. Evaluate audience fit based on the client's requirements
        3. Consider the podcast's content style and themes
        4. Check for promotional opportunities alignment
        5. Assess the podcast's professionalism and production quality

        For each criterion, provide:
        - A clear, specific criterion
        - Why it matters for this specific client
        - A weight from 1 (least important) to 5 (most important)

        Generate a JSON object that adheres to the VettingChecklist schema.
        """
        
        # Build the client profile details
        profile_details = f"""- Ideal Podcast Description: {client_profile['ideal_podcast_description']}
        - Expertise Topics: {', '.join(client_profile['expertise_topics'][:10])}
        - Suggested Discussion Topics: {', '.join(client_profile['suggested_topics'][:10])}
        - Key Messages: {'; '.join(client_profile['key_messages'][:3])}
        - Content Themes: {', '.join(client_profile['content_themes'][:5])}
        - Audience Requirements: {audience_req_str}
        - Previous Show Types: {', '.join(client_profile['media_preferences'].get('previous_show_types', [])[:5])}
        - Items to Promote: {'; '.join(client_profile['promotion_items'][:2])}"""
        
        try:
            checklist_obj = await self.gemini_service.get_structured_data(
                prompt_template_str=prompt_template,
                user_query=profile_details,
                output_model=VettingChecklist,
                workflow="enhanced_vetting_checklist_generation"
            )
            return checklist_obj
        except Exception as e:
            logger.error(f"Failed to generate enhanced vetting checklist: {e}", exc_info=True)
            return None

    async def _gather_enhanced_podcast_evidence(self, media_id: int) -> str:
        """Gather comprehensive podcast data including episode themes and guest patterns."""
        media_record = await media_queries.get_media_by_id_from_db(media_id)
        if not media_record:
            return "No media data available."

        episodes = await episode_queries.get_episodes_for_media_with_content(media_id)
        
        # Basic podcast info
        evidence_parts = [
            "=== PODCAST OVERVIEW ===",
            f"Podcast Name: {media_record.get('name')}",
            f"Description: {media_record.get('description')}",
            f"AI-Generated Description: {media_record.get('ai_description')}",
            f"Category: {media_record.get('category')}",
            f"Host(s): {', '.join(media_record.get('host_names') or [])}",
            f"Audience Size Estimate: {media_record.get('audience_size')}",
            f"ListenNotes Score: {media_record.get('listen_score')}",
            f"Social Followers: Twitter={media_record.get('twitter_followers')}, LinkedIn={media_record.get('linkedin_followers')}",
            f"Quality Score: {media_record.get('quality_score')}",
            f"Publishing Frequency: {media_record.get('publishing_frequency')}",
            f"Average Episode Length: {media_record.get('average_episode_length')} minutes"
        ]

        # Episode analysis with more detail
        if episodes:
            evidence_parts.append("\n=== RECENT EPISODES ANALYSIS ===")
            
            # Collect all themes and keywords for pattern analysis
            all_themes = []
            all_keywords = []
            guest_types = []
            
            for i, ep in enumerate(episodes[:5]):  # Analyze top 5 episodes
                evidence_parts.append(f"\nEpisode {i+1}:")
                evidence_parts.append(f"- Title: {ep.get('title')}")
                evidence_parts.append(f"- Published: {ep.get('published_at')}")
                evidence_parts.append(f"- Summary: {ep.get('ai_episode_summary') or ep.get('episode_summary')}")
                
                themes = ep.get('episode_themes', [])
                keywords = ep.get('episode_keywords', [])
                
                if themes:
                    evidence_parts.append(f"- Themes: {', '.join(themes)}")
                    all_themes.extend(themes)
                if keywords:
                    evidence_parts.append(f"- Keywords: {', '.join(keywords)}")
                    all_keywords.extend(keywords)
                
                # Extract guest type from title/summary if available
                guest_info = ep.get('guest_info')
                if guest_info:
                    evidence_parts.append(f"- Guest Type: {guest_info}")
                    guest_types.append(guest_info)
            
            # Add aggregated patterns
            if all_themes:
                theme_counts = {}
                for theme in all_themes:
                    theme_counts[theme] = theme_counts.get(theme, 0) + 1
                top_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                evidence_parts.append(f"\nTop Recurring Themes: {', '.join([t[0] for t in top_themes])}")
            
            if all_keywords:
                keyword_counts = {}
                for keyword in all_keywords:
                    keyword_counts[keyword] = keyword_counts.get(keyword, 0) + 1
                top_keywords = sorted(keyword_counts.items(), key=lambda x: x[1], reverse=True)[:10]
                evidence_parts.append(f"Top Keywords: {', '.join([k[0] for k in top_keywords])}")
            
            if guest_types:
                evidence_parts.append(f"Typical Guest Types: {', '.join(set(guest_types))}")

        # Add enrichment data if available
        if media_record.get('enrichment_data'):
            evidence_parts.append("\n=== ENRICHMENT DATA ===")
            enrichment = media_record['enrichment_data']
            if isinstance(enrichment, dict):
                for key, value in enrichment.items():
                    if value and key not in ['raw_data', 'last_updated']:
                        evidence_parts.append(f"- {key.replace('_', ' ').title()}: {value}")

        return "\n".join(filter(None, evidence_parts))

    async def _score_with_topic_matching(
        self, 
        checklist: VettingChecklist, 
        evidence: str, 
        client_profile: Dict[str, Any]
    ) -> Optional[VettingAnalysis]:
        """Enhanced scoring that specifically analyzes topic matching."""
        # Format checklist without curly braces that could be interpreted as template variables
        checklist_str = json.dumps(checklist.model_dump(), indent=2).replace('{', '{{').replace('}', '}}')
        
        prompt_template = """
        You are an expert podcast vetting analyst. Evaluate the following podcast based on the provided checklist and evidence, with special attention to topic matching.

        {user_query}

        For each criterion:
        1. Provide a score from 0 (no fit) to 100 (perfect fit) using this scale:
           - 0-20: No alignment or very poor fit
           - 21-40: Minimal alignment, significant gaps
           - 41-60: Moderate alignment, some relevant overlap  
           - 61-80: Strong alignment, good fit with minor gaps
           - 81-100: Excellent alignment, near-perfect or perfect fit
        2. Justify your score with specific evidence from the podcast data
        3. When evaluating topic match, look for:
           - Direct keyword matches with client's expertise
           - Conceptual alignment even if exact words differ
           - Recent episode themes that align with client's areas
           - Guest types that match the client's profile
        4. Be generous with scoring - if there's reasonable alignment, score in the 70-80 range

        Additionally, provide:
        - A detailed topic match analysis explaining how well the podcast's content aligns with the client's expertise
        - A final summary assessing overall fit

        Generate a JSON object that adheres to the VettingAnalysis schema.
        """
        
        # Build the analysis context
        context = f"""**Client's Expertise Areas:**
        - Primary Expertise: {', '.join(client_profile['expertise_topics'][:10])}
        - Suggested Topics: {', '.join(client_profile['suggested_topics'][:10])}
        - Content Themes: {', '.join(client_profile['content_themes'][:5])}

        **Vetting Checklist:**
        {checklist_str}

        **Podcast Evidence:**
        ---
        {evidence}
        ---"""
        
        try:
            analysis_obj = await self.gemini_service.get_structured_data(
                prompt_template_str=prompt_template,
                user_query=context,
                output_model=VettingAnalysis,
                workflow="enhanced_vetting_scoring"
            )
            return analysis_obj
        except Exception as e:
            logger.error(f"Failed to score podcast with topic matching: {e}", exc_info=True)
            return None

    def _calculate_final_weighted_score(self, analysis: VettingAnalysis, checklist: VettingChecklist) -> int:
        """Calculate the final weighted score out of 100."""
        total_score = 0
        total_weight = 0
        
        checklist_map = {item.criterion: item.weight for item in checklist.checklist}

        for score_item in analysis.scores:
            weight = checklist_map.get(score_item.criterion, 1)
            total_score += score_item.score * weight
            total_weight += weight
        
        if total_weight == 0:
            return 0

        normalized_score = total_score / total_weight
        return round(normalized_score)

    async def vet_match_enhanced(self, campaign_data: Dict[str, Any], media_id: int) -> Optional[Dict[str, Any]]:
        """Enhanced vetting that uses comprehensive questionnaire data."""
        try:
            # 1. Extract comprehensive client profile
            client_profile = self._extract_comprehensive_client_profile(campaign_data)
            
            if not client_profile['ideal_podcast_description'] and not client_profile['expertise_topics']:
                logger.warning(f"Campaign {campaign_data['campaign_id']} lacks sufficient data for vetting")
                return None

            # 2. Generate enhanced checklist
            checklist = await self._generate_enhanced_vetting_checklist(client_profile)
            if not checklist:
                return None

            # 3. Gather comprehensive evidence
            evidence = await self._gather_enhanced_podcast_evidence(media_id)

            # 4. Score with topic matching analysis
            analysis = await self._score_with_topic_matching(checklist, evidence, client_profile)
            if not analysis:
                return None

            # 5. Calculate final score
            final_score = self._calculate_final_weighted_score(analysis, checklist)

            # 6. Compile comprehensive results
            vetting_results = {
                "vetting_score": final_score,
                "vetting_reasoning": analysis.final_summary,
                "topic_match_analysis": analysis.topic_match_analysis,
                "vetting_checklist": checklist.model_dump(),
                "vetting_criteria_scores": [
                    {
                        "criterion": score.criterion,
                        "score": score.score,
                        "justification": score.justification
                    } for score in analysis.scores
                ],
                "client_expertise_matched": client_profile['expertise_topics'][:10]  # Top 10 for storage
                # Note: last_vetted_at is handled by the database with vetted_at = NOW()
            }
            
            return vetting_results
            
        except Exception as e:
            logger.error(f"Error in enhanced vetting for media {media_id}: {e}", exc_info=True)
            return None
    
    async def vet_match(self, campaign_data: Dict[str, Any], media_id: int) -> Optional[Dict[str, Any]]:
        """Compatibility method that calls vet_match_enhanced."""
        # Ensure we have minimum required data
        if not campaign_data:
            logger.error("No campaign data provided for vetting")
            return None
            
        # If no ideal_podcast_description and no questionnaire, we can't vet
        if not campaign_data.get('ideal_podcast_description') and not campaign_data.get('questionnaire_responses'):
            logger.warning(f"Campaign {campaign_data.get('campaign_id')} lacks both ideal_podcast_description and questionnaire_responses")
            return None
            
        return await self.vet_match_enhanced(campaign_data, media_id)
    
    async def vet_media_for_campaign(self, media_id: int, campaign_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compatibility method with reversed parameters."""
        result = await self.vet_match_enhanced(campaign_data, media_id)
        if result:
            return {
                'status': 'success',
                'vetting_score': result.get('vetting_score', 0),
                'vetting_reasoning': result.get('vetting_reasoning', ''),
                'vetting_checklist': result.get('vetting_checklist', {}),
                'topic_match_analysis': result.get('topic_match_analysis', ''),
                'client_expertise_matched': result.get('client_expertise_matched', [])
            }
        else:
            return {
                'status': 'failed',
                'vetting_score': 0,
                'error': 'Vetting failed to produce results'
            }