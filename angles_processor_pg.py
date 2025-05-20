import asyncio
import concurrent.futures
import logging
import time
import os
import random
import json
import traceback
from typing import Dict, Any, Optional, Tuple
from datetime import datetime
import uuid

# LangChain and Google
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage
from langchain.text_splitter import RecursiveCharacterTextSplitter

# Project-specific services
import db_service_pg # Corrected: Use the updated db_service_pg
from src.google_docs_service import GoogleDocsService
from src.openai_service import OpenAIService # For structuring, can be replaced with Gemini if preferred
from src.ai_usage_tracker import tracker as ai_tracker
from src.data_processor import extract_document_id # Assuming this is available or moved here

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class AnglesProcessorPG:
    """
    Processes campaign data from PostgreSQL to generate bios and angles,
    storing results back in PostgreSQL and as Google Docs.
    """
    
    def __init__(self):
        # Initialize services
        self.google_docs_service = GoogleDocsService()
        self.openai_service = OpenAIService() # Used for structuring Gemini's output
        
        self.gemini_model = ChatGoogleGenerativeAI(
            model="gemini-2.0-flash", # Consider "gemini-1.5-flash" or "gemini-pro" for complex tasks
            google_api_key=os.getenv("GEMINI_API_KEY"),
            temperature=0.3,
            max_output_tokens=None 
        )
        
        # Thread pool for synchronous SDK calls
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)
        
        # Prompt document IDs (if you still use master prompts from GDocs)
        # For this refactor, we'll embed a generic prompt structure, but you can re-add these.
        self.bio_angles_prompt_template_text = """
        Based on the provided information (mock interview, social posts, podcast transcripts, articles), 
        please generate the following for the campaign '{campaign_name}':

        1.  **Detailed Bio**: A comprehensive and engaging biography.
        2.  **Three Distinct Angles**: Each angle should include:
            *   **Topic**: The core subject or theme.
            *   **Outcome**: The benefit or result for the audience.
            *   **Description**: A detailed explanation of the angle.

        Ensure the tone is professional and compelling. Structure the output clearly.
        """
        self.keyword_prompt_text = """
        Based on the following Bio and Angles for the campaign '{campaign_name}', 
        generate a concise list of relevant SEO keywords (around 10-15 keywords).

        Bio:
        {bio_content}

        Angles:
        {angles_content}

        Keywords:
        """

        self.stats = {
            "campaigns_processed": 0,
            "successful_generations": 0,
            "failed_generations": 0,
            "total_execution_time": 0,
            "execution_times_list": [],
            "token_usage": {'input': 0, 'output': 0}
        }
        self._log_service_account_info()

    def _log_service_account_info(self):
        """Logs information about the Google service account being used."""
        service_account_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if service_account_path:
            logger.info(f"Using service account file: {service_account_path}")
            if os.path.exists(service_account_path):
                try:
                    with open(service_account_path, 'r') as f:
                        service_info = json.load(f)
                        logger.info(f"Service account client_email: {service_info.get('client_email')}")
                        logger.info(f"Service account project_id: {service_info.get('project_id')}")
                except Exception as e:
                    logger.error(f"Error reading service account file: {e}")
            else:
                logger.error(f"Service account file does not exist: {service_account_path}")
        else:
            logger.warning("GOOGLE_APPLICATION_CREDENTIALS environment variable not set.")


    async def _run_in_executor(self, func, *args):
        """Helper to run synchronous functions in the thread pool."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, func, *args)

    async def _call_gemini_langchain(self, prompt: str, workflow_name: str, delay_seconds: float = 1.0) -> str:
        """Generates text using LangChain Gemini model with error handling and tracking."""
        await asyncio.sleep(delay_seconds)
        start_time = time.time()
        try:
            messages = [HumanMessage(content=prompt)]
            response = await self._run_in_executor(self.gemini_model.invoke, messages)
            text_response = response.content
            
            execution_time = time.time() - start_time
            # Simplified token approximation for LangChain
            tokens_in = len(prompt) // 4 
            tokens_out = len(text_response) // 4

            ai_tracker.log_usage(
                workflow=workflow_name,
                model="gemini-2.0-flash", # or whichever model is configured
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                execution_time=execution_time,
                endpoint="gemini_langchain.invoke"
            )
            self.stats['token_usage']['input'] += tokens_in
            self.stats['token_usage']['output'] += tokens_out
            return text_response
        except Exception as e:
            logger.error(f"Error during Gemini LangChain call for workflow '{workflow_name}': {e}")
            if "429" in str(e) or "quota" in str(e).lower() or "rate limit" in str(e).lower():
                logger.warning("Rate limit hit. Consider increasing delay or checking quotas.")
            # Depending on retry strategy, you might re-raise or return an error indicator
            raise # Re-raise for the caller to handle or for a potential outer retry mechanism

    async def _get_gdoc_content_async(self, doc_link_or_id: Optional[str], doc_title_for_log: str) -> str:
        """Fetches Google Doc content asynchronously given a link or ID."""
        if not doc_link_or_id:
            logger.info(f"No document link/ID provided for {doc_title_for_log}, skipping fetch.")
            return ""
        
        doc_id = extract_document_id(doc_link_or_id)
        if not doc_id:
            logger.warning(f"Could not extract Google Doc ID from '{doc_link_or_id}' for {doc_title_for_log}.")
            return ""
        
        try:
            logger.info(f"Fetching content from Google Doc: {doc_title_for_log} (ID: {doc_id})")
            await asyncio.sleep(random.uniform(0.5, 1.5)) # Small random delay
            content = await self._run_in_executor(self.google_docs_service.get_document_content, doc_id)
            logger.info(f"Successfully fetched content for {doc_title_for_log} (Length: {len(content)}).")
            return content if content else ""
        except Exception as e:
            logger.error(f"Error fetching Google Doc {doc_title_for_log} (ID: {doc_id}): {e}\n{traceback.format_exc()}")
            return "" # Return empty string on error to allow process to continue if possible

    async def _summarize_content_if_needed(self, content: str, title_for_log: str, max_length: int = 70000) -> str:
        """Summarizes content if it exceeds max_length to prevent token overruns."""
        if not content or len(content) <= max_length:
            return content
        
        logger.info(f"Content for '{title_for_log}' (length {len(content)}) exceeds max_length {max_length}. Summarizing...")
        try:
            # Using RecursiveCharacterTextSplitter for potentially better semantic chunking
            text_splitter = RecursiveCharacterTextSplitter(
                chunk_size=max_length, # Target size for summaries
                chunk_overlap=max_length//10, # 10% overlap
                length_function=len
            )
            chunks = text_splitter.split_text(content)
            summarized_chunks = []

            for i, chunk in enumerate(chunks):
                if not chunk.strip(): continue
                prompt = f"Summarize the following text for '{title_for_log}' (Part {i+1}/{len(chunks)}). Retain all key information, topics, unique perspectives, and important quotes:\n\n{chunk}"
                summary_piece = await self._call_gemini_langchain(prompt, f"summarize_{title_for_log}", delay_seconds=1.0 + i*0.5)
                summarized_chunks.append(summary_piece)
                if len(summarized_chunks) > 1 and i < len(chunks) -1 : # Add some delay between summary calls
                    await asyncio.sleep(1.0)
            
            final_summary = "\\n\\n---\\n\\n".join(summarized_chunks) # Join summaries with a clear separator
            logger.info(f"Summarized '{title_for_log}': Original length {len(content)}, Summary length {len(final_summary)}")
            return final_summary
        except Exception as e:
            logger.error(f"Error summarizing content for '{title_for_log}': {e}. Returning truncated original.")
            return content[:max_length - 500] # Truncate to be safe


    async def process_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """
        Main processing function for a single campaign.
        Fetches data, generates bio & angles, creates GDocs, and updates PostgreSQL.
        """
        start_time = time.time()
        self.stats["campaigns_processed"] += 1
        campaign_name = "Unknown Campaign" # Default in case of early failure
        
        try:
            campaign_pg = await db_service_pg.get_campaign_by_id(uuid.UUID(campaign_id)) # Use correct service & ensure UUID
            if not campaign_pg:
                logger.error(f"Campaign {campaign_id} not found in PostgreSQL.")
                self.stats["failed_generations"] += 1
                return {"status": "error", "reason": f"Campaign {campaign_id} not found."}

            campaign_name = campaign_pg.get("campaign_name", "Untitled Campaign")
            logger.info(f"Processing campaign: '{campaign_name}' (ID: {campaign_id})")

            mock_interview_input = campaign_pg.get("mock_interview_trancript", "")
            if not mock_interview_input or (isinstance(mock_interview_input, str) and not mock_interview_input.strip()):
                logger.warning(f"Mock interview transcript is missing or empty for campaign {campaign_id}. Cannot proceed.")
                self.stats["failed_generations"] += 1
                return {"status": "skipped", "reason": "Mock interview transcript missing or empty."}
            
            # Fetch content from GDocs if links are provided, or use direct text
            # Mock Interview
            if mock_interview_input.startswith("https://docs.google.com/document/d/"):
                mock_interview_content = await self._get_gdoc_content_async(mock_interview_input, f"{campaign_name} - Mock Interview")
            else:
                mock_interview_content = mock_interview_input # Assume direct text

            # Other supplementary content (these are optional)
            social_posts_input = campaign_pg.get("compiled_social_posts", "")
            social_posts_content = ""
            if social_posts_input:
                if social_posts_input.startswith("https://docs.google.com/document/d/"):
                     social_posts_content = await self._get_gdoc_content_async(social_posts_input, f"{campaign_name} - Social Posts")
                else: # Assume direct text
                    social_posts_content = social_posts_input
            
            podcast_transcripts_content = await self._get_gdoc_content_async(campaign_pg.get("podcast_transcript_link"), f"{campaign_name} - Podcast Transcripts")
            articles_content = await self._get_gdoc_content_async(campaign_pg.get("compiled_articles_link"), f"{campaign_name} - Articles")

            # Summarize if necessary (especially the mock interview)
            # Adjust max_length based on typical Gemini context window and prompt overhead
            summarized_mock_interview = await self._summarize_content_if_needed(mock_interview_content, f"{campaign_name} - Mock Interview", max_length=70000)
            summarized_social = await self._summarize_content_if_needed(social_posts_content, f"{campaign_name} - Social Posts", max_length=30000)
            summarized_podcasts = await self._summarize_content_if_needed(podcast_transcripts_content, f"{campaign_name} - Podcasts", max_length=50000)
            summarized_articles = await self._summarize_content_if_needed(articles_content, f"{campaign_name} - Articles", max_length=50000)

            # 2. Generate Bio and Angles using Gemini
            # Construct the main prompt for Gemini
            # Using the embedded prompt template text
            generation_prompt = self.bio_angles_prompt_template_text.format(campaign_name=campaign_name)
            
            full_prompt_for_gemini = f"""
            Campaign Name: {campaign_name}

            Key Information from Mock Interview:
            {summarized_mock_interview}

            Supplementary Information from Social Media Posts:
            {summarized_social if summarized_social else "Not available."}

            Supplementary Information from Podcast Transcripts:
            {summarized_podcasts if summarized_podcasts else "Not available."}

            Supplementary Information from Articles:
            {summarized_articles if summarized_articles else "Not available."}

            ---
            TASK:
            {generation_prompt}
            """
            
            logger.info(f"Generating Bio & Angles for '{campaign_name}' using Gemini...")
            raw_gemini_output = await self._call_gemini_langchain(full_prompt_for_gemini, "generate_bio_angles", delay_seconds=1.5)

            # 3. Structure the output (e.g., using OpenAI or a more robust Gemini prompt for JSON)
            logger.info(f"Structuring Gemini output for '{campaign_name}'...")
            structured_data = await self._run_in_executor(
                self.openai_service.transform_text_to_structured_data,
                "Parse the following text into a JSON object with two main keys: 'Bio' (string) and 'Angles' (string, containing all angles formatted nicely).", # Adjust prompt as needed
                raw_gemini_output,
                "Structured", # Corrected: data_type to match openai_service.py condition
                "structure_bio_angles" # workflow for AI tracker
            )

            if not structured_data or "Bio" not in structured_data or "Angles" not in structured_data:
                logger.error(f"Failed to structure Bio/Angles output for {campaign_name}. OpenAI output: {structured_data}")
                self.stats["failed_generations"] += 1
                # Store raw output if structuring fails, for manual review
                await db_service_pg.update_campaign(uuid.UUID(campaign_id), {
                    "campaign_bio": f"Structuring failed. Raw output: {raw_gemini_output[:2000]}...",
                    "campaign_angles": "Structuring failed."
                })
                return {"status": "error", "reason": "Failed to structure AI output."}

            bio_text_content = structured_data.get("Bio", "Bio generation failed.")
            angles_text_content = structured_data.get("Angles", "Angles generation failed.")

            # 4. Create Google Docs for Bio and Angles
            logger.info(f"Creating Google Docs for '{campaign_name}'...")
            await asyncio.sleep(1.0) # Small delay
            bio_gdoc_title = f"{campaign_name} - Campaign Bio"
            bio_gdoc_link = await self._run_in_executor(self.google_docs_service.create_document, bio_gdoc_title, bio_text_content)
            if bio_gdoc_link:
                 bio_gdoc_id = extract_document_id(bio_gdoc_link)
                 await self._run_in_executor(self.google_docs_service.share_document, bio_gdoc_id) # Share it
                 logger.info(f"Bio GDoc created and shared: {bio_gdoc_link}")
            else:
                logger.error(f"Failed to create Bio GDoc for {campaign_name}")
                # Handle GDoc creation failure - perhaps proceed without link or log error

            await asyncio.sleep(1.5) # Small delay
            angles_gdoc_title = f"{campaign_name} - Campaign Angles"
            angles_gdoc_link = await self._run_in_executor(self.google_docs_service.create_document, angles_gdoc_title, angles_text_content)
            if angles_gdoc_link:
                angles_gdoc_id = extract_document_id(angles_gdoc_link)
                await self._run_in_executor(self.google_docs_service.share_document, angles_gdoc_id) # Share it
                logger.info(f"Angles GDoc created and shared: {angles_gdoc_link}")
            else:
                logger.error(f"Failed to create Angles GDoc for {campaign_name}")

            # 5. Generate Keywords
            logger.info(f"Generating keywords for '{campaign_name}'...")
            # Using the embedded keyword prompt
            keyword_generation_prompt = self.keyword_prompt_text.format(
                campaign_name=campaign_name,
                bio_content=bio_text_content[:2000], # Use a portion to avoid overly long prompts
                angles_content=angles_text_content[:3000]
            )
            generated_keywords = await self._call_gemini_langchain(keyword_generation_prompt, "generate_keywords", delay_seconds=1.0)
            # Clean up keywords: remove "Keywords:", newlines, excessive spacing.
            cleaned_keywords = generated_keywords.replace("Keywords:", "").strip()
            logger.info(f"Keywords generated for '{campaign_name}': {cleaned_keywords}")
            
            # Convert cleaned_keywords string to a list for TEXT[] compatibility
            # Assuming keywords are comma-separated; adjust if AI returns them differently (e.g., newline-separated)
            keywords_list = [kw.strip() for kw in cleaned_keywords.split(',') if kw.strip()] 
            if not keywords_list and cleaned_keywords: # Handle case where it might be a single keyword or space-separated
                keywords_list = [kw.strip() for kw in cleaned_keywords.split() if kw.strip()]

            # 6. Update PostgreSQL
            update_payload = {
                "campaign_bio": bio_gdoc_link if bio_gdoc_link else "Bio GDoc creation failed",
                "campaign_angles": angles_gdoc_link if angles_gdoc_link else "Angles GDoc creation failed",
                "campaign_keywords": keywords_list # Pass the list of keywords
            }
            logger.info(f"Updating campaign {campaign_id} in PostgreSQL with generated content links and keywords list: {keywords_list}")
            await db_service_pg.update_campaign(uuid.UUID(campaign_id), update_payload)

            self.stats["successful_generations"] += 1
            execution_time = time.time() - start_time
            self.stats["total_execution_time"] += execution_time
            self.stats["execution_times_list"].append(execution_time)
            
            logger.info(f"Successfully processed campaign '{campaign_name}' (ID: {campaign_id}) in {execution_time:.2f}s.")
            return {
                "status": "success", 
                "campaign_id": campaign_id,
                "bio_doc_link": bio_gdoc_link,
                "angles_doc_link": angles_gdoc_link,
                "keywords": keywords_list
            }

        except Exception as e:
            logger.error(f"Unhandled error processing campaign {campaign_id} ('{campaign_name}'): {e}\n{traceback.format_exc()}")
            self.stats["failed_generations"] += 1
            # Attempt to log error to DB campaign record if possible
            try:
                await db_service_pg.update_campaign(uuid.UUID(campaign_id), {
                    "campaign_bio": f"Error during generation: {str(e)[:500]}", # Log a snippet of the error
                    "campaign_angles": "Error during generation."
                })
            except Exception as db_e:
                logger.error(f"Failed to log error to DB for campaign {campaign_id}: {db_e}")
            return {"status": "error", "reason": str(e)}

    def get_stats(self) -> Dict[str, Any]:
        """Returns current processing statistics."""
        avg_time = 0
        if self.stats["execution_times_list"]:
            avg_time = sum(self.stats["execution_times_list"]) / len(self.stats["execution_times_list"])
        
        return {
            "campaigns_processed": self.stats["campaigns_processed"],
            "successful_generations": self.stats["successful_generations"],
            "failed_generations": self.stats["failed_generations"],
            "total_execution_time_seconds": round(self.stats["total_execution_time"], 2),
            "average_execution_time_per_campaign_seconds": round(avg_time, 2),
            "token_usage": self.stats["token_usage"],
            "last_updated": datetime.now().isoformat()
        }

    def cleanup(self):
        """Shuts down the thread pool executor."""
        if hasattr(self, "executor") and self.executor:
            logger.info("Shutting down thread pool executor...")
            self.executor.shutdown(wait=True)
            logger.info("Thread pool executor shut down.")

# Example of how to run this (e.g., from a FastAPI endpoint or a main script)
async def main_process_single_campaign(campaign_id_to_process: str):
    processor = AnglesProcessorPG()
    try:
        result = await processor.process_campaign(campaign_id_to_process)
        print("Processing Result:", result)
    finally:
        processor.cleanup()
        print("Final Stats:", processor.get_stats())

if __name__ == "__main__":
    # This is a placeholder for testing. 
    # You'd typically get campaign_id from a queue, API request, or DB query.
    test_campaign_id = "your_campaign_id_here" # Replace with an actual campaign ID from your DB
    
    if test_campaign_id == "your_campaign_id_here":
        print("Please replace 'your_campaign_id_here' with an actual campaign ID for testing.")
    else:
        asyncio.run(main_process_single_campaign(test_campaign_id)) 