# podcast_outreach/services/matches/episode_matcher.py

import logging
from typing import Optional, List, Dict, Any
import numpy as np

from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.database.queries import campaigns as campaign_queries

logger = logging.getLogger(__name__)

class EpisodeMatcher:
    """Service to find the best matching episode for a campaign using embeddings."""
    
    async def find_best_matching_episode(
        self, 
        campaign_id: str, 
        media_id: int
    ) -> Optional[int]:
        """
        Find the best matching episode for a campaign from a specific podcast.
        Uses cosine similarity between campaign and episode embeddings.
        
        Returns:
            episode_id of the best match, or None if no episodes found
        """
        try:
            # Get campaign embedding
            campaign = await campaign_queries.get_campaign_by_id(campaign_id)
            if not campaign or not campaign.get('embedding'):
                logger.warning(f"Campaign {campaign_id} has no embedding")
                return None
            
            campaign_embedding = np.array(campaign['embedding'])
            
            # Get all episodes for this media with embeddings
            episodes = await episode_queries.get_episodes_with_embeddings_for_media(media_id)
            
            if not episodes:
                logger.info(f"No episodes with embeddings found for media {media_id}")
                return None
            
            # Calculate cosine similarities
            best_episode_id = None
            best_similarity = -1.0
            
            for episode in episodes:
                if episode.get('embedding'):
                    episode_embedding = np.array(episode['embedding'])
                    
                    # Calculate cosine similarity
                    similarity = self._cosine_similarity(campaign_embedding, episode_embedding)
                    
                    if similarity > best_similarity:
                        best_similarity = similarity
                        best_episode_id = episode['episode_id']
            
            if best_episode_id:
                logger.info(
                    f"Best matching episode {best_episode_id} for campaign {campaign_id} "
                    f"and media {media_id} with similarity {best_similarity:.3f}"
                )
            
            return best_episode_id
            
        except Exception as e:
            logger.error(f"Error finding best matching episode: {e}")
            return None
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
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