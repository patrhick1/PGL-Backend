# podcast_outreach/database/queries/pitch_templates.py
import logging
from typing import Any, Dict, Optional, List
from datetime import datetime
import uuid # Though template_id is TEXT, campaign_id might be UUID if ever linked

from podcast_outreach.database.connection import get_db_pool

logger = logging.getLogger(__name__)

async def create_template(template_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Creates a new pitch template in the database."""
    query = """
    INSERT INTO pitch_templates (
        template_id, media_type, target_media_type, language_code, 
        tone, prompt_body, created_by
    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
    RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                template_data['template_id'],
                template_data.get('media_type'),
                template_data.get('target_media_type'),
                template_data.get('language_code'),
                template_data.get('tone'),
                template_data['prompt_body'],
                template_data.get('created_by')
            )
            if row:
                logger.info(f"Pitch template '{row['template_id']}' created successfully.")
                return dict(row)
            return None
        except Exception as e:
            # Consider specific error handling for unique constraint violation on template_id
            logger.exception(f"Error creating pitch template '{template_data.get('template_id')}': {e}")
            return None # Or raise

async def get_template_by_id(template_id_str: str) -> Optional[Dict[str, Any]]:
    """Fetches a pitch template by its ID."""
    query = "SELECT * FROM pitch_templates WHERE template_id = $1;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, template_id_str)
            return dict(row) if row else None
        except Exception as e:
            logger.exception(f"Error fetching pitch template by ID '{template_id_str}': {e}")
            return None # Or raise

async def list_templates(skip: int = 0, limit: int = 100) -> List[Dict[str, Any]]:
    """Lists pitch templates with pagination."""
    query = "SELECT * FROM pitch_templates ORDER BY created_at DESC OFFSET $1 LIMIT $2;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(query, skip, limit)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error listing pitch templates: {e}")
            return []

async def update_template(template_id_str: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Updates an existing pitch template."""
    # Construct SET clauses dynamically to only update provided fields
    set_clauses = []
    values = []
    param_idx = 1

    for key, value in update_data.items():
        if key in ['media_type', 'target_media_type', 'language_code', 'tone', 'prompt_body', 'created_by']:
            set_clauses.append(f"{key} = ${param_idx}")
            values.append(value)
            param_idx += 1
    
    if not set_clauses:
        logger.warning(f"No valid fields provided for updating template '{template_id_str}'.")
        return await get_template_by_id(template_id_str) # Return current state if no updates

    # Add updated_at if your table has it and an auto-update trigger isn't covering all changes
    # For now, assuming created_at is set on creation and doesn't change.
    # If you add an `updated_at` column, ensure it's handled: `set_clauses.append(f"updated_at = NOW()")`

    query = f"""
    UPDATE pitch_templates
    SET {', '.join(set_clauses)}
    WHERE template_id = ${param_idx}
    RETURNING *;
    """
    values.append(template_id_str)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *values)
            if row:
                logger.info(f"Pitch template '{template_id_str}' updated successfully.")
                return dict(row)
            logger.warning(f"Pitch template '{template_id_str}' not found for update.")
            return None
        except Exception as e:
            logger.exception(f"Error updating pitch template '{template_id_str}': {e}")
            return None # Or raise

async def delete_template(template_id_str: str) -> bool:
    """Deletes a pitch template by its ID."""
    query = "DELETE FROM pitch_templates WHERE template_id = $1 RETURNING template_id;"
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            deleted_id = await conn.fetchval(query, template_id_str)
            if deleted_id:
                logger.info(f"Pitch template '{template_id_str}' deleted successfully.")
                return True
            logger.warning(f"Pitch template '{template_id_str}' not found for deletion.")
            return False
        except Exception as e:
            logger.exception(f"Error deleting pitch template '{template_id_str}': {e}")
            return False # Or raise 