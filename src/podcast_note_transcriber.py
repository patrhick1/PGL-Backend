import os
from urllib.parse import urlparse
import time
import base64
from pathlib import Path
import pydub
from pydub import AudioSegment
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
import requests  
import logging
import asyncio
import tempfile
from functools import partial # Ensure partial is imported
from typing import Dict, Any, Optional, List, Tuple

# Project-specific imports
import db_service_pg # For PostgreSQL interactions

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('transcriber.log', mode='a') # Append mode for logs
    ]
)
logger = logging.getLogger(__name__) # Use __name__ for logger

# ---------------------------------------------------------------------------
# Concurrency / Rate-limit Configuration
# ---------------------------------------------------------------------------
MAX_RETRIES = int(os.getenv("GEMINI_TRANSCRIPTION_MAX_RETRIES", "3"))
RETRY_DELAY = int(os.getenv("GEMINI_TRANSCRIPTION_RETRY_DELAY", "5")) # Seconds

# Max concurrent calls to the Gemini API for transcription
GEMINI_API_CONCURRENCY = int(os.getenv("GEMINI_API_CONCURRENCY", "10")) # Reduced default, tune based on quotas

# Max concurrent audio downloads
DOWNLOAD_CONCURRENCY = int(os.getenv("DOWNLOAD_CONCURRENCY", "5"))

# Max episodes to fetch from DB in one batch by the main orchestrator
MAX_EPISODES_PER_BATCH = int(os.getenv("TRANSCRIBER_MAX_EPISODES_PER_BATCH", "20"))

# Set the full path to the ffmpeg and ffprobe executables (if needed by pydub)
FFMPEG_PATH = os.getenv("FFMPEG_CUSTOM_PATH") # e.g., r"C:\ffmpeg\bin\ffmpeg.exe"
FFPROBE_PATH = os.getenv("FFPROBE_CUSTOM_PATH") # e.g., r"C:\ffmpeg\bin\ffprobe.exe"

if FFMPEG_PATH and os.path.exists(FFMPEG_PATH):
    AudioSegment.converter = FFMPEG_PATH
    logger.info(f"Using custom ffmpeg at: {FFMPEG_PATH}")
elif not AudioSegment.converter or not os.path.exists(AudioSegment.converter):
    logger.warning("ffmpeg not found at default or custom path. Transcription of some formats may fail.")

if FFPROBE_PATH and os.path.exists(FFPROBE_PATH):
    # pydub.utils.get_prober_name = lambda: FFPROBE_PATH # This was the old way
    # For newer pydub, you might need to set it on an instance or ensure it's in PATH
    # Or, if pydub finds ffprobe in PATH, this might not be strictly necessary.
    # For now, let's rely on pydub's default discovery or PATH.
    logger.info(f"Custom ffprobe path set: {FFPROBE_PATH}. Ensure pydub uses it if default fails.")
elif not pydub.utils.get_prober_name() or not os.path.exists(pydub.utils.get_prober_name()):
    logger.warning("ffprobe not found at default or custom path. Audio duration checks might fail.")


# Global Gemini model instance (initialized in main or passed)
_gemini_model_transcription = None
_gemini_api_semaphore = None # Will be an asyncio.Semaphore

def init_gemini_model_for_transcription():
    global _gemini_model_transcription, _gemini_api_semaphore
    if _gemini_model_transcription is None:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY environment variable not set for transcription.")
            raise ValueError("Please set the GEMINI_API_KEY environment variable.")
        try:
            genai.configure(api_key=api_key)
            # Using a model known for good transcription, adjust if needed
            # Consider gemini-1.5-pro for potentially better speaker diarization if flash isn't enough
            _gemini_model_transcription = genai.GenerativeModel('gemini-1.5-flash-latest') 
            _gemini_api_semaphore = asyncio.Semaphore(GEMINI_API_CONCURRENCY)
            logger.info(f"Gemini model for transcription ('{_gemini_model_transcription.model_name}') initialized with semaphore limit {GEMINI_API_CONCURRENCY}.")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini model for transcription: {e}", exc_info=True)
            raise
    return _gemini_model_transcription, _gemini_api_semaphore


async def _process_audio_file_async(file_path: str) -> Dict[str, Any]:
    """Async wrapper to process an audio file and return content for the API."""
    # This function involves file I/O, so run it in a thread
    return await asyncio.to_thread(process_audio_file_sync, file_path)

def process_audio_file_sync(file_path: str) -> Dict[str, Any]:
    """Synchronous version of process_audio_file (for use with to_thread)."""
    path = Path(file_path)
    if not path.exists():
        logger.error(f"Audio file not found: {file_path}")
        raise FileNotFoundError(f"Audio file not found: {file_path}")
    
    extension = path.suffix.lower()
    mime_map = {
        '.mp3': 'audio/mp3', '.wav': 'audio/wav', '.flac': 'audio/flac',
        '.m4a': 'audio/mp4', '.aac': 'audio/aac', '.ogg': 'audio/ogg',
        '.opus': 'audio/opus' # Opus is common in podcasts
    }
    mime_type = mime_map.get(extension)
    if not mime_type:
        # Try to guess with pydub if not in map
        try:
            audio_segment = AudioSegment.from_file(file_path)
            # Pydub's underlying ffmpeg usually knows the format string
            format_str = Path(audio_segment. पता).suffix[1:] if hasattr(audio_segment, ' पता') and Path(audio_segment. पता).suffix else extension[1:]
            if format_str == 'm4a': mime_type = 'audio/mp4' # Common case
            elif format_str: mime_type = f'audio/{format_str}'
            
            if not mime_type:
                logger.error(f"Unsupported audio format (and could not guess): {extension} for file {file_path}")
                raise ValueError(f"Unsupported audio format: {extension}")
            logger.info(f"Guessed mime_type '{mime_type}' for extension '{extension}' using pydub.")
        except Exception as e:
            logger.error(f"Failed to guess mime_type for {extension} from {file_path}: {e}")
            raise ValueError(f"Unsupported audio format: {extension}, and failed to determine type.")

    logger.info(f"Loading audio file: {file_path} (MIME: {mime_type})")
    with open(file_path, 'rb') as f:
        audio_data = f.read()
    
    return {
        "mime_type": mime_type,
        # Gemini API expects raw bytes for the data, not base64 encoded string
        # when passing Parts directly. If using older methods or specific SDK parts,
        # base64 might be needed, but for genai.GenerativeModel.generate_content
        # with Parts, raw bytes are typical.
        "data": audio_data 
    }

async def _transcribe_audio_gemini_async(
    model: genai.GenerativeModel, 
    semaphore: asyncio.Semaphore,
    audio_bytes: bytes, 
    mime_type: str,
    episode_title: str, 
    speakers: Optional[List[str]] = None, 
    chunk_id: Optional[int] = None
) -> str:
    """Transcribe audio using Gemini API with retries, managed by an asyncio semaphore."""
    chunk_info = f" (chunk {chunk_id})" if chunk_id is not None else ""
    prompt_parts = [
        "Transcribe this podcast audio accurately. Use speaker labels (e.g., Speaker 1, Speaker 2, or Host, Guest if identifiable from context or provided names).",
        "Provide timestamps in [HH:MM:SS] format at reasonable intervals or speaker changes."
    ]
    if speakers:
        prompt_parts.append(f"Known speaker names that might be present: {', '.join(speakers)}. Prioritize using these names if you identify them.")
    if episode_title:
        prompt_parts.append(f"This is from an episode titled: '{episode_title}'.")
    prompt_parts.append("Format each speaker turn clearly, e.g.: [00:00:15] Speaker 1: Hello world.")
    
    full_prompt = "\n".join(prompt_parts)

    # Create the audio part for the Gemini API request
    audio_part = {"mime_type": mime_type, "data": audio_bytes}

    for attempt in range(MAX_RETRIES):
        try:
            logger.info(f"Sending transcription request{chunk_info} for '{episode_title}' (attempt {attempt+1}/{MAX_RETRIES})...")
            async with semaphore: # Acquire semaphore before API call
                # generate_content_async is the correct async method
                response = await model.generate_content_async(
                    [audio_part, full_prompt], # Pass parts directly
                    generation_config=genai.types.GenerationConfig(temperature=0.2) # Adjust temperature as needed
                )
            
            # Check response.text directly, or parse parts if more complex
            if response.text:
                logger.info(f"Transcription complete{chunk_info} for '{episode_title}'. Length: {len(response.text)}")
                return response.text
            else: # Handle cases where response.text might be empty but no error raised
                logger.warning(f"Gemini response for '{episode_title}'{chunk_info} has no text. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'Unknown'}")
                # You might want to check response.candidates[0].finish_reason here
                # (e.g., SAFETY, RECITATION, etc.)
                if response.candidates and response.candidates[0].finish_reason != genai.types.Candidate.FinishReason.STOP:
                    return f"ERROR: Transcription failed for '{episode_title}'{chunk_info}. Reason: {response.candidates[0].finish_reason.name}"
                return f"ERROR: Empty transcript received for '{episode_title}'{chunk_info}."

        except (ResourceExhausted, ServiceUnavailable) as e:
            logger.warning(f"Gemini API error{chunk_info} for '{episode_title}' (attempt {attempt+1}): {e}. Retrying in {RETRY_DELAY}s...")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)
            else:
                logger.error(f"Failed to transcribe '{episode_title}'{chunk_info} after {MAX_RETRIES} attempts: {e}")
                return f"ERROR: API limit reached or service unavailable for '{episode_title}'{chunk_info} after retries."
        except Exception as e: # Catch other potential errors from API call
            logger.error(f"Unexpected error during Gemini transcription{chunk_info} for '{episode_title}': {e}", exc_info=True)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY) # Still retry for other unexpected errors
            else:
                return f"ERROR: Unexpected error during transcription of '{episode_title}'{chunk_info}: {str(e)}"
    return f"ERROR: Transcription failed for '{episode_title}'{chunk_info} after all retries." # Fallback


async def _process_audio_chunk_async(
    chunk_index: int, 
    audio_segment_chunk: AudioSegment, 
    total_chunks: int, 
    file_suffix: str, 
    episode_title: str, 
    speakers: Optional[List[str]],
    model: genai.GenerativeModel,
    semaphore: asyncio.Semaphore
) -> Tuple[int, str]:
    """Processes a single audio chunk asynchronously and returns its transcript."""
    # Use a temporary file that will be automatically cleaned up
    # tempfile.NamedTemporaryFile needs to be handled carefully with async
    # It's better to run the file operations in a thread.
    
    loop = asyncio.get_running_loop()
    temp_path = None
    
    try:
        # Create temp file in sync part or ensure sync context for NamedTemporaryFile
        fd, temp_path = tempfile.mkstemp(suffix=file_suffix)
        os.close(fd) # Close file descriptor as pydub will open/write

        await loop.run_in_executor(None, partial(audio_segment_chunk.export, temp_path, format=file_suffix.lstrip('.')))
        
        audio_processed_content = await _process_audio_file_async(temp_path)
        
        chunk_transcript = await _transcribe_audio_gemini_async(
            model,
            semaphore,
            audio_processed_content["data"], # Expecting bytes
            audio_processed_content["mime_type"],
            f"{episode_title} - Part {chunk_index+1}", 
            speakers,
            chunk_id=chunk_index+1
        )
        return chunk_index, chunk_transcript
    except Exception as e:
        logger.error(f"Error processing chunk {chunk_index+1} for '{episode_title}': {e}", exc_info=True)
        return chunk_index, f"ERROR in chunk {chunk_index+1} for '{episode_title}': {str(e)}"
    finally:
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
                logger.debug(f"Removed temporary chunk file: {temp_path}")
            except Exception as e_rm:
                logger.error(f"Error removing temporary chunk file {temp_path}: {e_rm}")

async def _process_long_audio_async(
    file_path: str, 
    episode_title: str,
    model: genai.GenerativeModel,
    semaphore: asyncio.Semaphore,
    chunk_minutes: int = 50, # Gemini 1.5 Flash can handle up to 1 hour, but shorter chunks are safer
    overlap_seconds: int = 15, 
    speakers: Optional[List[str]] = None
) -> str:
    """Processes a long audio file by splitting it into manageable chunks with parallelization (async)."""
    logger.info(f"Processing long audio: '{episode_title}' from {file_path} (chunk: {chunk_minutes}min, overlap: {overlap_seconds}s)")
    
    try:
        # Loading and splitting audio can be I/O and CPU bound, run in thread
        audio = await asyncio.to_thread(AudioSegment.from_file, file_path)
    except Exception as e:
        logger.error(f"Failed to load audio file {file_path} for '{episode_title}': {e}")
        return f"ERROR: Could not load audio file for '{episode_title}'."

    chunk_length_ms = chunk_minutes * 60 * 1000
    overlap_ms = overlap_seconds * 1000
    total_chunks = (len(audio) + chunk_length_ms - 1) // chunk_length_ms # Ceiling division
    
    logger.info(f"Audio '{episode_title}' length: {len(audio)/1000/60:.2f} min, split into {total_chunks} chunks.")
    if total_chunks == 0 and len(audio) > 0: # Handle very short audio that might result in 0 chunks
        total_chunks = 1
    elif len(audio) == 0:
        logger.warning(f"Audio file '{episode_title}' is empty or unreadable.")
        return f"ERROR: Audio file for '{episode_title}' is empty."

    file_suffix = Path(file_path).suffix or ".mp3" # Default suffix

    tasks = []
    for i in range(total_chunks):
        start_ms = i * chunk_length_ms
        # For overlap, the previous chunk should extend into this one,
        # but Gemini processes whole files. The prompt can guide context.
        # If strict non-overlapping but context-stitched required, more complex logic is needed.
        # Here, we are sending complete (potentially overlapping if chunking logic was different) audio chunks.
        # For simplicity with Gemini 1.5's long context, let's send slightly overlapping chunks.
        # This means the start of chunk `i` is `i * chunk_length_ms - (overlap_ms if i > 0 else 0)`.
        # And end is `(i+1) * chunk_length_ms`.
        
        # Corrected chunking logic for distinct, manageable chunks for the model:
        # Chunk `i` runs from `i * effective_chunk_len` to `(i+1) * effective_chunk_len`
        # We're sending full audio files for each chunk now.
        # Let's define chunks to be mostly independent but with slight overlap for stitching.
        
        # Simple non-overlapping chunking (Gemini 1.5 can handle context well)
        # If overlap is desired:
        # current_chunk_start_ms = max(0, i * chunk_length_ms - (overlap_ms if i > 0 else 0))
        # current_chunk_end_ms = min(len(audio), (i + 1) * chunk_length_ms)
        current_chunk_start_ms = i * chunk_length_ms
        current_chunk_end_ms = min(len(audio), (i + 1) * chunk_length_ms)

        if current_chunk_start_ms >= len(audio): continue # Skip if start is beyond audio length
        
        audio_chunk_segment = audio[current_chunk_start_ms:current_chunk_end_ms]
        
        tasks.append(
            _process_audio_chunk_async(
                i, audio_chunk_segment, total_chunks, file_suffix, episode_title, speakers, model, semaphore
            )
        )
    
    results = await asyncio.gather(*tasks)
    
    # Sort results by chunk index
    results.sort(key=lambda x: x[0])
    transcripts = [transcript_text for _, transcript_text in results]
    
    logger.info(f"Completed processing all {len(transcripts)} chunks for '{episode_title}'.")
    # Join transcripts, potentially with a note about chunking
    # Consider adding a separator that indicates a chunk boundary if useful
    return "\n\n--- (Chunk Boundary) ---\n\n".join(transcripts)


async def _download_audio_async(audio_url: str, temp_dir: str) -> Optional[str]:
    """Downloads audio from URL to a temporary file. Returns file path or None."""
    try:
        logger.info(f"Downloading audio from: {audio_url}")
        headers = { # Browser-like headers
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'audio/*',
        }
        # Use a proper async HTTP client if this becomes a bottleneck, requests is blocking
        response = await asyncio.to_thread(requests.get, audio_url, headers=headers, timeout=60, stream=True)
        response.raise_for_status() # Raise HTTPError for bad responses (4xx or 5xx)

        parsed_url = urlparse(audio_url)
        url_path = parsed_url.path
        file_extension = os.path.splitext(url_path)[1] or ".mp3"
        
        # Create a temporary file within the provided temp_dir
        fd, temp_file_path = tempfile.mkstemp(suffix=file_extension, dir=temp_dir)
        os.close(fd) # Close descriptor, we open in 'wb'

        with open(temp_file_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        logger.info(f"Audio downloaded to temporary file: {temp_file_path} from {audio_url}")
        return temp_file_path
    except requests.exceptions.RequestException as e:
        logger.error(f"Error downloading audio from {audio_url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during audio download from {audio_url}: {e}", exc_info=True)
        return None


async def process_single_episode_transcription(
    episode_data: Dict[str, Any], 
    model: genai.GenerativeModel, 
    semaphore: asyncio.Semaphore,
    download_semaphore: asyncio.Semaphore
) -> Optional[str]:
    """Handles downloading and transcribing a single episode."""
    episode_id = episode_data.get('episode_id')
    audio_url = episode_data.get('episode_url')
    episode_title = episode_data.get('title', f"Episode {episode_id}")

    if not audio_url:
        logger.warning(f"No audio URL for episode_id {episode_id}. Skipping.")
        return None
    
    temp_download_dir = tempfile.mkdtemp(prefix="podcast_audio_")
    downloaded_file_path = None
    transcript_text = None

    try:
        async with download_semaphore: # Limit concurrent downloads
             downloaded_file_path = await _download_audio_async(audio_url, temp_download_dir)

        if not downloaded_file_path:
            return f"ERROR: Failed to download audio for '{episode_title}'."

        # Estimate audio duration to decide on chunking (optional, Gemini 1.5 handles long audio)
        # For simplicity, we can assume _process_long_audio_async will handle it if needed.
        # Or, always use _process_long_audio_async.
        # Let's keep it simpler: assume up to 55-60 min is fine for direct, else chunk.
        # This check can be rough.
        try:
            audio_for_duration = await asyncio.to_thread(AudioSegment.from_file, downloaded_file_path)
            duration_minutes = len(audio_for_duration) / (60 * 1000)
            logger.info(f"Audio duration for '{episode_title}': {duration_minutes:.2f} minutes.")
        except Exception as dur_e:
            logger.warning(f"Could not determine audio duration for '{episode_title}': {dur_e}. Proceeding without chunking decision based on duration.")
            duration_minutes = 0 # Assume short or let Gemini handle it

        # Max duration for single call to Gemini without explicit client-side chunking.
        # Gemini 1.5 Flash can take up to 1 hour. Let's use 58 min as a safe threshold.
        GEMINI_SINGLE_FILE_MAX_MIN = 58 

        if duration_minutes > GEMINI_SINGLE_FILE_MAX_MIN:
            logger.info(f"Long audio detected for '{episode_title}' ({duration_minutes:.2f}m > {GEMINI_SINGLE_FILE_MAX_MIN}m). Using chunked processing.")
            transcript_text = await _process_long_audio_async(downloaded_file_path, episode_title, model, semaphore)
        else:
            logger.info(f"Processing '{episode_title}' as a single audio file for transcription.")
            audio_content_processed = await _process_audio_file_async(downloaded_file_path)
            transcript_text = await _transcribe_audio_gemini_async(
                model, 
                semaphore,
                audio_content_processed["data"], 
                audio_content_processed["mime_type"],
                episode_title
            )
        return transcript_text
        
    except Exception as e:
        logger.error(f"Error during transcription pipeline for episode_id {episode_id} ('{episode_title}'): {e}", exc_info=True)
        return f"ERROR: Pipeline failure for '{episode_title}': {str(e)}"
    finally:
        if downloaded_file_path and os.path.exists(downloaded_file_path):
            try: os.remove(downloaded_file_path)
            except OSError as e_rm: logger.error(f"Error removing temp audio file {downloaded_file_path}: {e_rm}")
        try: os.rmdir(temp_download_dir) # remove directory if empty
        except OSError: pass # Ignore if not empty (e.g. due to failed file delete)


async def run_batch_transcription_pg(stop_event: Optional[asyncio.Event] = None):
    """Main orchestrator for transcribing episodes fetched from PostgreSQL."""
    try:
        model, semaphore = init_gemini_model_for_transcription() # Ensure model and semaphore are ready
        download_sem = asyncio.Semaphore(DOWNLOAD_CONCURRENCY)
    except ValueError as e: # Catch API key error from init
        logger.error(f"Halting transcription run: {e}")
        return

    logger.info(f"Starting batch transcription process. Fetching up to {MAX_EPISODES_PER_BATCH} episodes.")
    
    try:
        episodes_to_process = await db_service_pg.get_episodes_to_transcribe(batch_size=MAX_EPISODES_PER_BATCH)
    except Exception as e_db_fetch:
        logger.error(f"Failed to fetch episodes from DB: {e_db_fetch}", exc_info=True)
        return # Cannot proceed without episodes

    if not episodes_to_process:
        logger.info("No episodes found marked for transcription.")
        return

    logger.info(f"Fetched {len(episodes_to_process)} episodes for transcription.")

    tasks = []
    for episode_data in episodes_to_process:
        if stop_event and stop_event.is_set():
            logger.info("Stop event detected. Halting submission of new transcription tasks.")
            break
        tasks.append(
            process_single_episode_transcription(episode_data, model, semaphore, download_sem)
        )

    completed_count = 0
    failed_count = 0

    for i, future in enumerate(asyncio.as_completed(tasks)):
        if stop_event and stop_event.is_set():
            logger.info("Stop event detected during task processing. Remaining tasks may be cancelled if gather is cancelled.")
            # Individual tasks already check stop_event, this is a fallback for the loop itself.
            break 
        
        episode_id = episodes_to_process[i].get('episode_id') # Assuming order is preserved by as_completed or tasks list
        episode_title_log = episodes_to_process[i].get('title', f"EID {episode_id}")

        try:
            transcript_result_text = await future
            
            if transcript_result_text and not transcript_result_text.startswith("ERROR:"):
                # TODO: Implement guest name extraction if possible from transcript_result_text
                # For now, passing None for guest_names_str
                guest_names_str: Optional[str] = None 
                
                # Max length for DB field (adjust if needed, should match schema's TEXT capacity)
                # TEXT fields in Postgres are variable length, up to 1GB, so truncation might be more for practical display/use.
                # However, if a hard limit is desired:
                # MAX_DB_TRANSCRIPT_LENGTH = 99900 # Example limit
                # if len(transcript_result_text) > MAX_DB_TRANSCRIPT_LENGTH:
                #    logger.warning(f"Transcript for episode {episode_id} is very long ({len(transcript_result_text)} chars), truncating for DB.")
                #    transcript_result_text = transcript_result_text[:MAX_DB_TRANSCRIPT_LENGTH]

                success_db = await db_service_pg.update_episode_transcript(episode_id, transcript_result_text, guest_names_str)
                if success_db:
                    logger.info(f"Successfully transcribed and updated DB for episode_id: {episode_id} ('{episode_title_log}')")
                    completed_count += 1
                else:
                    logger.error(f"Transcription for episode_id: {episode_id} ('{episode_title_log}') was successful, but DB update failed.")
                    failed_count += 1 # Count as failed if DB update fails
            else:
                logger.error(f"Transcription failed for episode_id: {episode_id} ('{episode_title_log}'). Reason: {transcript_result_text}")
                # Optionally, update DB to mark as failed (e.g., set downloaded=FALSE, transcribe=FALSE, add error note)
                # For now, it will remain transcribe=TRUE, downloaded=FALSE and be picked up again unless error is persistent.
                failed_count += 1

        except Exception as e_task:
            logger.error(f"Error processing task for episode_id {episode_id} ('{episode_title_log}'): {e_task}", exc_info=True)
            failed_count += 1
        
        if i + 1 < len(tasks): # Avoid sleeping after the very last task
             await asyncio.sleep(0.1) # Small delay between processing results of each task

    logger.info(f"Batch transcription finished. Successful: {completed_count}, Failed: {failed_count} out of {len(episodes_to_process)} episodes.")

# --- Main Execution ---
if __name__ == "__main__":
    async def main():
        # Load .env file for environment variables
        from dotenv import load_dotenv
        load_dotenv()

        # Initialize DB Pool (must be done in async context)
        await db_service_pg.init_db_pool()
        
        stop_event = asyncio.Event() # Example stop event, can be set from elsewhere
        try:
            # Example: run one batch
            await run_batch_transcription_pg(stop_event)
            
            # Example: simulate running for a bit, then stopping
            # asyncio.create_task(run_batch_transcription_pg(stop_event))
            # await asyncio.sleep(30) # Let it run for 30s
            # print("Main: Requesting stop...")
            # stop_event.set()
            # await asyncio.sleep(5) # Give time for tasks to notice
            
        except Exception as e:
            logger.error(f"Error in main execution: {e}", exc_info=True)
        finally:
            await db_service_pg.close_db_pool()
            logger.info("Transcription script finished and DB pool closed.")

    asyncio.run(main())

