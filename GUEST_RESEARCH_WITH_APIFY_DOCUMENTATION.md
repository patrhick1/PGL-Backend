# Guest Research System with Social Media Integration and Apify

## Table of Contents
1. [Overview](#overview)
2. [System Architecture](#system-architecture)
3. [Core Components](#core-components)
4. [Apify Integration](#apify-integration)
5. [Research Workflow](#research-workflow)
6. [Data Input and Output](#data-input-and-output)
7. [Code Examples](#code-examples)
8. [API Configuration](#api-configuration)
9. [Error Handling](#error-handling)
10. [Performance Optimization](#performance-optimization)

## Overview

The Guest Research System is an automated tool that researches podcast guests using their social media profiles. It leverages Apify's web scraping capabilities to extract data from LinkedIn and Twitter/X, then uses AI models to analyze and generate comprehensive research reports.

### Key Features
- **Automated social media profile scraping** using Apify actors
- **Historical post retrieval** from LinkedIn and Twitter
- **AI-powered content analysis** for insights extraction
- **Structured report generation** in multiple formats
- **Parallel processing** for efficient data collection
- **Rate limiting** to respect API constraints

## System Architecture

```
┌─────────────────────┐
│   User Interface    │
│  (Web/CLI Input)    │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐     ┌──────────────────┐
│  Research Engine    │────▶│  State Manager   │
│ (main.py)           │     │(research_state.py)│
└──────────┬──────────┘     └──────────────────┘
           │
           ▼
┌─────────────────────┐
│   Apify Client      │
│ (Social Scraping)   │
└──────────┬──────────┘
           │
     ┌─────┴─────┐
     ▼           ▼
┌─────────┐ ┌─────────┐
│LinkedIn │ │Twitter  │
│ Scraper │ │ Scraper │
└─────────┘ └─────────┘
```

## Core Components

### 1. PodcastResearchEngine (main.py)

The central engine that orchestrates the entire research process:

```python
class PodcastResearchEngine:
    """Main engine handling guest research workflow"""
    
    def __init__(self):
        self.clients = APIClients()
        self.linkedin_pattern = re.compile(
            r'^https?://(www\.)?linkedin\.com/in/[a-z0-9-]+/?(\?.*)?$', re.IGNORECASE
        )
        self.twitter_pattern = re.compile(
            r'^https?://(www\.)?(twitter\.com|x\.com)/[a-z0-9_]+/?(\?.*)?$', re.IGNORECASE
        )
```

### 2. APIClients Container

Manages all external API connections:

```python
class APIClients:
    """Container for external API clients"""
    
    def __init__(self):
        # AI Models for content analysis
        self.chat_llm = ChatOpenAI(
            model_name="o3-mini",
            temperature=None,
            openai_api_key=os.getenv("OPENAI_KEY"),
            reasoning_effort="medium"
        )
        
        # Apify client for social media scraping
        self.apify_client = ApifyClient(os.getenv("APIFY_CLIENT_TOKEN"))
        
        # Search API for finding profiles
        self.tavily_search = TavilySearchAPIWrapper()
```

### 3. ResearchStateManager (research_state.py)

Manages the state throughout the research process:

```python
class GuestResearchState(TypedDict):
    """State container for guest research workflow"""
    host_podcast: str
    guest_name: str
    linkedin_url: str
    twitter_url: str
    linkedIn_post: str
    linkedin_profile: str
    twitter_post: str
    report: str
    # ... other fields
```

## Apify Integration

### LinkedIn Profile Scraping

The system uses two Apify actors for LinkedIn data:

#### 1. LinkedIn Profile Data Extraction
```python
async def _get_linkedin_profile(self, profile_url: str) -> str:
    """Extract LinkedIn profile information using Apify"""
    try:
        logger.info(f"Starting LinkedIn profile extraction for URL: {profile_url}")
        
        # Call the LinkedIn profile scraper actor
        run = await asyncio.to_thread(
            self.clients.apify_client.actor('supreme_coder/linkedin-profile-scraper').call,
            run_input={
                "findContacts": False,
                "scrapeCompany": False,
                "urls": [
                    {
                        "url": profile_url,
                        "method": "GET"
                    }
                ]
            }
        )
        
        # Retrieve the scraped data
        dataset = await asyncio.to_thread(
            self.clients.apify_client.dataset(run["defaultDatasetId"]).list_items
        )
        
        # Process and format the profile data
        profile = dataset.items[0]
        
        # Extract structured information
        result = (
            f"Name: {profile.get('firstName', '')} {profile.get('lastName', '')}\n"
            f"Headline: {profile.get('headline', 'N/A')}\n"
            f"Summary: {profile.get('summary', 'N/A')}\n\n"
            f"Current Position: {profile.get('jobTitle', 'N/A')} at {profile.get('companyName', 'N/A')}\n"
            # ... additional fields
        )
        
        return result
    except Exception as e:
        logger.error(f"LinkedIn profile extraction failed: {str(e)}")
        return f"Error retrieving LinkedIn profile: {str(e)}"
```

#### 2. LinkedIn Posts Retrieval
```python
async def _get_linkedin_posts(self, profile_url: str) -> str:
    """Retrieve LinkedIn posts using Apify"""
    try:
        run_input = {
            "username": profile_url,
            "maxPosts": 20,
            "timeout": 60
        }
        
        # Call the LinkedIn posts scraper
        run = await asyncio.to_thread(
            self.clients.apify_client.actor('apimaestro/linkedin-profile-posts').call,
            run_input=run_input
        )
        
        # Get the posts data
        dataset = await asyncio.to_thread(
            self.clients.apify_client.dataset(run["defaultDatasetId"]).list_items
        )
        
        # Format posts for analysis
        formatted_posts = self._format_social_posts(dataset.items, "linkedin")
        return formatted_posts
    except Exception as e:
        logger.warning(f"LinkedIn posts retrieval failed: {str(e)}")
        return f"Error retrieving LinkedIn posts: {str(e)}"
```

### Twitter/X Scraping

```python
async def _get_twitter_posts(self, profile_url: str) -> str:
    """Retrieve Twitter posts using Apify"""
    try:
        # Extract username from URL
        username = profile_url.rstrip('/').split('/')[-1].split('?')[0]
        
        run_input = {
            "max_posts": 50,
            "username": username
        }
        
        # Call the Twitter scraper
        run = await asyncio.to_thread(
            self.clients.apify_client.actor("danek/twitter-scraper-ppr").call,
            run_input=run_input
        )
        
        # Retrieve tweets
        dataset = await asyncio.to_thread(
            self.clients.apify_client.dataset(run["defaultDatasetId"]).list_items
        )
        
        # Format tweets with engagement metrics
        formatted_posts = self._format_social_posts(dataset.items, "twitter")
        return formatted_posts
    except Exception as e:
        logger.warning(f"Twitter posts retrieval failed: {str(e)}")
        return f"Error retrieving tweets: {str(e)}"
```

### Post Formatting

```python
def _format_social_posts(self, posts: List[Dict], platform: str) -> str:
    """Format social posts for analysis"""
    formatted = []
    for idx, post in enumerate(posts[:10]):  # Limit to 10 posts
        try:
            if platform == "linkedin":
                text = post.get("text", "")[:500]  # Truncate long posts
                date = post.get("posted_at", {}).get("date", "Unknown date")
                
            elif platform == "twitter":
                text = post.get("text", "")[:500]
                date = post.get("created_at", "Unknown date")
                favorites = post.get("favorites", "")
                retweets = post.get("retweets", "")
                
                # Add engagement metrics
                engagement = f" | ❤️ {favorites} | 🔄 {retweets}"
                text = f"{text}\n{engagement}"
            
            formatted.append(f"Post {idx+1} ({date}):\n{text}\n")
            
        except Exception as e:
            logger.warning(f"Error formatting {platform} post {idx}: {str(e)}")
            formatted.append(f"Post {idx+1}: [Error formatting post]\n")
    
    return "\n".join(formatted)
```

## Research Workflow

### 1. Direct Social Media Research Flow

When social media URLs are provided directly:

```python
async def research_podcast_guest(state: GuestResearchState, session_id: str = None, custom_entry_point: str = None) -> Dict[str, Any]:
    """Main function to research a podcast guest"""
    
    # Determine workflow entry point
    if state.get('direct_social') and (state.get('linkedin_url') or state.get('twitter_url')):
        entry_point = "retrieve_social_content"
        logger.info(f"Using direct social workflow")
    
    # Create and execute workflow
    workflow = create_research_workflow(entry_point)
    results = await workflow.ainvoke(state)
```

### 2. Profile Search Flow

When searching for profiles by name:

```python
async def find_social_profiles(self, state: GuestResearchState) -> GuestResearchState:
    """Find social media profiles using search APIs"""
    search_query = f"{state['guest_name']} {state['guest_unique_element']}"
    
    # Parallel social media searches
    linkedin_task = self._search_linkedin(search_query)
    twitter_task = self._search_twitter(search_query)
    
    state["linkedin_url"], state["twitter_url"] = await asyncio.gather(
        linkedin_task, twitter_task
    )
    
    return state

async def _search_linkedin(self, query: str) -> str:
    """Search for LinkedIn profile"""
    results = await async_tavily_search(f"{query} LinkedIn")
    for result in results:
        if await validate_social_url(self.linkedin_pattern, result["url"]):
            return result["url"]
    return ""
```

### 3. Content Retrieval and Analysis

```python
async def retrieve_social_content(self, state: GuestResearchState) -> GuestResearchState:
    """Retrieve historical social media posts"""
    tasks = []
    
    if state["linkedin_url"]:
        tasks.append(self._get_linkedin_posts(state["linkedin_url"]))
        tasks.append(self._get_linkedin_profile(state["linkedin_url"]))
    
    if state["twitter_url"]:
        tasks.append(self._get_twitter_posts(state["twitter_url"]))
    
    # Execute all tasks in parallel
    results = await asyncio.gather(*tasks)
    
    # Store results in state
    if state["linkedin_url"]:
        state["linkedIn_post"] = results[0]
        state["linkedin_profile"] = results[1]
    
    if state["twitter_url"]:
        state["twitter_post"] = results[-1]
    
    return state
```

### 4. Report Generation

```python
async def generate_research_report(self, state: GuestResearchState) -> GuestResearchState:
    """Generate comprehensive research report using multiple LLM calls"""
    
    # LLM call 1: Create Introduction
    introduction = await self._generate_introduction(state)
    
    # LLM call 2: Generate Summary of Topics & Themes
    summary = await self._generate_summary(state)
    
    # LLM call 3: Create Podcast Questions
    questions = await self._generate_questions(state)
    
    # LLM call 4: Structure Previous Podcast Appearances
    appearances = await self._format_appearances(state)
    
    # Combine all parts into final report
    final_report = f"""
# Guest Profile Report for {state['guest_name']}

## Introduction
{introduction}

## Summary of Topics & Themes
{summary}

## Podcast Questions
{questions}

## Previous Podcast Appearances
{appearances}
    """
    
    state["report"] = final_report
    return state
```

## Data Input and Output

### Input Data Structure

```python
# Example input for direct social media research
input_state = {
    "episode_title": "Interview with Tech Innovator",
    "request_id": "unique-request-123",
    "guest_name": "Jane Doe",
    "linkedin_url": "https://linkedin.com/in/janedoe",
    "twitter_url": "https://twitter.com/janedoe",
    "direct_social": True,
    "host_podcast": "The Innovation Show"
}
```

### LinkedIn Data Output

```json
{
    "firstName": "Jane",
    "lastName": "Doe",
    "headline": "CEO & Founder at TechStartup | Innovation Speaker",
    "summary": "Passionate about leveraging technology...",
    "positions": [
        {
            "title": "Chief Executive Officer",
            "companyName": "TechStartup",
            "timePeriod": {
                "startDate": {"month": 1, "year": 2020},
                "endDate": null
            }
        }
    ],
    "educations": [
        {
            "schoolName": "MIT",
            "degreeName": "Master's",
            "fieldOfStudy": "Computer Science"
        }
    ],
    "skills": ["AI", "Machine Learning", "Leadership"]
}
```

### LinkedIn Posts Output

```json
[
    {
        "text": "Excited to announce our new AI product launch...",
        "posted_at": {
            "date": "2024-01-15"
        },
        "reactions": 245,
        "comments": 32
    }
]
```

### Twitter Data Output

```json
[
    {
        "text": "Just published my thoughts on the future of AI...",
        "created_at": "2024-01-20",
        "favorites": 1250,
        "retweets": 432,
        "url": "https://twitter.com/janedoe/status/123456789"
    }
]
```

### Final Report Output

```markdown
# Guest Profile Report for Jane Doe

## Introduction
Jane Doe is a technology innovator and CEO of TechStartup, with a strong presence on social media.
- LinkedIn: https://linkedin.com/in/janedoe
- Twitter: https://twitter.com/janedoe

Her company, TechStartup, focuses on AI-powered solutions for enterprise clients...

## Summary of Topics & Themes
Based on analysis of Jane's social media posts, the following key themes emerge:

1. **Artificial Intelligence & Machine Learning**
   - Frequently discusses AI ethics and responsible development
   - Shares insights on practical AI applications

2. **Leadership & Entrepreneurship**
   - Posts about building diverse teams
   - Shares startup journey experiences

3. **Innovation in Technology**
   - Commentary on emerging tech trends
   - Predictions about future technological developments

## Podcast Questions
1. Can you tell us about your journey from MIT to founding TechStartup?
2. What inspired you to focus on AI-powered solutions for enterprise?
3. In your recent LinkedIn post, you mentioned "responsible AI development." What does that mean to you?
4. How do you balance technical innovation with ethical considerations?
5. What advice would you give to aspiring tech entrepreneurs?

## Previous Podcast Appearances
- The AI Revolution Podcast (January 2024)
- Startup Stories (December 2023)
- Tech Leaders Unplugged (November 2023)
```

## API Configuration

### Required Environment Variables

```bash
# Apify Configuration
APIFY_CLIENT_TOKEN=your_apify_api_token

# AI Model Configuration
OPENAI_KEY=your_openai_api_key
GEMINI_API_KEY=your_gemini_api_key

# Search API
TAVILY_API_KEY=your_tavily_api_key

# Podcast APIs (optional)
PODSCANAPI=your_podscan_api_key
LISTENNOTES_API_KEY=your_listennotes_api_key
```

### Apify Actor Configuration

LinkedIn Profile Scraper:
```python
actor_config = {
    "actor": "supreme_coder/linkedin-profile-scraper",
    "input": {
        "findContacts": False,
        "scrapeCompany": False,
        "urls": [{"url": profile_url, "method": "GET"}]
    }
}
```

LinkedIn Posts Scraper:
```python
actor_config = {
    "actor": "apimaestro/linkedin-profile-posts",
    "input": {
        "username": profile_url,
        "maxPosts": 20,
        "timeout": 60
    }
}
```

Twitter Scraper:
```python
actor_config = {
    "actor": "danek/twitter-scraper-ppr",
    "input": {
        "max_posts": 50,
        "username": username
    }
}
```

## Error Handling

### Apify Error Handling

```python
async def _get_linkedin_posts(self, profile_url: str) -> str:
    """Retrieve LinkedIn posts with comprehensive error handling"""
    if not profile_url:
        logger.info("LinkedIn posts URL not provided")
        return "No LinkedIn profile URL provided."
    
    try:
        # Call Apify actor
        run = await asyncio.to_thread(
            self.clients.apify_client.actor('apimaestro/linkedin-profile-posts').call,
            run_input=run_input
        )
    except Exception as actor_error:
        logger.warning(f"Error calling LinkedIn scraper actor: {str(actor_error)}")
        return f"Error accessing LinkedIn data: {str(actor_error)}"
    
    # Verify response structure
    if not run or not isinstance(run, dict) or "defaultDatasetId" not in run:
        logger.warning(f"Invalid response from LinkedIn scraper")
        return "Unable to retrieve LinkedIn posts: Invalid API response"
    
    # Get dataset with error handling
    try:
        dataset = await asyncio.to_thread(
            self.clients.apify_client.dataset(run["defaultDatasetId"]).list_items
        )
    except Exception as dataset_error:
        logger.warning(f"Error retrieving LinkedIn dataset: {str(dataset_error)}")
        return f"Error retrieving LinkedIn posts: {str(dataset_error)}"
    
    # Check data validity
    if not dataset or not hasattr(dataset, 'items'):
        logger.warning(f"No LinkedIn posts data structure")
        return "No LinkedIn posts found (invalid data structure)."
```

### Rate Limiting

```python
# Rate limiter configuration
TRANSCRIPTION_LIMITER = AsyncLimiter(5, 60)  # 5 requests per minute

async def _check_rate_limits(self):
    """Check and handle API rate limits"""
    current_time = time.time()
    
    # Reset counter if past reset time
    if current_time > self.rate_limit_reset_time:
        self.rate_limit_remaining = 60
        self.rate_limit_reset_time = current_time + 60
    
    # Wait if close to limit
    if self.rate_limit_remaining < 3:
        wait_time = max(0, self.rate_limit_reset_time - current_time)
        logger.info(f"Rate limit almost reached, waiting for {wait_time:.2f} seconds")
        await asyncio.sleep(wait_time + 1)
```

## Performance Optimization

### 1. Parallel Processing

The system uses asyncio for concurrent operations:

```python
async def retrieve_social_content(self, state: GuestResearchState) -> GuestResearchState:
    """Retrieve all social content in parallel"""
    tasks = []
    
    # Create all tasks
    if state["linkedin_url"]:
        tasks.append(self._get_linkedin_posts(state["linkedin_url"]))
        tasks.append(self._get_linkedin_profile(state["linkedin_url"]))
    
    if state["twitter_url"]:
        tasks.append(self._get_twitter_posts(state["twitter_url"]))
    
    # Execute all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
```

### 2. Batch Processing

For large numbers of posts:

```python
async def summarize_social_posts(self, posts: List[Dict[str, Any]], 
                                platform: str, 
                                guest_name: str, 
                                batch_size: int = 5) -> List[Dict[str, Any]]:
    """Process posts in batches to avoid rate limits"""
    
    for i in range(0, len(posts), batch_size):
        batch = posts[i:i+batch_size]
        
        # Wait for rate limits
        await self._check_rate_limits()
        
        # Process batch
        response = await self.llm.ainvoke([prompt, content])
        
        # Add delay between batches
        await asyncio.sleep(1)
```

### 3. Caching Strategy

```python
# Use temporary file caching for audio transcriptions
with tempfile.NamedTemporaryFile(suffix=file_extension) as temp_file:
    temp_file_path = temp_file.name
    temp_file.write(audio_data)
    
    # Process file
    result = await process_audio_file(temp_file_path)
```

## Complete Example: Research Flow

```python
import asyncio
from main import research_podcast_guest, GuestResearchState

async def research_guest_example():
    """Complete example of researching a podcast guest"""
    
    # Initialize state with social media URLs
    state = GuestResearchState(
        episode_title="Tech Innovation Discussion",
        request_id="req-123",
        guest_name="Jane Doe",
        linkedin_url="https://linkedin.com/in/janedoe",
        twitter_url="https://twitter.com/janedoe",
        direct_social=True,
        host_podcast="The Innovation Show",
        # Initialize other required fields
        rss_feed="",
        search_guest_name="",
        episodes=[],
        episode_description="",
        guest_company="",
        transcript="",
        is_linkedin_url=True,
        is_twitter_url=True,
        linkedIn_post="",
        linkedin_profile="",
        twitter_post="",
        guest_unique_element="",
        guest_reason="",
        report="",
        document_url="",
        introduction="",
        summary="",
        question="",
        appearance="",
        transcript_summary=[]
    )
    
    try:
        # Run the research
        results = await research_podcast_guest(state)
        
        # Access the results
        print(f"Guest: {results['guest']}")
        print(f"LinkedIn: {results['linkedin']}")
        print(f"Report URL: {results['document_url']}")
        print(f"\nIntroduction:\n{results['introduction']}")
        print(f"\nSummary:\n{results['summary']}")
        print(f"\nQuestions:\n{results['question']}")
        
    except Exception as e:
        print(f"Research failed: {str(e)}")

# Run the example
asyncio.run(research_guest_example())
```

## Conclusion

The Guest Research System provides a comprehensive solution for automated podcast guest research by:

1. **Leveraging Apify's powerful web scraping capabilities** to extract data from social media platforms
2. **Using AI models** to analyze and summarize large amounts of content
3. **Implementing parallel processing** for efficient data collection
4. **Handling errors gracefully** with fallbacks and detailed logging
5. **Generating structured reports** that provide actionable insights for podcast hosts

The system transforms hours of manual research into an automated process that delivers comprehensive guest profiles in minutes, making it an invaluable tool for podcast production teams.