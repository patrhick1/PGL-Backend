#!/usr/bin/env python3
"""
Script to update existing match suggestions with best_matching_episode_id
using embeddings similarity between campaign and episodes.
"""

import asyncio
import logging
import numpy as np
from datetime import datetime

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import episodes as episode_queries

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Calculate cosine similarity between two vectors."""
    try:
        dot_product = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        
        if norm_a == 0 or norm_b == 0:
            return 0.0
        
        return dot_product / (norm_a * norm_b)
    except Exception as e:
        logger.error(f"Error calculating cosine similarity: {e}")
        return 0.0


async def find_best_episode_for_match(campaign_id: str, media_id: int) -> tuple[int, float]:
    """Find the best matching episode for a campaign and media pair."""
    try:
        # Get campaign embedding
        campaign = await campaign_queries.get_campaign_by_id(campaign_id)
        if not campaign or not campaign.get('embedding'):
            logger.warning(f"Campaign {campaign_id} has no embedding")
            return None, 0.0
        
        campaign_embedding = np.array(campaign['embedding'])
        
        # Get all episodes with embeddings for this media
        episodes = await episode_queries.get_episodes_with_embeddings_for_media(media_id)
        
        if not episodes:
            logger.info(f"No episodes with embeddings found for media {media_id}")
            return None, 0.0
        
        # Find best match
        best_episode_id = None
        best_similarity = -1.0
        
        for episode in episodes:
            if episode.get('embedding'):
                episode_embedding = np.array(episode['embedding'])
                similarity = cosine_similarity(campaign_embedding, episode_embedding)
                
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_episode_id = episode['episode_id']
        
        return best_episode_id, best_similarity
        
    except Exception as e:
        logger.error(f"Error finding best episode: {e}")
        return None, 0.0


async def update_match_suggestions():
    """Update all match suggestions without best_matching_episode_id."""
    pool = await get_db_pool()
    
    try:
        async with pool.acquire() as conn:
            # Get all match suggestions
            query = """
            SELECT match_id, campaign_id, media_id, best_matching_episode_id
            FROM match_suggestions
            ORDER BY match_id;
            """
            
            matches = await conn.fetch(query)
            logger.info(f"Found {len(matches)} match suggestions")
            
            updated_count = 0
            
            for match in matches:
                match_id = match['match_id']
                campaign_id = match['campaign_id']
                media_id = match['media_id']
                current_episode_id = match['best_matching_episode_id']
                
                logger.info(f"\nProcessing match {match_id} (campaign: {campaign_id}, media: {media_id})")
                
                # Find best episode
                best_episode_id, similarity = await find_best_episode_for_match(
                    str(campaign_id), media_id
                )
                
                if best_episode_id:
                    # Update the match suggestion
                    update_query = """
                    UPDATE match_suggestions
                    SET best_matching_episode_id = $1
                    WHERE match_id = $2
                    RETURNING match_id;
                    """
                    
                    result = await conn.fetchrow(update_query, best_episode_id, match_id)
                    
                    if result:
                        logger.info(
                            f"✓ Updated match {match_id} with episode {best_episode_id} "
                            f"(similarity: {similarity:.3f})"
                        )
                        updated_count += 1
                    else:
                        logger.error(f"Failed to update match {match_id}")
                else:
                    logger.warning(f"No suitable episode found for match {match_id}")
            
            logger.info(f"\nCompleted! Updated {updated_count} out of {len(matches)} match suggestions")
            
    except Exception as e:
        logger.error(f"Error updating match suggestions: {e}")
        raise


async def main():
    """Main function."""
    logger.info("Starting match suggestions episode update...")
    
    try:
        await update_match_suggestions()
        logger.info("Update completed successfully!")
    except Exception as e:
        logger.error(f"Script failed: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())