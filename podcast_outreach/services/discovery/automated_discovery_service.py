"""
Automated Discovery Service
Automatically discovers podcasts for campaigns that are ready, respecting user limits.
"""

import logging
import asyncio
from typing import Dict, Any, List, Optional, Tuple, Set
from datetime import datetime, timezone, timedelta
import uuid
from contextlib import asynccontextmanager

from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import client_profiles as profile_queries
from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.connection import get_db_pool, get_background_task_pool
from podcast_outreach.services.business_logic.enhanced_discovery_workflow import EnhancedDiscoveryWorkflow
from podcast_outreach.services.enrichment.discovery import DiscoveryService
from podcast_outreach.services.events.event_bus import get_event_bus, Event, EventType
from podcast_outreach.services.events.notification_service import get_notification_service

logger = logging.getLogger(__name__)

# Constants for reliability
MAX_RUNTIME_SECONDS = 1500  # 25 minutes max runtime
HEARTBEAT_INTERVAL_SECONDS = 30  # Update heartbeat every 30 seconds
STUCK_THRESHOLD_MINUTES = 5  # Consider stuck if no heartbeat for 5 minutes
KEYWORD_BATCH_SIZE = 5  # Process keywords in batches of 5

class AutomatedDiscoveryService:
    """
    Service to automatically discover podcasts for campaigns that are ready.
    Respects user limits and runs in the background.
    """
    
    def __init__(self):
        self.discovery_service = DiscoveryService()
        self.enhanced_workflow = EnhancedDiscoveryWorkflow()
        self.notification_service = get_notification_service()
        self._heartbeat_task = None
        self._should_stop = False
        
    async def startup_cleanup(self):
        """Clean up any stuck campaigns on startup"""
        try:
            pool = await get_background_task_pool()
            
            # Find and reset stuck or old error campaigns
            stuck_query = """
            UPDATE campaigns
            SET auto_discovery_status = 'pending',
                auto_discovery_error = NULL,
                auto_discovery_progress = '{}'::jsonb
            WHERE (
                -- Reset stuck running campaigns
                (auto_discovery_status = 'running'
                AND (
                    auto_discovery_last_heartbeat IS NULL 
                    OR auto_discovery_last_heartbeat < NOW() - make_interval(mins => $1)
                    OR auto_discovery_last_run < NOW() - make_interval(mins => $2)
                ))
                -- Also reset old error campaigns for retry
                OR (auto_discovery_status = 'error' 
                    AND auto_discovery_last_run < NOW() - INTERVAL '2 hours')
            )
            RETURNING campaign_id, campaign_name, auto_discovery_status as old_status;
            """
            
            async with pool.acquire() as conn:
                stuck_campaigns = await conn.fetch(
                    stuck_query, 
                    STUCK_THRESHOLD_MINUTES,
                    STUCK_THRESHOLD_MINUTES * 2
                )
                
            if stuck_campaigns:
                logger.warning(f"Reset {len(stuck_campaigns)} campaigns on startup")
                for campaign in stuck_campaigns:
                    old_status = campaign['old_status']
                    logger.info(f"Reset campaign from '{old_status}' to 'pending': {campaign['campaign_name']} ({campaign['campaign_id']})")
                    
        except Exception as e:
            logger.error(f"Error in startup cleanup: {e}")
    
    async def _update_heartbeat(self, campaign_id: uuid.UUID):
        """Update heartbeat timestamp periodically"""
        while not self._should_stop:
            try:
                bg_pool = await get_background_task_pool()
                await campaign_queries.update_campaign(campaign_id, {
                    'auto_discovery_last_heartbeat': datetime.now(timezone.utc)
                })
                await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            except Exception as e:
                logger.error(f"Error updating heartbeat: {e}")
                break
    
    @asynccontextmanager
    async def _campaign_processing_context(self, campaign_id: uuid.UUID):
        """Context manager for safe campaign processing with heartbeat"""
        self._should_stop = False
        self._heartbeat_task = None
        
        try:
            # Start heartbeat task
            self._heartbeat_task = asyncio.create_task(self._update_heartbeat(campaign_id))
            
            # Update status to running
            bg_pool = await get_background_task_pool()
            await campaign_queries.update_campaign(campaign_id, {
                'auto_discovery_status': 'running',
                'auto_discovery_last_run': datetime.now(timezone.utc),
                'auto_discovery_last_heartbeat': datetime.now(timezone.utc),
                'auto_discovery_error': None,
                'auto_discovery_progress': {'stage': 'starting', 'keywords_processed': 0}
            })
            
            yield
            
        finally:
            # Stop heartbeat
            self._should_stop = True
            if self._heartbeat_task:
                self._heartbeat_task.cancel()
                try:
                    await self._heartbeat_task
                except asyncio.CancelledError:
                    pass

    async def check_and_run_discoveries(self) -> Dict[str, Any]:
        """
        Main method called by scheduler to check and run automated discoveries.
        """
        results = {
            "campaigns_processed": 0,
            "discoveries_initiated": 0,
            "matches_created": 0,
            "campaigns_paused": 0,
            "errors": []
        }
        
        try:
            # Clean up stuck campaigns first
            await self.startup_cleanup()
            
            # Get campaigns ready for auto-discovery
            ready_campaigns = await self.get_campaigns_ready_for_auto_discovery()
            logger.info(f"Found {len(ready_campaigns)} campaigns ready for auto-discovery")
            
            for campaign in ready_campaigns:
                try:
                    # Process with timeout protection
                    campaign_results = await asyncio.wait_for(
                        self._process_campaign_discovery(campaign),
                        timeout=MAX_RUNTIME_SECONDS
                    )
                    results["campaigns_processed"] += 1
                    results["discoveries_initiated"] += campaign_results.get("discoveries_created", 0)
                    results["matches_created"] += campaign_results.get("matches", 0)
                    if campaign_results.get("paused"):
                        results["campaigns_paused"] += 1
                        
                except asyncio.TimeoutError:
                    campaign_id = campaign['campaign_id']
                    logger.error(f"Campaign {campaign_id} discovery timed out after {MAX_RUNTIME_SECONDS}s")
                    bg_pool = await get_background_task_pool()
                    await campaign_queries.update_campaign(campaign_id, {
                        'auto_discovery_status': 'error',
                        'auto_discovery_error': f'Process timed out after {MAX_RUNTIME_SECONDS} seconds'
                    })
                    results["errors"].append({
                        "campaign_id": str(campaign_id),
                        "error": f"Timeout after {MAX_RUNTIME_SECONDS}s"
                    })
                except Exception as e:
                    logger.error(f"Error processing campaign {campaign['campaign_id']}: {e}")
                    results["errors"].append({
                        "campaign_id": str(campaign['campaign_id']),
                        "error": str(e)
                    })
                    
                # Small delay between campaigns to avoid overload
                await asyncio.sleep(2)
            
            logger.info(f"Auto-discovery check completed: {results}")
            return results
            
        except Exception as e:
            logger.error(f"Error in automated discovery check: {e}")
            results["errors"].append({"general_error": str(e)})
            return results
    
    async def get_campaigns_ready_for_auto_discovery(self) -> List[Dict[str, Any]]:
        """
        Get campaigns that are ready for automated discovery.
        Includes client profile info to check limits.
        """
        query = """
        SELECT 
            c.*,
            cp.person_id,
            cp.plan_type,
            cp.current_weekly_matches,
            cp.weekly_match_allowance,
            cp.auto_discovery_matches_this_week,
            CASE 
                WHEN cp.plan_type = 'free' THEN 50 - cp.current_weekly_matches
                ELSE 200 - COALESCE(cp.auto_discovery_matches_this_week, 0)
            END as remaining_auto_matches
        FROM campaigns c
        JOIN people p ON c.person_id = p.person_id
        JOIN client_profiles cp ON p.person_id = cp.person_id
        WHERE c.ideal_podcast_description IS NOT NULL
        AND c.ideal_podcast_description != ''
        AND (c.campaign_keywords IS NOT NULL AND array_length(c.campaign_keywords, 1) > 0)
        AND c.auto_discovery_enabled = TRUE
        AND (
            -- Include campaigns that are not currently running
            c.auto_discovery_status != 'running' 
            OR c.auto_discovery_status IS NULL
            -- Also include error campaigns that haven't been tried in the last hour
            OR (c.auto_discovery_status = 'error' 
                AND (c.auto_discovery_last_run IS NULL 
                     OR c.auto_discovery_last_run < NOW() - INTERVAL '1 hour'))
        )
        AND (
            -- Free users: still have weekly match allowance
            (cp.plan_type = 'free' AND cp.current_weekly_matches < 50)
            OR 
            -- Paid users: under 200 auto-discoveries this week
            (cp.plan_type != 'free' AND COALESCE(cp.auto_discovery_matches_this_week, 0) < 200)
        )
        ORDER BY 
            -- Prioritize paid users
            CASE WHEN cp.plan_type != 'free' THEN 0 ELSE 1 END,
            -- Then by least recent auto-discovery
            c.auto_discovery_last_run ASC NULLS FIRST,
            c.created_at DESC
        LIMIT 10; -- Process up to 10 campaigns per run
        """
        pool = await get_background_task_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            return [dict(row) for row in rows]
    
    async def _process_campaign_discovery(self, campaign: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process discovery for a single campaign with reliability improvements.
        """
        campaign_id = campaign['campaign_id']
        
        async with self._campaign_processing_context(campaign_id):
            try:
                return await self._process_campaign_discovery_inner(campaign)
            except Exception as e:
                logger.error(f"Error in campaign discovery: {e}")
                bg_pool = await get_background_task_pool()
                await campaign_queries.update_campaign(campaign_id, {
                    'auto_discovery_status': 'error',
                    'auto_discovery_error': str(e)
                })
                raise
    
    async def _process_campaign_discovery_inner(self, campaign: Dict[str, Any]) -> Dict[str, Any]:
        """
        Inner processing logic with progress tracking.
        Strategy:
        1. Fetch ALL podcasts for ALL keywords (maximize media table growth)
        2. Create campaign_media_discoveries records in batches (50 initially)
        3. Process through enrichment and vetting
        4. If matches < limit, add more discoveries and continue
        """
        campaign_id = campaign['campaign_id']
        person_id = campaign['person_id']
        plan_type = campaign['plan_type']
        remaining_matches = campaign['remaining_auto_matches']
        keywords = campaign.get('campaign_keywords', [])
        
        logger.info(f"Processing auto-discovery for campaign {campaign_id} "
                   f"(plan: {plan_type}, remaining matches: {remaining_matches})")
        
        results = {
            "total_podcasts_found": 0,
            "discoveries_created": 0,
            "matches": 0,
            "paused": False
        }
        
        try:
            # Process keywords in batches for better progress tracking
            all_discovered_media = []
            
            for i in range(0, len(keywords), KEYWORD_BATCH_SIZE):
                if self._should_stop:
                    logger.info(f"Stopping discovery for campaign {campaign_id} (interrupted)")
                    break
                    
                keyword_batch = keywords[i:i + KEYWORD_BATCH_SIZE]
                batch_num = i // KEYWORD_BATCH_SIZE + 1
                total_batches = (len(keywords) + KEYWORD_BATCH_SIZE - 1) // KEYWORD_BATCH_SIZE
                
                logger.info(f"Processing keyword batch {batch_num}/{total_batches} for campaign {campaign_id}")
                
                # Update progress
                bg_pool = await get_background_task_pool()
                await campaign_queries.update_campaign(campaign_id, {
                    'auto_discovery_progress': {
                        'stage': 'fetching_podcasts',
                        'keywords_processed': i,
                        'total_keywords': len(keywords),
                        'current_batch': batch_num,
                        'total_batches': total_batches
                    }
                })
                
                # Fetch podcasts for this batch
                batch_media = await self._fetch_podcasts_for_keywords(campaign_id, keyword_batch)
                all_discovered_media.extend(batch_media)
                
                logger.info(f"Batch {batch_num} found {len(batch_media)} podcasts")
            
            results["total_podcasts_found"] = len(all_discovered_media)
            
            logger.info(f"Found {len(all_discovered_media)} total podcasts for campaign {campaign_id}")
            
            if not all_discovered_media:
                logger.warning(f"No podcasts found for campaign {campaign_id}")
                bg_pool = await get_background_task_pool()
                await campaign_queries.update_campaign(campaign_id, {
                    'auto_discovery_status': 'completed'
                })
                return results
            
            # STEP 2: Process in batches with progressive discovery creation
            batch_size = 50  # Initial batch of discoveries to create
            processed_media_ids = set()
            
            while results["matches"] < remaining_matches and len(processed_media_ids) < len(all_discovered_media):
                # Get next batch of media to process
                batch_to_process = []
                for media_id, keyword in all_discovered_media:
                    if media_id not in processed_media_ids:
                        batch_to_process.append((media_id, keyword))
                        if len(batch_to_process) >= batch_size:
                            break
                
                if not batch_to_process:
                    logger.info(f"No more media to process for campaign {campaign_id}")
                    break
                
                logger.info(f"Creating {len(batch_to_process)} discovery records for campaign {campaign_id}")
                
                # Create discovery records for this batch
                discovery_results = []
                # Get background pool for queries
                bg_pool = await get_background_task_pool()
                for media_id, keyword in batch_to_process:
                    # Check if discovery already exists
                    exists = await media_queries.check_campaign_media_discovery_exists(campaign_id, media_id, pool=bg_pool)
                    if not exists:
                        discovery_created = await media_queries.track_campaign_media_discovery(campaign_id, media_id, keyword, pool=bg_pool)
                        if discovery_created:
                            discovery_results.append((media_id, keyword))
                            results["discoveries_created"] += 1
                    processed_media_ids.add(media_id)
                
                logger.info(f"Created {len(discovery_results)} new discovery records")
                
                # Update progress for discovery creation
                bg_pool = await get_background_task_pool()
                await campaign_queries.update_campaign(campaign_id, {
                    'auto_discovery_progress': {
                        'stage': 'creating_discoveries',
                        'processed': len(processed_media_ids),
                        'total': len(all_discovered_media),
                        'matches_created': results["matches"]
                    }
                })
                
                # Process this batch through enrichment and vetting
                for media_id, discovery_keyword in discovery_results:
                    # Check if we've reached match limit
                    if plan_type == 'free' and results["matches"] >= remaining_matches:
                        logger.info(f"Reached match limit for free campaign {campaign_id}")
                        results["paused"] = True
                        break
                    elif plan_type != 'free' and results["matches"] >= remaining_matches:
                        logger.info(f"Reached weekly auto-discovery limit for campaign {campaign_id}")
                        results["paused"] = True
                        break
                    
                    # Run the enhanced pipeline
                    pipeline_result = await self.enhanced_workflow.process_discovery(
                        campaign_id=campaign_id,
                        media_id=media_id,
                        discovery_keyword=discovery_keyword,
                        is_client=True,
                        person_id=person_id
                    )
                    
                    # Check if a match was created
                    if pipeline_result.get('match_id'):
                        results["matches"] += 1
                        
                        # Update auto-discovery match count for paid users
                        if plan_type != 'free':
                            await self._increment_auto_discovery_count(person_id, 1)
                
                if results["paused"]:
                    break
                
                # If we haven't reached match limit, continue with next batch
                logger.info(f"Processed batch. Matches so far: {results['matches']}/{remaining_matches}")
            
            # Update final status with progress
            new_status = 'paused' if results["paused"] else 'completed'
            bg_pool = await get_background_task_pool()
            await campaign_queries.update_campaign(campaign_id, {
                'auto_discovery_status': new_status,
                'auto_discovery_progress': {
                    'stage': 'completed',
                    'total_podcasts': results["total_podcasts_found"],
                    'discoveries_created': results["discoveries_created"],
                    'matches_created': results["matches"]
                }
            })
            
            # Send notification with detailed results
            if results["matches"] > 0 or results["discoveries_created"] > 0:
                await self.notification_service.send_client_event(
                    person_id,
                    "client.auto_discovery.matches_found",
                    {
                        "campaign_id": str(campaign_id),
                        "campaign_name": campaign.get('campaign_name'),
                        "total_podcasts_found": results["total_podcasts_found"],
                        "discoveries_created": results["discoveries_created"],
                        "matches_created": results["matches"],
                        "status": new_status
                    }
                )
            
            logger.info(f"Auto-discovery completed for campaign {campaign_id}: "
                       f"{results['total_podcasts_found']} podcasts found, "
                       f"{results['discoveries_created']} discoveries created, "
                       f"{results['matches']} matches")
            
            return results
            
        except Exception as e:
            # Status will be updated by context manager
            logger.error(f"Error in campaign auto-discovery: {e}")
            raise
    
    async def _fetch_all_podcasts_for_campaign(self, campaign_id: uuid.UUID) -> List[Tuple[int, str]]:
        """
        Fetch ALL podcasts for ALL keywords without creating discovery records.
        This maximizes our media table collection.
        Returns list of (media_id, keyword) tuples.
        """
        bg_pool = await get_background_task_pool()
        campaign = await campaign_queries.get_campaign_by_id(campaign_id, pool=bg_pool)
        if not campaign:
            return []
        
        keywords = campaign.get('campaign_keywords', [])
        if not keywords:
            logger.warning(f"No keywords for campaign {campaign_id}")
            return []
        
        return await self._fetch_podcasts_for_keywords(campaign_id, keywords)
    
    async def _fetch_podcasts_for_keywords(self, campaign_id: uuid.UUID, keywords: List[str]) -> List[Tuple[int, str]]:
        """
        Fetch ALL podcasts for ALL keywords without creating discovery records.
        This maximizes our media table collection.
        Returns list of (media_id, keyword) tuples.
        """
        # Use MediaFetcher directly to fetch and upsert all podcasts
        from podcast_outreach.services.media.podcast_fetcher import MediaFetcher
        
        if not keywords:
            return []
        
        # Get background pool for MediaFetcher
        bg_pool = await get_background_task_pool()
        media_fetcher = MediaFetcher(db_pool=bg_pool)
        all_media = []
        processed_identifiers = set()
        
        try:
            for keyword in keywords:
                keyword = keyword.strip()
                if not keyword:
                    continue
                
                logger.info(f"Fetching podcasts for keyword '{keyword}'")
                
                # Generate category IDs for better search results
                listennotes_genre_ids = await media_fetcher._generate_genre_ids_async(keyword, str(campaign_id))
                podscan_category_ids = await media_fetcher._generate_podscan_category_ids_async(keyword, str(campaign_id))
                
                # Search ListenNotes (no limits)
                ln_media = await media_fetcher._search_and_track_discoveries(
                    'ListenNotes', keyword, campaign_id, processed_identifiers,
                    listennotes_genre_ids=listennotes_genre_ids
                )
                for media_id, _, _ in ln_media:
                    all_media.append((media_id, keyword))
                
                # Search Podscan (no limits)
                ps_media = await media_fetcher._search_and_track_discoveries(
                    'PodscanFM', keyword, campaign_id, processed_identifiers,
                    podscan_category_ids=podscan_category_ids
                )
                for media_id, _, _ in ps_media:
                    all_media.append((media_id, keyword))
                
                logger.info(f"Found {len(ln_media) + len(ps_media)} podcasts for keyword '{keyword}'")
                
                # Small delay between keywords
                await asyncio.sleep(2)
        
        finally:
            media_fetcher.cleanup()
        
        # Remove duplicates while preserving order
        seen = set()
        unique_media = []
        for media_id, keyword in all_media:
            if media_id not in seen:
                seen.add(media_id)
                unique_media.append((media_id, keyword))
        
        logger.info(f"Total unique podcasts found for campaign {campaign_id}: {len(unique_media)}")
        return unique_media
    
    async def _increment_auto_discovery_count(self, person_id: int, count: int):
        """
        Increment auto-discovery count for paid users.
        """
        query = """
        UPDATE client_profiles
        SET auto_discovery_matches_this_week = 
            COALESCE(auto_discovery_matches_this_week, 0) + $1,
            updated_at = NOW()
        WHERE person_id = $2
        """
        pool = await get_background_task_pool()
        async with pool.acquire() as conn:
            await conn.execute(query, count, person_id)
    
    async def reset_weekly_auto_discovery_counts(self):
        """
        Reset weekly auto-discovery counts for paid users.
        Called weekly by scheduler.
        """
        query = """
        UPDATE client_profiles
        SET auto_discovery_matches_this_week = 0,
            last_auto_discovery_reset = NOW(),
            updated_at = NOW()
        WHERE plan_type != 'free'
        AND last_auto_discovery_reset < NOW() - INTERVAL '7 days'
        RETURNING person_id;
        """
        pool = await get_background_task_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(query)
            count = len(rows)
            logger.info(f"Reset auto-discovery counts for {count} paid users")
            return count
    
    async def process_single_campaign(self, campaign_id: uuid.UUID) -> Dict[str, Any]:
        """
        Process auto-discovery for a single campaign immediately.
        Used when campaign becomes ready (questionnaire completed).
        """
        # Get campaign with profile info
        query = """
        SELECT 
            c.*,
            cp.person_id,
            cp.plan_type,
            cp.current_weekly_matches,
            cp.weekly_match_allowance,
            cp.auto_discovery_matches_this_week,
            CASE 
                WHEN cp.plan_type = 'free' THEN 50 - cp.current_weekly_matches
                ELSE 200 - COALESCE(cp.auto_discovery_matches_this_week, 0)
            END as remaining_auto_matches
        FROM campaigns c
        JOIN people p ON c.person_id = p.person_id
        JOIN client_profiles cp ON p.person_id = cp.person_id
        WHERE c.campaign_id = $1
        AND c.auto_discovery_enabled = TRUE;
        """
        pool = await get_background_task_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(query, campaign_id)
            if row:
                campaign = dict(row)
                try:
                    return await asyncio.wait_for(
                        self._process_campaign_discovery(campaign),
                        timeout=MAX_RUNTIME_SECONDS
                    )
                except asyncio.TimeoutError:
                    logger.error(f"Single campaign discovery timed out after {MAX_RUNTIME_SECONDS}s")
                    bg_pool = await get_background_task_pool()
                    await campaign_queries.update_campaign(campaign_id, {
                        'auto_discovery_status': 'error',
                        'auto_discovery_error': f'Process timed out after {MAX_RUNTIME_SECONDS} seconds'
                    })
                    return {"error": f"Process timed out after {MAX_RUNTIME_SECONDS} seconds"}
            else:
                logger.warning(f"Campaign {campaign_id} not found or auto-discovery disabled")
                return {"error": "Campaign not found or auto-discovery disabled"}