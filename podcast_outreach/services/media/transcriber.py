import aiohttp
import logging
import os
import tempfile
from typing import Optional, List
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

# Configure logging for the MediaTranscriber class
logger = logging.getLogger(__name__)

# --- Global FFmpeg/FFprobe Configuration ---
# These paths are set globally for pydub.
# It's recommended to have ffmpeg/ffprobe in your system's PATH,
# or specify their full paths here.
FFMPEG_PATH = os.getenv("FFMPEG_PATH", r"C:\ffmpeg\bin\ffmpeg.exe")
FFPROBE_PATH = os.getenv("FFPROBE_PATH", r"C:\ffmpeg\bin\ffprobe.exe")

# Only set the paths if the files exist, otherwise pydub will try system defaults
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
    # This limits how many Gemini API calls related to chunks can be in flight simultaneously.
    MAX_CHUNK_CONCURRENCY = int(os.getenv("CHUNK_CONCURRENCY", "20"))

    # Maximum duration for an audio file to be processed as a single chunk (in minutes).
    # Files longer than this will be split and processed in chunks.
    MAX_SINGLE_CHUNK_DURATION_MINUTES = 60

    # Default chunk size for long audio files (in minutes)
    DEFAULT_CHUNK_MINUTES = 45
    # Default overlap between chunks (in seconds)
    DEFAULT_OVERLAP_SECONDS = 30

    def __init__(self, api_key: Optional[str] = None):
        """
        Initializes the MediaTranscriber with Gemini API configuration.
        Args:
            api_key: Optional Gemini API key. If not provided, it will be read from GEMINI_API_KEY env var.
        """
        self._model: Optional[genai.GenerativeModel] = None
        self._api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not self._api_key:
            logger.error("GEMINI_API_KEY environment variable not set or api_key not provided.")
            raise ValueError("Please set the GEMINI_API_KEY environment variable or provide it to the constructor.")

        # Semaphore to limit concurrent Gemini API calls across all operations
        # (single file transcription, and individual chunk transcriptions).
        # This helps manage API rate limits. A conservative default is 10.
        self._gemini_api_semaphore = asyncio.Semaphore(int(os.getenv("GEMINI_API_CONCURRENCY", "10")))

        self._setup_gemini_api()
        logger.info("MediaTranscriber initialized.")

    def _setup_gemini_api(self):
        """Set up the Gemini API with authentication."""
        genai.configure(api_key=self._api_key)
        # Using the async client for better integration with asyncio
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
        tmp_file.close() # Close the handle so aiohttp can write to it

        # Add browser-like headers to prevent 403 Forbidden errors
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'audio/webm,audio/ogg,audio/mp3,audio/wav,audio/*;q=0.9,application/ogg;q=0.7,video/*;q=0.6,*/*;q=0.5',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://www.buzzsprout.com/', # Example referer, adjust if needed
            'DNT': '1',
            'Connection': 'keep-alive',
        }

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(url) as resp:
                    resp.raise_for_status()  # Raise an exception for bad status codes (4xx, 5xx)
                    with open(tmp_path, "wb") as f:
                        while True:
                            chunk = await resp.content.read(8192) # Read in chunks to handle large files
                            if not chunk:
                                break
                            f.write(chunk)
            logger.info("Downloaded audio from %s to %s", url, tmp_path)
            return tmp_path
        except aiohttp.ClientError as e:
            logger.error(f"Failed to download audio from {url}: {e}")
            if os.path.exists(tmp_path):
                os.remove(tmp_path) # Clean up partial download
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
                # Create a temporary file for the chunk
                temp_file = tempfile.NamedTemporaryFile(suffix=file_suffix, delete=False)
                temp_path = temp_file.name
                temp_file.close() # Close the handle so pydub can write to it

                # Export chunk to a temporary file (synchronous pydub operation)
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
                # Ensure temporary file is removed
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

        # Load audio segment (synchronous pydub operation, run in a thread)
        audio = await asyncio.to_thread(AudioSegment.from_file, file_path)
        chunk_length_ms = chunk_minutes * 60 * 1000
        overlap_ms = overlap_seconds * 1000
        total_chunks = len(audio) // chunk_length_ms + (1 if len(audio) % chunk_length_ms > 0 else 0)

        logger.info(f"Audio length: {len(audio)/1000/60:.2f} minutes, will be split into {total_chunks} chunks")

        file_suffix = Path(file_path).suffix

        # Create tasks for each chunk
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

        # Run chunk tasks concurrently, limited by MAX_CHUNK_CONCURRENCY
        chunk_semaphore = asyncio.Semaphore(self.MAX_CHUNK_CONCURRENCY)

        async def run_task_with_semaphore(task_coro):
            async with chunk_semaphore:
                return await task_coro

        # Use asyncio.gather to run all chunk processing tasks concurrently
        completed_tasks = await asyncio.gather(*(run_task_with_semaphore(task) for task in tasks))

        results = []
        for chunk_index, transcript in completed_tasks:
            results.append((chunk_index, transcript))
            if "ERROR in chunk" not in transcript:
                logger.info(f"Completed chunk {chunk_index+1}/{total_chunks}")
            else:
                logger.error(f"Chunk {chunk_index+1}/{total_chunks} failed: {transcript}")

        # Sort the results by chunk index to maintain the correct order
        results.sort(key=lambda x: x[0])
        transcripts = [transcript for _, transcript in results]

        logger.info(f"Completed processing all {total_chunks} chunks")
        return "\n\n".join(transcripts)

    async def transcribe_audio(
        self,
        audio_path: str,
        episode_title: Optional[str] = None,
        speakers: Optional[List[str]] = None
    ) -> str:
        """
        Transcribe audio using Gemini. Handles both short and long audio files by chunking.

        Args:
            audio_path: Local path to the audio file.
            episode_title: Optional title of the episode for better identification in transcription.
            speakers: Optional list of speaker names for better speaker identification.

        Returns:
            The transcribed text.

        Raises:
            FileNotFoundError: If the audio file does not exist.
            ValueError: If the audio format is unsupported or a content policy violation occurs.
            Exception: For other unexpected errors during transcription.
        """
        if not os.path.exists(audio_path):
            raise FileNotFoundError(f"Audio file not found at: {audio_path}")

        logger.info("Starting transcription for %s", audio_path)

        try:
            # Estimate audio duration (synchronous pydub operation, run in a thread)
            audio = await asyncio.to_thread(AudioSegment.from_file, audio_path)
            duration_minutes = len(audio) / (60 * 1000)
            logger.info(f"Audio duration: {duration_minutes:.2f} minutes")

            if duration_minutes > self.MAX_SINGLE_CHUNK_DURATION_MINUTES:
                logger.info(f"Long audio detected ({duration_minutes:.2f} min > {self.MAX_SINGLE_CHUNK_DURATION_MINUTES} min), processing in parallel chunks")
                transcript = await self._process_long_audio(
                    audio_path,
                    chunk_minutes=self.DEFAULT_CHUNK_MINUTES,
                    overlap_seconds=self.DEFAULT_OVERLAP_SECONDS,
                    episode_name=episode_title,
                    speakers=speakers
                )
            else:
                logger.info(f"Processing audio as a single file ({duration_minutes:.2f} min)")
                audio_content = await self._process_audio_file_for_gemini(audio_path)
                transcript = await self._transcribe_gemini_api_call(audio_content, episode_title, speakers)

            # Check if any chunk failed and returned an error string
            if "ERROR in chunk" in transcript:
                logger.error(f"Transcription completed with errors in some chunks for {audio_path}. Review transcript for 'ERROR in chunk' messages.")
                # Depending on desired behavior, you might want to raise an exception here
                # instead of returning a partial transcript with error messages.

            logger.info("Transcription completed successfully for %s", audio_path)
            return transcript

        except ValueError as e:
            # Specifically catch ValueError likely from content policy violations
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
            async with self._gemini_api_semaphore: # Use semaphore for summarization API call too
                response = await self._model.generate_content_async(
                    [prompt],
                    generation_config={"temperature": 0.2, "max_output_tokens": 500} # Limit summary length
                )
            summary = response.text
            logger.info("Summary generated successfully.")
            return summary
        except Exception as e:
            logger.error(f"Error summarizing transcript: {e}", exc_info=True)
            # Fallback to simple truncation if API call fails
            summary = transcript[:500] + "..." if len(transcript) > 500 else transcript
            logger.warning("Failed to get Gemini summary, returning truncated transcript.")
            return summary
