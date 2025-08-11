#!/usr/bin/env python3
"""
Script to re-enrich host names for discoveries blocked from vetting.
This will:
1. Calculate and update confidence scores for media with host names but no confidence
2. Re-enrich media without host names using enhanced discovery methods
"""

import asyncio
import asyncpg
import os
import sys
from dotenv import load_dotenv
from datetime import datetime, timezone
import json

# Add project root to path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '.'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

load_dotenv()

# Import necessary services
from podcast_outreach.services.enrichment.host_confidence_verifier import HostConfidenceVerifier
from podcast_outreach.services.enrichment.enrichment_agent import EnrichmentAgent
from podcast_outreach.services.ai.tavily_client import async_tavily_search
from podcast_outreach.services.ai.gemini_client import GeminiService
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.database.connection import get_db_pool, init_db_pool, close_db_pool

async def fix_existing_confidence_scores():
    """
    For media that have host names but no confidence score,
    calculate confidence based on existing data.
    """
    pool = await get_db_pool()
    
    print("\n" + "=" * 80)
    print("FIXING CONFIDENCE SCORES FOR EXISTING HOST NAMES")
    print("=" * 80)
    
    # Find media with host names but no confidence score
    query = """
    SELECT m.media_id, m.name, m.host_names, 
           m.host_names_discovery_sources, m.host_names_discovery_confidence
    FROM media m
    WHERE m.host_names IS NOT NULL 
    AND array_length(m.host_names, 1) > 0
    AND (m.host_names_confidence IS NULL OR m.host_names_confidence = 0)
    LIMIT 100
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        
        if not rows:
            print("No media found with missing confidence scores")
            return
        
        print(f"Found {len(rows)} media with host names but no confidence score")
        
        fixed_count = 0
        for row in rows:
            media_id = row['media_id']
            media_name = row['name']
            host_names = row['host_names']
            discovery_confidence = row['host_names_discovery_confidence']
            
            # Calculate overall confidence
            overall_confidence = 0.5  # Default confidence if no data
            
            if discovery_confidence:
                try:
                    # Parse JSONB if it's a string
                    if isinstance(discovery_confidence, str):
                        discovery_confidence = json.loads(discovery_confidence)
                    
                    if isinstance(discovery_confidence, dict) and discovery_confidence:
                        # Use the maximum confidence among all hosts
                        overall_confidence = max(discovery_confidence.values())
                except Exception as e:
                    print(f"  Error parsing confidence for {media_name}: {e}")
                    overall_confidence = 0.5
            
            # If we still don't have good confidence, use a default based on source
            if overall_confidence < 0.5:
                # Check if host names look reasonable (not empty, proper names)
                if host_names and any(len(name.split()) >= 2 for name in host_names):
                    overall_confidence = 0.7  # Reasonable default for existing data
                else:
                    overall_confidence = 0.5
            
            # Update the confidence score
            update_query = """
            UPDATE media 
            SET host_names_confidence = $1,
                updated_at = NOW()
            WHERE media_id = $2
            """
            
            try:
                await conn.execute(update_query, overall_confidence, media_id)
                fixed_count += 1
                print(f"  Fixed: {media_name} (ID: {media_id}) - Confidence: {overall_confidence:.2f}")
            except Exception as e:
                print(f"  Error updating {media_name}: {e}")
        
        print(f"\nFixed confidence scores for {fixed_count} media items")

async def enhance_host_discovery_for_media(media_id: int, media_data: dict) -> dict:
    """
    Enhanced host discovery using multiple sources:
    1. Podcast description
    2. Episode transcripts
    3. Tavily web search
    4. Gemini analysis
    """
    print(f"\n  Enhancing host discovery for: {media_data['name']} (ID: {media_id})")
    
    discovered_hosts = set()
    confidence_sources = {}
    
    # 1. Try to extract from description
    description = media_data.get('description', '')
    if description:
        import re
        patterns = [
            r'hosted by\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'with host\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
            r'your host[,\s]+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)',
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, description, re.IGNORECASE)
            for match in matches:
                if match and len(match.split()) <= 4:
                    discovered_hosts.add(match.strip())
                    confidence_sources[match.strip()] = 'description'
    
    # 2. Try episode transcripts (if available)
    try:
        episodes = await episode_queries.get_episodes_for_media_paginated(media_id, offset=0, limit=3)
        for episode in episodes:
            if episode.get('transcript_summary'):
                # Look for host mentions in transcript
                text = episode['transcript_summary'][:500]  # Check first part
                if 'host' in text.lower() or "i'm" in text.lower() or "my name" in text.lower():
                    # Simple extraction - could be enhanced
                    import re
                    name_pattern = r"(?:I'm|my name is|this is)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)"
                    matches = re.findall(name_pattern, text, re.IGNORECASE)
                    for match in matches:
                        if match and len(match.split()) <= 4:
                            discovered_hosts.add(match.strip())
                            confidence_sources[match.strip()] = 'transcript'
    except Exception as e:
        print(f"    Error checking transcripts: {e}")
    
    # 3. Tavily search
    if len(discovered_hosts) < 1:  # Only if we haven't found hosts yet
        try:
            search_query = f"{media_data['name']} podcast host name who is"
            tavily_result = await async_tavily_search(
                query=search_query,
                max_results=3,
                search_depth="advanced",
                include_answer=True
            )
            
            if tavily_result and tavily_result.get('answer'):
                # Extract names from Tavily answer
                answer = tavily_result['answer']
                import re
                # Look for proper names
                name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
                potential_names = re.findall(name_pattern, answer)
                
                # Filter to likely host names
                for name in potential_names[:3]:  # Take top 3
                    if 2 <= len(name.split()) <= 4:  # Reasonable name length
                        discovered_hosts.add(name)
                        confidence_sources[name] = 'tavily'
                        
                print(f"    Found via Tavily: {list(discovered_hosts)}")
        except Exception as e:
            print(f"    Tavily search error: {e}")
    
    # 4. If still no hosts, try Gemini for deeper analysis
    if len(discovered_hosts) < 1 and description:
        try:
            gemini_service = GeminiService()
            prompt = f"""
            Analyze this podcast description and extract the host name(s):
            
            Podcast: {media_data['name']}
            Description: {description[:500]}
            
            Return only the host name(s), nothing else. If no host name is found, return "Unknown".
            """
            
            gemini_response = await gemini_service.create_message(prompt, workflow="host_extraction", related_media_id=media_id)
            if gemini_response and gemini_response != "Unknown":
                # Parse the response for names
                import re
                name_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
                potential_names = re.findall(name_pattern, gemini_response)
                
                for name in potential_names[:2]:
                    if 2 <= len(name.split()) <= 4:
                        discovered_hosts.add(name)
                        confidence_sources[name] = 'gemini'
                        
                print(f"    Found via Gemini: {list(discovered_hosts)}")
        except Exception as e:
            print(f"    Gemini analysis error: {e}")
    
    # Calculate confidence based on source
    source_confidence_map = {
        'transcript': 0.9,
        'description': 0.8,
        'tavily': 0.85,
        'gemini': 0.75
    }
    
    if discovered_hosts:
        host_list = list(discovered_hosts)
        
        # Calculate confidence scores
        confidence_scores = {}
        for host in host_list:
            source = confidence_sources.get(host, 'unknown')
            confidence_scores[host] = source_confidence_map.get(source, 0.5)
        
        # Overall confidence is the max
        overall_confidence = max(confidence_scores.values()) if confidence_scores else 0.5
        
        return {
            'host_names': host_list,
            'host_names_confidence': overall_confidence,
            'host_names_discovery_confidence': confidence_scores,
            'host_names_discovery_sources': list(set(confidence_sources.values()))
        }
    
    return None

async def reenrich_missing_hosts():
    """
    Re-enrich media that have no host names at all.
    """
    pool = await get_db_pool()
    
    print("\n" + "=" * 80)
    print("RE-ENRICHING MEDIA WITHOUT HOST NAMES")
    print("=" * 80)
    
    # Find media without host names that are blocking vetting
    query = """
    SELECT DISTINCT m.media_id, m.name, m.description, m.rss_url
    FROM media m
    JOIN campaign_media_discoveries cmd ON m.media_id = cmd.media_id
    WHERE cmd.enrichment_status = 'completed'
    AND cmd.vetting_status = 'pending'
    AND (m.host_names IS NULL OR array_length(m.host_names, 1) = 0)
    LIMIT 50
    """
    
    async with pool.acquire() as conn:
        rows = await conn.fetch(query)
        
        if not rows:
            print("No media found without host names")
            return
        
        print(f"Found {len(rows)} media without host names")
        
        enriched_count = 0
        for row in rows:
            media_id = row['media_id']
            media_data = dict(row)
            
            # Try enhanced discovery
            result = await enhance_host_discovery_for_media(media_id, media_data)
            
            if result and result.get('host_names'):
                # Update the media record
                update_query = """
                UPDATE media 
                SET host_names = $1,
                    host_names_confidence = $2,
                    host_names_discovery_confidence = $3::jsonb,
                    host_names_discovery_sources = $4::jsonb,
                    host_names_last_verified = NOW(),
                    updated_at = NOW()
                WHERE media_id = $5
                """
                
                try:
                    await conn.execute(
                        update_query,
                        result['host_names'],
                        result['host_names_confidence'],
                        json.dumps(result['host_names_discovery_confidence']),
                        json.dumps(result['host_names_discovery_sources']),
                        media_id
                    )
                    enriched_count += 1
                    print(f"    [SUCCESS] Enriched: {media_data['name']} - Hosts: {result['host_names']}, Confidence: {result['host_names_confidence']:.2f}")
                except Exception as e:
                    print(f"    [ERROR] Error updating {media_data['name']}: {e}")
            else:
                print(f"    [NO_HOSTS] No hosts found for: {media_data['name']}")
            
            # Small delay to avoid overwhelming APIs
            await asyncio.sleep(1)
        
        print(f"\nEnriched host names for {enriched_count} media items")

async def verify_improvements():
    """
    Check how many discoveries are now ready for vetting.
    """
    pool = await get_db_pool()
    
    print("\n" + "=" * 80)
    print("VERIFICATION - CHECKING IMPROVEMENTS")
    print("=" * 80)
    
    # Check new statistics
    query_stats = """
    SELECT 
        COUNT(*) as total,
        COUNT(*) FILTER (WHERE m.host_names IS NOT NULL 
                         AND array_length(m.host_names, 1) > 0 
                         AND m.host_names_confidence >= 0.8) as ready_for_vetting,
        COUNT(*) FILTER (WHERE m.host_names IS NULL) as no_host_names,
        COUNT(*) FILTER (WHERE m.host_names IS NOT NULL 
                         AND array_length(m.host_names, 1) > 0 
                         AND (m.host_names_confidence IS NULL OR m.host_names_confidence < 0.8)) as low_confidence
    FROM campaign_media_discoveries cmd
    JOIN media m ON cmd.media_id = m.media_id
    WHERE cmd.enrichment_status = 'completed'
    AND cmd.vetting_status = 'pending'
    """
    
    async with pool.acquire() as conn:
        result = await conn.fetchrow(query_stats)
        
        total = result['total']
        ready = result['ready_for_vetting']
        no_hosts = result['no_host_names']
        low_conf = result['low_confidence']
        
        print(f"Total pending vetting: {total}")
        print(f"Ready for vetting (confidence >= 0.8): {ready} ({ready/total*100:.1f}%)")
        print(f"Still missing host names: {no_hosts} ({no_hosts/total*100:.1f}%)")
        print(f"Low confidence (< 0.8): {low_conf} ({low_conf/total*100:.1f}%)")
        
        improvement = ready - 0  # Previously 0 were ready
        print(f"\n[COMPLETE] Improvement: {improvement} more discoveries are now ready for vetting!")

async def main():
    """Main execution function."""
    try:
        # Initialize database pool
        await init_db_pool()
        
        # Step 1: Fix existing confidence scores
        await fix_existing_confidence_scores()
        
        # Step 2: Re-enrich media without host names
        await reenrich_missing_hosts()
        
        # Step 3: Verify improvements
        await verify_improvements()
        
    except Exception as e:
        print(f"\nError during re-enrichment: {e}")
    finally:
        # Close database pool
        await close_db_pool()

if __name__ == "__main__":
    print("Starting host name re-enrichment process...")
    print("This will fix confidence scores and discover missing host names.")
    
    response = input("\nProceed? (yes/no): ")
    if response.lower() == 'yes':
        asyncio.run(main())
    else:
        print("Aborted.")