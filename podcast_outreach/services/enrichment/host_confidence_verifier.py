"""
Host Name Confidence Verification Service

This service provides functionality to:
1. Track host name discovery sources
2. Calculate confidence scores for host names
3. Cross-reference host names from multiple sources
4. Flag low-confidence hosts for manual review
"""

import logging
import asyncio
from typing import Dict, List, Optional, Set, Tuple, Any
from datetime import datetime, timezone, timedelta
import re
from difflib import SequenceMatcher

from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

class HostConfidenceVerifier:
    """
    Service for verifying and scoring confidence in discovered host names.
    """
    
    # Source confidence weights
    SOURCE_CONFIDENCE_WEIGHTS = {
        "manual_entry": 1.0,           # Manually entered by user
        "rss_owner": 0.9,             # From RSS feed owner field
        "episode_transcript": 0.85,    # Extracted from episode transcripts
        "ai_analysis": 0.8,           # From AI episode analysis
        "podcast_description": 0.7,    # From podcast description
        "tavily_search": 0.6,         # From web search
        "llm_extraction": 0.5,        # From LLM extraction without specific source
        "social_media": 0.4,          # From social media profiles
    }
    
    # Verification interval (days)
    VERIFICATION_INTERVAL_DAYS = 30
    
    def __init__(self):
        self.name_similarity_threshold = 0.85  # For fuzzy matching similar names
        logger.info("HostConfidenceVerifier initialized")
    
    def calculate_name_similarity(self, name1: str, name2: str) -> float:
        """
        Calculate similarity between two names using fuzzy matching.
        Returns a score between 0.0 and 1.0.
        """
        # Normalize names
        name1 = name1.lower().strip()
        name2 = name2.lower().strip()
        
        # Handle common variations
        # Remove titles (Dr., Mr., Ms., etc.)
        title_pattern = r'^(dr\.?|mr\.?|mrs\.?|ms\.?|prof\.?|professor)\s+'
        name1 = re.sub(title_pattern, '', name1, flags=re.IGNORECASE)
        name2 = re.sub(title_pattern, '', name2, flags=re.IGNORECASE)
        
        # Check exact match after normalization
        if name1 == name2:
            return 1.0
        
        # Check if one name contains the other (e.g., "John Smith" vs "John")
        if name1 in name2 or name2 in name1:
            return 0.9
        
        # Use sequence matcher for fuzzy matching
        return SequenceMatcher(None, name1, name2).ratio()
    
    async def verify_host_names(self, media_id: int) -> Dict[str, Any]:
        """
        Verify host names for a media item by cross-referencing multiple sources.
        
        Returns:
            Dict containing:
            - verified_hosts: List of verified host names with confidence scores
            - discovery_sources: List of all sources where hosts were found
            - low_confidence_hosts: List of hosts with confidence < 0.7
            - confidence_scores: Dict mapping host names to confidence scores
        """
        logger.info(f"Starting host name verification for media_id: {media_id}")
        
        try:
            # Get current media data
            media_data = await media_queries.get_media_by_id_from_db(media_id)
            if not media_data:
                logger.error(f"Media {media_id} not found")
                return {}
            
            # Initialize tracking data
            host_sources: Dict[str, Set[str]] = {}  # host_name -> set of sources
            all_discovered_hosts: Set[str] = set()
            discovery_sources: Set[str] = set()
            
            # 1. Check existing host_names field
            current_hosts = media_data.get('host_names', [])
            if current_hosts and isinstance(current_hosts, list):
                for host in current_hosts:
                    if host and isinstance(host, str):
                        normalized_host = host.strip()
                        all_discovered_hosts.add(normalized_host)
                        if normalized_host not in host_sources:
                            host_sources[normalized_host] = set()
                        # Determine source based on existing confidence data
                        existing_confidence = media_data.get('host_names_discovery_confidence', {})
                        if normalized_host in existing_confidence and existing_confidence[normalized_host] >= 0.9:
                            host_sources[normalized_host].add("manual_entry")
                        else:
                            host_sources[normalized_host].add("llm_extraction")
            
            # 2. Check RSS owner name
            rss_owner = media_data.get('rss_owner_name')
            if rss_owner and isinstance(rss_owner, str):
                normalized_owner = rss_owner.strip()
                all_discovered_hosts.add(normalized_owner)
                if normalized_owner not in host_sources:
                    host_sources[normalized_owner] = set()
                host_sources[normalized_owner].add("rss_owner")
                discovery_sources.add("rss_owner")
            
            # 3. Check episode transcripts and AI analysis
            episodes = await episode_queries.get_episodes_for_media_paginated(media_id, offset=0, limit=10)
            
            for episode in episodes:
                # Check AI-analyzed host names
                episode_hosts = episode.get('host_names', [])
                if episode_hosts and isinstance(episode_hosts, list):
                    for host in episode_hosts:
                        if host and isinstance(host, str):
                            normalized_host = host.strip()
                            all_discovered_hosts.add(normalized_host)
                            if normalized_host not in host_sources:
                                host_sources[normalized_host] = set()
                            
                            # Determine if from transcript or AI analysis
                            if episode.get('transcript'):
                                host_sources[normalized_host].add("episode_transcript")
                                discovery_sources.add("episode_transcript")
                            else:
                                host_sources[normalized_host].add("ai_analysis")
                                discovery_sources.add("ai_analysis")
            
            # 4. Extract from podcast description if available
            description = media_data.get('description', '')
            if description:
                hosts_from_desc = self._extract_hosts_from_description(description)
                for host in hosts_from_desc:
                    all_discovered_hosts.add(host)
                    if host not in host_sources:
                        host_sources[host] = set()
                    host_sources[host].add("podcast_description")
                    discovery_sources.add("podcast_description")
            
            # 5. Consolidate similar names
            consolidated_hosts = self._consolidate_similar_names(list(all_discovered_hosts))
            
            # 6. Calculate confidence scores
            confidence_scores = {}
            for host_group in consolidated_hosts:
                # Use the most common variant as the canonical name
                canonical_name = max(host_group, key=lambda x: len(host_sources.get(x, [])))
                
                # Combine sources from all variants
                combined_sources = set()
                for variant in host_group:
                    combined_sources.update(host_sources.get(variant, set()))
                
                # Calculate weighted confidence score
                confidence = self._calculate_confidence_score(combined_sources)
                confidence_scores[canonical_name] = confidence
            
            # 7. Prepare results
            verified_hosts = []
            low_confidence_hosts = []
            
            for host, confidence in confidence_scores.items():
                host_info = {
                    "name": host,
                    "confidence": confidence,
                    "sources": list(host_sources.get(host, set()))
                }
                verified_hosts.append(host_info)
                
                if confidence < 0.7:
                    low_confidence_hosts.append(host_info)
            
            # Sort by confidence
            verified_hosts.sort(key=lambda x: x['confidence'], reverse=True)
            
            # 8. Update database with verification results
            await self._update_host_verification_data(
                media_id,
                verified_hosts,
                list(discovery_sources),
                confidence_scores
            )
            
            result = {
                "verified_hosts": verified_hosts,
                "discovery_sources": list(discovery_sources),
                "low_confidence_hosts": low_confidence_hosts,
                "confidence_scores": confidence_scores,
                "total_hosts_found": len(verified_hosts)
            }
            
            logger.info(f"Host verification completed for media {media_id}: {len(verified_hosts)} hosts found")
            return result
            
        except Exception as e:
            logger.error(f"Error verifying host names for media {media_id}: {e}", exc_info=True)
            return {}
    
    def _extract_hosts_from_description(self, description: str) -> List[str]:
        """
        Extract potential host names from podcast description.
        """
        hosts = []
        
        # Common patterns for host mentions
        patterns = [
            r'hosted by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'with host\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'your host[,\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'(?:I\'m|I am)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            for match in matches:
                # Basic validation - should look like a name
                if match and len(match.split()) <= 4 and not any(char.isdigit() for char in match):
                    hosts.append(match.strip())
        
        return hosts
    
    def _consolidate_similar_names(self, names: List[str]) -> List[List[str]]:
        """
        Group similar names together (e.g., "John Smith" and "John A. Smith").
        Returns list of groups where each group contains similar name variants.
        """
        if not names:
            return []
        
        groups = []
        processed = set()
        
        for name in names:
            if name in processed:
                continue
            
            # Find all similar names
            group = [name]
            processed.add(name)
            
            for other_name in names:
                if other_name != name and other_name not in processed:
                    similarity = self.calculate_name_similarity(name, other_name)
                    if similarity >= self.name_similarity_threshold:
                        group.append(other_name)
                        processed.add(other_name)
            
            groups.append(group)
        
        return groups
    
    def _calculate_confidence_score(self, sources: Set[str]) -> float:
        """
        Calculate weighted confidence score based on discovery sources.
        """
        if not sources:
            return 0.0
        
        # Get weights for each source
        weights = [self.SOURCE_CONFIDENCE_WEIGHTS.get(source, 0.3) for source in sources]
        
        # Use a combination of max weight and source diversity
        max_weight = max(weights)
        source_diversity_bonus = min(0.2, len(sources) * 0.05)  # Up to 0.2 bonus for multiple sources
        
        # Final confidence is max weight plus diversity bonus
        confidence = min(1.0, max_weight + source_diversity_bonus)
        
        return round(confidence, 2)
    
    async def _update_host_verification_data(
        self,
        media_id: int,
        verified_hosts: List[Dict[str, Any]],
        discovery_sources: List[str],
        confidence_scores: Dict[str, float]
    ):
        """
        Update the database with host verification results.
        """
        try:
            # Prepare update data
            host_names_list = [host['name'] for host in verified_hosts]
            
            update_data = {
                'host_names': host_names_list,
                'host_names_discovery_sources': discovery_sources,
                'host_names_discovery_confidence': confidence_scores,
                'host_names_last_verified': datetime.now(timezone.utc)
            }
            
            # Update media record
            await media_queries.update_media_enrichment_data(media_id, update_data)
            
            logger.info(f"Updated host verification data for media {media_id}")
            
        except Exception as e:
            logger.error(f"Error updating host verification data: {e}", exc_info=True)
    
    async def get_media_needing_verification(self, limit: int = 50) -> List[int]:
        """
        Get list of media IDs that need host name verification.
        """
        try:
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.VERIFICATION_INTERVAL_DAYS)
            
            # Query for media that:
            # 1. Has never been verified (host_names_last_verified IS NULL)
            # 2. OR was verified more than VERIFICATION_INTERVAL_DAYS ago
            # 3. AND has host_names populated
            
            from podcast_outreach.database.connection import get_db_pool
            pool = await get_db_pool()
            
            query = """
                SELECT media_id
                FROM media
                WHERE host_names IS NOT NULL 
                AND array_length(host_names, 1) > 0
                AND (
                    host_names_last_verified IS NULL 
                    OR host_names_last_verified < $1
                )
                ORDER BY 
                    CASE WHEN host_names_last_verified IS NULL THEN 0 ELSE 1 END,
                    host_names_last_verified ASC NULLS FIRST
                LIMIT $2
            """
            
            async with pool.acquire() as conn:
                rows = await conn.fetch(query, cutoff_date, limit)
                return [row['media_id'] for row in rows]
                
        except Exception as e:
            logger.error(f"Error getting media needing verification: {e}", exc_info=True)
            return []
    
    async def run_verification_batch(self, batch_size: int = 20):
        """
        Run host name verification for a batch of media items.
        """
        logger.info(f"Starting host verification batch (size: {batch_size})")
        
        media_ids = await self.get_media_needing_verification(batch_size)
        
        if not media_ids:
            logger.info("No media items need host verification")
            return
        
        logger.info(f"Found {len(media_ids)} media items needing verification")
        
        results = []
        for media_id in media_ids:
            try:
                result = await self.verify_host_names(media_id)
                results.append({
                    "media_id": media_id,
                    "status": "success",
                    "hosts_found": result.get("total_hosts_found", 0),
                    "low_confidence_count": len(result.get("low_confidence_hosts", []))
                })
                
                # Small delay to avoid overwhelming the system
                await asyncio.sleep(0.5)
                
            except Exception as e:
                logger.error(f"Error verifying media {media_id}: {e}")
                results.append({
                    "media_id": media_id,
                    "status": "error",
                    "error": str(e)
                })
        
        # Log summary
        successful = sum(1 for r in results if r["status"] == "success")
        total_low_confidence = sum(r.get("low_confidence_count", 0) for r in results)
        
        logger.info(f"Host verification batch completed: {successful}/{len(results)} successful, "
                   f"{total_low_confidence} low-confidence hosts found")
        
        return results