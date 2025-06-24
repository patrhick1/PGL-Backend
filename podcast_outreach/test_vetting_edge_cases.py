#!/usr/bin/env python3
"""
Test script for vetting system edge cases.
Tests various scenarios to ensure robust vetting behavior.
"""

import asyncio
import logging
import json
import uuid
from datetime import datetime, timezone
from typing import Dict, Any, Optional

from podcast_outreach.database.connection import get_db_pool
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import campaign_media_discoveries as cmd_queries
from podcast_outreach.services.matches.enhanced_vetting_agent import EnhancedVettingAgent
from podcast_outreach.services.matches.enhanced_vetting_orchestrator import EnhancedVettingOrchestrator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VettingEdgeCaseTester:
    """Test various edge cases for the vetting system."""
    
    def __init__(self):
        self.vetting_agent = EnhancedVettingAgent()
        self.test_results = []
    
    async def test_minimal_questionnaire(self):
        """Test vetting with minimal questionnaire data."""
        logger.info("\n=== Test 1: Minimal Questionnaire Data ===")
        
        # Create minimal campaign data
        campaign_data = {
            'campaign_id': uuid.uuid4(),
            'ideal_podcast_description': 'Looking for business podcasts',
            'questionnaire_responses': {}  # Empty questionnaire
        }
        
        # Get a test media ID
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            media_row = await conn.fetchrow("SELECT media_id FROM media LIMIT 1")
            if not media_row:
                logger.error("No media found in database")
                return False
            
            media_id = media_row['media_id']
        
        try:
            result = await self.vetting_agent.vet_match(campaign_data, media_id)
            if result:
                logger.info(f"✓ Minimal questionnaire handled: Score = {result['vetting_score']}")
                self.test_results.append({
                    'test': 'minimal_questionnaire',
                    'status': 'passed',
                    'score': result['vetting_score']
                })
                return True
            else:
                logger.error("✗ Failed to handle minimal questionnaire")
                self.test_results.append({
                    'test': 'minimal_questionnaire',
                    'status': 'failed',
                    'error': 'No result returned'
                })
                return False
        except Exception as e:
            logger.error(f"✗ Exception with minimal questionnaire: {e}")
            self.test_results.append({
                'test': 'minimal_questionnaire',
                'status': 'error',
                'error': str(e)
            })
            return False
    
    async def test_null_questionnaire(self):
        """Test vetting with null questionnaire."""
        logger.info("\n=== Test 2: Null Questionnaire ===")
        
        campaign_data = {
            'campaign_id': uuid.uuid4(),
            'ideal_podcast_description': 'Tech podcast for developers',
            'questionnaire_responses': None  # Null questionnaire
        }
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            media_row = await conn.fetchrow("SELECT media_id FROM media LIMIT 1")
            media_id = media_row['media_id']
        
        try:
            result = await self.vetting_agent.vet_match(campaign_data, media_id)
            if result:
                logger.info(f"✓ Null questionnaire handled: Score = {result['vetting_score']}")
                self.test_results.append({
                    'test': 'null_questionnaire',
                    'status': 'passed',
                    'score': result['vetting_score']
                })
                return True
            else:
                logger.error("✗ Failed to handle null questionnaire")
                self.test_results.append({
                    'test': 'null_questionnaire',
                    'status': 'failed'
                })
                return False
        except Exception as e:
            logger.error(f"✗ Exception with null questionnaire: {e}")
            self.test_results.append({
                'test': 'null_questionnaire',
                'status': 'error',
                'error': str(e)
            })
            return False
    
    async def test_rich_questionnaire(self):
        """Test vetting with comprehensive questionnaire data."""
        logger.info("\n=== Test 3: Rich Questionnaire Data ===")
        
        campaign_data = {
            'campaign_id': uuid.uuid4(),
            'ideal_podcast_description': 'Business and entrepreneurship podcasts with engaged audience',
            'questionnaire_responses': {
                'professionalBio': {
                    'expertiseTopics': 'Digital Marketing, SEO, Content Strategy, Social Media Marketing',
                    'aboutWork': 'I help businesses grow their online presence through strategic digital marketing',
                    'achievements': 'Grew client revenue by 300% in 12 months, Published author on digital marketing'
                },
                'suggestedTopics': {
                    'topics': '1. SEO strategies for 2024\n2. Content marketing best practices\n3. Building brand authority online',
                    'keyStoriesOrMessages': 'Story about helping a startup go from 0 to $1M in revenue through content marketing'
                },
                'atAGlanceStats': {
                    'emailSubscribers': '25k+',
                    'yearsOfExperience': '10+',
                    'keynoteEngagements': '50+'
                },
                'mediaExperience': {
                    'previousAppearances': [
                        {'showName': 'Marketing School'},
                        {'showName': 'Online Marketing Made Easy'}
                    ]
                },
                'promotionPrefs': {
                    'itemsToPromote': 'New book: "Digital Marketing Mastery" and online course',
                    'preferredIntro': 'Digital marketing expert and author'
                },
                'social_enrichment': {
                    'expertise_topics': ['Digital Marketing', 'SEO', 'Content Strategy'],
                    'key_messages': ['ROI-focused marketing', 'Data-driven strategies'],
                    'content_themes': ['Business growth', 'Marketing innovation']
                }
            }
        }
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            media_row = await conn.fetchrow("SELECT media_id FROM media LIMIT 1")
            media_id = media_row['media_id']
        
        try:
            result = await self.vetting_agent.vet_match(campaign_data, media_id)
            if result:
                logger.info(f"✓ Rich questionnaire handled: Score = {result['vetting_score']}")
                logger.info(f"  Checklist items: {len(result['vetting_checklist']['checklist'])}")
                logger.info(f"  Expertise matched: {len(result.get('client_expertise_matched', []))}")
                self.test_results.append({
                    'test': 'rich_questionnaire',
                    'status': 'passed',
                    'score': result['vetting_score'],
                    'checklist_count': len(result['vetting_checklist']['checklist'])
                })
                return True
            else:
                logger.error("✗ Failed to handle rich questionnaire")
                self.test_results.append({
                    'test': 'rich_questionnaire',
                    'status': 'failed'
                })
                return False
        except Exception as e:
            logger.error(f"✗ Exception with rich questionnaire: {e}")
            self.test_results.append({
                'test': 'rich_questionnaire',
                'status': 'error',
                'error': str(e)
            })
            return False
    
    async def test_missing_ideal_description(self):
        """Test vetting without ideal_podcast_description."""
        logger.info("\n=== Test 4: Missing Ideal Podcast Description ===")
        
        campaign_data = {
            'campaign_id': uuid.uuid4(),
            'ideal_podcast_description': None,  # Missing
            'questionnaire_responses': {
                'professionalBio': {
                    'expertiseTopics': 'Finance, Investing, Wealth Management'
                }
            }
        }
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            media_row = await conn.fetchrow("SELECT media_id FROM media LIMIT 1")
            media_id = media_row['media_id']
        
        try:
            result = await self.vetting_agent.vet_match(campaign_data, media_id)
            if result:
                logger.info(f"✓ Missing ideal description handled: Score = {result['vetting_score']}")
                self.test_results.append({
                    'test': 'missing_ideal_description',
                    'status': 'passed',
                    'score': result['vetting_score']
                })
                return True
            else:
                logger.warning("⚠ No result with missing ideal description (expected)")
                self.test_results.append({
                    'test': 'missing_ideal_description',
                    'status': 'expected_none'
                })
                return True
        except Exception as e:
            logger.error(f"✗ Exception with missing ideal description: {e}")
            self.test_results.append({
                'test': 'missing_ideal_description',
                'status': 'error',
                'error': str(e)
            })
            return False
    
    async def test_large_vetting_data(self):
        """Test with very large vetting data to check JSONB limits."""
        logger.info("\n=== Test 5: Large Vetting Data ===")
        
        # Create campaign with lots of expertise topics
        expertise_topics = [f"Topic_{i}" for i in range(100)]
        
        campaign_data = {
            'campaign_id': uuid.uuid4(),
            'ideal_podcast_description': 'A podcast about everything',
            'questionnaire_responses': {
                'professionalBio': {
                    'expertiseTopics': ', '.join(expertise_topics),
                    'aboutWork': 'Expert in many fields ' * 100,  # Large text
                    'achievements': 'Many achievements ' * 50
                },
                'suggestedTopics': {
                    'topics': '\n'.join([f"{i}. Topic about {topic}" for i, topic in enumerate(expertise_topics)])
                }
            }
        }
        
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            media_row = await conn.fetchrow("SELECT media_id FROM media LIMIT 1")
            media_id = media_row['media_id']
        
        try:
            result = await self.vetting_agent.vet_match(campaign_data, media_id)
            if result:
                # Check size of vetting data
                vetting_json = json.dumps(result)
                size_kb = len(vetting_json) / 1024
                logger.info(f"✓ Large data handled: Score = {result['vetting_score']}")
                logger.info(f"  Vetting data size: {size_kb:.2f} KB")
                self.test_results.append({
                    'test': 'large_vetting_data',
                    'status': 'passed',
                    'score': result['vetting_score'],
                    'data_size_kb': size_kb
                })
                return True
            else:
                logger.error("✗ Failed to handle large data")
                self.test_results.append({
                    'test': 'large_vetting_data',
                    'status': 'failed'
                })
                return False
        except Exception as e:
            logger.error(f"✗ Exception with large data: {e}")
            self.test_results.append({
                'test': 'large_vetting_data',
                'status': 'error',
                'error': str(e)
            })
            return False
    
    async def test_concurrent_vetting(self):
        """Test concurrent vetting of same discovery."""
        logger.info("\n=== Test 6: Concurrent Vetting ===")
        
        # Create a test discovery
        campaign_id = uuid.UUID("cdc33aee-b0f8-4460-beec-cce66ea3772c")
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            media_row = await conn.fetchrow("SELECT media_id FROM media LIMIT 1")
            media_id = media_row['media_id']
        
        # Create discovery
        discovery = await cmd_queries.create_or_get_discovery(
            campaign_id, media_id, "concurrent_test"
        )
        
        if not discovery:
            logger.error("Failed to create test discovery")
            return False
        
        # Mark as ready for vetting
        await cmd_queries.update_enrichment_status(discovery['id'], 'completed')
        
        # Try to acquire same discovery concurrently
        async def acquire_discovery():
            discoveries = await cmd_queries.acquire_vetting_work_batch(limit=10)
            return [d for d in discoveries if d['id'] == discovery['id']]
        
        # Run concurrent acquisitions
        results = await asyncio.gather(
            acquire_discovery(),
            acquire_discovery(),
            acquire_discovery(),
            return_exceptions=True
        )
        
        # Count successful acquisitions
        successful_acquisitions = sum(1 for r in results if isinstance(r, list) and len(r) > 0)
        
        if successful_acquisitions == 1:
            logger.info("✓ Concurrent access properly controlled (only 1 acquisition)")
            self.test_results.append({
                'test': 'concurrent_vetting',
                'status': 'passed',
                'acquisitions': successful_acquisitions
            })
            
            # Cleanup
            await cmd_queries.update_vetting_status(discovery['id'], 'failed', 'Test cleanup')
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM campaign_media_discoveries WHERE id = $1",
                    discovery['id']
                )
            return True
        else:
            logger.error(f"✗ Concurrent access issue: {successful_acquisitions} acquisitions")
            self.test_results.append({
                'test': 'concurrent_vetting',
                'status': 'failed',
                'acquisitions': successful_acquisitions
            })
            return False
    
    async def test_ai_service_failure(self):
        """Test behavior when AI service fails."""
        logger.info("\n=== Test 7: AI Service Failure Simulation ===")
        
        # This would require mocking the AI service, so we'll just document it
        logger.info("⚠ AI service failure test requires mocking - skipping")
        self.test_results.append({
            'test': 'ai_service_failure',
            'status': 'skipped',
            'reason': 'Requires mocking infrastructure'
        })
        return True
    
    def print_summary(self):
        """Print test summary."""
        logger.info("\n" + "="*50)
        logger.info("VETTING EDGE CASE TEST SUMMARY")
        logger.info("="*50)
        
        passed = sum(1 for r in self.test_results if r['status'] == 'passed')
        failed = sum(1 for r in self.test_results if r['status'] == 'failed')
        errors = sum(1 for r in self.test_results if r['status'] == 'error')
        skipped = sum(1 for r in self.test_results if r['status'] in ['skipped', 'expected_none'])
        
        logger.info(f"Total Tests: {len(self.test_results)}")
        logger.info(f"Passed: {passed}")
        logger.info(f"Failed: {failed}")
        logger.info(f"Errors: {errors}")
        logger.info(f"Skipped/Expected: {skipped}")
        
        logger.info("\nDetailed Results:")
        for result in self.test_results:
            status_symbol = {
                'passed': '✓',
                'failed': '✗',
                'error': '❌',
                'skipped': '⚠',
                'expected_none': '➖'
            }.get(result['status'], '?')
            
            logger.info(f"{status_symbol} {result['test']}: {result['status']}")
            if 'score' in result:
                logger.info(f"  Score: {result['score']}")
            if 'error' in result:
                logger.info(f"  Error: {result['error']}")
            if 'data_size_kb' in result:
                logger.info(f"  Data size: {result['data_size_kb']:.2f} KB")

async def main():
    """Run all edge case tests."""
    tester = VettingEdgeCaseTester()
    
    # Run all tests
    await tester.test_minimal_questionnaire()
    await tester.test_null_questionnaire()
    await tester.test_rich_questionnaire()
    await tester.test_missing_ideal_description()
    await tester.test_large_vetting_data()
    await tester.test_concurrent_vetting()
    await tester.test_ai_service_failure()
    
    # Print summary
    tester.print_summary()
    
    logger.info("\n✅ Edge case testing completed!")
    logger.info("Review the results above to identify any issues that need addressing.")

if __name__ == "__main__":
    asyncio.run(main())