import logging
from typing import Any, Dict, Optional

from db_service_pg import get_db_pool

logger = logging.getLogger(__name__)

async def upsert_media_in_db(media_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Create or update a media record based on rss_url."""
    rss_url = media_data.get("rss_url")
    existing = None
    if rss_url:
        query = "SELECT * FROM media WHERE rss_url = $1;"
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            existing = await conn.fetchrow(query, rss_url)
            existing = dict(existing) if existing else None
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if existing:
            set_clauses = []
            values = []
            idx = 1
            for k, v in media_data.items():
                if k in ["media_id", "rss_url"]:
                    continue
                set_clauses.append(f"{k} = ${idx}")
                values.append(v)
                idx += 1
            if not set_clauses:
                return existing
            query = f"UPDATE media SET {', '.join(set_clauses)} WHERE rss_url = ${idx} RETURNING *;"
            values.append(rss_url)
            row = await conn.fetchrow(query, *values)
            return dict(row) if row else None
        else:
            query = """
            INSERT INTO media (name, rss_url, company_id, category, language, contact_email)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *;
            """
            row = await conn.fetchrow(
                query,
                media_data.get("name"),
                rss_url,
                media_data.get("company_id"),
                media_data.get("category"),
                media_data.get("language"),
                media_data.get("contact_email"),
            )
            return dict(row) if row else None
