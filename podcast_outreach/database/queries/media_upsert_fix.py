"""
Enhanced media upsert function that handles cross-API source transitions properly.
This fixes the merge_and_upsert_media failures when podcasts exist in multiple APIs.
"""

import logging
import json
from typing import Dict, Any, Optional
import asyncpg

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)


async def upsert_media_with_rss_fallback(media_data: Dict[str, Any], pool: Optional[asyncpg.Pool] = None) -> Optional[Dict[str, Any]]:
    """
    Enhanced upsert that handles source API transitions by using RSS URL as the primary identifier.
    
    This fixes the issue where promoting a ListenNotes podcast to Podscan causes failures
    because the api_id changes, breaking the ON CONFLICT clause.
    
    Strategy:
    1. First try to find existing media by RSS URL (most stable identifier)
    2. If not found, try by current source_api + api_id combination  
    3. Update if found (including api_id changes for promotions), insert if not found
    4. Handle api_id changes safely when promoting between APIs
    """
    # Clean the data before processing
    cleaned_data = media_data.copy()
    
    # URL fields that should contain valid URLs
    url_fields = [
        'podcast_twitter_url', 'podcast_linkedin_url', 'podcast_instagram_url',
        'podcast_facebook_url', 'podcast_youtube_url', 'podcast_tiktok_url',
        'podcast_other_social_url', 'website', 'image_url', 'rss_url'
    ]
    
    # Clean URL fields - move emails to contact_email if needed
    for field in url_fields:
        if field in cleaned_data and cleaned_data[field]:
            value = str(cleaned_data[field]).strip()
            # Check if it's an email (contains @ but not a valid URL)
            if '@' in value and not value.startswith(('http://', 'https://')):
                logger.warning(f"Found email '{value}' in URL field '{field}', moving to contact_email")
                # Move email to contact_email field if it's not already set
                if not cleaned_data.get('contact_email'):
                    cleaned_data['contact_email'] = value
                # Clear the URL field
                cleaned_data[field] = None
    
    if pool is None:
        pool = await get_db_pool()
    
    async with pool.acquire() as conn:
        try:
            # First, try to find existing media by RSS URL (primary identifier)
            existing_media = None
            existing_api_id = None
            rss_url = cleaned_data.get('rss_url')
            api_id = cleaned_data.get('api_id')
            source_api = cleaned_data.get('source_api')
            
            if rss_url:
                # Get full record to check if api_id is changing
                existing_query = "SELECT media_id, api_id, source_api FROM media WHERE rss_url = $1 LIMIT 1"
                existing_row = await conn.fetchrow(existing_query, rss_url)
                if existing_row:
                    existing_media = existing_row['media_id']
                    existing_api_id = existing_row['api_id']
                    logger.info(f"Found existing media by RSS URL for '{cleaned_data.get('name')}': media_id={existing_media}, existing_api_id={existing_api_id}")
            
            # If not found by RSS, try by api_id alone (not source_api + api_id)
            # This catches cases where the same api_id might exist but wasn't found by RSS
            if not existing_media and api_id:
                existing_query = "SELECT media_id, rss_url FROM media WHERE api_id = $1 LIMIT 1"
                existing_row = await conn.fetchrow(existing_query, api_id)
                if existing_row:
                    # Check if this is actually the same podcast (by comparing RSS if available)
                    if rss_url and existing_row['rss_url'] and existing_row['rss_url'] != rss_url:
                        # Different RSS URLs - this is a different podcast with same api_id (shouldn't happen but handle it)
                        logger.warning(f"Found media with same api_id but different RSS URL. Treating as new media.")
                    else:
                        existing_media = existing_row['media_id']
                        existing_api_id = api_id
                        logger.info(f"Found existing media by API ID for '{cleaned_data.get('name')}': media_id={existing_media}")
            
            if existing_media:
                # UPDATE existing record
                # Special handling for api_id changes during promotion
                if api_id and existing_api_id and api_id != existing_api_id:
                    # Check if the new api_id already exists on a different record
                    check_query = "SELECT media_id FROM media WHERE api_id = $1 AND media_id != $2"
                    conflict_row = await conn.fetchrow(check_query, api_id, existing_media)
                    if conflict_row:
                        logger.warning(f"Cannot update api_id to {api_id} - already exists on media_id {conflict_row['media_id']}. Keeping existing api_id.")
                        # Remove api_id from the update to avoid conflict
                        cleaned_data.pop('api_id', None)
                    else:
                        logger.info(f"Promoting media_id {existing_media}: changing api_id from {existing_api_id} to {api_id}")
                
                # Build dynamic UPDATE query
                update_fields = []
                update_values = []
                value_index = 1
                
                # Define fields that can be updated
                updatable_fields = [
                    'source_api', 'api_id', 'name', 'title', 'rss_url', 'website', 'description',
                    'contact_email', 'language', 'category', 'image_url', 'total_episodes',
                    'itunes_id', 'podcast_spotify_id', 'listen_score', 'listen_score_global_rank',
                    'itunes_rating_average', 'itunes_rating_count', 'audience_size', 'last_posted_at',
                    'podcast_twitter_url', 'podcast_linkedin_url', 'podcast_instagram_url',
                    'podcast_facebook_url', 'podcast_youtube_url', 'podcast_tiktok_url',
                    'podcast_other_social_url', 'host_names', 'last_enriched_timestamp'
                ]
                
                for field in updatable_fields:
                    if field in cleaned_data and cleaned_data[field] is not None:
                        update_fields.append(f"{field} = ${value_index}")
                        update_values.append(cleaned_data[field])
                        value_index += 1
                
                if update_fields:
                    update_fields.append("updated_at = NOW()")
                    update_query = f"""
                        UPDATE media 
                        SET {', '.join(update_fields)}
                        WHERE media_id = ${value_index}
                        RETURNING *
                    """
                    update_values.append(existing_media)
                    
                    row = await conn.fetchrow(update_query, *update_values)
                    if row:
                        logger.info(f"Updated existing media: '{row['name']}' (ID: {row['media_id']}) with source_api={row['source_api']}")
                        return dict(row)
                else:
                    # No fields to update, just return existing
                    select_query = "SELECT * FROM media WHERE media_id = $1"
                    row = await conn.fetchrow(select_query, existing_media)
                    if row:
                        return dict(row)
            
            else:
                # INSERT new record - but first double-check RSS URL doesn't exist
                # This handles race conditions where two processes might be inserting simultaneously
                if rss_url:
                    final_check_query = "SELECT media_id FROM media WHERE rss_url = $1 LIMIT 1"
                    final_check_row = await conn.fetchrow(final_check_query, rss_url)
                    if final_check_row:
                        # Another process just inserted this media, return it instead
                        logger.info(f"Race condition avoided: found media_id {final_check_row['media_id']} on final RSS check")
                        select_query = "SELECT * FROM media WHERE media_id = $1"
                        row = await conn.fetchrow(select_query, final_check_row['media_id'])
                        if row:
                            return dict(row)
                
                # Check if api_id already exists before insert
                if api_id:
                    api_check_query = "SELECT media_id, name, rss_url FROM media WHERE api_id = $1 LIMIT 1"
                    api_check_row = await conn.fetchrow(api_check_query, api_id)
                    if api_check_row:
                        logger.warning(f"Cannot insert new media with api_id {api_id} - already exists on media_id {api_check_row['media_id']} ('{api_check_row['name']}')")
                        # If RSS URLs match, this is the same podcast - return existing
                        if rss_url and api_check_row['rss_url'] == rss_url:
                            logger.info(f"Same podcast detected by matching RSS. Returning existing media_id {api_check_row['media_id']}")
                            select_query = "SELECT * FROM media WHERE media_id = $1"
                            row = await conn.fetchrow(select_query, api_check_row['media_id'])
                            if row:
                                return dict(row)
                        # Otherwise, clear the api_id to allow insert with NULL api_id
                        logger.info(f"Inserting without api_id to avoid conflict")
                        cleaned_data['api_id'] = None
                
                # Proceed with insert
                cols = [
                    'api_id', 'source_api', 'name', 'title', 'rss_url', 'website', 'description',
                    'contact_email', 'language', 'category', 'image_url', 'total_episodes',
                    'itunes_id', 'podcast_spotify_id', 'listen_score', 'listen_score_global_rank',
                    'itunes_rating_average', 'itunes_rating_count', 'audience_size', 'last_posted_at',
                    'podcast_twitter_url', 'podcast_linkedin_url', 'podcast_instagram_url',
                    'podcast_facebook_url', 'podcast_youtube_url', 'podcast_tiktok_url',
                    'podcast_other_social_url', 'host_names', 'last_enriched_timestamp'
                ]
                
                values = [cleaned_data.get(c) for c in cols]
                placeholders = ", ".join([f"${i+1}" for i in range(len(cols))])
                
                insert_query = f"""
                    INSERT INTO media ({', '.join(cols)})
                    VALUES ({placeholders})
                    RETURNING *
                """
                
                row = await conn.fetchrow(insert_query, *values)
                if row:
                    logger.info(f"Inserted new media: '{row['name']}' (ID: {row['media_id']}) with source_api={row['source_api']}")
                    return dict(row)
            
            logger.error(f"Upsert failed for '{cleaned_data.get('name')}' - no row returned")
            return None
            
        except asyncpg.UniqueViolationError as e:
            # This might still happen if two processes try to insert the same new record simultaneously
            logger.warning(f"Unique violation during upsert for '{cleaned_data.get('name')}': {e}")
            # Try one more time to find and update the existing record
            if rss_url:
                try:
                    select_query = "SELECT * FROM media WHERE rss_url = $1 LIMIT 1"
                    row = await conn.fetchrow(select_query, rss_url)
                    if row:
                        return dict(row)
                except Exception:
                    pass
            return None
            
        except Exception as e:
            logger.exception(f"Error during enhanced upsert for media '{cleaned_data.get('name')}': {e}")
            raise