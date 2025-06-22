import logging
import uuid
import json
from typing import Dict, Any, Optional, List
from datetime import datetime

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

async def create_media_kit_in_db(kit_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Inserts a new media_kit record into the database."""
    # Ensure required fields for insertion are present, especially slug, campaign_id, person_id
    if not all(k in kit_data for k in ['slug', 'campaign_id', 'person_id']):
        logger.error("Missing required fields (slug, campaign_id, person_id) for media_kit creation.")
        return None

    query = """
    INSERT INTO media_kits (
        campaign_id, person_id, title, slug, is_public, theme_preference,
        headline, introduction, full_bio_content, summary_bio_content, short_bio_content,
        talking_points, key_achievements, previous_appearances, social_media_stats,
        headshot_image_url, logo_image_url, call_to_action_text, contact_information_for_booking,
        custom_sections,
        tagline, bio_source, keywords,
        angles_source, sample_questions, testimonials_section,
        person_social_links
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17, $18, $19, $20,
        $21, $22, $23, $24, $25, $26, $27
    ) RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            # JSONB fields: serialize to JSON strings
            talking_points_json = json.dumps(kit_data.get('talking_points', []))
            key_achievements_json = json.dumps(kit_data.get('key_achievements', []))
            previous_appearances_json = json.dumps(kit_data.get('previous_appearances', []))
            social_media_stats_json = json.dumps(kit_data.get('social_media_stats', {}))
            custom_sections_json = json.dumps(kit_data.get('custom_sections', []))
            sample_questions_json = json.dumps(kit_data.get('sample_questions', []))
            person_social_links_json = json.dumps(kit_data.get('person_social_links', {}))
            
            # TEXT field: pass as string
            headshot_image_url = kit_data.get('headshot_image_url')

            row = await conn.fetchrow(
                query,
                kit_data['campaign_id'], kit_data['person_id'], kit_data.get('title'), kit_data['slug'],
                kit_data.get('is_public', False), kit_data.get('theme_preference', 'modern'),
                kit_data.get('headline'), kit_data.get('introduction'),
                kit_data.get('full_bio_content'), kit_data.get('summary_bio_content'), kit_data.get('short_bio_content'),
                talking_points_json, key_achievements_json, previous_appearances_json, social_media_stats_json,
                headshot_image_url, kit_data.get('logo_image_url'), 
                kit_data.get('call_to_action_text'), kit_data.get('contact_information_for_booking'), 
                custom_sections_json,
                kit_data.get('tagline'), kit_data.get('bio_source'), kit_data.get('keywords', []),
                kit_data.get('angles_source'), sample_questions_json, kit_data.get('testimonials_section'),
                person_social_links_json
            )
            if row:
                logger.info(f"MediaKit created with ID: {row['media_kit_id']} for campaign {kit_data['campaign_id']}")
                # Deserialize fields when returning
                return _process_media_kit_row(row)
            return None
        except Exception as e:
            logger.exception(f"Error creating MediaKit in DB for campaign {kit_data.get('campaign_id')}: {e}")
            raise

def _process_media_kit_row(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    processed_row = dict(row)
    # Only JSONB fields need JSON parsing, not TEXT[] fields
    jsonb_fields = ['talking_points', 'key_achievements', 'previous_appearances', 
                   'social_media_stats', 'custom_sections', 'sample_questions', 
                   'person_social_links']
    for field in jsonb_fields:
        if field in processed_row and isinstance(processed_row[field], str):
            try:
                processed_row[field] = json.loads(processed_row[field])
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON field '{field}' for media kit {processed_row.get('media_kit_id')}: {e}. Leaving as string.")
    # headshot_image_url is TEXT and should be a string from asyncpg
    return processed_row

async def update_media_kit_in_db(media_kit_id: uuid.UUID, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates an existing media_kit record."""
    if not update_data:
        return await get_media_kit_by_id_from_db(media_kit_id) # Return current if no update data

    set_clauses = []
    values = []
    idx = 1
    
    # JSONB fields that should be JSON serialized if they are dict/list
    jsonb_fields_to_serialize = ['talking_points', 'key_achievements', 'previous_appearances', 
                                'social_media_stats', 'custom_sections', 'sample_questions',
                                'person_social_links']

    for key, value in update_data.items():
        if key in ["media_kit_id", "campaign_id", "person_id", "created_at"]: # These shouldn't be updated this way
            continue
        
        if key in jsonb_fields_to_serialize and isinstance(value, (dict, list)):
            values.append(json.dumps(value))
        elif key == 'headshot_image_url' and isinstance(value, str):
            # TEXT field: pass as string directly
            values.append(value)
        else:
            values.append(value)
        set_clauses.append(f"{key} = ${idx}")
        idx += 1
    
    if not set_clauses:
        return await get_media_kit_by_id_from_db(media_kit_id)

    # Always update the updated_at timestamp implicitly via trigger, or explicitly if no trigger
    # set_clauses.append(f"updated_at = NOW()") 

    query = f"UPDATE media_kits SET {", ".join(set_clauses)} WHERE media_kit_id = ${idx} RETURNING *;"
    values.append(media_kit_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            if row:
                logger.info(f"MediaKit updated: {media_kit_id}")
                return _process_media_kit_row(row) # Deserialize fields when returning
            logger.warning(f"MediaKit {media_kit_id} not found for update.")
            return None
        except Exception as e:
            logger.exception(f"Error updating MediaKit {media_kit_id} in DB: {e}")
            raise

async def get_media_kit_by_id_from_db(media_kit_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM media_kits WHERE media_kit_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, media_kit_id)
            return _process_media_kit_row(row) # Deserialize fields
        except Exception as e:
            logger.exception(f"Error fetching MediaKit by ID {media_kit_id}: {e}")
            raise

async def get_media_kit_by_campaign_id_from_db(campaign_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM media_kits WHERE campaign_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, campaign_id)
            return _process_media_kit_row(row) # Deserialize fields
        except Exception as e:
            logger.exception(f"Error fetching MediaKit by campaign_id {campaign_id}: {e}")
            raise

async def get_media_kit_by_slug_from_db(slug: str) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM media_kits WHERE slug = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, slug)
            return _process_media_kit_row(row) # Deserialize fields
        except Exception as e:
            logger.exception(f"Error fetching MediaKit by slug {slug}: {e}")
            raise

async def check_slug_exists(slug: str, exclude_media_kit_id: Optional[uuid.UUID] = None) -> bool:
    """Checks if a slug already exists, optionally excluding a specific media_kit_id (for updates)."""
    query_parts = ["SELECT EXISTS(SELECT 1 FROM media_kits WHERE slug = $1"]
    params = [slug]
    if exclude_media_kit_id:
        query_parts.append("AND media_kit_id != $2")
        params.append(exclude_media_kit_id)
    query_parts.append(");")
    query = " ".join(query_parts)
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            exists = await conn.fetchval(query, *params)
            return exists if exists is not None else False
        except Exception as e:
            logger.exception(f"Error checking slug existence for {slug}: {e}")
            raise 

async def get_media_kit_by_slug_enriched(slug: str) -> Optional[Dict[str, Any]]:
    """Fetches a single media kit by its slug and enriches it with client (person) details."""
    query = """
    SELECT 
        mk.*, 
        p.full_name AS client_full_name, 
        p.email AS client_email, 
        p.website AS client_website, 
        p.linkedin_profile_url AS client_linkedin_profile_url, 
        p.twitter_profile_url AS client_twitter_profile_url,
        p.instagram_profile_url AS client_instagram_profile_url,
        p.tiktok_profile_url AS client_tiktok_profile_url,
        p.role AS client_role,
        c.campaign_name
    FROM media_kits mk
    JOIN campaigns c ON mk.campaign_id = c.campaign_id
    JOIN people p ON mk.person_id = p.person_id  -- Direct join if person_id on media_kits is correct
                                             -- Or JOIN people p ON c.person_id = p.person_id if media_kits.person_id is just for reference to owner
    WHERE mk.slug = $1;
    """
    # Assuming media_kits.person_id directly refers to the client/person for the kit.
    # If person_id on media_kits refers to an admin creator and client is via campaign.person_id, adjust JOIN for people.
    # Based on your schema, media_kits.person_id REFERENCES people(person_id) seems to be the client.

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, slug)
            if not row:
                logger.debug(f"Enriched media kit not found for slug: {slug}")
                return None
            # For enriched queries, the _process_media_kit_row needs to be applied to the mk portion.
            # However, direct dict(row) is fine if Pydantic models downstream handle parsing, 
            # or ensure that the fields like mk.talking_points are correctly typed from DB already.
            # Given our new _process_media_kit_row, it's safer to use it.
            return _process_media_kit_row(dict(row)) # Process the row before returning
        except Exception as e:
            logger.exception(f"Error fetching enriched media kit by slug {slug}: {e}")
            return None # Or raise

async def get_active_public_media_kit_ids(limit: Optional[int] = None) -> List[uuid.UUID]:
    """Fetches IDs of media kits that are public and potentially active (e.g., recently updated or linked to active campaigns)."""
    # Simple version: just public kits, ordered by last updated (oldest first for refresh)
    # More complex logic can be added to prioritize based on campaign activity or last social stat refresh.
    query = """
    SELECT media_kit_id 
    FROM media_kits 
    WHERE is_public = TRUE 
    ORDER BY updated_at ASC -- Or a dedicated 'social_stats_last_fetched_at' column if you add one
    """
    params = []
    if limit is not None:
        query += " LIMIT $1"
        params.append(limit)
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, *params)
            return [row['media_kit_id'] for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching active public media kit IDs: {e}")
            return [] 