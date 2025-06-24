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
import uuid

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

# Database queries (add review_tasks)
from podcast_outreach.database.queries import campaigns as campaign_queries
from podcast_outreach.database.queries import media as media_queries
from podcast_outreach.database.queries import episodes as episode_queries
from podcast_outreach.database.queries import match_suggestions as match_queries
from podcast_outreach.database.queries import review_tasks as review_task_queries

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
            # The prompt file itself will need to be updated to include new placeholders
            with open("podcast_outreach/services/ai/prompts/campaign/prompt_determine_good_fit.txt", "r") as f:
                template = f.read()
            
            # Add new input_variables for the revised prompt
            return PromptTemplate(
                template=template,
                input_variables=[
                    "podcast_name", 
                    "podcast_description", 
                    "episode_content_snippet", # e.g., summary or transcript part of best_matching_episode
                    "client_bio", 
                    "client_angles",
                    "initial_match_score", # Quantitative score
                    "initial_match_reasoning" # Reasoning from MatchCreationService
                ]
            )
        except Exception as e:
            logger.error(f"Failed to create prompt template: {e}", exc_info=True)
            raise
    
    async def _run_llm_assessment(
        self,
        prompt_inputs: Dict[str, Any], # Changed to accept a dict of inputs
        match_suggestion_id: int, # For tracking
        related_media_id: int, 
        related_campaign_id: uuid.UUID
    ) -> Tuple[Optional[FitAssessment], Dict[str, Any], float]:
        """
        Run the LLM to assess podcast fit for a client.
        Args:
            prompt_inputs: Dictionary containing all necessary fields for the prompt template.
            match_suggestion_id: ID of the match suggestion for logging.
            related_media_id: ID of the media for AI tracking.
            related_campaign_id: ID of the campaign for AI tracking.
        Returns:
            Tuple of (FitAssessment object, token info dict, execution time)
        """
        token_info = {'input': 0, 'output': 0, 'total': 0}
        start_time = time.time()
        assessment_result = None
        
        try:
            formatted_prompt = self.prompt_template.format(**prompt_inputs)
            
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
                await ai_tracker.log_usage( # Changed to await
                    workflow="determine_fit_qualitative", # More specific workflow name
                    model=model_name,
                    tokens_in=token_info['input'],
                    tokens_out=token_info['output'],
                    execution_time=execution_time,
                    endpoint="langchain.llm.ainvoke",
                    related_media_id=related_media_id, # Use media_id for tracking
                    related_campaign_id=related_campaign_id, # Add campaign_id for tracking
                    related_match_suggestion_id=match_suggestion_id # Add match_suggestion_id for tracking
                )
            
            return assessment_result, token_info, execution_time
            
        except Exception as e:
            execution_time = time.time() - start_time
            logger.critical(f"Failed to complete assessment after all retries: {type(e).__name__} - {e}", exc_info=True)
            return None, token_info, execution_time
    
    async def process_single_record(self, review_task_record: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process a single 'match_suggestion_qualitative_review' task.
        Fetches match_suggestion, campaign, media, and best episode data.
        Performs LLM assessment and updates tables.
        
        Args:
            review_task_record: The review_tasks record of type 'match_suggestion_qualitative_review'.
            
        Returns:
            Dict containing the processing results for the review task.
        """
        review_task_id = review_task_record.get('review_task_id')
        match_suggestion_id = review_task_record.get('related_id') # This is match_suggestions.match_id

        result = {
            'review_task_id': review_task_id,
            'match_suggestion_id': match_suggestion_id,
            'status': 'Error',
            'fit_assessment': None,
            'error_reason': '',
            'execution_time': 0,
            'tokens_used': 0,
            'processing_timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        if not match_suggestion_id:
            result['error_reason'] = f"Review task {review_task_id} has no related_id (match_suggestion_id)."
            logger.error(result['error_reason'])
            await review_task_queries.update_review_task_status_in_db(review_task_id, "failed", result['error_reason'])
            return result

        try:
            logger.info(f"Processing qualitative review task {review_task_id} for Match Suggestion ID: {match_suggestion_id}")

            # 1. Fetch Match Suggestion, Campaign, Media, and Best Episode data
            match_suggestion = await match_queries.get_match_suggestion_by_id(match_suggestion_id)
            if not match_suggestion:
                result['error_reason'] = f"MatchSuggestion ID {match_suggestion_id} not found."
                logger.error(result['error_reason'])
                await review_task_queries.update_review_task_status_in_db(review_task_id, "failed", result['error_reason'])
                return result

            campaign_id = match_suggestion.get('campaign_id')
            media_id = match_suggestion.get('media_id')
            best_episode_id = match_suggestion.get('best_matching_episode_id')

            campaign_record = await campaign_queries.get_campaign_by_id(campaign_id)
            if not campaign_record:
                result['error_reason'] = f"Campaign record {campaign_id} not found for match {match_suggestion_id}."
                logger.error(result['error_reason'])
                await review_task_queries.update_review_task_status_in_db(review_task_id, "failed", result['error_reason'])
                return result
            
            media_record = await media_queries.get_media_by_id_from_db(media_id)
            if not media_record:
                result['error_reason'] = f"Media record {media_id} not found for match {match_suggestion_id}."
                logger.error(result['error_reason'])
                await review_task_queries.update_review_task_status_in_db(review_task_id, "failed", result['error_reason'])
                return result

            episode_content_snippet = "No specific episode content available for this match."
            if best_episode_id:
                best_episode_record = await episode_queries.get_episode_by_id(best_episode_id)
                if best_episode_record:
                    ep_summary = best_episode_record.get('ai_episode_summary') or best_episode_record.get('episode_summary')
                    ep_transcript_sample = (best_episode_record.get('transcript') or "")[:1000]
                    if ep_summary:
                        episode_content_snippet = f"Best Matching Episode (ID: {best_episode_id}, Title: {best_episode_record.get('title', 'N/A')}):\nSummary: {ep_summary}"
                    elif ep_transcript_sample:
                        episode_content_snippet = f"Best Matching Episode (ID: {best_episode_id}, Title: {best_episode_record.get('title', 'N/A')}):\nTranscript Snippet: {ep_transcript_sample}..."
                    else:
                        episode_content_snippet = f"Best Matching Episode (ID: {best_episode_id}, Title: {best_episode_record.get('title', 'N/A')}): Content not summarized."
            
            # Prepare inputs for the LLM prompt
            client_bio_text = ""
            campaign_bio_source = campaign_record.get('campaign_bio', '')
            if self.google_docs_client.is_google_doc_link(campaign_bio_source): # Assuming is_google_doc_link method exists
                client_bio_text = await asyncio.to_thread(self.google_docs_client.get_document_content_from_url, campaign_bio_source)
            elif campaign_bio_source: # Direct text
                client_bio_text = campaign_bio_source

            client_angles_text = ""
            campaign_angles_source = campaign_record.get('campaign_angles', '')
            if self.google_docs_client.is_google_doc_link(campaign_angles_source):
                client_angles_text = await asyncio.to_thread(self.google_docs_client.get_document_content_from_url, campaign_angles_source)
            elif campaign_angles_source: # Direct text
                client_angles_text = campaign_angles_source
            
            if not client_bio_text and campaign_record.get('questionnaire_responses'): # Fallback to person bio from questionnaire if GDoc is empty
                q_res = campaign_record.get('questionnaire_responses')
                if q_res.get('personalInfo', {}).get('bio'):
                    client_bio_text = "Client Bio (from questionnaire):\n" + q_res['personalInfo']['bio']
            

            prompt_inputs = {
                "podcast_name": media_record.get('name', 'N/A'),
                "podcast_description": media_record.get('description', media_record.get('ai_description', 'No description available.')),
                "episode_content_snippet": episode_content_snippet,
                "client_bio": client_bio_text[:10000], # Truncate for prompt
                "client_angles": client_angles_text[:10000], # Truncate for prompt
                "initial_match_score": f"{match_suggestion.get('match_score', 0.0):.3f}",
                "initial_match_reasoning": match_suggestion.get('ai_reasoning', 'No initial quantitative reasoning provided.')
            }

            # Step 2: Run the LLM assessment
            assessment, token_info, execution_time = await self._run_llm_assessment(
                prompt_inputs, 
                match_suggestion_id=match_suggestion_id,
                related_media_id=media_id,
                related_campaign_id=campaign_id
            )
            
            result['execution_time'] = execution_time
            result['tokens_used'] = token_info['total']

            if assessment is None or not isinstance(assessment, FitAssessment):
                result['error_reason'] = "Failed to get a valid assessment from the LLM after retries."
                logger.error(f"{result['error_reason']} for match {match_suggestion_id}")
                await review_task_queries.update_review_task_status_in_db(review_task_id, "failed", result['error_reason'])
                # Also update match suggestion status to reflect failure
                await match_queries.update_match_suggestion_in_db(match_suggestion_id, {"status": "qualitative_assessment_failed"})
                return result
            
            # Step 3: Update match_suggestions table
            fit_status_llm = assessment.Answer # "Fit" or "Not a fit"
            new_match_status = "pending_human_review" if fit_status_llm == "Fit" else "rejected_by_ai"
            
            # Append qualitative reasoning to existing quantitative reasoning
            qualitative_reasoning = f"LLM Qualitative Assessment: {fit_status_llm}. Justification: (LLM should provide this as part of its response, if not, this part will be empty or you might need to adjust prompt/parsing)."
            # For now, the FitAssessment model only has Answer. If LLM provides more, prompt/parser needs update.
            # Let's assume for now the full assessment (which is just Fit/Not a fit currently) is the reasoning.
            qualitative_reasoning = f"LLM Qualitative Assessment: {assessment.model_dump_json()}"
            
            updated_ai_reasoning = f"{match_suggestion.get('ai_reasoning', '')}\n\n{qualitative_reasoning}"

            match_update_payload = {
                'status': new_match_status,
                'ai_reasoning': updated_ai_reasoning.strip()
            }
            updated_match = await match_queries.update_match_suggestion_in_db(match_suggestion_id, match_update_payload)
            
            if not updated_match:
                result['error_reason'] = f"Failed to update match suggestion {match_suggestion_id} after LLM assessment."
                logger.error(result['error_reason'])
                await review_task_queries.update_review_task_status_in_db(review_task_id, "failed", result['error_reason'])
                return result
            
            # Step 4: Update the current review_task to 'completed'
            await review_task_queries.update_review_task_status_in_db(review_task_id, "completed", f"Qualitative assessment done: {fit_status_llm}")

            # Step 5: If Fit, create a new review_task for final human approval
            if new_match_status == "pending_human_review":
                human_review_task_payload = {
                    'task_type': 'match_suggestion', # This is the original task type for human UI
                    'related_id': match_suggestion_id,
                    'campaign_id': campaign_id,
                    'status': 'pending',
                    'notes': f"Final human review needed for AI-assessed 'Fit' match (Qualitative Score: {fit_status_llm}). Quantitative score: {match_suggestion.get('match_score', 0.0):.3f}"
                }
                created_human_task = await review_task_queries.create_review_task_in_db(human_review_task_payload)
                if created_human_task:
                    logger.info(f"Created 'match_suggestion' task {created_human_task['review_task_id']} for human review of match {match_suggestion_id}.")
                else:
                    logger.error(f"Failed to create 'match_suggestion' task for human review of match {match_suggestion_id}.")
            
            result.update({
                'status': 'Success',
                'fit_assessment': fit_status_llm,
            })
            logger.info(f"Successfully processed qualitative review for match {match_suggestion_id}. LLM Assessment: {fit_status_llm}")
            return result
            
        except Exception as e:
            logger.error(f"Error processing qualitative review task {review_task_id} for match {match_suggestion_id}: {e}", exc_info=True)
            result['error_reason'] = str(e)
            try: # Attempt to mark task as failed
                await review_task_queries.update_review_task_status_in_db(review_task_id, "failed", str(e)[:250])
                if match_suggestion_id: # Also mark match suggestion
                     await match_queries.update_match_suggestion_in_db(match_suggestion_id, {"status": "qualitative_assessment_error"})
            except Exception as db_error:
                logger.error(f"Further error trying to mark task/match as failed: {db_error}")
            return result

    # Removed process_batch and process_all_records as this service will be triggered by individual review tasks.
    # The orchestration of processing multiple review tasks (e.g., via a polling mechanism or a queue worker)
    # would happen in a separate orchestrator/background task runner if needed.

# Main orchestrator for this service, if it were to run independently (e.g., polling for tasks)
# This is a placeholder for how it *could* be run if not triggered by a larger task system.
async def main_determine_fit_orchestrator(max_concurrent_tasks: int = 3, poll_interval_seconds: int = 60):
    """
    Polls for 'match_suggestion_qualitative_review' tasks and processes them.
    This is a conceptual orchestrator. In a real system, this might be part of a larger worker service.
    """
    processor = DetermineFitProcessor()
    logger.info(f"Starting DetermineFitProcessor orchestrator. Polling every {poll_interval_seconds}s.")
    
    stop_event = asyncio.Event() # For graceful shutdown if needed

    async def process_pending_tasks():
        pending_tasks = await review_task_queries.get_all_review_tasks_paginated(
            task_type='match_suggestion_qualitative_review', 
            status='pending', 
            size=max_concurrent_tasks * 2 # Fetch a bit more to fill queue
        )
        
        if not pending_tasks[0]:
            logger.debug("No pending qualitative review tasks found in this poll cycle.")
            return

        logger.info(f"Found {len(pending_tasks[0])} pending qualitative review tasks to process.")
        
        # Use a semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrent_tasks)
        active_processing_tasks = []

        for task_record in pending_tasks[0]:
            # Acquire semaphore before starting the task
            await semaphore.acquire()
            logger.info(f"Acquired semaphore for task {task_record['review_task_id']}. Starting processing.")
            
            async def process_task_with_semaphore_release(record):
                try:
                    await processor.process_single_record(record)
                finally:
                    semaphore.release()
                    logger.info(f"Released semaphore after task {record['review_task_id']}.")

            active_processing_tasks.append(asyncio.create_task(process_task_with_semaphore_release(task_record)))
        
        if active_processing_tasks:
            await asyncio.gather(*active_processing_tasks, return_exceptions=True)
            logger.info("Completed processing current batch of qualitative review tasks.")

    try:
        while not stop_event.is_set():
            await process_pending_tasks()
            try:
                # Wait for the poll interval, but break early if stop_event is set
                await asyncio.wait_for(stop_event.wait(), timeout=poll_interval_seconds)
                break # Stop event was set
            except asyncio.TimeoutError:
                pass # Timeout occurred, continue loop
    except KeyboardInterrupt:
        logger.info("Orchestrator interrupted. Shutting down...")
    except Exception as e:
        logger.error(f"DetermineFitOrchestrator encountered an error: {e}", exc_info=True)
    finally:
        logger.info("DetermineFitOrchestrator stopped.")
        stop_event.set()


# The main way to trigger this processor will be via a background task in tasks.py
# that fetches a 'match_suggestion_qualitative_review' task and calls processor.process_single_record(task_record)
# The main_determine_fit_orchestrator above is more for a standalone worker/poller scenario.
