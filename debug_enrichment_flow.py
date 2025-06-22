#!/usr/bin/env python3
"""
Debug script to trace the exact flow from Tavily → Gemini → Pydantic
to find where the social URL contamination is being introduced.
"""

import asyncio
import sys
import os
import json

# Add the project root to the path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__)))
sys.path.insert(0, project_root)

from dotenv import load_dotenv
load_dotenv()

async def debug_enrichment_flow():
    """Debug the enrichment flow step by step."""
    
    print("=== DEBUGGING ENRICHMENT FLOW ===\n")
    
    # Test with "The CM Mentors Podcast" which has contaminated URLs in the database
    test_podcast = {
        "media_id": 2,
        "name": "The CM Mentors Podcast", 
        "api_id": "pd_gokljvnrey3537ma",
        "description": "The CM Mentors Podcast is an informative, entertaining, and interactive experience for construction managers by construction managers."
    }
    
    try:
        # Step 1: Test raw Tavily response
        print("[STEP 1] Testing raw Tavily response...")
        from podcast_outreach.services.ai.tavily_client import async_tavily_search
        
        search_query = f"Podcast Twitter URL for the podcast '{test_podcast['name']}'"
        print(f"Query: {search_query}")
        
        tavily_response = await async_tavily_search(search_query, max_results=2, search_depth="advanced", include_answer=True)
        
        print("\n[TAVILY RAW RESPONSE]:")
        if tavily_response:
            print(f"Answer: {tavily_response.get('answer', 'No answer')}")
            print(f"Results count: {len(tavily_response.get('results', []))}")
            
            # Check for contamination in raw response
            contaminated_urls = [
                "twitter.com/masterofnonepod",
                "linkedin.com/company/none-of-your-business-podcast",
                "youtube.com/@noonecanknowaboutthispodca"
            ]
            
            found_contamination = []
            response_text = str(tavily_response).lower()
            for url in contaminated_urls:
                if url in response_text:
                    found_contamination.append(url)
            
            if found_contamination:
                print(f"[CONTAMINATION IN TAVILY] Found: {found_contamination}")
            else:
                print("[TAVILY CLEAN] No contamination found in raw Tavily response")
        else:
            print("No response from Tavily")
            return
        
        # Step 2: Test the enrichment agent's processing
        print("\n[STEP 2] Testing enrichment agent processing...")
        
        from podcast_outreach.services.ai.gemini_client import GeminiService
        from podcast_outreach.services.enrichment.social_scraper import SocialDiscoveryService
        from podcast_outreach.services.enrichment.data_merger import DataMergerService
        from podcast_outreach.services.enrichment.enrichment_agent import EnrichmentAgent
        
        # Initialize services
        gemini_service = GeminiService()
        social_discovery_service = SocialDiscoveryService()
        data_merger = DataMergerService()
        enrichment_agent = EnrichmentAgent(gemini_service, social_discovery_service, data_merger)
        
        # Step 3: Test the _discover_initial_info_with_gemini_and_tavily method
        print("\n[STEP 3] Testing Gemini+Tavily discovery...")
        
        # Patch the enrichment agent to capture intermediate data
        original_method = enrichment_agent._discover_initial_info_with_gemini_and_tavily
        
        async def debug_discover_method(initial_data):
            print(f"[DEBUG] Starting discovery for: {initial_data.get('name')}")
            
            # Call the original method but capture intermediate steps
            podcast_name = initial_data.get('name') or initial_data.get('title') or 'Unknown Podcast'
            print(f"[DEBUG] Podcast name resolved to: {podcast_name}")
            
            # Test ALL discovery targets like the real enrichment process
            discovery_targets = [
                ("Host Names", 'host_names', 'host_names', False),
                ("Podcast Twitter URL", 'podcast_twitter_url', 'podcast_twitter_url', False),
                ("Podcast LinkedIn URL", 'podcast_linkedin_url', 'podcast_linkedin_url', False),
                ("Podcast Instagram URL", 'podcast_instagram_url', 'podcast_instagram_url', False),
                ("Podcast Facebook URL", 'podcast_facebook_url', 'podcast_facebook_url', False),
                ("Podcast YouTube URL", 'podcast_youtube_url', 'podcast_youtube_url', False),
                ("Podcast TikTok URL", 'podcast_tiktok_url', 'podcast_tiktok_url', False),
                ("Primary Host LinkedIn URL", 'host_linkedin_url', 'host_linkedin_url', True),
                ("Primary Host Twitter URL", 'host_twitter_url', 'host_twitter_url', True)
            ]
            
            found_info_texts = [f"Original Podcast Name: {podcast_name}"]
            
            for target_name, initial_key, gemini_key, needs_host_context in discovery_targets:
                search_query = f"{target_name} for the podcast '{podcast_name}'"
                print(f"[DEBUG] Search query: {search_query}")
                
                tavily_response = await async_tavily_search(search_query, max_results=2, search_depth="advanced", include_answer=True)
                
                search_output_for_gemini = f"Search Query for {target_name}: {search_query}\n"
                if tavily_response and not tavily_response.get("error"):
                    if tavily_response.get("answer"): 
                        search_output_for_gemini += f"Tavily Answer: {tavily_response['answer']}\n"
                        print(f"[DEBUG] Tavily answer: {tavily_response['answer']}")
                    elif tavily_response.get("results"): 
                        snippets = "\n".join([f"- {res.get('title', '')}: {res.get('content', '')[:200]}... (URL: {res.get('url')})" for res in tavily_response["results"]])
                        search_output_for_gemini += f"Tavily Snippets:\n{snippets}\n"
                        print(f"[DEBUG] Tavily snippets: {snippets[:300]}...")
                    else: 
                        search_output_for_gemini += "Tavily: No specific answer or results found.\n"
                else: 
                    error_msg = tavily_response.get('error', 'Unknown error') if tavily_response else 'No response (rate limited or failed)'
                    search_output_for_gemini += f"Tavily: Search failed or error: {error_msg}\n"
                
                found_info_texts.append(search_output_for_gemini)
                
                # Add a small delay like the real enrichment process
                await asyncio.sleep(0.25)
            
            combined_text_for_parsing = "\n\n---\n\n".join(found_info_texts)
            print(f"\n[DEBUG] Combined text for Gemini (length {len(combined_text_for_parsing)}):")
            print("=" * 60)
            print(combined_text_for_parsing)
            print("=" * 60)
            
            # Check for contamination in combined text
            found_contamination = []
            combined_text_lower = combined_text_for_parsing.lower()
            for url in contaminated_urls:
                if url in combined_text_lower:
                    found_contamination.append(url)
            
            if found_contamination:
                print(f"[CONTAMINATION IN COMBINED TEXT] Found: {found_contamination}")
            else:
                print("[COMBINED TEXT CLEAN] No contamination found")
            
            # Test Gemini structured output
            print(f"\n[STEP 4] Testing Gemini structured output...")
            
            from podcast_outreach.database.models.llm_outputs import GeminiPodcastEnrichment
            
            # Get the schema
            schema_dict = GeminiPodcastEnrichment.model_json_schema()
            schema_json_string = json.dumps(schema_dict, indent=2)
            escaped_schema_json_string = schema_json_string.replace("{", "{{").replace("}", "}}")
            
            final_parser_prompt = f"""You are an expert data extraction assistant.
Based *only* on the information within the 'Provided Text' section below, extract the required information and structure it according to the 'JSON Schema'.

Key Instructions:
1. If specific information for a field is not explicitly found in the 'Provided Text', use null for that field. Do not guess or infer.
2. For social media URLs, look for full, valid HTTP/HTTPS links.
3. If the text explicitly states "unable to find", then use null.

Provided Text:
---
{combined_text_for_parsing}
---

JSON Schema:
```json
{escaped_schema_json_string}
```
"""
            
            print(f"[DEBUG] Gemini prompt length: {len(final_parser_prompt)}")
            
            structured_output = await gemini_service.get_structured_data(
                prompt_template_str=final_parser_prompt,
                user_query=combined_text_for_parsing,
                output_model=GeminiPodcastEnrichment,
                temperature=0.1,
                workflow="podcast_info_discovery",
                related_media_id=initial_data.get('media_id')
            )
            
            print(f"\n[GEMINI STRUCTURED OUTPUT]:")
            if structured_output:
                output_dict = structured_output.model_dump()
                print(json.dumps(output_dict, indent=2))
                
                # Check for contamination in Gemini output
                found_contamination = []
                output_text = str(output_dict).lower()
                for url in contaminated_urls:
                    if url in output_text:
                        found_contamination.append(url)
                
                if found_contamination:
                    print(f"[CONTAMINATION IN GEMINI OUTPUT] Found: {found_contamination}")
                else:
                    print("[GEMINI OUTPUT CLEAN] No contamination found")
            else:
                print("No structured output returned")
            
            return structured_output
        
        # Replace the method and test
        enrichment_agent._discover_initial_info_with_gemini_and_tavily = debug_discover_method
        
        result = await enrichment_agent._discover_initial_info_with_gemini_and_tavily(test_podcast)
        
        print(f"\n[FINAL RESULT] Discovery completed")
        
    except Exception as e:
        print(f"[ERROR] Error during debug: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("Debugging enrichment flow...")
    asyncio.run(debug_enrichment_flow())