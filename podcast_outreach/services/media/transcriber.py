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
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from urllib.parse import urlparse
import time
import functools
import uuid

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

logger = logging.getLogger(__name__)

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


class MediaTranscriber:
    """Utility class for downloading and transcribing podcast audio using Gemini."""

    MAX_RETRIES = 3
    RETRY_DELAY = 5
    MAX_CHUNK_CONCURRENCY = int(os.getenv("CHUNK_CONCURRENCY", "10"))
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
        self._gemini_api_semaphore = asyncio.Semaphore(int(os.getenv("GEMINI_API_CONCURRENCY", "10")))
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
        """Synchronous download using requests library - sometimes works better than aiohttp."""
        parsed_url = urlparse(url)
        file_extension = os.path.splitext(parsed_url.path)[1] or ".mp3"
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
            tmp_path = tmp_file.name

        # Use a session to handle cookies and redirects properly
        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

        try:
            # Start with a HEAD request to check if the URL is accessible
            head_resp = session.head(url, allow_redirects=True, timeout=30)
            logger.info(f"HEAD request status: {head_resp.status_code}, final URL: {head_resp.url}")
            
            # Now make the actual download request
            response = session.get(url, allow_redirects=True, timeout=300, stream=True)
            response.raise_for_status()
            
            logger.info(f"Download response status: {response.status_code}, content-type: {response.headers.get('content-type', 'unknown')}")
            
            # Download the file in chunks
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(tmp_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0 and downloaded % (5 * 1024 * 1024) == 0:  # Log every 5MB instead of every 1MB
                            progress = (downloaded / total_size) * 100
                            logger.debug(f"Download progress: {progress:.1f}% ({downloaded}/{total_size} bytes)")
            
            # Validate downloaded file
            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) < 1024:
                logger.error(f"Downloaded file is too small or doesn't exist: {tmp_path}")
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
                return None
                
            file_size = os.path.getsize(tmp_path)
            logger.info(f"Successfully downloaded audio from {url} to {tmp_path} (size: {file_size} bytes)")
            return tmp_path
            
        except requests.exceptions.HTTPError as e:
            logger.error(f"HTTP error downloading from {url}: {e}")
            if hasattr(e, 'response'):
                if e.response.status_code == 404:
                    logger.error(f"404 Not Found - Audio file does not exist at URL: {url}")
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
                    # Raise special exception for 404 errors that shouldn't be retried
                    raise AudioNotFoundError(f"Audio not found (404): {url}")
                elif e.response.status_code == 403:
                    logger.error("403 Forbidden - this may indicate:")
                    logger.error("1. The audio URL requires specific referrer headers")
                    logger.error("2. The hosting service blocks programmatic access")
                    logger.error("3. The URL may be geo-restricted or time-limited")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return None
        except Exception as e:
            logger.error(f"Error downloading audio from {url}: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            return None
        finally:
            session.close()

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
            media_record = await media_queries.get_media_by_id(media_id, pool)
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
        
        for attempt in range(self.MAX_RETRIES):
            try:
                logger.info(f"Sending transcription request{chunk_info} (attempt {attempt+1}/{self.MAX_RETRIES})...")
                async with self._gemini_api_semaphore:
                    response = await self._model.generate_content_async([audio_content, prompt], generation_config={"temperature": 0.1})
                logger.info(f"Transcription complete{chunk_info}")
                return response.text
            except (ResourceExhausted, ServiceUnavailable) as e:
                if attempt < self.MAX_RETRIES - 1:
                    logger.warning(f"API error{chunk_info}: {e}. Retrying in {self.RETRY_DELAY} seconds...")
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1))
                else:
                    logger.error(f"Failed to transcribe{chunk_info} after {self.MAX_RETRIES} attempts: {e}")
                    raise
            except Exception as e:
                logger.error(f"An unexpected error occurred during Gemini API call{chunk_info}: {e}")
                raise

    async def _process_audio_chunk(self, chunk_index: int, audio_segment: AudioSegment, total_chunks: int, chunk_length_ms: int, overlap_ms: int, file_suffix: str, episode_name: Optional[str]) -> tuple[int, str]:
        try:
            logger.info(f"Processing chunk {chunk_index+1} of {total_chunks}")
            start_ms = max(chunk_index * chunk_length_ms - overlap_ms, 0) if chunk_index > 0 else 0
            end_ms = min((chunk_index + 1) * chunk_length_ms, len(audio_segment))
            chunk = audio_segment[start_ms:end_ms]
            
            with tempfile.NamedTemporaryFile(suffix=file_suffix, delete=False) as temp_file:
                temp_path = temp_file.name
            
            try:
                await asyncio.to_thread(chunk.export, temp_path, format="mp3")
                audio_content = await self._process_audio_file_for_gemini(temp_path)
                chunk_transcript = await self._transcribe_gemini_api_call(audio_content, f"{episode_name} - Part {chunk_index+1}" if episode_name else f"Chunk {chunk_index+1}", chunk_id=chunk_index+1)
                return chunk_index, chunk_transcript
            finally:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        except Exception as e:
            logger.error(f"Error processing chunk {chunk_index+1}: {e}", exc_info=True)
            return chunk_index, f"ERROR in chunk {chunk_index+1}: {str(e)}"

    async def _process_long_audio(self, file_path: str, episode_name: Optional[str] = None) -> str:
        logger.info(f"Processing long audio file: {file_path}")
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
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found at: {audio_path}")
        
        # Check file size before processing
        file_size = os.path.getsize(audio_path)
        if file_size < 1024:  # Less than 1KB
            raise ValueError(f"Audio file too small ({file_size} bytes), likely corrupted: {audio_path}")

        transcript, summary, embedding = "", None, None
        try:
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
        
        return transcript, summary, embedding