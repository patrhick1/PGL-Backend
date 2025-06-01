# podcast_outreach/services/media_kits/generator.py
import logging
import uuid
import re
import json
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

from podcast_outreach.database.queries import media_kits as media_kit_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import people as people_queries
from podcast_outreach.integrations.google_docs import GoogleDocsService
from podcast_outreach.logging_config import get_logger

# LLM and AI Template imports
from podcast_outreach.services.ai.gemini_client import GeminiService # Assuming Gemini for this task
from podcast_outreach.services.ai import templates as ai_templates_loader
from podcast_outreach.api.schemas.media_kit_schemas import ParsedBioSections, ParsedTalkingPoints, TalkingPoint

from podcast_outreach.services.enrichment.social_scraper import SocialDiscoveryService # Import SocialDiscoveryService

logger = get_logger(__name__)

def generate_slug(text: str) -> str:
    """Generates a URL-friendly slug from text."""
    text = text.lower()
    text = re.sub(r'\s+', '-', text)  # Replace spaces with hyphens
    text = re.sub(r'[^a-z0-9\-]', '', text)  # Remove non-alphanumeric characters except hyphens
    text = re.sub(r'-{2,}', '-', text)  # Replace multiple hyphens with a single one
    return text.strip('-')

class MediaKitService:
    def __init__(self):
        self.google_docs_service = GoogleDocsService()
        self.llm_service = GeminiService() # Initialize LLM service
        self.social_discovery_service = SocialDiscoveryService() # Initialize SocialDiscoveryService

    async def _get_content_from_gdoc(self, gdoc_url: Optional[str]) -> str:
        if not gdoc_url:
            return ""
        try:
            doc_id = self.google_docs_service.extract_document_id(gdoc_url)
            if doc_id:
                return await self.google_docs_service.get_document_content_async(doc_id)
            return ""
        except Exception as e:
            logger.error(f"Failed to fetch GDoc content from {gdoc_url}: {e}")
            return "Error fetching content."

    async def _parse_bio_from_gdoc_content(self, content: str, campaign_id: uuid.UUID) -> Dict[str, Optional[str]]:
        if not content or content == "Error fetching content." or not content.strip():
            return {"full_bio_content": None, "summary_bio_content": None, "short_bio_content": None}
        
        instructional_prompt_str = await ai_templates_loader.load_prompt_template("media_kit/parse_bio_prompt")
        if not instructional_prompt_str:
            logger.error("Parse bio prompt template not found. Using basic parsing.")
            full_bio = content
            summary_bio = content[:500] + "..." if len(content) > 500 else content
            short_bio = content[:150] + "..." if len(content) > 150 else content
            return {"full_bio_content": full_bio, "summary_bio_content": summary_bio, "short_bio_content": short_bio}

        try:
            parsed_data: Optional[ParsedBioSections] = await self.llm_service.get_structured_data(
                prompt_template_str=instructional_prompt_str, 
                user_query=content, 
                output_model=ParsedBioSections,
                workflow="media_kit_parse_bio",
                related_campaign_id=campaign_id
            )
            if parsed_data and (parsed_data.full_bio or parsed_data.summary_bio or parsed_data.short_bio):
                return {
                    "full_bio_content": parsed_data.full_bio,
                    "summary_bio_content": parsed_data.summary_bio,
                    "short_bio_content": parsed_data.short_bio
                }
            else: # LLM returned no usable bio sections
                logger.warning(f"LLM parsing for bio for campaign {campaign_id} returned empty sections. Falling back to basic parsing of GDoc content.")
                full_bio = content
                summary_bio = content[:500] + "..." if len(content) > 500 else content
                short_bio = content[:150] + "..." if len(content) > 150 else content
                return {"full_bio_content": full_bio, "summary_bio_content": summary_bio, "short_bio_content": short_bio}
        except Exception as e:
            logger.error(f"LLM failed to parse bio from GDoc content for campaign {campaign_id}: {e}. Using basic parsing.", exc_info=True)
        
        full_bio = content
        summary_bio = content[:500] + "..." if len(content) > 500 else content
        short_bio = content[:150] + "..." if len(content) > 150 else content
        return {"full_bio_content": full_bio, "summary_bio_content": summary_bio, "short_bio_content": short_bio}

    async def _parse_talking_points_from_gdoc_content(self, content: str, campaign_id: uuid.UUID) -> List[Dict[str, str]]:
        if not content or content == "Error fetching content." or not content.strip():
            return []

        instructional_prompt_str = await ai_templates_loader.load_prompt_template("media_kit/parse_talking_points_prompt")
        if not instructional_prompt_str:
            logger.error("Parse talking points prompt template not found. Using basic parsing.")
            points = []
            lines = [line.strip() for line in content.split('\n') if line.strip()]
            for line in lines[:5]: # Limit to 5 points for basic parsing
                points.append({"topic": line, "outcome": "N/A", "description": "Further details available."})
            return points

        try:
            parsed_data: Optional[ParsedTalkingPoints] = await self.llm_service.get_structured_data(
                prompt_template_str=instructional_prompt_str, 
                user_query=content, 
                output_model=ParsedTalkingPoints,
                workflow="media_kit_parse_talking_points",
                related_campaign_id=campaign_id
            )
            if parsed_data and parsed_data.talking_points:
                return [tp.model_dump() for tp in parsed_data.talking_points]
            else: # LLM returned no usable talking points
                logger.warning(f"LLM parsing for talking points for campaign {campaign_id} returned empty. Falling back to basic parsing of GDoc content.")
                points = []
                lines = [line.strip() for line in content.split('\n') if line.strip()]
                for line in lines[:5]:
                    points.append({"topic": line, "outcome": "N/A", "description": "Further details available."})
                return points
        except Exception as e:
            logger.error(f"LLM failed to parse talking points from GDoc content for campaign {campaign_id}: {e}. Using basic parsing.", exc_info=True)

        points = []
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        for line in lines[:5]:
            points.append({"topic": line, "outcome": "N/A", "description": "Further details available."})
        return points

    def _generate_summary_from_text(self, text: Optional[str], max_length: int = 500) -> Optional[str]:
        if not text or not text.strip(): return None
        # Simple truncation, could be more sophisticated (e.g., sentence-aware)
        return text[:max_length] + "..." if len(text) > max_length else text

    def _generate_short_bio_from_text(self, text: Optional[str], max_length: int = 150) -> Optional[str]:
        if not text or not text.strip(): return None
        return text[:max_length] + "..." if len(text) > max_length else text

    async def create_or_update_media_kit(
        self,
        campaign_id: uuid.UUID,
        editable_content: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        logger.info(f"Creating/updating media kit for campaign_id: {campaign_id}")
        editable_content = editable_content or {}

        campaign = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign:
            logger.error(f"Campaign {campaign_id} not found for media kit generation.")
            return None
        
        person_id = campaign.get("person_id")
        if not person_id:
            logger.error(f"Person ID not found for campaign {campaign_id}.")
            return None
        
        person = await people_queries.get_person_by_id_from_db(person_id)
        if not person:
            logger.error(f"Person {person_id} not found for media kit generation.")
            return None

        kit_data = {
            "campaign_id": campaign_id,
            "person_id": person_id,
            "title": editable_content.get("title") or f"Media Kit for {person.get('full_name', 'Client')} - {campaign.get('campaign_name', 'Campaign')}",
            "headline": editable_content.get("headline"),
            "introduction": editable_content.get("introduction"),
            "key_achievements": editable_content.get("key_achievements", []),
            "previous_appearances": editable_content.get("previous_appearances", []),
            "social_media_stats": editable_content.get("social_media_stats", {}),
            "headshot_image_urls": editable_content.get("headshot_image_urls", []),
            "logo_image_url": editable_content.get("logo_image_url"),
            "call_to_action_text": editable_content.get("call_to_action_text"),
            "contact_information_for_booking": editable_content.get("contact_information_for_booking"),
            "custom_sections": editable_content.get("custom_sections", []),
            "is_public": editable_content.get("is_public", False),
            "theme_preference": editable_content.get("theme_preference", "modern"),
            "bio_source": "unavailable", # Default
            "angles_source": "unavailable" # Default
        }

        # --- Determine Bio Content ---
        bio_gdoc_url = campaign.get("campaign_bio")
        parsed_bios_from_gdoc = None
        if bio_gdoc_url:
            bio_content_str = await self._get_content_from_gdoc(bio_gdoc_url)
            if bio_content_str and bio_content_str != "Error fetching content." and bio_content_str.strip():
                parsed_bios_from_gdoc = await self._parse_bio_from_gdoc_content(bio_content_str, campaign_id)
        
        if parsed_bios_from_gdoc and (parsed_bios_from_gdoc.get("full_bio_content") or parsed_bios_from_gdoc.get("summary_bio_content")):
            kit_data.update(parsed_bios_from_gdoc)
            kit_data["bio_source"] = "gdoc"
        else:
            questionnaire_bio = campaign.get("questionnaire_responses", {}).get("personalInfo", {}).get("bio")
            if questionnaire_bio and questionnaire_bio.strip():
                kit_data["full_bio_content"] = questionnaire_bio
                kit_data["summary_bio_content"] = self._generate_summary_from_text(questionnaire_bio)
                kit_data["short_bio_content"] = self._generate_short_bio_from_text(questionnaire_bio)
                kit_data["bio_source"] = "questionnaire"
            else:
                kit_data["full_bio_content"] = kit_data.get("full_bio_content") # Keep if already set by Gdoc (e.g. error message)
                kit_data["summary_bio_content"] = None
                kit_data["short_bio_content"] = None
                # bio_source remains "unavailable" or what Gdoc parsing returned (e.g. error message)
                if not kit_data.get("full_bio_content"): # if GDoc also failed or was empty
                     kit_data["full_bio_content"] = "Bio information not yet available."

        # --- Determine Talking Points ---
        angles_gdoc_url = campaign.get("campaign_angles")
        parsed_talking_points_from_gdoc = None
        if angles_gdoc_url:
            angles_content_str = await self._get_content_from_gdoc(angles_gdoc_url)
            if angles_content_str and angles_content_str != "Error fetching content." and angles_content_str.strip():
                parsed_talking_points_from_gdoc = await self._parse_talking_points_from_gdoc_content(angles_content_str, campaign_id)

        if parsed_talking_points_from_gdoc:
            kit_data["talking_points"] = parsed_talking_points_from_gdoc
            kit_data["angles_source"] = "gdoc"
        else:
            q_responses = campaign.get("questionnaire_responses", {})
            q_preferred_topics = q_responses.get("preferences", {}).get("preferredTopics", [])
            q_key_messages = q_responses.get("goals", {}).get("keyMessages", "")
            if q_preferred_topics:
                talking_points_from_q = []
                for topic in q_preferred_topics:
                    if isinstance(topic, str) and topic.strip():
                        talking_points_from_q.append({
                            "topic": topic,
                            "description": q_key_messages or "Key insights and actionable advice related to this topic.",
                            "outcome": "Valuable takeaways for your audience."
                        })
                if talking_points_from_q:
                    kit_data["talking_points"] = talking_points_from_q
                    kit_data["angles_source"] = "questionnaire"
                else:
                    kit_data["talking_points"] = [] # Ensure it's an empty list if no valid topics
            else:
                kit_data["talking_points"] = []
        
        # Fallback if still no talking points
        if not kit_data.get("talking_points"):
            kit_data["talking_points"] = []

        # Slug generation and handling
        base_slug_text = kit_data["title"]
        generated_slug = generate_slug(base_slug_text)
        
        existing_kit = await media_kit_queries.get_media_kit_by_campaign_id_from_db(campaign_id)
        final_slug = generated_slug
        counter = 1
        
        slug_to_check = editable_content.get("slug") 
        if not slug_to_check and not existing_kit: 
            slug_to_check = generated_slug
        elif existing_kit and not slug_to_check: 
            slug_to_check = existing_kit.get("slug", generated_slug)
        elif not slug_to_check:
             slug_to_check = generate_slug(kit_data["title"]) if kit_data["title"] else "untitled-media-kit"

        final_slug = slug_to_check

        is_new_slug = not existing_kit or (existing_kit and existing_kit.get("slug") != final_slug)
        if is_new_slug:
            temp_slug = final_slug
            current_excluded_id = existing_kit.get("media_kit_id") if existing_kit else None
            while await media_kit_queries.check_slug_exists(temp_slug, exclude_media_kit_id=current_excluded_id):
                final_slug = f"{slug_to_check}-{counter}"
                temp_slug = final_slug
                counter += 1
        
        kit_data["slug"] = final_slug

        db_operation_successful = False
        result_kit_dict = None
        media_kit_id_for_social_update = None # Initialize

        if existing_kit:
            logger.info(f"Updating existing media kit (ID: {existing_kit['media_kit_id']}) for campaign {campaign_id}")
            result_kit_dict = await media_kit_queries.update_media_kit_in_db(existing_kit['media_kit_id'], kit_data)
            if result_kit_dict:
                db_operation_successful = True
                media_kit_id_for_social_update = existing_kit['media_kit_id'] 
        else:
            logger.info(f"Creating new media kit for campaign {campaign_id}")
            result_kit_dict = await media_kit_queries.create_media_kit_in_db(kit_data)
            if result_kit_dict:
                db_operation_successful = True
                media_kit_id_for_social_update = result_kit_dict['media_kit_id'] 

        if db_operation_successful and result_kit_dict and media_kit_id_for_social_update:
            # Check campaign type before updating social stats
            if campaign.get("campaign_type") != "lead_magnet_prospect":
                logger.info(f"Media kit DB operation successful for campaign {campaign_id}. Triggering social stats update for media_kit_id: {media_kit_id_for_social_update}.")
                try:
                    updated_kit_with_stats = await self.update_social_stats_for_media_kit(media_kit_id_for_social_update)
                    return updated_kit_with_stats if updated_kit_with_stats else result_kit_dict
                except Exception as e_social:
                    logger.error(f"Error triggering social stats update for media_kit_id {media_kit_id_for_social_update}: {e_social}. Proceeding with original result.")
                    return result_kit_dict
            else:
                logger.info(f"Skipping social stats update for lead_magnet_prospect campaign {campaign_id}, media_kit_id: {media_kit_id_for_social_update}.")
                return result_kit_dict # Return the kit without social stats update
        elif result_kit_dict:
             logger.warning(f"DB operation for media kit campaign {campaign_id} was successful, but could not proceed to social stats update (or it was skipped). ")
             return result_kit_dict
        else:
            logger.error(f"Media kit DB operation FAILED for campaign {campaign_id}.")
            return None

    async def get_media_kit_by_campaign_id(self, campaign_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        return await media_kit_queries.get_media_kit_by_campaign_id_from_db(campaign_id)

    async def get_media_kit_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        return await media_kit_queries.get_media_kit_by_slug_enriched(slug)

    async def update_social_stats_for_media_kit(self, media_kit_id: uuid.UUID) -> Optional[Dict[str, Any]]:
        logger.info(f"Attempting to update social stats for media_kit_id: {media_kit_id}")
        kit = await media_kit_queries.get_media_kit_by_id_from_db(media_kit_id)
        if not kit:
            logger.warning(f"Media kit {media_kit_id} not found for social stats update.")
            return None
        
        person_id = kit.get("person_id")
        if not person_id:
            logger.warning(f"Person_id not found in media kit {media_kit_id}. Cannot fetch social stats.")
            return kit 

        person = await people_queries.get_person_by_id_from_db(person_id)
        if not person:
            logger.warning(f"Person {person_id} not found. Cannot fetch social stats for media kit {media_kit_id}.")
            return kit

        social_urls_to_fetch = {
            "twitter": person.get("twitter_profile_url"),
            "linkedin": person.get("linkedin_profile_url"),
            "instagram": person.get("instagram_profile_url"),
            "tiktok": person.get("tiktok_profile_url"),
        }

        fetched_stats_payload = {}
        current_time_utc = datetime.now(timezone.utc).isoformat()

        if social_urls_to_fetch["twitter"]:
            twitter_data_map = await self.social_discovery_service.get_twitter_data_for_urls([social_urls_to_fetch["twitter"]])
            twitter_data = twitter_data_map.get(social_urls_to_fetch["twitter"])
            if twitter_data:
                fetched_stats_payload["twitter"] = {
                    "url": twitter_data.get("profile_url"),
                    "username": twitter_data.get("username"),
                    "name": twitter_data.get("name"),
                    "followers_count": twitter_data.get("followers_count"),
                    "following_count": twitter_data.get("following_count"),
                    "is_verified": twitter_data.get("is_verified"),
                    "tweets_count": twitter_data.get("tweets_count"),
                    "profile_picture_url": twitter_data.get("profile_picture_url"),
                    "description": twitter_data.get("description"),
                    "last_fetched_at": current_time_utc
                }
        
        if social_urls_to_fetch["linkedin"]:
            linkedin_data_map = await self.social_discovery_service.get_linkedin_data_for_urls([social_urls_to_fetch["linkedin"]])
            linkedin_data = linkedin_data_map.get(social_urls_to_fetch["linkedin"])
            if linkedin_data:
                fetched_stats_payload["linkedin"] = {
                    "url": linkedin_data.get("profile_url"),
                    "headline": linkedin_data.get("headline"),
                    "summary": linkedin_data.get("summary"),
                    "connections_count": linkedin_data.get("connections_count"),
                    "profile_picture_url": linkedin_data.get("profile_picture_url"),
                    "last_fetched_at": current_time_utc
                }

        if social_urls_to_fetch["instagram"]:
            insta_data_map = await self.social_discovery_service.get_instagram_data_for_urls([social_urls_to_fetch["instagram"]])
            insta_data = insta_data_map.get(social_urls_to_fetch["instagram"])
            if insta_data:
                fetched_stats_payload["instagram"] = {
                    "url": insta_data.get("profile_url"),
                    "username": insta_data.get("username"),
                    "name": insta_data.get("name"),
                    "followers_count": insta_data.get("followers_count"),
                    "following_count": insta_data.get("following_count"),
                    "posts_count": insta_data.get("posts_count"),
                    "is_verified": insta_data.get("is_verified"),
                    "profile_picture_url": insta_data.get("profile_picture_url"),
                    "description": insta_data.get("description"),
                    "last_fetched_at": current_time_utc
                }

        if social_urls_to_fetch["tiktok"]:
            tiktok_data_map = await self.social_discovery_service.get_tiktok_data_for_urls([social_urls_to_fetch["tiktok"]])
            tiktok_data = tiktok_data_map.get(social_urls_to_fetch["tiktok"])
            if tiktok_data:
                fetched_stats_payload["tiktok"] = {
                    "url": tiktok_data.get("profile_url"),
                    "username": tiktok_data.get("username"),
                    "name": tiktok_data.get("name"),
                    "followers_count": tiktok_data.get("followers_count"),
                    "following_count": tiktok_data.get("following_count"),
                    "likes_count": tiktok_data.get("likes_count"),
                    "videos_count": tiktok_data.get("videos_count"),
                    "is_verified": tiktok_data.get("is_verified"),
                    "profile_picture_url": tiktok_data.get("profile_picture_url"),
                    "description": tiktok_data.get("description"),
                    "last_fetched_at": current_time_utc
                }

        if fetched_stats_payload:
            logger.info(f"Successfully fetched social stats for media kit {media_kit_id}. Platforms: {list(fetched_stats_payload.keys())}")
            existing_social_stats = kit.get("social_media_stats", {})
            if isinstance(existing_social_stats, str):
                try: existing_social_stats = json.loads(existing_social_stats)
                except: existing_social_stats = {}
            if not isinstance(existing_social_stats, dict): existing_social_stats = {}
            
            merged_stats = {**existing_social_stats, **fetched_stats_payload}
            
            return await media_kit_queries.update_media_kit_in_db(media_kit_id, {"social_media_stats": merged_stats})
        else:
            logger.info(f"No new social stats fetched for media kit {media_kit_id}.")
            return kit 