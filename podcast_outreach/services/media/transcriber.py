# podcast_outreach/services/media/transcriber.py

import aiohttp
import requests
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
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable, DeadlineExceeded, InternalServerError
from urllib.parse import urlparse
import time
import functools
import uuid
import contextlib
import random

# Custom exception for permanent audio errors
class AudioNotFoundError(Exception):
    """Raised when audio URL returns 404 or other permanent error"""
    pass

# Project-specific imports
from podcast_outreach.database.queries import episodes as episode_queries, media as media_queries, campaigns as campaign_queries
from podcast_outreach.services.ai.openai_client import OpenAIService
from podcast_outreach.services.matches.match_creation import MatchCreationService
from podcast_outreach.services.enrichment.quality_score import QualityService
from podcast_outreach.database.models.media_models import EnrichedPodcastProfile
from podcast_outreach.config import ORCHESTRATOR_CONFIG, FFMPEG_PATH, FFPROBE_PATH
from podcast_outreach.utils.memory_monitor import check_memory_usage, memory_guard, cleanup_memory

logger = logging.getLogger(__name__)

# --- Global Concurrency Control ---
GLOBAL_TRANSCRIPTION_SEMAPHORE = asyncio.Semaphore(int(os.getenv("GLOBAL_TRANSCRIPTION_LIMIT", "3")))

# --- Global FFmpeg/FFprobe Configuration ---
if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
    AudioSegment.converter = FFMPEG_PATH
    logger.info(f"Using ffmpeg at: {FFMPEG_PATH}")
else:
    logger.warning(f"ffmpeg not found at configured path or path not set. Using system default if available.")

if FFPROBE_PATH and os.path.exists(FFPROBE_PATH):
    pydub.utils.get_prober_name = lambda: FFPROBE_PATH
    logger.info(f"Using ffprobe at: {FFPROBE_PATH}")
else:
    logger.warning(f"ffprobe not found at configured path or path not set. Using system default if available.")


@contextlib.contextmanager
def temp_audio_file(suffix=".mp3"):
    """Context manager for temporary audio files with guaranteed cleanup."""
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    tmp_path = tmp_file.name
    tmp_file.close()
    try:
        yield tmp_path
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
                logger.debug(f"Cleaned up temp file: {tmp_path}")
            except Exception as e:
                logger.error(f"Failed to clean up temp file {tmp_path}: {e}")


class MediaTranscriber:
    """Utility class for downloading and transcribing podcast audio using Gemini."""

    MAX_RETRIES = 3
    RETRY_DELAY = 5
    MAX_CHUNK_CONCURRENCY = int(os.getenv("CHUNK_CONCURRENCY", "3"))  # Reduced from 10 to 3
    MAX_SINGLE_CHUNK_DURATION_MINUTES = 59 # Gemini 1.5 has a 1-hour limit per file
    DEFAULT_CHUNK_MINUTES = 45
    DEFAULT_OVERLAP_SECONDS = 30
    MAX_TRANSCRIPT_CHARS_FOR_EMBEDDING = 10000

    def __init__(self, api_key: Optional[str] = None):
        self._model: Optional[genai.GenerativeModel] = None
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self._api_key:
            raise ValueError("GEMINI_API_KEY is required.")
        
        self._openai_service = OpenAIService()
        self._gemini_api_semaphore = asyncio.Semaphore(int(os.getenv("GEMINI_API_CONCURRENCY", "3")))  # Reduced from 10 to 3
        self._setup_gemini_api()
        logger.info("MediaTranscriber initialized.")

    def _setup_gemini_api(self):
        genai.configure(api_key=self._api_key)
        self._model = genai.GenerativeModel('gemini-1.5-flash-latest')
        logger.info("Gemini API configured for MediaTranscriber.")

    async def download_audio(self, url: str, episode_id: Optional[int] = None) -> Optional[str]:
        """Download audio file from URL using a fallback approach.
        
        Raises:
            AudioNotFoundError: If the audio URL returns 404 (file not found)
        """
        return await asyncio.to_thread(self._download_audio_sync, url)

    def _download_audio_sync(self, url: str) -> Optional[str]:
        """Synchronous download using requests library with proper cleanup."""
        parsed_url = urlparse(url)
        file_extension = os.path.splitext(parsed_url.path)[1] or ".mp3"
        
        tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_extension)
        tmp_path = tmp_file.name
        tmp_file.close()
        
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        download_successful = False
        
        try:
            # Check file size BEFORE download
            head_resp = session.head(url, allow_redirects=True, timeout=30)
            logger.info(f"HEAD request status: {head_resp.status_code}, final URL: {head_resp.url}")
            
            # Check Content-Length if available
            content_length = head_resp.headers.get('content-length')
            if content_length:
                file_size_mb = int(content_length) / (1024 * 1024)
                MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "500"))
                
                if file_size_mb > MAX_FILE_SIZE_MB:
                    raise ValueError(f"File too large: {file_size_mb:.1f} MB (max: {MAX_FILE_SIZE_MB} MB)")
                
                logger.info(f"File size from HEAD: {file_size_mb:.1f} MB")
            
            # Download the file
            response = session.get(url, allow_redirects=True, timeout=600, stream=True)
            response.raise_for_status()
            
            logger.info(f"Download response status: {response.status_code}, content-type: {response.headers.get('content-type', 'unknown')}")
            
            # Download in chunks
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(tmp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and downloaded % (5 * 1024 * 1024) == 0:  # Log every 5MB
                            progress = (downloaded / total_size) * 100
                            logger.debug(f"Download progress: {progress:.1f}% ({downloaded}/{total_size} bytes)")
            
            # Validate downloaded file
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) < 1024:
                raise ValueError(f"Downloaded file is too small or doesn't exist: {tmp_path}")
            
            file_size = os.path.getsize(tmp_path)
            logger.info(f"Successfully downloaded audio from {url} to {tmp_path} (size: {file_size} bytes)")
            
            download_successful = True
            return tmp_path
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error downloading from {url}: {e}")
            if hasattr(e, 'response'):
                if e.response.status_code == 404:
                    logger.error(f"404 Not Found - Audio file does not exist at URL: {url}")
                    raise AudioNotFoundError(f"Audio not found (404): {url}")
                elif e.response.status_code == 403:
                    logger.error("403 Forbidden - access denied")
            return None
            
        except Exception as e:
            logger.error(f"Error downloading audio from {url}: {e}")
            return None
            
        finally:
            session.close()
            
            # CRITICAL FIX: Always clean up temp file if download wasn't successful
            if not download_successful and tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                    logger.debug(f"Cleaned up failed download temp file: {tmp_path}")
                except Exception as cleanup_error:
                    logger.error(f"Failed to clean up temp file {tmp_path}: {cleanup_error}")

    async def _refresh_episode_audio_url(self, episode_id: int) -> Optional[str]:
        """
        Attempts to refresh the audio URL for an episode by re-fetching from the source API.
        This is useful when URLs expire (common with Acast and other dynamic hosting services).
        """
        try:
            from podcast_outreach.services.media.episode_handler import EpisodeHandlerService
            from podcast_outreach.database.queries import episodes as episode_queries, media as media_queries
            from podcast_outreach.database.connection import get_db_pool
            
            pool = await get_db_pool()
            
            # Get episode and media information
            episode_data = await episode_queries.get_episode_by_id(episode_id, pool)
            if not episode_data:
                logger.error(f"Episode {episode_id} not found in database")
                return None
                
            media_id = episode_data.get('media_id')
            api_episode_id = episode_data.get('api_episode_id')
            
            if not media_id or not api_episode_id:
                logger.error(f"Episode {episode_id} missing media_id or api_episode_id")
                return None
                
            # Get media record to determine source API
            media_record = await media_queries.get_media_by_id_from_db(media_id)
            if not media_record:
                logger.error(f"Media {media_id} not found in database")
                return None
                
            source_api = media_record.get('source_api')
            api_id = media_record.get('api_id')
            
            if not source_api or not api_id:
                logger.error(f"Media {media_id} missing source_api or api_id")
                return None
                
            # Re-fetch episode data from source API
            episode_handler = EpisodeHandlerService()
            fresh_episodes = await episode_handler._fetch_episodes_from_source(media_record, 50)  # Get more episodes to find the right one
            
            # Find the matching episode by api_episode_id
            for fresh_episode in fresh_episodes:
                fresh_api_id = fresh_episode.get('id') if source_api == "ListenNotes" else fresh_episode.get('episode_id')
                if str(fresh_api_id) == str(api_episode_id):
                    # Extract the fresh audio URL
                    if source_api == "ListenNotes":
                        fresh_audio_url = fresh_episode.get('audio') or fresh_episode.get('enclosure_url')
                    elif source_api == "PodscanFM":
                        fresh_audio_url = fresh_episode.get('episode_audio_url')
                    else:
                        logger.error(f"Unknown source_api: {source_api}")
                        return None
                        
                    if fresh_audio_url:
                        # Update the episode record with the fresh URL
                        await episode_queries.update_episode_audio_url(episode_id, fresh_audio_url, pool)
                        logger.info(f"Refreshed audio URL for episode {episode_id}: {fresh_audio_url}")
                        return fresh_audio_url
                    else:
                        logger.warning(f"Fresh episode data for {api_episode_id} has no audio URL")
                        return None
                        
            logger.warning(f"Could not find episode {api_episode_id} in fresh data from {source_api}")
            return None
            
        except Exception as e:
            logger.error(f"Error refreshing audio URL for episode {episode_id}: {e}", exc_info=True)
            return None

    async def _process_audio_file_for_gemini(self, file_path: str) -> dict:
        return await asyncio.to_thread(self.__sync_process_audio_file_for_gemini, file_path)

    def __sync_process_audio_file_for_gemini(self, file_path: str) -> dict:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {file_path}")
        
        extension = path.suffix.lower()
        mime_map = {'.mp3': 'audio/mp3', '.wav': 'audio/wav', '.flac': 'audio/flac', '.m4a': 'audio/mp4', '.aac': 'audio/aac'}
        
        # Check if we need to convert MP4 to MP3
        if extension == '.mp4':
            logger.info(f"Converting MP4 to MP3 for Gemini compatibility: {file_path}")
            try:
                # Load the MP4 file using pydub
                audio = AudioSegment.from_file(file_path, format="mp4")
                
                # Create a temporary MP3 file
                with temp_audio_file(suffix=".mp3") as temp_mp3_path:
                    # Export as MP3
                    audio.export(temp_mp3_path, format="mp3")
                    logger.info(f"Successfully converted MP4 to MP3: {temp_mp3_path}")
                    
                    # Process the converted MP3 file
                    with open(temp_mp3_path, 'rb') as f:
                        audio_data = f.read()
                    
                    return {"mime_type": "audio/mp3", "data": base64.b64encode(audio_data).decode('utf-8')}
                    
            except Exception as e:
                logger.error(f"Failed to convert MP4 to MP3: {e}")
                raise ValueError(f"Failed to process MP4 file: {e}")
        
        # For other supported formats, process normally
        mime_type = mime_map.get(extension)
        if not mime_type:
            raise ValueError(f"Unsupported audio format: {extension}")
        
        with open(file_path, 'rb') as f:
            audio_data = f.read()
        
        return {"mime_type": mime_type, "data": base64.b64encode(audio_data).decode('utf-8')}

    async def _transcribe_gemini_api_call(self, audio_content: dict, episode_name: Optional[str] = None, chunk_id: Optional[int] = None) -> str:
        if not self._model:
            raise RuntimeError("Gemini model not initialized.")
        
        chunk_info = f" (chunk {chunk_id})" if chunk_id is not None else ""
        prompt = "Transcribe this podcast with speaker labels and timestamps in [HH:MM:SS] format. If a speaker's name isn't mentioned, label them as 'Host', 'Guest', or 'Speaker 1', 'Speaker 2', etc."
        
        retry_delay = self.RETRY_DELAY
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.info(f"Sending transcription request{chunk_info} (attempt {attempt+1}/{self.MAX_RETRIES})...")
                async with self._gemini_api_semaphore:
                    # Apply timeout using asyncio.wait_for
                    try:
                        response = await asyncio.wait_for(
                            self._model.generate_content_async(
                                [audio_content, prompt], 
                                generation_config={"temperature": 0.1}
                            ),
                            timeout=600  # 10 minute timeout for transcription
                        )
                    except asyncio.TimeoutError:
                        raise DeadlineExceeded(f"Transcription timed out after 600 seconds{chunk_info}")
                logger.info(f"Transcription complete{chunk_info}")
                return response.text
            except (ResourceExhausted, ServiceUnavailable, DeadlineExceeded, InternalServerError) as e:
                # Check if it's a retriable error
                is_retriable = True
                if isinstance(e, DeadlineExceeded) and '504' in str(e):
                    logger.warning(f"Thread cancellation error{chunk_info}: {e}")
                elif isinstance(e, ServiceUnavailable) and 'overloaded' in str(e).lower():
                    logger.warning(f"Model overloaded{chunk_info}: {e}")
                
                if attempt < self.MAX_RETRIES - 1 and is_retriable:
                    # Exponential backoff with jitter
                    jitter = random.uniform(0, retry_delay * 0.3)
                    actual_delay = retry_delay + jitter
                    
                    logger.warning(f"Retriable API error{chunk_info}: {e}. Retrying in {actual_delay:.2f} seconds...")
                    await asyncio.sleep(actual_delay)
                    retry_delay = min(retry_delay * 2, 60)  # Cap at 60 seconds
                else:
                    logger.error(f"Failed to transcribe{chunk_info} after {self.MAX_RETRIES} attempts: {e}")
                    raise
            except Exception as e:
                # Check if it's a known retriable error pattern
                error_str = str(e).lower()
                if ('503' in error_str or '504' in error_str or 'overloaded' in error_str or 
                    'timeout' in error_str or 'deadline' in error_str):
                    if attempt < self.MAX_RETRIES - 1:
                        jitter = random.uniform(0, retry_delay * 0.3)
                        actual_delay = retry_delay + jitter
                        
                        logger.warning(f"Retriable error pattern detected{chunk_info}: {e}. Retrying in {actual_delay:.2f} seconds...")
                        await asyncio.sleep(actual_delay)
                        retry_delay = min(retry_delay * 2, 60)
                        continue
                
                logger.error(f"An unexpected error occurred during Gemini API call{chunk_info}: {e}")
                raise

    async def _process_audio_chunk(self, chunk_index: int, audio_segment: AudioSegment, total_chunks: int, chunk_length_ms: int, overlap_ms: int, file_suffix: str, episode_name: Optional[str]) -> tuple[int, str]:
        try:
            logger.info(f"Processing chunk {chunk_index+1} of {total_chunks}")
            start_ms = max(chunk_index * chunk_length_ms - overlap_ms, 0) if chunk_index > 0 else 0
            end_ms = min((chunk_index + 1) * chunk_length_ms, len(audio_segment))
            chunk = audio_segment[start_ms:end_ms]
            
            with temp_audio_file(suffix=file_suffix) as temp_path:
                await asyncio.to_thread(chunk.export, temp_path, format="mp3")
                audio_content = await self._process_audio_file_for_gemini(temp_path)
                chunk_transcript = await self._transcribe_gemini_api_call(audio_content, f"{episode_name} - Part {chunk_index+1}" if episode_name else f"Chunk {chunk_index+1}", chunk_id=chunk_index+1)
                return chunk_index, chunk_transcript
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_index+1}: {e}", exc_info=True)
            return chunk_index, f"ERROR in chunk {chunk_index+1}: {str(e)}"

    @memory_guard(threshold_percent=60.0)  # Use 60% threshold for better cloud stability
    async def _process_long_audio(self, file_path: str, episode_name: Optional[str] = None) -> str:
        logger.info(f"Processing long audio file: {file_path}")
        
        # Check memory before loading large audio file
        if not check_memory_usage():
            raise MemoryError("Memory usage too high to process long audio file")
        
        audio = await asyncio.to_thread(AudioSegment.from_file, file_path)
        chunk_length_ms = self.DEFAULT_CHUNK_MINUTES * 60 * 1000
        overlap_ms = self.DEFAULT_OVERLAP_SECONDS * 1000
        total_chunks = -(-len(audio) // chunk_length_ms) # Ceiling division
        
        tasks = [
            self._process_audio_chunk(i, audio, total_chunks, chunk_length_ms, overlap_ms, Path(file_path).suffix, episode_name)
            for i in range(total_chunks)
        ]
        
        results = await asyncio.gather(*tasks)
        results.sort(key=lambda x: x[0])
        transcripts = [transcript for _, transcript in results]
        
        # Free memory after processing chunks
        del audio
        cleanup_memory()
        
        return "\n\n".join(transcripts)

    async def summarize_transcript(self, transcript: str, episode_title: str = "", podcast_name: str = "", episode_summary: str = "") -> str:
        """Generate a comprehensive AI summary optimized for semantic matching and embeddings."""
        logger.info("Generating comprehensive episode summary (%d chars transcript)", len(transcript))
        
        # Enhanced prompt for better semantic understanding
        prompt = f"""You are an expert podcast content analyst. Create a comprehensive summary that will be used for guest matching and semantic search.

Podcast: {podcast_name if podcast_name else "Unknown Podcast"}
Episode: {episode_title if episode_title else "Untitled Episode"}

{f"Original Summary: {episode_summary}" if episode_summary else ""}

TRANSCRIPT:
{transcript}

Create a structured summary optimized for semantic matching:

**CORE THEMES**: What are the 3-5 main topics/themes discussed?

**HOST STYLE**: How does the host conduct interviews? What's their approach and expertise?

**GUEST PROFILE**: If applicable, what's the guest's background, expertise, and unique perspectives?

**KEY INSIGHTS**: What are 4-6 actionable takeaways, insights, or memorable quotes?

**AUDIENCE VALUE**: Who would most benefit from this content? What problems does it solve?

**PROFESSIONAL FOCUS**: What business/career/industry topics are covered? Any specific expertise areas?

**CONVERSATION STYLE**: Interview format, depth level, discussion style (casual/formal/technical)?

Provide a comprehensive but concise summary (400-600 words) that captures the episode's semantic essence for matching relevant guests to similar content."""
        
        try:
            async with self._gemini_api_semaphore:
                response = await self._model.generate_content_async(
                    [prompt], 
                    generation_config={"temperature": 0.3, "max_output_tokens": 2048}
                )
            return response.text
        except Exception as e:
            logger.error(f"Error generating comprehensive episode summary: {e}", exc_info=True)
            # Fallback to basic summary if AI fails
            return f"Episode: {episode_title}\n\nBasic content from transcript: {transcript[:800]}..."

    async def transcribe_audio(self, audio_path: str, episode_id: int, episode_title: Optional[str] = None) -> Tuple[str, Optional[str], Optional[List[float]]]:
        # Use global semaphore to limit total concurrent transcriptions
        async with GLOBAL_TRANSCRIPTION_SEMAPHORE:
            if not os.path.exists(audio_path):
                raise FileNotFoundError(f"Audio file not found at: {audio_path}")
            
            # Check file size before processing
            file_size = os.path.getsize(audio_path)
            if file_size < 1024:  # Less than 1KB
                raise ValueError(f"Audio file too small ({file_size} bytes), likely corrupted: {audio_path}")
            
            # Skip extremely large files (> 500MB)
            MAX_FILE_SIZE = 500 * 1024 * 1024  # 500MB
            if file_size > MAX_FILE_SIZE:
                raise ValueError(f"Audio file too large ({file_size / (1024*1024):.1f} MB), skipping to avoid timeout: {audio_path}")

            transcript, summary, embedding = "", None, None
            should_cleanup = False  # Flag to determine if we should clean up the input file
            
            try:
                # Check if this is a temp file we should clean up (if it's in temp directory)
                temp_dir = tempfile.gettempdir()
                if audio_path.startswith(temp_dir):
                    should_cleanup = True
                    logger.debug(f"Audio file {audio_path} is in temp directory, will clean up after processing")
            
                audio = await asyncio.to_thread(AudioSegment.from_file, audio_path)
                duration_minutes = len(audio) / (60 * 1000)
                
                if duration_minutes > self.MAX_SINGLE_CHUNK_DURATION_MINUTES:
                    transcript = await self._process_long_audio(audio_path, episode_name=episode_title)
                else:
                    audio_content = await self._process_audio_file_for_gemini(audio_path)
                    transcript = await self._transcribe_gemini_api_call(audio_content, episode_title)

                if transcript and "ERROR in chunk" not in transcript:
                    # Create enhanced summary with context
                    summary = await self.summarize_transcript(
                        transcript=transcript,
                        episode_title=episode_title or "Untitled Episode",
                        podcast_name="",  # Could be passed as parameter if needed
                        episode_summary=""  # Could include original Podscan summary if available
                    )
                    # Use only title + AI summary for embeddings (no transcript truncation)
                    embedding_text = f"Title: {episode_title or 'Untitled Episode'}\nSummary: {summary}"
                    embedding = await self._openai_service.get_embedding(text=embedding_text, workflow="episode_embedding", related_ids={"episode_id": episode_id})
            except Exception as e:
                logger.error(f"Error during transcription process for {audio_path}: {e}", exc_info=True)
                raise
            finally:
                # Clean up the audio file if it's a temp file
                if should_cleanup and os.path.exists(audio_path):
                    try:
                        os.remove(audio_path)
                        logger.debug(f"Cleaned up temp audio file: {audio_path}")
                    except Exception as e:
                        logger.error(f"Failed to clean up temp audio file {audio_path}: {e}")
            
            return transcript, summary, embedding