"""Campaign related database queries."""
from typing import Dict, Any, Optional, List, Tuple
import uuid
import json
from datetime import date, datetime, timezone # Ensure timezone is imported

from podcast_outreach.logging_config import get_logger
from podcast_outreach.database.connection import get_db_pool

logger = get_logger(__name__)

async def create_campaign_in_db(campaign_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    query = """
    INSERT INTO campaigns (
        campaign_id, person_id, attio_client_id, campaign_name, campaign_type,
        campaign_bio, campaign_angles, campaign_keywords, compiled_social_posts,
        podcast_transcript_link, compiled_articles_link, mock_interview_trancript,
        start_date, end_date, goal_note, media_kit_url, instantly_campaign_id,
        questionnaire_responses -- <<< NEW FIELD
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17,
        $18 -- <<< NEW PARAMETER
    ) RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            keywords = campaign_data.get("campaign_keywords", []) or []
            
            q_responses_dict = campaign_data.get('questionnaire_responses')
            
            # --- SOLUTION: Explicitly serialize the dictionary to a JSON string ---
            q_responses_json_str = None
            if isinstance(q_responses_dict, dict):
                q_responses_json_str = json.dumps(q_responses_dict)
            elif q_responses_dict is None:
                q_responses_json_str = None # Or 'null'::jsonb if your DB requires it for NULLs
            else:
                # If it's already a string, assume it's valid JSON or handle error
                # For safety, if it's not a dict or None, log a warning and set to None
                logger.warning(f"questionnaire_responses for campaign {campaign_data.get('campaign_id')} is not a dict or None, type: {type(q_responses_dict)}. Setting to NULL for DB.")
                q_responses_json_str = None

            row = await conn.fetchrow(
                query,
                campaign_data['campaign_id'], campaign_data['person_id'], campaign_data.get('attio_client_id'),
                campaign_data['campaign_name'], campaign_data.get('campaign_type'),
                campaign_data.get('campaign_bio'), campaign_data.get('campaign_angles'), keywords,
                campaign_data.get('compiled_social_posts'), campaign_data.get('podcast_transcript_link'),
                campaign_data.get('compiled_articles_link'), campaign_data.get('mock_interview_trancript'),
                campaign_data.get('start_date'), campaign_data.get('end_date'),
                campaign_data.get('goal_note'), campaign_data.get('media_kit_url'),
                campaign_data.get('instantly_campaign_id'),
                q_responses_json_str # <<< PASS THE JSON STRING
            )
            logger.info(f"Campaign created: {campaign_data.get('campaign_id')}")
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error creating campaign (ID: {campaign_data.get('campaign_id')}) in DB: {e}")
            raise

async def get_campaign_by_id(campaign_id: uuid.UUID) -> Optional[Dict[str, Any]]:
    query = "SELECT * FROM campaigns WHERE campaign_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, campaign_id)
            if not row:
                logger.warning(f"Campaign not found: {campaign_id}")
                return None
            
            # Process the row to convert JSON string to dict if necessary
            processed_row = dict(row)
            if "questionnaire_responses" in processed_row and isinstance(processed_row["questionnaire_responses"], str):
                try:
                    processed_row["questionnaire_responses"] = json.loads(processed_row["questionnaire_responses"])
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse questionnaire_responses for campaign {campaign_id}: {e}. Leaving as string or None.")
                    # Depending on strictness, you might set it to None or leave as is, or re-raise
            return processed_row
        except Exception as e:
            logger.exception(f"Error fetching campaign {campaign_id}: {e}")
            raise

async def get_all_campaigns_from_db(
    skip: int = 0, 
    limit: int = 100,
    person_id: Optional[int] = None # New parameter
) -> List[Dict[str, Any]]:
    """Fetches campaigns with pagination, optionally filtered by person_id."""
    params = [skip, limit]
    where_clauses = []
    
    param_idx = 3 # Start after skip and limit
    if person_id is not None:
        where_clauses.append(f"person_id = ${param_idx}")
        params.append(person_id)
        param_idx +=1

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)
    
    # Note: Parameter order for LIMIT and OFFSET is $1, $2 in the final query if no WHERE. 
    # If WHERE exists, they shift. It's safer to build params list carefully.
    # Corrected approach: query parameters for WHERE first, then pagination.
    
    final_params = []
    final_where_clauses = []
    current_param_idx = 1

    if person_id is not None:
        final_where_clauses.append(f"person_id = ${current_param_idx}")
        final_params.append(person_id)
        current_param_idx += 1
    
    final_where_sql = ""
    if final_where_clauses:
        final_where_sql = "WHERE " + " AND ".join(final_where_clauses)

    final_params.extend([limit, skip]) # limit is $N, offset is $N+1
    limit_param_num = current_param_idx
    offset_param_num = current_param_idx + 1

    query = f"""SELECT * FROM campaigns 
                 {final_where_sql} 
                 ORDER BY created_at DESC 
                 LIMIT ${limit_param_num} OFFSET ${offset_param_num};"""
    
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, *final_params)
            processed_rows = []
            for row in rows:
                processed_row = dict(row)
                if "questionnaire_responses" in processed_row and isinstance(processed_row["questionnaire_responses"], str):
                    try:
                        processed_row["questionnaire_responses"] = json.loads(processed_row["questionnaire_responses"])
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse questionnaire_responses for campaign {processed_row.get('campaign_id')}: {e}. Leaving as string or None.")
                        # Depending on strictness, you might set it to None or leave as is, or re-raise
                processed_rows.append(processed_row)
            return processed_rows
        except Exception as e:
            logger.exception(f"Error fetching campaigns (person_id: {person_id}): {e}")
            # Consider re-raising or returning empty list based on desired error handling
            raise

async def update_campaign(campaign_id: uuid.UUID, update_fields: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not update_fields:
        logger.warning(f"No update data for campaign {campaign_id}. Fetching current.")
        return await get_campaign_by_id(campaign_id)

    set_clauses = []
    values = []
    idx = 1
    for key, val in update_fields.items():
        if key == "campaign_keywords" and val is not None and not isinstance(val, list):
            keywords_list = [kw.strip() for kw in str(val).split(',') if kw.strip()]
            if not keywords_list and str(val).strip():
                keywords_list = [kw.strip() for kw in str(val).split() if kw.strip()]
            val = keywords_list
        
        if key == "questionnaire_keywords" and val is not None and not isinstance(val, list):
            # Similar handling for questionnaire_keywords if it can come as a string
            q_keywords_list = [kw.strip() for kw in str(val).split(',') if kw.strip()]
            if not q_keywords_list and str(val).strip():
                q_keywords_list = [kw.strip() for kw in str(val).split() if kw.strip()]
            val = q_keywords_list

        if key == "embedding" and isinstance(val, list):
            # Convert list of floats to pgvector-compatible string format '[f1,f2,...]'
            val = str(val).replace(" ", "") # Ensure no spaces, pgvector is sensitive

        if key == "questionnaire_responses":
            if isinstance(val, dict):
                val = json.dumps(val) # Serialize to JSON string for update
            elif val is None:
                pass # Keep as None
            else:
                logger.warning(f"Updating questionnaire_responses for campaign {campaign_id} with non-dict/non-None value of type {type(val)}. This might cause issues if not a valid JSON string.")
                # If `val` is already a string, assume it's a valid JSON string.
                # If it's something else, it might error or be cast by DB.

        set_clauses.append(f"{key} = ${idx}")
        values.append(val)
        idx += 1

    if not set_clauses:
        return await get_campaign_by_id(campaign_id)

    set_clause_str = ", ".join(set_clauses)
    query = f"UPDATE campaigns SET {set_clause_str} WHERE campaign_id = ${idx} RETURNING *;"
    values.append(campaign_id)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            if not row:
                logger.warning(f"Campaign {campaign_id} not found after update or update returned no rows.")
                return None
            
            processed_row = dict(row)
            if "questionnaire_responses" in processed_row and isinstance(processed_row["questionnaire_responses"], str):
                try:
                    processed_row["questionnaire_responses"] = json.loads(processed_row["questionnaire_responses"])
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse questionnaire_responses for updated campaign {campaign_id}: {e}. Leaving as string or None.")
            
            logger.info(f"Campaign updated: {campaign_id} with fields: {list(update_fields.keys())}")
            return processed_row

        except Exception as e:
            logger.exception(f"Error updating campaign {campaign_id}: {e}")
            raise

async def delete_campaign_from_db(campaign_id: uuid.UUID) -> bool:
    query = "DELETE FROM campaigns WHERE campaign_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            result = await conn.execute(query, campaign_id)
            deleted_count = int(result.split(" ")[1]) if result.startswith("DELETE ") else 0
            if deleted_count > 0:
                logger.info(f"Campaign deleted: {campaign_id}")
                return True
            logger.warning(f"Campaign not found for deletion or delete failed: {campaign_id}")
            return False
        except Exception as e:
            logger.exception(f"Error deleting campaign {campaign_id} from DB: {e}")
            raise

async def count_active_campaigns(person_id: Optional[int] = None) -> int:
    """Counts active campaigns. An active campaign has no end_date or end_date is in the future."""
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            today = date.today()
            base_query = "SELECT COUNT(*) FROM campaigns WHERE (end_date IS NULL OR end_date >= $1)"
            params = [today]
            if person_id is not None:
                base_query += f" AND person_id = ${len(params) + 1}"
                params.append(person_id)
            
            count = await conn.fetchval(base_query, *params)
            return count if count is not None else 0
        except Exception as e:
            logger.exception(f"Error counting active campaigns (person_id: {person_id}): {e}")
            return 0

async def get_campaigns_with_embeddings(limit: int = 200, offset: int = 0, person_id: Optional[int] = None) -> Tuple[List[Dict[str, Any]], int]:
    """
    Fetches campaigns that have an embedding, ordered by creation date, optionally filtered by person_id.
    Returns a list of campaign records and the total count of such campaigns.
    """
    base_query = "FROM campaigns WHERE embedding IS NOT NULL"
    count_base_query = "SELECT COUNT(*) FROM campaigns WHERE embedding IS NOT NULL"
    
    params = []
    conditions = []
    param_idx = 1

    if person_id is not None:
        conditions.append(f"person_id = ${param_idx}")
        params.append(person_id)
        param_idx += 1
    
    where_clause = ""
    if conditions:
        where_clause = " AND " + " AND ".join(conditions) # Add to existing WHERE embedding IS NOT NULL

    query_sql = f"SELECT * {base_query} {where_clause} ORDER BY created_at DESC LIMIT ${param_idx} OFFSET ${param_idx + 1};"
    count_sql = f"{count_base_query} {where_clause};"
    
    final_query_params = params + [limit, offset]
    final_count_params = params

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query_sql, *final_query_params)
            total_count_record = await conn.fetchrow(count_sql, *final_count_params)
            total = total_count_record['count'] if total_count_record else 0
            return [dict(row) for row in rows], total
        except Exception as e:
            logger.error(f"Error fetching campaigns with embeddings (person_id: {person_id}): {e}", exc_info=True)
            return [], 0

async def update_campaign_status(campaign_id: uuid.UUID, status: str, status_message: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Updates the status of a campaign. Assumes 'status' and 'status_message' columns exist or are handled by other means.
    This is a placeholder; actual implementation depends on how campaign status is stored.
    If campaigns table has 'campaign_status' and 'status_notes' fields, it would be:
    """
    # Example: UPDATE campaigns SET campaign_status = $1, status_notes = $2, updated_at = NOW() 
    #          WHERE campaign_id = $3 RETURNING *;
    logger.info(f"Attempting to update status for campaign {campaign_id} to '{status}' with message: '{status_message}'. This function is a placeholder.")
    # For now, just fetch and return the campaign as no actual status fields are defined for update here.
    return await get_campaign_by_id(campaign_id)