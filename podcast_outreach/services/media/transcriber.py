# podcast_outreach/services/media/transcriber.py

import aiohttp
import logging
import os
import tempfile
from typing import Optional, List, Tuple, Dict, Any
import asyncio
import base64
from pathlib import Path
import pydub
from pydub import AudioSegment
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from urllib.parse import urlparse
import time
from functools import partial
 
# Import modular queries
from podcast_outreach.database.queries import episodes as episode_queries, media as media_queries
from podcast_outreach.database.connection import get_db_pool, close_db_pool # For main function
from podcast_outreach.services.ai.openai_client import OpenAIService # Added for embeddings
from podcast_outreach.services.matches.match_creation import MatchCreationService # Added for triggering matching
from podcast_outreach.database.queries import campaigns as campaign_queries # Added for fetching campaigns
from podcast_outreach.services.enrichment.quality_score import QualityService
from podcast_outreach.database.models.media_models import EnrichedPodcastProfile
from podcast_outreach.config import ORCHESTRATOR_CONFIG

# Configure logging for the MediaTranscriber class
logger = logging.getLogger(__name__)
 
# --- Global FFmpeg/FFprobe Configuration ---
FFMPEG_PATH = os.getenv("FFMPEG_CUSTOM_PATH", r"C:\ffmpeg\bin\ffmpeg.exe")
FFPROBE_PATH = os.getenv("FFPROBE_CUSTOM_PATH", r"C:\ffmpeg\bin\ffprobe.exe")
 
if os.path.exists(FFMPEG_PATH):
    AudioSegment.converter = FFMPEG_PATH
    logger.info(f"Using ffmpeg at: {FFMPEG_PATH}")
else:
    logger.warning(f"ffmpeg not found at {FFMPEG_PATH}. Using system default if available.")
 
if os.path.exists(FFPROBE_PATH):
    pydub.utils.get_prober_name = lambda: FFPROBE_PATH
    logger.info(f"Using ffprobe at: {FFPROBE_PATH}")
else:
    logger.warning(f"ffprobe not found at {FFPROBE_PATH}. Using system default if available.")
 
# --- MediaTranscriber Class ---
class MediaTranscriber:
    """Utility class for downloading and transcribing podcast audio using Gemini."""
 
    # Concurrency / Rate-limit Configuration
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # Seconds between Gemini retries
 
    # Maximum number of parallel chunk transcriptions for a single long audio file.
    MAX_CHUNK_CONCURRENCY = int(os.getenv("CHUNK_CONCURRENCY", "20"))
 
    # Maximum duration for an audio file to be processed as a single chunk (in minutes).
    MAX_SINGLE_CHUNK_DURATION_MINUTES = 60
 
    # Default chunk size for long audio files (in minutes)
    DEFAULT_CHUNK_MINUTES = 45
    # Default overlap between chunks (in seconds)
    DEFAULT_OVERLAP_SECONDS = 30
    # Max characters of transcript to use for embedding
    MAX_TRANSCRIPT_CHARS_FOR_EMBEDDING = 10000
 
    def __init__(self, api_key: Optional[str] = None):
        """
        Initializes the MediaTranscriber with Gemini API configuration.
        """
        self._model: Optional[genai.GenerativeModel] = None
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self._api_key:
            logger.error("GEMINI_API_KEY environment variable not set or api_key not provided.")
            raise ValueError("Please set the GEMINI_API_KEY environment variable or provide it to the constructor.")
 
        self._openai_service = OpenAIService() # Initialize OpenAIService
        self._gemini_api_semaphore = asyncio.Semaphore(int(os.getenv("GEMINI_API_CONCURRENCY", "10")))
 
        self._setup_gemini_api()
        logger.info("MediaTranscriber initialized.")
 
    def _setup_gemini_api(self):
        """Set up the Gemini API with authentication."""
        genai.configure(api_key=self._api_key)
        self._model = genai.GenerativeModel('gemini-1.5-flash-001')
        logger.info("Gemini API configured.")
 
    async def download_audio(self, url: str) -> str:
        """
        Download an audio file from a URL and return the local path.
        Includes robust headers and error handling.
        """
        parsed_url = urlparse(url)
        url_path = parsed_url.path
        file_extension = os.path.splitext(url_path)[1] or ".mp3"
 
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
        tmp_path = tmp_file.name
        tmp_file.close()
 
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'audio/webm,audio/ogg,audio/mp3,audio/wav,audio/*;q=0.9,application/ogg;q=0.7,video/*;q=0.6,*/*;q=0.5',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.buzzsprout.com/',
            'DNT': '1',
            'Connection': 'keep-alive',
        }
 
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url) as resp:
                    resp.raise_for_status()
                    with open(tmp_path, "wb") as f:
                        while True:
                            chunk = await resp.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
            logger.info("Downloaded audio from %s to %s", url, tmp_path)
            return tmp_path
        except aiohttp.ClientError as e:
            logger.error(f"Failed to download audio from {url}: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred during download from {url}: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            raise
 
    async def _process_audio_file_for_gemini(self, file_path: str) -> dict:
        """
        Reads an audio file and prepares its content for the Gemini API.
        This involves synchronous file I/O and base64 encoding, so it's run in a thread.
        """
        return await asyncio.to_thread(self.__sync_process_audio_file_for_gemini, file_path)
 
    def __sync_process_audio_file_for_gemini(self, file_path: str) -> dict:
        """Synchronous helper for _process_audio_file_for_gemini."""
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")
 
        extension = path.suffix.lower()
        mime_map = {
            '.mp3': 'audio/mp3',
            '.wav': 'audio/wav',
            '.flac': 'audio/flac',
            '.m4a': 'audio/mp4',
            '.aac': 'audio/aac',
        }
        mime_type = mime_map.get(extension)
        if not mime_type:
            raise ValueError(f"Unsupported audio format: {extension}")
 
        logger.debug(f"Loading audio file: {file_path} ({mime_type})")
        with open(file_path, 'rb') as f:
            audio_data = f.read()
 
        return {
            "mime_type": mime_type,
            "data": base64.b64encode(audio_data).decode('utf-8')
        }
 
    async def _transcribe_gemini_api_call(
        self,
        audio_content: dict,
        episode_name: Optional[str] = None,
        speakers: Optional[List[str]] = None,
        chunk_id: Optional[int] = None
    ) -> str:
        """
        Performs the actual Gemini API call for transcription with retries and concurrency control.
        """
        if not self._model:
            raise RuntimeError("Gemini model not initialized. Call _setup_gemini_api first.")
 
        chunk_info = f" (chunk {chunk_id})" if chunk_id is not None else ""
        prompt = "Transcribe this podcast with speaker labels and timestamps in [HH:MM:SS] format. " \
                 "Listen for speaker names mentioned in the conversation and use those real names as speaker labels. " \
                 "If a speaker's name isn't mentioned, label them as 'Host', 'Guest','Narrator' etc. or 'Speaker 1', 'Speaker 2', etc."
        if speakers:
            speakers_str = ", ".join(speakers)
            prompt += f" Identify speakers as: {speakers_str}."
        if episode_name:
            prompt += f" This is an episode titled '{episode_name}'."
        prompt += " Format as [HH:MM:SS] Speaker: Text"
 
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.info(f"Sending transcription request{chunk_info} (attempt {attempt+1}/{self.MAX_RETRIES})...")
                async with self._gemini_api_semaphore: # Limit concurrent API calls
                    response = await self._model.generate_content_async(
                        [audio_content, prompt],
                        generation_config={"temperature": 0.1})
                logger.info(f"Transcription complete{chunk_info}")
                return response.text
            except (ResourceExhausted, ServiceUnavailable) as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"API error{chunk_info}: {e}. Retrying in {self.RETRY_DELAY} seconds...")
                    await asyncio.sleep(self.RETRY_DELAY)
                else:
                    logger.error(f"Failed to transcribe{chunk_info} after {self.MAX_RETRIES} attempts: {e}")
                    raise
            except Exception as e:
                logger.error(f"An unexpected error occurred during Gemini API call{chunk_info}: {e}")
                raise
 
    async def _process_audio_chunk(
        self,
        chunk_index: int,
        audio_segment: AudioSegment,
        total_chunks: int,
        chunk_length_ms: int,
        overlap_ms: int,
        file_suffix: str,
        episode_name: Optional[str],
        speakers: Optional[List[str]]
    ) -> tuple[int, str]:
        """
        Processes a single audio chunk: exports it to a temp file, prepares for Gemini, and transcribes.
        Synchronous pydub operations are run in a thread.
        """
        try:
            logger.info(f"Processing chunk {chunk_index+1} of {total_chunks}")
 
            start_ms = max(chunk_index * chunk_length_ms - overlap_ms, 0) if chunk_index > 0 else 0
            end_ms = min((chunk_index + 1) * chunk_length_ms, len(audio_segment))
            chunk = audio_segment[start_ms:end_ms]
 
            temp_path = None
            try:
                temp_file = tempfile.NamedTemporaryFile(suffix=file_suffix, delete=False)
                temp_path = temp_file.name
                temp_file.close()
 
                await asyncio.to_thread(chunk.export, temp_path, format="mp3")
                logger.debug(f"Exported chunk {chunk_index+1} to {temp_path}")
 
                audio_content = await self._process_audio_file_for_gemini(temp_path)
                chunk_transcript = await self._transcribe_gemini_api_call(
                    audio_content,
                    f"{episode_name} - Part {chunk_index+1}" if episode_name else f"Chunk {chunk_index+1}",
                    speakers,
                    chunk_id=chunk_index+1
                )
                return chunk_index, chunk_transcript
            finally:
                if temp_path and os.path.exists(temp_path):
                    os.remove(temp_path)
                    logger.debug(f"Removed temporary file: {temp_path}")
 
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_index+1}: {e}", exc_info=True)
            return chunk_index, f"ERROR in chunk {chunk_index+1}: {str(e)}"
 
    async def _process_long_audio(
        self,
        file_path: str,
        chunk_minutes: int,
        overlap_seconds: int,
        episode_name: Optional[str] = None,
        speakers: Optional[List[str]] = None
    ) -> str:
        """
        Processes a long audio file by splitting it into manageable chunks and transcribing them concurrently.
        """
        logger.info(f"Processing long audio file: {file_path} (chunk size: {chunk_minutes} minutes, overlap: {overlap_seconds} seconds)")
 
        audio = await asyncio.to_thread(AudioSegment.from_file, file_path)
        chunk_length_ms = chunk_minutes * 60 * 1000
        overlap_ms = overlap_seconds * 1000
        total_chunks = len(audio) // chunk_length_ms + (1 if len(audio) % chunk_length_ms > 0 else 0)
 
        logger.info(f"Audio length: {len(audio)/1000/60:.2f} minutes, will be split into {total_chunks} chunks")
 
        file_suffix = Path(file_path).suffix
 
        tasks = []
        for i in range(total_chunks):
            tasks.append(
                self._process_audio_chunk(
                    chunk_index=i,
                    audio_segment=audio,
                    total_chunks=total_chunks,
                    chunk_length_ms=chunk_length_ms,
                    overlap_ms=overlap_ms,
                    file_suffix=file_suffix,
                    episode_name=episode_name,
                    speakers=speakers
                )
            )
 
        chunk_semaphore = asyncio.Semaphore(self.MAX_CHUNK_CONCURRENCY)
 
        async def run_task_with_semaphore(task_coro):
            async with chunk_semaphore:
                return await task_coro
 
        completed_tasks = await asyncio.gather(*(run_task_with_semaphore(task) for task in tasks))
 
        results = []
        for chunk_index, transcript in completed_tasks:
            results.append((chunk_index, transcript))
            if "ERROR in chunk" not in transcript:
                logger.info(f"Completed chunk {chunk_index+1}/{total_chunks}")
            else:
                logger.error(f"Chunk {chunk_index+1}/{total_chunks} failed: {transcript}")
 
        results.sort(key=lambda x: x[0])
        transcripts = [transcript for _, transcript in results]
 
        logger.info(f"Completed processing all {total_chunks} chunks")
        return "\n\n".join(transcripts)
 
    async def transcribe_audio(
        self,
        audio_path: str,
        episode_id: int, # Added episode_id
        episode_title: Optional[str] = None,
        speakers: Optional[List[str]] = None
    ) -> Tuple[str, Optional[str], Optional[List[float]]]: # Return transcript, summary, embedding
        """
        Transcribe audio using Gemini. Handles both short and long audio files by chunking.
        Also generates a summary and an embedding for the episode.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found at: {audio_path}")
 
        logger.info(f"Starting transcription for episode_id {episode_id}, audio_path {audio_path}")
        transcript = ""
        summary = None
        embedding = None
 
        try:
            audio = await asyncio.to_thread(AudioSegment.from_file, audio_path)
            duration_minutes = len(audio) / (60 * 1000)
            logger.info(f"Audio duration: {duration_minutes:.2f} minutes for episode_id {episode_id}")
 
            if duration_minutes > self.MAX_SINGLE_CHUNK_DURATION_MINUTES:
                logger.info(f"Long audio detected ({duration_minutes:.2f} min > {self.MAX_SINGLE_CHUNK_DURATION_MINUTES} min) for ep {episode_id}, processing in parallel chunks")
                transcript = await self._process_long_audio(
                    audio_path,
                    chunk_minutes=self.DEFAULT_CHUNK_MINUTES,
                    overlap_seconds=self.DEFAULT_OVERLAP_SECONDS,
                    episode_name=episode_title,
                    speakers=speakers
                )
            else:
                logger.info(f"Processing audio as a single file ({duration_minutes:.2f} min) for episode_id {episode_id}")
                audio_content = await self._process_audio_file_for_gemini(audio_path)
                transcript = await self._transcribe_gemini_api_call(audio_content, episode_title, speakers)
 
            if "ERROR in chunk" in transcript:
                logger.error(f"Transcription completed with errors in some chunks for episode_id {episode_id}. Review transcript for 'ERROR in chunk' messages.")
            else:
                logger.info(f"Transcription completed successfully for episode_id {episode_id}")
 
            # Generate summary
            if transcript and not "ERROR in chunk" in transcript: # Only summarize if transcription was somewhat successful
                summary = await self.summarize_transcript(transcript)
                logger.info(f"Summary generated for episode_id {episode_id}")
 
                # Generate embedding
                embedding_text_parts = []
                if episode_title:
                    embedding_text_parts.append(episode_title)
                if summary:
                    embedding_text_parts.append(summary)
                
                # Add first N chars of transcript if available and not only errors
                # Check if transcript is not just error messages before appending
                meaningful_transcript_segment = transcript[:self.MAX_TRANSCRIPT_CHARS_FOR_EMBEDDING]
                if transcript and not all("ERROR in chunk" in line for line in transcript.split('\n') if line.strip()):
                     embedding_text_parts.append(meaningful_transcript_segment)
 
                if embedding_text_parts:
                    embedding_text = " \n\n ".join(embedding_text_parts)
                    logger.info(f"Generating embedding for episode_id {episode_id} from text (first 200 chars): '{embedding_text[:200]}...'")
                    embedding = await self._openai_service.get_embedding(
                        text=embedding_text,
                        workflow="episode_embedding",
                        related_ids={"episode_id": episode_id}
                    )
                    if embedding:
                        logger.info(f"Embedding generated successfully for episode_id {episode_id}")
                    else:
                        logger.error(f"Failed to generate embedding for episode_id {episode_id}")
                else:
                    logger.warning(f"Not enough content to generate embedding for episode_id {episode_id}")
 
            return transcript, summary, embedding
 
        except ValueError as e:
            error_str = str(e).lower()
            if "finish_reason" in error_str and ("is 4" in error_str or "is 3" in error_str or "recitation" in error_str or "safety" in error_str):
                logger.warning(f"Content policy violation detected during transcription for {audio_path}: {e}")
                raise ValueError("Content Policy Violation: " + str(e)) from e
            else:
                logger.error(f"ValueError during transcription for {audio_path}: {e}", exc_info=True)
                raise
        except Exception as e:
            logger.error(f"Unexpected error during transcription for {audio_path}: {e}", exc_info=True)
            raise
 
    async def summarize_transcript(self, transcript: str) -> str:
        """
        Summarize a transcript using Gemini.
        """
        logger.info("Summarizing transcript (%d chars)", len(transcript))
        if not self._model:
            raise RuntimeError("Gemini model not initialized. Call _setup_gemini_api first.")
 
        prompt = f"Summarize the following transcript:\n\n{transcript}\n\nSummary:"
        try:
            async with self._gemini_api_semaphore:
                response = await self._model.generate_content_async(
                    [prompt],
                    generation_config={"temperature": 0.2, "max_output_tokens": 500}
                )
            summary = response.text
            logger.info("Summary generated successfully.")
            return summary
        except Exception as e:
            logger.error(f"Error summarizing transcript: {e}", exc_info=True)
            summary = transcript[:500] + "..." if len(transcript) > 500 else transcript
            logger.warning("Failed to get Gemini summary, returning truncated transcript.")
            return summary

async def process_single_episode_for_transcription(
    transcriber: MediaTranscriber, 
    episode: Dict[str, Any],
    media_analyzer_service: Optional[Any] = None,
    match_creation_service: Optional[MatchCreationService] = None # Added MatchCreationService instance
) -> None:
    logger.info(f"Processing episode_id: {episode['episode_id']} - '{episode['title']}' from media_id: {episode['media_id']}")
    local_audio_path = None
    try:
        local_audio_path = await transcriber.download_audio(episode["episode_url"])
        transcript, summary, embedding = await transcriber.transcribe_audio(
            local_audio_path, 
            episode_id=episode["episode_id"], 
            episode_title=episode["title"]
        )

        # Update episode with transcript, summary, and embedding
        updated_episode = await episode_queries.update_episode_transcription(
            episode_id=episode["episode_id"],
            transcript=transcript,
            summary=summary,
            embedding=embedding
        )
        logger.info(f"Successfully transcribed and updated episode {episode['episode_id']}")

        # If episode was successfully updated with an embedding, trigger matching for its media_id
        if updated_episode and updated_episode.get('embedding') and match_creation_service:
            media_id_for_match = updated_episode.get('media_id')
            if media_id_for_match:
                try:
                    logger.info(f"Triggering match creation for media_id {media_id_for_match} due to new/updated episode {episode['episode_id']}.")
                    # Fetch all active campaigns with embeddings to match against
                    # This is an example, you might want more specific filtering for campaigns
                    active_campaigns, total_campaigns = await campaign_queries.get_campaigns_with_embeddings(limit=200, offset=0) 
                    
                    if active_campaigns:
                        logger.info(f"Media {media_id_for_match} will be matched against {len(active_campaigns)} campaigns.")
                        await match_creation_service.create_and_score_match_suggestions_for_media(
                            media_id=media_id_for_match,
                            campaign_records=active_campaigns
                        )
                        logger.info(f"Match creation/update process initiated for media {media_id_for_match}.")
                    else:
                        logger.info(f"No active campaigns with embeddings found to match against media {media_id_for_match}.")
                except Exception as e_match_media:
                    logger.error(f"Error triggering match creation for media {media_id_for_match}: {e_match_media}", exc_info=True)
            else:
                logger.warning(f"Updated episode {episode['episode_id']} has no media_id, cannot trigger matching.")

        # If MediaAnalyzerService is provided and transcription was successful
        if media_analyzer_service and transcript and not "ERROR in chunk" in transcript:
            logger.info(f"Analyzing episode {episode['episode_id']} with MediaAnalyzerService.")
            try:
                analysis_result = await media_analyzer_service.analyze_episode(
                    transcript=transcript,
                    episode_title=episode.get("title"),
                    # Pass other relevant details if your analyzer uses them, e.g., episode_summary
                )
                if analysis_result:
                    await episode_queries.update_episode_analysis_data(
                        episode_id=episode["episode_id"],
                        host_names=analysis_result.get("host_names_identified"),
                        guest_names=analysis_result.get("guest_names_identified"),
                        episode_themes=analysis_result.get("episode_themes"),
                        episode_keywords=analysis_result.get("episode_keywords"),
                        ai_analysis_done=True
                    )
                    logger.info(f"Successfully updated analysis data for episode {episode['episode_id']}")
                else:
                    logger.warning(f"MediaAnalyzerService returned no result for episode {episode['episode_id']}")
            except Exception as e_analyze:
                logger.error(f"Error during MediaAnalyzerService processing for episode {episode['episode_id']}: {e_analyze}", exc_info=True)

        # --- NEW LOGIC: Trigger quality score update ---
        if updated_episode: # Check if the DB update was successful
            media_id_for_quality_check = updated_episode.get('media_id')
            if media_id_for_quality_check:
                try:
                    # Check if the podcast now meets the criteria for scoring
                    transcribed_count = await media_queries.count_transcribed_episodes_for_media(media_id_for_quality_check)
                    
                    # Use the threshold from your config
                    min_episodes_needed = ORCHESTRATOR_CONFIG.get("quality_score_min_transcribed_episodes", 3)

                    if transcribed_count >= min_episodes_needed:
                        logger.info(f"Media {media_id_for_quality_check} now has {transcribed_count} transcribed episodes. Triggering quality score update.")
                        
                        # Fetch the full, updated media record for scoring
                        media_data_for_scoring = await media_queries.get_media_by_id_from_db(media_id_for_quality_check)
                        
                        if media_data_for_scoring:
                            quality_service = QualityService()
                            profile = EnrichedPodcastProfile(**media_data_for_scoring)
                            score, _ = quality_service.calculate_podcast_quality_score(profile)
                            
                            if score is not None:
                                await media_queries.update_media_quality_score(media_id_for_quality_check, score)
                                logger.info(f"Automatically updated quality score for media {media_id_for_quality_check} to {score}.")
                        else:
                            logger.warning(f"Could not fetch media data for {media_id_for_quality_check} to update quality score.")
                    else:
                        logger.info(f"Media {media_id_for_quality_check} has {transcribed_count}/{min_episodes_needed} transcribed episodes. Deferring quality score update.")

                except Exception as e_quality:
                    logger.error(f"Error during automatic quality score update for media {media_id_for_quality_check}: {e_quality}", exc_info=True)
        # --- END OF NEW LOGIC ---

    except FileNotFoundError:
        logger.error(f"File not found for episode_id {episode['episode_id']}: {episode['episode_url']}")
    except Exception as e:
        logger.error(f"Error processing episode_id {episode['episode_id']}: {e}", exc_info=True)

async def main_transcribe_orchestrator(limit: int = 20, use_analyzer: bool = True): # Added use_analyzer flag
    logger.info("--- Starting Episode Transcription and Analysis Process ---")
    await get_db_pool()

    transcriber = MediaTranscriber()
    match_creation_serv = MatchCreationService() # Instantiate MatchCreationService
    media_analyzer = None
    if use_analyzer:
        try:
            from podcast_outreach.services.media.analyzer import MediaAnalyzerService # Import here to avoid circular deps if analyzer uses transcriber models
            media_analyzer = MediaAnalyzerService() # Initialize your analyzer
            logger.info("MediaAnalyzerService initialized.")
        except ImportError as e:
            logger.warning(f"Could not import MediaAnalyzerService: {e}. Analysis will be skipped.")
        except Exception as e_analyzer_init:
            logger.error(f"Could not initialize MediaAnalyzerService: {e_analyzer_init}. Analysis will be skipped.")

    episodes_to_process = await episode_queries.fetch_episodes_for_transcription(limit=limit)

    if not episodes_to_process:
        logger.info("No episodes to process.")
        return

    transcription_tasks = [
        process_single_episode_for_transcription(transcriber, episode, media_analyzer, match_creation_serv) # Pass services
        for episode in episodes_to_process
    ]

    await asyncio.gather(*transcription_tasks)

if __name__ == "__main__":
    # Example of how to run the orchestrator
    # asyncio.run(main_transcribe_orchestrator(limit=5))
    # To run with analyzer (assuming it's set up):
    asyncio.run(main_transcribe_orchestrator(limit=5, use_analyzer=True)) # Example with analyzer
