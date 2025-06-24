# podcast_outreach/services/media/podcast_transcriber.py
import logging
import asyncio
import uuid
import os
import tempfile
import requests
from typing import Dict, Any, List, Optional
from urllib.parse import urlparse
import yt_dlp  # For downloading audio from various platforms
# Remove text-based GeminiService, import genai directly for audio
# from podcast_outreach.services.ai.gemini_client import GeminiService 
import google.generativeai as genai
from pathlib import Path
import base64
from google.api_core.exceptions import ResourceExhausted, ServiceUnavailable
from podcast_outreach.logging_config import get_logger

logger = get_logger(__name__)

class PodcastTranscriberService:
    """
    Service for downloading and transcribing podcast episodes from URLs.
    Supports various platforms including direct audio files, YouTube, Spotify (if available), etc.
    Uses Gemini for transcription.
    """
    MAX_RETRIES = 3
    RETRY_DELAY = 5  # Seconds

    def __init__(self):
        # self.gemini_service = GeminiService() # This is for text-based generation
        self._api_key = os.getenv("GEMINI_API_KEY")
        if not self._api_key:
            logger.error("GEMINI_API_KEY environment variable not set for PodcastTranscriberService.")
            raise ValueError("Please set the GEMINI_API_KEY environment variable.")
        
        genai.configure(api_key=self._api_key)
        # Using a model known for multimodal capabilities; adjust if needed
        # Based on the other transcriber.py, 'gemini-1.5-flash-001' was used. 
        # Let's use 'gemini-1.5-flash-latest' for potentially newer features if available, 
        # or fallback to a specific version if issues arise.
        self._model = genai.GenerativeModel('gemini-2.0-flash') 
        self._transcription_semaphore = asyncio.Semaphore(5) # Limit concurrent Gemini transcription calls
        logger.info("PodcastTranscriberService initialized with Gemini model for audio.")

    async def _prepare_audio_for_gemini(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Reads an audio file and prepares its content for the Gemini API.
        Synchronous file I/O is run in a thread.
        """
        try:
            p = Path(file_path)
            if not await asyncio.to_thread(p.exists):
                logger.error(f"Audio file not found for Gemini prep: {file_path}")
                return None

            mime_type = None
            extension = p.suffix.lower()
            # Common audio MIME types
            mime_map = {
                '.mp3': 'audio/mpeg', # Corrected from audio/mp3 for wider compatibility
                '.wav': 'audio/wav',
                '.flac': 'audio/flac',
                '.m4a': 'audio/mp4', # Often mpeg for mp4 audio
                '.aac': 'audio/aac',
                '.ogg': 'audio/ogg',
                '.opus': 'audio/opus',
            }
            mime_type = mime_map.get(extension)
            
            if not mime_type:
                logger.warning(f"Unsupported or unknown audio format for Gemini: {extension} for file {file_path}. Attempting generic audio/ogg.")
                # Fallback or raise error - for now, let's try a common one if specific not found
                # Gemini might still reject if not truly supported.
                # This part needs careful testing with actual Gemini audio model capabilities.
                # For now, if not in map, we might have to skip or try a generic one.
                # Let's be strict for now and return None if not explicitly mapped.
                logger.error(f"Cannot determine MIME type for {extension}. Transcription may fail.")
                return None


            def read_and_encode():
                with open(file_path, 'rb') as f:
                    audio_data = f.read()
                return base64.b64encode(audio_data).decode('utf-8')

            encoded_data = await asyncio.to_thread(read_and_encode)
            
            return {
                "mime_type": mime_type,
                "data": encoded_data
            }
        except Exception as e:
            logger.error(f"Error preparing audio file {file_path} for Gemini: {e}")
            return None
    
    async def extract_audio_from_url(self, url: str, max_duration_minutes: int = 120) -> Optional[str]:
        """
        Extract audio file from a URL using yt-dlp.
        
        Args:
            url (str): URL to the podcast episode
            max_duration_minutes (int): Maximum duration to download in minutes
            
        Returns:
            Optional[str]: Path to the downloaded audio file, or None if failed
        """
        try:
            # Create temporary directory for audio files
            temp_dir = tempfile.mkdtemp(prefix="podcast_audio_")
            
            # Configure yt-dlp options
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': os.path.join(temp_dir, '%(title)s.%(ext)s'),
                'extractaudio': True,
                'audioformat': 'mp3',
                'audioquality': '192K',
                'no_warnings': True,
                'quiet': True,
                # Limit download time to prevent very long episodes
                'match_filter': lambda info_dict: None if info_dict.get('duration', 0) <= max_duration_minutes * 60 else "Episode too long"
            }
            
            def download_audio():
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    # Extract info first to check duration
                    info = ydl.extract_info(url, download=False)
                    duration = info.get('duration', 0)
                    
                    if duration > max_duration_minutes * 60:
                        logger.warning(f"Episode too long: {duration/60:.1f} minutes (max: {max_duration_minutes})")
                        return None
                    
                    # Download the audio
                    ydl.download([url])
                    
                    # Find the downloaded file
                    files = os.listdir(temp_dir)
                    if files:
                        return os.path.join(temp_dir, files[0])
                    return None
            
            # Run download in thread to avoid blocking
            audio_file = await asyncio.to_thread(download_audio)
            
            if audio_file and os.path.exists(audio_file):
                logger.info(f"Successfully downloaded audio from {url}")
                return audio_file
            else:
                logger.error(f"Failed to download audio from {url}")
                return None
                
        except Exception as e:
            logger.error(f"Error extracting audio from {url}: {e}")
            return None
    
    async def transcribe_audio_file(self, audio_file_path: str, campaign_id: Optional[uuid.UUID] = None) -> Optional[str]:
        """
        Transcribe audio file using Gemini multimodal capabilities.
        
        Args:
            audio_file_path (str): Path to the audio file
            campaign_id (Optional[uuid.UUID]): Campaign ID for tracking (currently unused in this method but good for future)
            
        Returns:
            Optional[str]: Transcribed text, or None if failed
        """
        if not self._model:
            logger.error("Gemini model not initialized in PodcastTranscriberService.")
            return None

        prepared_audio = await self._prepare_audio_for_gemini(audio_file_path)
        if not prepared_audio:
            logger.error(f"Failed to prepare audio {audio_file_path} for Gemini.")
            return None

        # Simple transcription prompt
        prompt = "Transcribe the following audio. Provide speaker labels if possible (e.g., Speaker 1, Speaker 2)."

        for attempt in range(self.MAX_RETRIES):
            try:
                logger.info(f"Sending transcription request for {audio_file_path} (attempt {attempt + 1}/{self.MAX_RETRIES})...")
                async with self._transcription_semaphore: # Limit concurrent API calls
                    # Construct the content parts: one for audio, one for text prompt
                    # The audio part should be a dictionary with 'mime_type' and 'data' (base64 string)
                    # The genai.Part.from_data might be useful if directly passing bytes, 
                    # but since we have base64, we construct the dict as expected by the API indirectly.
                    # The API expects a list of Parts or [audio_dict, prompt_string].
                    response = await self._model.generate_content_async(
                        [prepared_audio, prompt] # Send audio data and text prompt
                    )
                
                if response.text:
                    logger.info(f"Transcription successful for {audio_file_path}.")
                    return response.text
                else:
                    logger.warning(f"Transcription for {audio_file_path} resulted in empty text. Finish reason: {response.candidates[0].finish_reason if response.candidates else 'Unknown'}")
                    # Check for safety reasons specifically if possible, though finish_reason is more general here
                    if response.candidates and response.candidates[0].finish_reason.name == "SAFETY":
                        logger.error(f"Transcription for {audio_file_path} blocked due to safety reasons.")
                        return "[Transcription blocked due to safety reasons]"
                    return None # Or handle other non-text responses appropriately

            except (ResourceExhausted, ServiceUnavailable) as e:
                logger.warning(f"API error during transcription for {audio_file_path} (attempt {attempt + 1}): {e}. Retrying in {self.RETRY_DELAY}s...")
                if attempt < self.MAX_RETRIES - 1:
                    await asyncio.sleep(self.RETRY_DELAY * (attempt + 1)) # Exponential backoff can be added here
                else:
                    logger.error(f"Failed to transcribe {audio_file_path} after {self.MAX_RETRIES} attempts due to API errors: {e}")
                    return None
            except Exception as e:
                logger.error(f"Unexpected error transcribing audio file {audio_file_path}: {e}", exc_info=True)
                return None
        return None # Should not be reached if retries exhausted unless an error above returns None first

    async def analyze_transcript_for_insights(self, transcript: str, campaign_id: Optional[uuid.UUID] = None) -> Dict[str, Any]:
        """
        Analyze podcast transcript to extract insights about the client's speaking style,
        common topics, and talking points.
        
        Args:
            transcript (str): The podcast transcript
            campaign_id (Optional[uuid.UUID]): Campaign ID for tracking
            
        Returns:
            Dict[str, Any]: Analysis results including topics, speaking style, etc.
        """
        try:
            analysis_prompt = f"""
            Analyze this podcast transcript and extract insights about the speaker's:
            1. Main topics and areas of expertise
            2. Speaking style and communication patterns
            3. Key messages and themes
            4. Frequently mentioned concepts or keywords
            5. Storytelling approach and examples used
            
            Transcript:
            {transcript}
            
            Please provide a structured analysis that could help improve their media kit and future podcast appearances.
            """
            
            analysis = await self.gemini_service.create_message(
                prompt=analysis_prompt,
                workflow="podcast_transcript_analysis",
                related_campaign_id=campaign_id
            )
            
            return {
                "analysis": analysis,
                "transcript_length": len(transcript),
                "word_count": len(transcript.split()),
                "status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Error analyzing transcript: {e}")
            return {
                "analysis": None,
                "error": str(e),
                "status": "failed"
            }
    
    async def process_podcast_urls_from_questionnaire(self, questionnaire_data: Dict[str, Any], campaign_id: uuid.UUID) -> List[Dict[str, Any]]:
        """
        Process podcast URLs from questionnaire data, download, transcribe, and analyze them.
        
        Args:
            questionnaire_data (Dict[str, Any]): The questionnaire responses
            campaign_id (uuid.UUID): Campaign ID for tracking
            
        Returns:
            List[Dict[str, Any]]: List of processing results for each URL
        """
        results = []
        
        try:
            # Extract podcast URLs from questionnaire data
            # Section 4: Podcast & Media Experience
            media_experience = questionnaire_data.get("mediaExperience", {})
            if not isinstance(media_experience, dict):
                logger.warning("No media experience section found in questionnaire")
                return results
            
            previous_appearances = media_experience.get("previousAppearances", [])
            speaking_clips = media_experience.get("speakingClips", [])
            
            # Combine all URLs
            all_urls = []
            
            # Handle previous appearances
            if isinstance(previous_appearances, list):
                for appearance in previous_appearances:
                    if isinstance(appearance, dict) and appearance.get("link"):
                        all_urls.append({
                            "url": appearance["link"],
                            "type": "previous_appearance",
                            "title": appearance.get("podcastName", "Unknown Podcast")
                        })
            
            # Handle speaking clips
            if isinstance(speaking_clips, list):
                for clip in speaking_clips:
                    if isinstance(clip, dict) and clip.get("link"):
                        all_urls.append({
                            "url": clip["link"],
                            "type": "speaking_clip",
                            "title": clip.get("title", "Speaking Clip")
                        })
                    elif isinstance(clip, str):  # Direct URL string
                        all_urls.append({
                            "url": clip,
                            "type": "speaking_clip",
                            "title": "Speaking Clip"
                        })
            
            logger.info(f"Found {len(all_urls)} podcast URLs to process for campaign {campaign_id}")
            
            # Process each URL
            for i, url_info in enumerate(all_urls):
                if i >= 5:  # Limit to 5 URLs to prevent excessive processing
                    logger.warning(f"Limiting to 5 podcast URLs. Skipping remaining {len(all_urls) - 5} URLs.")
                    break
                
                url = url_info["url"]
                result = {
                    "url": url,
                    "type": url_info["type"],
                    "title": url_info["title"],
                    "status": "processing"
                }
                
                try:
                    # Skip obviously invalid example URLs
                    if 'example.com' in url.lower():
                        logger.warning(f"Skipping example URL: {url}")
                        result.update({
                            "status": "skipped",
                            "error": "Example URL detected",
                            "transcript": None,
                            "analysis": None
                        })
                        results.append(result)
                        continue
                    
                    logger.info(f"Processing podcast URL: {url}")
                    
                    # Download audio
                    audio_file = await self.extract_audio_from_url(url)
                    if not audio_file:
                        result.update({
                            "status": "failed",
                            "error": "Failed to download audio",
                            "transcript": None,
                            "analysis": None
                        })
                        results.append(result)
                        continue
                    
                    # Transcribe audio
                    transcript = await self.transcribe_audio_file(audio_file, campaign_id)
                    if not transcript:
                        result.update({
                            "status": "failed",
                            "error": "Failed to transcribe audio",
                            "transcript": None,
                            "analysis": None
                        })
                        results.append(result)
                        continue
                    
                    # Analyze transcript
                    analysis = await self.analyze_transcript_for_insights(transcript, campaign_id)
                    
                    result.update({
                        "status": "completed",
                        "transcript": transcript,
                        "analysis": analysis,
                        "error": None
                    })
                    
                    logger.info(f"Successfully processed podcast URL: {url}")
                    
                except Exception as e:
                    logger.error(f"Error processing podcast URL {url}: {e}")
                    result.update({
                        "status": "failed",
                        "error": str(e),
                        "transcript": None,
                        "analysis": None
                    })
                
                results.append(result)
                
                # Add delay between processing to avoid rate limiting
                if i < len(all_urls) - 1:
                    await asyncio.sleep(2)
            
        except Exception as e:
            logger.error(f"Error processing podcast URLs from questionnaire: {e}")
        
        return results 