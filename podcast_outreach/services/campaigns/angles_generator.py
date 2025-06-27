# podcast_outreach/services/campaigns/angles_generator.py
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

# Project-specific services (UPDATED IMPORTS)
from podcast_outreach.database.queries import campaigns as campaign_queries # Use modular query
from podcast_outreach.services.campaigns.questionnaire_social_processor import QuestionnaireSocialProcessor
from podcast_outreach.integrations.google_docs import GoogleDocsService # Use new integration path
from podcast_outreach.services.ai.openai_client import OpenAIService # Use new AI service path
from podcast_outreach.services.ai.tracker import tracker as ai_tracker # Use new AI tracker path
from podcast_outreach.utils.data_processor import extract_document_id # Use new utils path
from podcast_outreach.services.campaigns.content_processor import ClientContentProcessor # Import ClientContentProcessor

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
        You are a junior consultant at a PR firm. I am attaching relevant client information for you.
        We want to pitch your client as a guest on other podcasts, pitch him for guest posts in blogs and have journalists write articles about him. From the information provided, follow the guides for crafting an effective bio and for developing angles.

        ---
        Craft an Effective Bio:
        One of the most important questions you need to address when you reach out to a host is: Who are you?
        To answer that question and make a great first impression, you'll need a rock solid bio that tells the podcast host a bit about you and why you're an authority within your niche. You'll want to prepare several different versions of your bio, each with a specific purpose:

        *   **Full Bio**: A detailed bio you would put up on a website or a blog. It can be up to several paragraphs long and should cover your background, accomplishments, and authority in detail.
        *   **Summary Bio**: A succinct bio that's generally just two paragraphs covering your background and current work. Hosts may use this version for show notes, on-air intros, and more.
        *   **Short Bio**: A bio that's less than 280 characters so it can be used for social media and short blogs.

        Creating your bios before you start reaching out to hosts allows you to take time to think things through and create strong, descriptive bios. You also have them on-hand and ready to send when a guest application or host inevitably asks for them.

        In addition to your bios, you need to tell hosts what topics you're available to talk about.

        ---
        Developing Your Angles:
        When it comes to podcast guest placement, angles are prepared topics and unique perspectives you can offer the hosts to whom you reach out. Angles are important because they narrow your expertise into a tangible subject for a podcast episode. After all, the hosts might not be experts in your industry — you are the expert.

        Providing angles in your pitches is vital for getting booked. Start your conversation with the host by being specific; it allows you to provide them with multiple options in case your initial angle doesn't resonate with them or they already have someone lined up for a similar discussion.

        You should prepare at least 10 angle options to use. Each angle should include the following:

        *   **Topic**: The subject in which you're an authority and about which you can talk as a guest.
        *   **Outcome**: The outcome(s) podcast listeners can expect to see or learn.
        *   **Description**: More information about the topic and your unique perspective, as well as why you're the authority to have on the show for such a discussion.

        Examples of angles in the following format (Topic; Outcome; Description), separated by a semi-colon:
        Topic: Content Creation: Quality vs. Quantity; Outcome: High Value engaged audience, more leads, clients that respect your more. ; Description: Discussing the importance of quality content creation over quantity for lead flow. We've just published our 5th piece of content coming up on our 3rd year in business as a content marketing agency.
        Topic: Educating clients vs. Traditional sales; Outcome: High Value engaged audience, more leads, clients that respect you more. ; Description: How educational content establishes authority and speeds sales when the traditional methods fall flat. We used this strategy to build Call For Content into a 6 figure agency.
        Topic: Is college worth the cost? ; Outcome: Who college isn't for, how to hack the best parts for free ; Description: Michael, a two time college dropout and recent graduate discusses how individuals can establish themselves without formal education and the importance of ROI in education.

        ---
        Now, craft the 3 bios (Full, Summary, Short) following the guidelines provided, and then give me at least 10 topics the client can speak on, with the outcome for each and a description for each, based on the method outlined in the examples provided.
        """
        # Keyword prompt template is now integrated directly into the process_campaign method

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

            await ai_tracker.log_usage(
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
            
            final_summary = "\n\n---\n\n".join(summarized_chunks) # Join summaries with a clear separator
            logger.info(f"Summarized '{title_for_log}': Original length {len(content)}, Summary length {len(final_summary)}")
            return final_summary
        except Exception as e:
            logger.error(f"Error summarizing content for '{title_for_log}': {e}. Returning truncated original.")
            return content[:max_length - 500] # Truncate to be safe


    def _extract_questionnaire_data(self, questionnaire_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract and organize questionnaire data into a structured format."""
        
        # Extract contact info
        contact_info = questionnaire_data.get("contactInfo", {})
        full_name = contact_info.get("fullName", "")
        email = contact_info.get("email", "")
        website = contact_info.get("website", "")
        social_links = contact_info.get("socialLinks", {})
        
        # Extract professional bio
        professional_bio = questionnaire_data.get("professionalBio", {})
        about_work = professional_bio.get("aboutWork", "")
        expertise_topics = professional_bio.get("expertiseTopics", [])
        achievements = professional_bio.get("achievements", "")
        unique_perspectives = professional_bio.get("uniquePerspectives", "")
        
        # Extract suggested topics
        suggested_topics = questionnaire_data.get("suggestedTopics", {})
        topics = suggested_topics.get("topics", [])
        key_stories = suggested_topics.get("keyStoriesOrMessages", "")
        
        # Extract sample questions
        sample_questions = questionnaire_data.get("sampleQuestions", {})
        frequently_asked = sample_questions.get("frequentlyAsked", "")
        love_to_be_asked = sample_questions.get("loveToBeAsked", "")
        
        # Extract social proof
        social_proof = questionnaire_data.get("socialProof", {})
        testimonials = social_proof.get("testimonials", "")
        notable_stats = social_proof.get("notableStats", "")
        
        # Extract media experience
        media_experience = questionnaire_data.get("mediaExperience", {})
        previous_features = media_experience.get("previousFeatures", "")
        notable_media = media_experience.get("notableMedia", "")
        
        # Extract audience insights
        audience_insights = questionnaire_data.get("audienceInsights", {})
        target_audience = audience_insights.get("targetAudience", "")
        audience_challenges = audience_insights.get("audienceChallenges", "")
        
        return {
            "full_name": full_name,
            "email": email,
            "website": website,
            "social_links": social_links,
            "about_work": about_work,
            "expertise_topics": expertise_topics,
            "achievements": achievements,
            "unique_perspectives": unique_perspectives,
            "topics": topics,
            "key_stories": key_stories,
            "frequently_asked": frequently_asked,
            "love_to_be_asked": love_to_be_asked,
            "testimonials": testimonials,
            "notable_stats": notable_stats,
            "previous_features": previous_features,
            "notable_media": notable_media,
            "target_audience": target_audience,
            "audience_challenges": audience_challenges
        }
    
    def _create_bio_generation_prompt(self, data: Dict[str, Any]) -> str:
        """Create a comprehensive prompt for bio generation using actual data."""
        
        prompt = f"""You are an expert PR consultant specializing in podcast guest placement. 
Create compelling bios for {data['full_name']} based on the following real information:

ABOUT THEIR WORK:
{data['about_work']}

AREAS OF EXPERTISE:
{', '.join(data['expertise_topics']) if isinstance(data['expertise_topics'], list) else data['expertise_topics']}

KEY ACHIEVEMENTS:
{data['achievements']}

UNIQUE PERSPECTIVES:
{data['unique_perspectives']}

TARGET AUDIENCE:
{data['target_audience']}

NOTABLE STATISTICS/METRICS:
{data['notable_stats']}

PREVIOUS MEDIA FEATURES:
{data['previous_features']}

Create three versions of their bio:

1. **FULL BIO** (2-3 paragraphs):
- Start with a powerful hook about who they are and their expertise
- Include their professional journey and key achievements
- Highlight what makes them unique in their field
- End with their current focus and mission
- Make it compelling and story-driven

2. **SUMMARY BIO** (2 paragraphs):
- Concise version highlighting their expertise and authority
- Include 1-2 key achievements or credentials
- Focus on what value they bring to audiences

3. **SHORT BIO** (Under 280 characters):
- Twitter-friendly version
- Include their main expertise and one standout credential
- Must be punchy and memorable

IMPORTANT GUIDELINES:
- Write in third person
- Use specific details and achievements from the provided information
- NO PLACEHOLDERS or generic statements
- Make each bio compelling and podcast-host friendly
- Focus on what makes them an interesting guest
- Include quantifiable results where available

Generate the bios now:"""
        
        return prompt
    
    def _create_angles_generation_prompt(self, data: Dict[str, Any]) -> str:
        """Create a comprehensive prompt for angles generation."""
        
        prompt = f"""You are an expert PR consultant specializing in podcast guest placement.
Create compelling podcast angles for {data['full_name']} based on their expertise and experience.

THEIR EXPERTISE:
{', '.join(data['expertise_topics']) if isinstance(data['expertise_topics'], list) else data['expertise_topics']}

KEY STORIES AND MESSAGES:
{data['key_stories']}

UNIQUE PERSPECTIVES:
{data['unique_perspectives']}

AUDIENCE CHALLENGES THEY ADDRESS:
{data['audience_challenges']}

QUESTIONS THEY LOVE TO ANSWER:
{data['love_to_be_asked']}

Generate 10-12 compelling podcast angles. Each angle should include:

**Topic**: The specific subject they can discuss (be specific, not generic)
**Outcome**: What listeners will learn or gain (be concrete and valuable)
**Description**: 2-3 sentences explaining their unique take and why they're the perfect guest for this topic

FORMAT EACH ANGLE EXACTLY LIKE THIS:
Topic: [Specific, compelling topic title]
Outcome: [Concrete listener benefit/learning]
Description: [2-3 sentences with their unique perspective and credentials]

IMPORTANT GUIDELINES:
- Make each angle specific and newsworthy
- Focus on current trends and timely topics in their field
- Include controversial or counterintuitive perspectives where appropriate
- Ensure outcomes are tangible and valuable to listeners
- Reference specific experiences or data points from their background
- Make angles diverse - covering different aspects of their expertise
- NO GENERIC TOPICS - be specific and compelling

Generate the angles now:"""
        
        return prompt

    async def process_campaign(self, campaign_id: str) -> Dict[str, Any]:
        """
        Main processing function for a single campaign.
        Fetches data, generates bio & angles, creates GDocs, and updates PostgreSQL.
        """
        start_time = time.time()
        self.stats["campaigns_processed"] += 1
        campaign_name = "Unknown Campaign" # Default in case of early failure
        
        try:
            campaign_pg = await campaign_queries.get_campaign_by_id(uuid.UUID(campaign_id)) # Use correct service & ensure UUID
            if not campaign_pg:
                logger.error(f"Campaign {campaign_id} not found in PostgreSQL.")
                self.stats["failed_generations"] += 1
                return {"status": "error", "reason": f"Campaign {campaign_id} not found."}

            campaign_name = campaign_pg.get("campaign_name", "Untitled Campaign")
            logger.info(f"Processing campaign: '{campaign_name}' (ID: {campaign_id})")

            # Check if we have questionnaire data
            questionnaire_data = campaign_pg.get("questionnaire_responses")
            if not questionnaire_data:
                logger.warning(f"No questionnaire data found for campaign {campaign_id}. Cannot proceed.")
                self.stats["failed_generations"] += 1
                return {"status": "skipped", "reason": "No questionnaire data available."}
            
            # Extract structured data from questionnaire
            extracted_data = self._extract_questionnaire_data(questionnaire_data)
            
            if not extracted_data.get("full_name"):
                logger.error(f"No name found in questionnaire data for campaign {campaign_id}")
                self.stats["failed_generations"] += 1
                return {"status": "error", "reason": "Missing client name in questionnaire data"}
            
            logger.info(f"Generating bio and angles for {extracted_data['full_name']} (Campaign: {campaign_id})")
            
            # Also fetch any supplementary content if available
            social_posts_input = campaign_pg.get("compiled_social_posts", "")
            social_posts_content = ""
            if social_posts_input:
                if social_posts_input.startswith("https://docs.google.com/document/d/"):
                        social_posts_content = await self._get_gdoc_content_async(social_posts_input, f"{campaign_name} - Social Posts")
                else: # Assume direct text
                    social_posts_content = social_posts_input
            
            podcast_transcripts_content = await self._get_gdoc_content_async(campaign_pg.get("podcast_transcript_link"), f"{campaign_name} - Podcast Transcripts")
            articles_content = await self._get_gdoc_content_async(campaign_pg.get("compiled_articles_link"), f"{campaign_name} - Articles")

            # Summarize supplementary content if necessary
            summarized_social = await self._summarize_content_if_needed(social_posts_content, f"{campaign_name} - Social Posts", max_length=30000)
            summarized_podcasts = await self._summarize_content_if_needed(podcast_transcripts_content, f"{campaign_name} - Podcast Transcripts", max_length=50000)
            summarized_articles = await self._summarize_content_if_needed(articles_content, f"{campaign_name} - Articles", max_length=50000)

            # 2. Generate Bio using actual questionnaire data
            bio_prompt = self._create_bio_generation_prompt(extracted_data)
            
            # Add supplementary content to the prompt if available
            if summarized_social or summarized_podcasts or summarized_articles:
                bio_prompt += "\n\nADDITIONAL CONTEXT FROM THEIR CONTENT:\n"
                if summarized_social:
                    bio_prompt += f"\nSocial Media Posts:\n{summarized_social[:2000]}..."
                if summarized_podcasts:
                    bio_prompt += f"\nPodcast Appearances:\n{summarized_podcasts[:2000]}..."
                if summarized_articles:
                    bio_prompt += f"\nArticles:\n{summarized_articles[:2000]}..."
            
            logger.info(f"Generating Bio for '{campaign_name}' using Gemini...")
            bio_response = await self._call_gemini_langchain(bio_prompt, "generate_bio", delay_seconds=1.5)

            # 3. Generate Angles using actual questionnaire data
            angles_prompt = self._create_angles_generation_prompt(extracted_data)
            
            # Add supplementary content to the prompt if available
            if summarized_social or summarized_podcasts or summarized_articles:
                angles_prompt += "\n\nADDITIONAL CONTEXT FROM THEIR CONTENT:\n"
                if summarized_social:
                    angles_prompt += f"\nSocial Media Posts:\n{summarized_social[:2000]}..."
                if summarized_podcasts:
                    angles_prompt += f"\nPodcast Appearances:\n{summarized_podcasts[:2000]}..."
                if summarized_articles:
                    angles_prompt += f"\nArticles:\n{summarized_articles[:2000]}..."
            
            logger.info(f"Generating Angles for '{campaign_name}' using Gemini...")
            angles_response = await self._call_gemini_langchain(angles_prompt, "generate_angles", delay_seconds=1.5)
            
            # Format the responses
            bio_text_content = bio_response if bio_response else "Bio generation failed."
            angles_text_content = angles_response if angles_response else "Angles generation failed."
            
            # Create formatted content with metadata
            formatted_bio_content = f"""
{extracted_data['full_name']} - Professional Bio
Generated: {datetime.now().strftime('%Y-%m-%d')}

===============================================

{bio_text_content}

===============================================

Website: {extracted_data.get('website', 'Not provided')}
Email: {extracted_data.get('email', 'Not provided')}
"""
            
            formatted_angles_content = f"""
{extracted_data['full_name']} - Podcast Angles
Generated: {datetime.now().strftime('%Y-%m-%d')}

===============================================

{angles_text_content}

===============================================

Additional Context:
- Target Audience: {extracted_data.get('target_audience', 'Not specified')}
- Key Expertise: {', '.join(extracted_data['expertise_topics']) if isinstance(extracted_data['expertise_topics'], list) else extracted_data['expertise_topics']}
"""

            # 4. Create Google Docs for Bio and Angles
            logger.info(f"Creating Google Docs for '{campaign_name}'...")
            await asyncio.sleep(1.0) # Small delay
            bio_gdoc_title = f"{extracted_data['full_name']} - Professional Bio"
            bio_gdoc_link = await self._run_in_executor(self.google_docs_service.create_document, bio_gdoc_title, formatted_bio_content)
            if bio_gdoc_link:
                    bio_gdoc_id = extract_document_id(bio_gdoc_link)
                    await self._run_in_executor(self.google_docs_service.share_document, bio_gdoc_id) # Share it
                    logger.info(f"Bio GDoc created and shared: {bio_gdoc_link}")
            else:
                logger.error(f"Failed to create Bio GDoc for {campaign_name}")
                # Handle GDoc creation failure - perhaps proceed without link or log error

            await asyncio.sleep(1.5) # Small delay
            angles_gdoc_title = f"{extracted_data['full_name']} - Podcast Angles"
            angles_gdoc_link = await self._run_in_executor(self.google_docs_service.create_document, angles_gdoc_title, formatted_angles_content)
            if angles_gdoc_link:
                angles_gdoc_id = extract_document_id(angles_gdoc_link)
                await self._run_in_executor(self.google_docs_service.share_document, angles_gdoc_id) # Share it
                logger.info(f"Angles GDoc created and shared: {angles_gdoc_link}")
            else:
                logger.error(f"Failed to create Angles GDoc for {campaign_name}")

            # 5. Generate Keywords based on actual content
            logger.info(f"Generating keywords for '{campaign_name}'...")
            # Using the embedded keyword prompt with actual bio and angles content
            keyword_generation_prompt = f"""You are an expert PR consultant specializing in podcast guest selection.
Based on the following client bio and angles, generate exactly 20 relevant keywords that represent their expertise, topics, and areas of knowledge.

These keywords should:
- Be specific to their actual expertise (not generic)
- Include industry terms, topics they can speak about on a podcast
- Represent their unique value proposition
- Be useful for podcast hosts to understand their niche
- Include both broad and specific terms
- Be 2-4 words each

Client Bio:
{bio_text_content[:2000]}

Client Angles:
{angles_text_content[:3000]}

Please respond with exactly 20 keywords separated by commas, no numbering or additional text:"""
            generated_keywords = await self._call_gemini_langchain(keyword_generation_prompt, "generate_keywords", delay_seconds=1.0)
            # Clean up keywords: remove "Keywords:", newlines, excessive spacing.
            cleaned_keywords = generated_keywords.replace("Keywords:", "").strip()
            logger.info(f"Keywords generated for '{campaign_name}': {cleaned_keywords}")
            
            # Convert cleaned_keywords string to a list for TEXT[] compatibility
            # Assuming keywords are comma-separated; adjust if AI returns them differently (e.g., newline-separated)
            keywords_list = [kw.strip() for kw in cleaned_keywords.split(',') if kw.strip()] 
            if not keywords_list and cleaned_keywords: # Handle case where it might be a single keyword or space-separated
                keywords_list = [kw.strip() for kw in cleaned_keywords.split() if kw.strip()]

            # 5.5. Generate ideal podcast description if questionnaire data exists
            ideal_podcast_description = None
            questionnaire_responses = campaign_pg.get('questionnaire_responses')
            if questionnaire_responses:
                try:
                    social_processor = QuestionnaireSocialProcessor()
                    ideal_podcast_description = social_processor.extract_ideal_podcast_description(questionnaire_responses)
                    logger.info(f"Generated ideal podcast description for '{campaign_name}': {ideal_podcast_description[:100]}...")
                except Exception as e:
                    logger.warning(f"Failed to generate ideal podcast description for campaign {campaign_id}: {e}")

            # 6. Update PostgreSQL
            update_payload = {
                "campaign_bio": bio_gdoc_link if bio_gdoc_link else "Bio GDoc creation failed",
                "campaign_angles": angles_gdoc_link if angles_gdoc_link else "Angles GDoc creation failed",
                "gdoc_keywords": keywords_list # Save to gdoc_keywords
            }
            
            # Add ideal podcast description if generated
            if ideal_podcast_description:
                update_payload["ideal_podcast_description"] = ideal_podcast_description
            
            fields_being_updated = list(update_payload.keys())
            logger.info(f"Updating campaign {campaign_id} in PostgreSQL with fields: {fields_being_updated}")
            updated_campaign_record = await campaign_queries.update_campaign(uuid.UUID(campaign_id), update_payload)

            if updated_campaign_record:
                # Directly call the content processor's main logic
                logger.info(f"Directly calling content processing for campaign {campaign_id} after GDoc processing.")
                content_processor = ClientContentProcessor()
                processing_success = await content_processor.process_and_embed_campaign_data(uuid.UUID(campaign_id))
                if processing_success:
                    logger.info(f"Content processing and embedding successful for campaign {campaign_id}.")
                else:
                    logger.warning(f"Content processing and embedding failed or returned False for campaign {campaign_id}.")
            else:
                logger.error(f"Failed to update campaign {campaign_id} with GDoc links and keywords, cannot proceed to content processing.")

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
                await campaign_queries.update_campaign(uuid.UUID(campaign_id), {
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
