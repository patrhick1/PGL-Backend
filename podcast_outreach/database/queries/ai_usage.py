# podcast_outreach/database/queries/ai_usage.py

import logging
from typing import Any, Dict, Optional, List
from datetime import datetime, date, timedelta
import uuid

from db_service_pg import get_db_pool

logger = logging.getLogger(__name__)

async def log_ai_usage_in_db(log_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Logs AI usage data into the ai_usage_logs table.

    Args:
        log_data: Dictionary containing usage details.
                  Expected keys: workflow, model, tokens_in, tokens_out, total_tokens,
                  cost, execution_time_sec, endpoint, related_pitch_gen_id (optional),
                  related_campaign_id (optional), related_media_id (optional).

    Returns:
        The created log record as a dictionary, or None on failure.
    """
    query = """
    INSERT INTO ai_usage_logs (
        timestamp, workflow, model, tokens_in, tokens_out, total_tokens,
        cost, execution_time_sec, endpoint, related_pitch_gen_id,
        related_campaign_id, related_media_id
    ) VALUES (
        $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
    ) RETURNING *;
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(
                query,
                log_data.get('timestamp', datetime.utcnow()),
                log_data['workflow'],
                log_data['model'],
                log_data['tokens_in'],
                log_data['tokens_out'],
                log_data['total_tokens'],
                log_data['cost'],
                log_data['execution_time_sec'],
                log_data.get('endpoint'),
                log_data.get('related_pitch_gen_id'),
                log_data.get('related_campaign_id'),
                log_data.get('related_media_id')
            )
            if row:
                logger.debug(f"AI usage logged: {row['log_id']} for workflow {row['workflow']}")
                return dict(row)
            return None
        except Exception as e:
            logger.exception(f"Error logging AI usage to DB for workflow {log_data.get('workflow')}: {e}")
            raise

async def get_ai_usage_logs(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    related_pitch_gen_id: Optional[int] = None,
    related_campaign_id: Optional[uuid.UUID] = None,
    related_media_id: Optional[int] = None,
    group_by_column: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Fetches AI usage logs, with optional filtering and grouping.
    If group_by_column is provided, returns aggregated data.
    """
    base_query = """
    SELECT
        {select_columns}
    FROM ai_usage_logs
    WHERE 1=1
    """
    
    where_clauses = []
    query_params = []
    param_idx = 1

    if start_date:
        where_clauses.append(f"timestamp >= ${param_idx}")
        query_params.append(start_date)
        param_idx += 1
    if end_date:
        where_clauses.append(f"timestamp < ${param_idx}") # Use < for end_date to include full day
        query_params.append(end_date + timedelta(days=1))
        param_idx += 1
    if related_pitch_gen_id:
        where_clauses.append(f"related_pitch_gen_id = ${param_idx}")
        query_params.append(related_pitch_gen_id)
        param_idx += 1
    if related_campaign_id:
        where_clauses.append(f"related_campaign_id = ${param_idx}")
        query_params.append(related_campaign_id)
        param_idx += 1
    if related_media_id:
        where_clauses.append(f"related_media_id = ${param_idx}")
        query_params.append(related_media_id)
        param_idx += 1

    if where_clauses:
        base_query += " AND " + " AND ".join(where_clauses)

    if group_by_column and group_by_column in ['workflow', 'model', 'endpoint', 'related_pitch_gen_id', 'related_campaign_id', 'related_media_id']:
        select_cols = f"""
            {group_by_column},
            COUNT(*) AS calls,
            SUM(tokens_in) AS tokens_in,
            SUM(tokens_out) AS tokens_out,
            SUM(total_tokens) AS total_tokens,
            SUM(cost) AS cost,
            AVG(execution_time_sec) AS avg_execution_time_sec
        """
        group_by_clause = f" GROUP BY {group_by_column} ORDER BY {group_by_column}"
    else:
        select_cols = "*"
        group_by_clause = " ORDER BY timestamp DESC"

    final_query = base_query.format(select_columns=select_cols) + group_by_clause

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            rows = await conn.fetch(final_query, *query_params)
            return [dict(row) for row in rows]
        except Exception as e:
            logger.exception(f"Error fetching AI usage logs: {e}")
            return []

async def get_total_ai_usage(
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
    related_pitch_gen_id: Optional[int] = None,
    related_campaign_id: Optional[uuid.UUID] = None,
    related_media_id: Optional[int] = None
) -> Dict[str, Any]:
    """
    Calculates total AI usage (tokens, cost, calls) for a given period/entity.
    """
    query = """
    SELECT
        COUNT(*) AS total_calls,
        SUM(tokens_in) AS total_tokens_in,
        SUM(tokens_out) AS total_tokens_out,
        SUM(total_tokens) AS total_tokens,
        SUM(cost) AS total_cost,
        SUM(execution_time_sec) AS total_execution_time_sec
    FROM ai_usage_logs
    WHERE 1=1
    """
    
    where_clauses = []
    query_params = []
    param_idx = 1

    if start_date:
        where_clauses.append(f"timestamp >= ${param_idx}")
        query_params.append(start_date)
        param_idx += 1
    if end_date:
        where_clauses.append(f"timestamp < ${param_idx}")
        query_params.append(end_date + timedelta(days=1))
        param_idx += 1
    if related_pitch_gen_id:
        where_clauses.append(f"related_pitch_gen_id = ${param_idx}")
        query_params.append(related_pitch_gen_id)
        param_idx += 1
    if related_campaign_id:
        where_clauses.append(f"related_campaign_id = ${param_idx}")
        query_params.append(related_campaign_id)
        param_idx += 1
    if related_media_id:
        where_clauses.append(f"related_media_id = ${param_idx}")
        query_params.append(related_media_id)
        param_idx += 1

    if where_clauses:
        query += " AND " + " AND ".join(where_clauses)

    pool = await get_db_pool()
    async with pool.acquire() as conn:
        try:
            row = await conn.fetchrow(query, *query_params)
            return dict(row) if row else {
                'total_calls': 0, 'total_tokens_in': 0, 'total_tokens_out': 0,
                'total_tokens': 0, 'total_cost': 0.0, 'total_execution_time_sec': 0.0
            }
        except Exception as e:
            logger.exception(f"Error getting total AI usage: {e}")
            return {
                'total_calls': 0, 'total_tokens_in': 0, 'total_tokens_out': 0,
                'total_tokens': 0, 'total_cost': 0.0, 'total_execution_time_sec': 0.0
            }
