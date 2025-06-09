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
import functools
import uuid

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

    async def download_audio(self, url: str) -> Optional[str]:
        parsed_url = urlparse(url)
        file_extension = os.path.splitext(parsed_url.path)[1] or ".mp3"
        
        # Use a context manager for the temporary file to ensure it's handled properly
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_extension) as tmp_file:
            tmp_path = tmp_file.name

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url, timeout=300) as resp: # Increased timeout for large files
                    resp.raise_for_status()
                    with open(tmp_path, "wb") as f:
                        while True:
                            chunk = await resp.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)
            logger.info(f"Downloaded audio from {url} to {tmp_path}")
            return tmp_path
        except Exception as e:
            logger.error(f"Failed to download audio from {url}: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
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

    async def summarize_transcript(self, transcript: str) -> str:
        logger.info("Summarizing transcript (%d chars)", len(transcript))
        prompt = f"Summarize the following podcast transcript:\n\n{transcript}\n\nSummary:"
        try:
            async with self._gemini_api_semaphore:
                response = await self._model.generate_content_async([prompt], generation_config={"temperature": 0.2, "max_output_tokens": 1024})
            return response.text
        except Exception as e:
            logger.error(f"Error summarizing transcript: {e}", exc_info=True)
            return transcript[:500] + "..."

    async def transcribe_audio(self, audio_path: str, episode_id: int, episode_title: Optional[str] = None) -> Tuple[str, Optional[str], Optional[List[float]]]:
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found at: {audio_path}")

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
                summary = await self.summarize_transcript(transcript)
                embedding_text = f"Title: {episode_title}\nSummary: {summary}\nTranscript: {transcript[:self.MAX_TRANSCRIPT_CHARS_FOR_EMBEDDING]}"
                embedding = await self._openai_service.get_embedding(text=embedding_text, workflow="episode_embedding", related_ids={"episode_id": episode_id})
        except Exception as e:
            logger.error(f"Error during transcription process for {audio_path}: {e}", exc_info=True)
            raise
        
        return transcript, summary, embedding