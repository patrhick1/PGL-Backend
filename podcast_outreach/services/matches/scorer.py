# podcast_outreach/services/matches/scorer.py

import os
import json
import logging
import re
import time
import asyncio
import random
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime, timedelta, timezone

# Environment and service imports (UPDATED IMPORTS)
from dotenv import load_dotenv
from podcast_outreach.integrations.google_docs import GoogleDocsService # Use new integration path
from podcast_outreach.services.ai.tracker import tracker as ai_tracker # Use new AI tracker path

# LangChain components
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.prompts import PromptTemplate
from langchain.output_parsers.pydantic import PydanticOutputParser
from pydantic import BaseModel, Field, ValidationError

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

# Pydantic model for fit assessment (based on existing model in openai_service.py)
class FitAssessment(BaseModel):
    Answer: str = Field(
        description="ONLY provide your overall fit assessment by outputting either 'Fit' or 'Not a fit'",
        enum=["Fit", "Not a fit"]
    )

def sanitize_filename(name):
    """
    Remove emojis and other non-ASCII characters from a filename.
    
    Args:
        name (str): The filename to sanitize
        
    Returns:
        str: A sanitized filename
    """
    # Remove emojis and other non-ASCII characters
    name = re.sub(r'[^\w\s-]', '', name, flags=re.UNICODE)
    # Replace spaces and other unsafe characters with underscores
    name = re.sub(r'[\s/\\]', '_', name)
    # Trim leading/trailing underscores
    return name.strip('_')


class DetermineFitProcessor:
    """
    A class to process podcast records and determine if they're a good fit for a client.
    Uses LangChain with Claude to assess fit based on podcast summaries and client info.
    """
    
    def __init__(self):
        """Initialize services and LLM configuration."""
        try:
            # Initialize services
            # self.airtable_service = PodcastService() # REMOVED: Airtable service
            self.google_docs_client = GoogleDocsService()
            self.parser = PydanticOutputParser(pydantic_object=FitAssessment)
            
            # LLM Configuration
            api_key = os.getenv("ANTHROPIC_API")
            if not api_key:
                raise ValueError("ANTHROPIC_API environment variable not set. Please set this in your environment or .env file.")
            """  
            self.llm = ChatAnthropic(
                model="claude-3-5-haiku-20241022",  # Using Haiku for cost efficiency
                anthropic_api_key=api_key,
                temperature=0.1
            )
            """
            self.llm = ChatGoogleGenerativeAI(
                model="gemini-2.0-flash", 
                google_api_key=os.getenv("GEMINI_API_KEY"), 
                temperature=0.25
            )
            # Constants (table and view names) - REMOVED: Airtable table names
            # self.CAMPAIGN_MANAGER_TABLE = 'Campaign Manager'
            # self.CAMPAIGNS_TABLE = 'Campaigns'
            # self.PODCASTS_TABLE = 'Podcasts'
            # self.PODCAST_EPISODES_TABLE = 'Podcast_Episodes'
            # self.OUTREACH_READY_VIEW = 'OR'
            self.PODCAST_INFO_FOLDER_ID = os.getenv('GOOGLE_PODCAST_INFO_FOLDER_ID')
            
            # Create prompt template
            self.prompt_template = self._create_prompt_template()
            
            logger.info("DetermineFitProcessor initialized successfully")
        except Exception as e:
            logger.critical(f"Failed to initialize DetermineFitProcessor: {e}", exc_info=True)
            raise
    
    def _create_prompt_template(self) -> PromptTemplate:
        """Create the prompt template for podcast fit assessment."""
        try:
            # Read the prompt template from file (UPDATED PATH)
            with open("podcast_outreach/services/ai/prompts/campaign/prompt_determine_good_fit.txt", "r") as f:
                template = f.read()
            
            # Create the prompt template
            return PromptTemplate(
                template=template,
                input_variables=["podcast_name", "episode_summaries", "client_bio", "client_angles"]
            )
        except Exception as e:
            logger.error(f"Failed to create prompt template: {e}", exc_info=True)
            raise
    
    async def _run_llm_assessment(
        self,
        podcast_name: str,
        episode_summaries: str,
        client_bio: str,
        client_angles: str,
        podcast_id: int # Changed to int for PostgreSQL media_id
    ) -> Tuple[Optional[FitAssessment], Dict[str, Any], float]:
        """
        Run the LLM to assess podcast fit for a client.
        
        Args:
            podcast_name: Name of the podcast
            episode_summaries: Text containing episode summaries
            client_bio: Client bio text
            client_angles: Client angles/topics text
            podcast_id: ID of the podcast for tracking (PostgreSQL media_id)
            
        Returns:
            Tuple of (FitAssessment object, token info dict, execution time)
        """
        token_info = {'input': 0, 'output': 0, 'total': 0}
        start_time = time.time()
        assessment_result = None
        
        try:
            formatted_prompt = self.prompt_template.format(
                podcast_name=podcast_name,
                episode_summaries=episode_summaries[:15000],  # Truncate if too long
                client_bio=client_bio,
                client_angles=client_angles
            )
            
            logger.debug(f"Formatted Prompt:\n{formatted_prompt[:500]}...")
            
            # Set up retries
            max_retries = 5
            retry_count = 0
            
            # Longer base delay for Anthropic models
            base_delay = 15 if 'anthropic' in str(self.llm).lower() else 5
            
            # Try to run the assessment with retries
            while retry_count < max_retries:
                try:
                    # Use structured output directly
                    llm_with_output = self.llm.with_structured_output(FitAssessment)
                    
                    # Execute the LLM call
                    llm_response = await asyncio.to_thread(llm_with_output.invoke, formatted_prompt)
                    assessment_result = llm_response # Assign the result directly
                    
                    # Basic validation
                    if assessment_result is None or not isinstance(assessment_result, FitAssessment):
                        raise ValueError("Invalid response structure from LLM")
                    
                    # Extract token usage
                    try:
                        input_tokens = 0
                        output_tokens = 0
                        total_tokens = 0
                        
                        # Try to extract token info from response metadata
                        try:
                            raw_response = getattr(assessment_result, '_raw_response', None) or getattr(assessment_result, 'response_metadata', None)
                            usage_metadata = getattr(raw_response, 'usage_metadata', None) if raw_response else None
                            
                            if usage_metadata:
                                input_tokens = usage_metadata.get('prompt_token_count', 0)
                                output_tokens = usage_metadata.get('candidates_token_count', 0)
                                total_tokens = usage_metadata.get('total_token_count', 0)
                        except Exception as e:
                            logger.warning(f"Error extracting token metadata: {e}")
                        
                        # Estimate if we couldn't get actual counts
                        if total_tokens == 0:
                            # Rough token estimation
                            input_tokens = len(formatted_prompt) // 4
                            output_tokens = len(str(assessment_result.model_dump())) // 4
                            total_tokens = input_tokens + output_tokens
                            
                        token_info = {
                            'input': input_tokens,
                            'output': output_tokens,
                            'total': total_tokens
                        }
                    except Exception as token_error:
                        logger.warning(f"Failed to extract token info: {token_error}")
                        # Safe defaults
                        token_info = {
                            'input': len(formatted_prompt) // 4,
                            'output': 200,
                            'total': (len(formatted_prompt) // 4) + 200
                        }
                    
                    # Success - break out of retry loop
                    break
                    
                except Exception as e:
                    retry_count += 1
                    logger.warning(f"Attempt {retry_count}/{max_retries} failed: {type(e).__name__} - {e}")
                    
                    # Check for rate limits or server errors
                    error_str = str(e).lower()
                    is_rate_limit = "quota" in error_str or "429" in error_str or "rate limit" in error_str or "concurrent" in error_str
                    is_server_error = "500" in error_str or "503" in error_str or "too many requests" in error_str
                    
                    if (is_rate_limit or is_server_error) and retry_count < max_retries:
                        # Use exponential backoff with jitter to avoid thundering herd problem
                        wait_time = base_delay * (2 ** (retry_count - 1)) + random.uniform(0, 5)
                        
                        # For rate limits specifically, add even more delay
                        if is_rate_limit:
                            wait_time *= 1.5
                            
                        logger.warning(f"Rate limit/server error. Retrying in {wait_time:.1f}s...")
                        
                        # For Anthropic rate limits, add an extra message about concurrency
                        if 'anthropic' in model_name and ('concurrent' in error_str or 'rate limit' in error_str):
                            logger.warning(f"Anthropic rate limit due to concurrent connections - consider using concurrency=1 for Claude models")
                        
                        await asyncio.sleep(wait_time)
                    elif retry_count >= max_retries:
                        logger.error(f"Max retries reached. Failing assessment.")
                        raise
                    else:
                        # For non-retryable errors, apply shorter delay but still retry
                        wait_time = 2 * (retry_count)
                        logger.error(f"Non-rate-limit error. Retrying in {wait_time}s...")
                        await asyncio.sleep(wait_time)
                        if retry_count >= max_retries:
                            raise
            
            execution_time = time.time() - start_time
            logger.info(f"Successfully completed fit assessment. Time: {execution_time:.2f}s, Tokens: {token_info['total']}")
            
            # Log token usage to tracker
            if assessment_result:
                model_name = getattr(self.llm, 'model', 'unknown')
                # Fix model name format by removing 'model/' prefix if present
                if isinstance(model_name, str) and '/' in model_name:
                    model_name = model_name.split('/')[-1]
                ai_tracker.log_usage(
                    workflow="determine_fit",
                    model=model_name,
                    tokens_in=token_info['input'],
                    tokens_out=token_info['output'],
                    execution_time=execution_time,
                    endpoint="langchain.llm.ainvoke",
                    related_media_id=podcast_id # Use media_id for tracking
                )
            
            return assessment_result, token_info, execution_time
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.critical(f"Failed to complete assessment after all retries: {type(e).__name__} - {e}", exc_info=True)
            return None, token_info, execution_time
    
    async def process_single_record(self, match_suggestion_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single match suggestion record to determine podcast fit.
        
        Args:
            match_suggestion_record: The PostgreSQL match_suggestions record
            
        Returns:
            Dict containing the processing results
        """
        # Import modular queries here to avoid circular dependencies at module level
        from podcast_outreach.database.queries import campaigns as campaign_queries
        from podcast_outreach.database.queries import media as media_queries
        from podcast_outreach.database.queries import episodes as episode_queries
        from podcast_outreach.database.queries import match_suggestions as match_queries

        result = {
            'match_id': match_suggestion_record.get('match_id'),
            'status': 'Error',
            'fit_assessment': None,
            'error_reason': '',
            'execution_time': 0,
            'tokens_used': 0,
            'processing_timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        
        try:
            # Step 1: Get the Campaign and Media records
            match_id = match_suggestion_record.get('match_id')
            campaign_id = match_suggestion_record.get('campaign_id')
            media_id = match_suggestion_record.get('media_id')

            logger.info(f"Processing Match Suggestion ID: {match_id} (Campaign: {campaign_id}, Media: {media_id})")

            campaign_record = await campaign_queries.get_campaign_by_id(campaign_id)
            if not campaign_record:
                result['error_reason'] = f"Failed to retrieve Campaign record {campaign_id}"
                return result
            
            media_record = await media_queries.get_media_by_id_from_db(media_id)
            if not media_record:
                result['error_reason'] = f"Failed to retrieve Media record {media_id}"
                return result
            
            # Extract relevant data
            client_bio = campaign_record.get('campaign_bio', '')
            client_angles = campaign_record.get('campaign_angles', '')
            podcast_name = media_record.get('name', '')

            # Step 2: Get episode summaries for the podcast
            episodes = await episode_queries.get_episodes_for_media_with_content(media_id)
            episode_summaries = ""
            for ep in episodes:
                summary_text = ep.get('ai_episode_summary') or ep.get('episode_summary') or ep.get('transcript')
                if summary_text:
                    episode_summaries += f"Episode Title: {ep.get('title', 'N/A')}\nSummary: {summary_text[:500]}\n\n" # Limit summary length
            
            if not episode_summaries:
                result['error_reason'] = f"No suitable episode summaries found for media {media_id}"
                return result

            # Step 3: Run the LLM assessment
            assessment, token_info, execution_time = await self._run_llm_analysis(
                podcast_name, episode_summaries, client_bio, client_angles, media_id
            )
            
            if assessment is None:
                result['error_reason'] = "Failed to get a valid assessment from the LLM"
                return result
            
            # Step 4: Update the status in PostgreSQL
            fit_status = assessment.Answer
            update_data = {
                'status': fit_status.replace(' ', '_').lower(), # Convert "Fit" to "fit", "Not a fit" to "not_a_fit"
                'match_score': 1.0 if fit_status == 'Fit' else 0.0, # Simple score based on fit
                'ai_reasoning': assessment.model_dump_json() # Store full assessment as JSON
            }
            updated_match = await match_queries.update_match_suggestion_in_db(match_id, update_data)
            
            if not updated_match:
                result['error_reason'] = "Failed to update match suggestion in database"
                return result
            
            # Update result with success data
            result.update({
                'status': 'Success',
                'fit_assessment': fit_status,
                'execution_time': execution_time,
                'tokens_used': token_info['total']
            })
            
            logger.info(f"Successfully processed match suggestion {match_id}, status: {fit_status}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing match suggestion {match_id}: {e}", exc_info=True)
            result['error_reason'] = str(e)
            return result
    
    async def process_batch(self, batch_records: List[Dict], semaphore, stop_flag=None) -> List[Dict]:
        """
        Process a batch of match suggestion records with concurrency control.
        
        Args:
            batch_records: List of match suggestion records to process
            semaphore: Asyncio semaphore for concurrency control
            stop_flag: Optional event to signal when to stop processing
            
        Returns:
            List of results from processing each record
        """
        tasks = []
        request_delay = 2  # Seconds between requests
        
        for record in batch_records:
            # Check for stop flag before processing each record
            if stop_flag and stop_flag.is_set():
                logger.info("Stop flag is set - terminating during batch processing")
                break
                
            async with semaphore:
                await asyncio.sleep(request_delay)
                task = asyncio.create_task(self.process_single_record(record))
                tasks.append(task)
        
        return await asyncio.gather(*tasks)
    
    async def process_all_records(self, max_concurrency=1, batch_size=1, stop_flag=None) -> Dict[str, Any]:
        """
        Process all pending match suggestion records.
        
        Args:
            max_concurrency: Maximum number of concurrent processes
            batch_size: Number of records per batch
            stop_flag: Optional event to signal when to stop processing
            
        Returns:
            Statistics about the processing
        """
        # Import modular queries here to avoid circular dependencies at module level
        from podcast_outreach.database.queries import match_suggestions as match_queries

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stats = {
            'total_processed': 0,
            'successful': 0,
            'failed': 0,
            'fit_count': 0,
            'not_fit_count': 0,
            'total_tokens': 0,
            'start_time': time.time(),
            'end_time': None,
            'duration_seconds': 0,
            'stopped_early': False
        }
        
        try:
            # Check for stop flag at the beginning
            if stop_flag and stop_flag.is_set():
                logger.info("Stop flag is set - terminating process_all_records before starting")
                stats['stopped_early'] = True
                stats['end_time'] = time.time()
                stats['duration_seconds'] = stats['end_time'] - stats['start_time']
                return stats
                
            # Fetch records from the database that are pending fit assessment
            logger.info(f"Fetching pending match suggestions for fit assessment...")
            records = await match_queries.get_match_suggestions_for_campaign_from_db(status='pending') # Assuming a method to get pending matches
            
            logger.info(f"Found {len(records)} record(s) to process")
            
            # Check for stop flag after fetching records
            if stop_flag and stop_flag.is_set():
                logger.info("Stop flag is set - terminating after fetching records")
                stats['stopped_early'] = True
                stats['end_time'] = time.time()
                stats['duration_seconds'] = stats['end_time'] - stats['start_time']
                return stats
            
            if not records:
                logger.info("No records found to process")
                stats['end_time'] = time.time()
                stats['duration_seconds'] = stats['end_time'] - stats['start_time']
                return stats
            
            # Process records in batches
            batches = [records[i:i + batch_size] for i in range(0, len(records), batch_size)]
            logger.info(f"Processing {len(records)} records in {len(batches)} batches")
            
            all_results = []
            semaphore = asyncio.Semaphore(max_concurrency)
            
            for i, batch in enumerate(batches):
                # Check for stop flag before processing each batch
                if stop_flag and stop_flag.is_set():
                    logger.info(f"Stop flag is set - terminating before batch {i+1}/{len(batches)}")
                    stats['stopped_early'] = True
                    break
                    
                batch_num = i + 1
                logger.info(f"Starting Batch {batch_num}/{len(batches)} ({len(batch)} records)")
                
                if i > 0:
                    # Add a delay between batches
                    logger.info(f"Pausing for 5 seconds before batch {batch_num}...")
                    
                    # Break down the pause into 1-second intervals to check stop flag
                    for _ in range(5):
                        if stop_flag and stop_flag.is_set():
                            logger.info(f"Stop flag is set - terminating during pause before batch {batch_num}")
                            stats['stopped_early'] = True
                            break
                        await asyncio.sleep(1)
                    
                    # Check if we should terminate after the pause
                    if stop_flag and stop_flag.is_set():
                        break
                
                start_batch_time = time.time()
                batch_results = await self.process_batch(batch, semaphore, stop_flag)
                batch_duration = time.time() - start_batch_time
                
                logger.info(f"Finished Batch {batch_num}/{len(batches)}. Duration: {batch_duration:.2f}s")
                all_results.extend(batch_results)
                
                # Update stats
                for result in batch_results:
                    stats['total_processed'] += 1
                    
                    if result['status'] == 'Success':
                        stats['successful'] += 1
                        if result['fit_assessment'] == 'Fit':
                            stats['fit_count'] += 1
                        else:
                            stats['not_fit_count'] += 1
                        stats['total_tokens'] += result['tokens_used']
                    else:
                        stats['failed'] += 1
                
                # Pause after every batch
                if batch_num < len(batches):
                    pause_duration = 30
                    logger.info(f"PAUSING for {pause_duration} seconds after processing batch {batch_num}...")
                    
                    # Break down the 30-second pause into smaller intervals to check stop flag
                    for _ in range(30):
                        if stop_flag and stop_flag.is_set():
                            logger.info(f"Stop flag is set - terminating during pause after batch {batch_num}")
                            stats['stopped_early'] = True
                            break
                        await asyncio.sleep(1)
                    
                    # Check if we should terminate after the pause
                    if stop_flag and stop_flag.is_set():
                        break
            
            # Update final stats
            stats['end_time'] = time.time()
            stats['duration_seconds'] = stats['end_time'] - stats['start_time']
            
            # Log statistics
            logger.info("--- Processing Statistics ---")
            logger.info(f"  Total records processed: {stats['total_processed']}")
            logger.info(f"  Successful: {stats['successful']} ({stats['successful']/max(stats['total_processed'], 1)*100:.1f}%)")
            logger.info(f"  Failed: {stats['failed']} ({stats['failed']/max(stats['total_processed'], 1)*100:.1f}%)")
            logger.info(f"  Fit: {stats['fit_count']} ({stats['fit_count']/max(stats['successful'], 1)*100:.1f}%)")
            logger.info(f"  Not Fit: {stats['not_fit_count']} ({stats['not_fit_count']/max(stats['successful'], 1)*100:.1f}%)")
            logger.info(f"  Total tokens used: {stats['total_tokens']}")
            logger.info(f"  Average tokens per record: {stats['total_tokens']/max(stats['successful'], 1):.1f}")
            logger.info(f"  Total processing duration: {stats['duration_seconds']:.2f} seconds")
            logger.info(f"  Stopped early: {stats['stopped_early']}")
            logger.info("-----------------------------")
            
            # Save stats to file
            stats_file = f"determine_fit_stats_{timestamp}.json"
            try:
                stats_save = stats.copy()
                stats_save['start_time'] = datetime.fromtimestamp(stats_save['start_time']).isoformat()
                stats_save['end_time'] = datetime.fromtimestamp(stats_save['end_time']).isoformat()
                with open(stats_file, 'w') as f:
                    json.dump(stats_save, f, indent=2)
                logger.info(f"Processing statistics saved to {stats_file}")
            except Exception as e:
                logger.error(f"Failed to save statistics to JSON: {e}")
            
            return stats
            
        except Exception as e:
            logger.critical(f"Critical error in process_all_records: {e}", exc_info=True)
            stats['end_time'] = time.time()
            stats['duration_seconds'] = stats['end_time'] - stats['start_time']
            return stats


# Function to run for standard processing (with stop flag support)
async def determine_fit_async(stop_flag: Optional[Any] = None, max_concurrency: int = 3, batch_size: int = 5) -> Dict[str, Any]:
    """
    Async entry point for determine_fit script.
    
    Args:
        stop_flag: Optional event to signal when to stop processing
        max_concurrency: Maximum number of concurrent processes to run
        batch_size: Number of records to process in each batch
        
    Returns:
        Dictionary with processing statistics
    """
    logger.info("Starting Determine Fit Automation (Optimized)")
    logger.info(f"Using max_concurrency={max_concurrency}, batch_size={batch_size}")
    
    try:
        processor = DetermineFitProcessor()
        
        # Check if should stop before starting
        if stop_flag and stop_flag.is_set():
            logger.info("Stop flag set before starting processing")
            return {'status': 'stopped', 'message': 'Processing stopped by stop flag', 'stopped_early': True}
        
        # Process all records with explicit concurrency and batch size
        stats = await processor.process_all_records(max_concurrency=max_concurrency, batch_size=batch_size, stop_flag=stop_flag)
        
        return stats
    except Exception as e:
        logger.critical(f"Determine Fit automation failed: {e}", exc_info=True)
        return {'status': 'error', 'message': str(e)}

# Synchronous wrapper for compatibility with existing code (REMOVED: Not needed in new structure)
# def determine_fit(stop_flag: Optional[Any] = None, max_concurrency: int = 3, batch_size: int = 5) -> Dict[str, Any]:
#     """
#     Synchronous wrapper for determine_fit_async.
#     """
#     return asyncio.run(determine_fit_async(stop_flag, max_concurrency, batch_size))

# Direct execution entry point (REMOVED: This is now a service, not a standalone script)
# if __name__ == "__main__":
#     from dotenv import load_dotenv
#     load_dotenv()
    
#     # Configuration for direct script execution
#     MAX_CONCURRENCY = 3
#     BATCH_SIZE = 5
    
#     logger.info("=============================================")
#     logger.info("Starting Determine Fit Process (Optimized)")
#     logger.info(f"Using max_concurrency={MAX_CONCURRENCY}, batch_size={BATCH_SIZE}")
#     logger.info("=============================================")
    
#     start_run_time = time.time()
#     results = asyncio.run(determine_fit_async(max_concurrency=MAX_CONCURRENCY, batch_size=BATCH_SIZE))
#     end_run_time = time.time()
    
#     total_run_duration = end_run_time - start_run_time
#     logger.info("=============================================")
#     logger.info("Determine Fit Process Ended")
#     logger.info(f"Total script execution time: {total_run_duration:.2f} seconds")
#     logger.info("=============================================")
