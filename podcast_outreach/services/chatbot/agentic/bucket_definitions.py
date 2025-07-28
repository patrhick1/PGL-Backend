# podcast_outreach/services/chatbot/agentic/bucket_definitions.py

from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
import re
from datetime import datetime
from .data_models import validate_social_media_list

@dataclass
class BucketDefinition:
    """Defines a single information bucket for the chatbot to collect"""
    id: str
    name: str
    description: str
    required: bool
    validation: Callable[[Any], bool]
    example_inputs: List[str]
    min_entries: int = 1
    max_entries: Optional[int] = None
    allow_multiple: bool = False
    data_type: str = "text"  # text, list, number, email, url, etc.
    
    def validate(self, value: Any) -> bool:
        """Validate a value against this bucket's rules"""
        if value is None and self.required:
            return False
        return self.validation(value) if value is not None else True

# Validation functions for reuse
def validate_email(value: str) -> bool:
    """Validate email format"""
    if not isinstance(value, str):
        return False
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, value.strip()))

def validate_url(value: str) -> bool:
    """Validate URL format"""
    if not isinstance(value, str):
        return False
    pattern = r'^https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)$'
    return bool(re.match(pattern, value.strip()))

def validate_linkedin_url(value: str) -> bool:
    """Validate LinkedIn URL specifically"""
    if not isinstance(value, str):
        return False
    return 'linkedin.com/in/' in value.lower()

def validate_non_empty_string(value: str) -> bool:
    """Validate non-empty string"""
    return isinstance(value, str) and len(value.strip()) > 0

def validate_string_list(value: List[str]) -> bool:
    """Validate list of strings"""
    # Accept the special "none" marker
    if value == "none":
        return True
    return isinstance(value, list) and all(isinstance(item, str) for item in value) and len(value) > 0

def validate_string_list_optional(value: Any) -> bool:
    """Validate list of strings for optional fields (can be empty)"""
    # Accept the special "none" marker
    if value == "none":
        return True
    # Accept empty lists for optional fields
    return isinstance(value, list) and all(isinstance(item, str) for item in value)

def validate_story(value: Any) -> bool:
    """Validate story structure - can be string or dict"""
    # Accept the special "none" marker
    if value == "none":
        return True
    if isinstance(value, str):
        # Accept any non-empty string as a valid story
        return bool(value.strip())
    elif isinstance(value, dict):
        # Must have at least subject and result
        return bool(value.get('subject')) and bool(value.get('result'))
    elif isinstance(value, list):
        # If it's a list, validate each item
        return all(validate_story(item) for item in value) if value else False
    return False

def validate_achievement(value: Any) -> bool:
    """Validate achievement structure - can be string or dict"""
    # Accept the special "none" marker
    if value == "none":
        return True
    if isinstance(value, str):
        # Accept any non-empty string as a valid achievement
        return bool(value.strip())
    elif isinstance(value, dict):
        # Must have description
        return bool(value.get('description'))
    elif isinstance(value, list):
        # If it's a list, validate each item
        return all(validate_achievement(item) for item in value) if value else False
    return False

def validate_years_experience(value: Any) -> bool:
    """Validate years of experience - accepts various formats"""
    if not value:
        return False
    
    # Convert to string for processing
    value_str = str(value).strip().lower()
    
    # Direct number
    if value_str.isdigit():
        return True
    
    # Try to extract number from common patterns
    import re
    patterns = [
        r'^(\d+)\s*years?',  # "4 years", "1 year"
        r'^(\d+)\s*yrs?',    # "4 yrs", "1 yr"
        r'^(\d+)$',          # Just the number
    ]
    
    for pattern in patterns:
        match = re.match(pattern, value_str)
        if match:
            return True
    
    return False

# Define all information buckets
INFORMATION_BUCKETS: Dict[str, BucketDefinition] = {
    # Contact Information
    "full_name": BucketDefinition(
        id="full_name",
        name="Full Name",
        description="The person's complete name for professional use",
        required=True,
        validation=validate_non_empty_string,
        example_inputs=[
            "My name is John Smith",
            "I'm Sarah Johnson",
            "Call me Dr. Michael Chen"
        ],
        min_entries=1,
        max_entries=1,
        data_type="text"
    ),
    
    "email": BucketDefinition(
        id="email",
        name="Email Address",
        description="Primary email address for podcast hosts to contact",
        required=True,
        validation=validate_email,
        example_inputs=[
            "My email is john@example.com",
            "You can reach me at sarah@company.org",
            "Contact me at mike@domain.co.uk"
        ],
        min_entries=1,
        max_entries=1,
        data_type="email"
    ),
    
    "linkedin_url": BucketDefinition(
        id="linkedin_url",
        name="LinkedIn Profile",
        description="LinkedIn profile URL for professional background analysis",
        required=False,
        validation=validate_linkedin_url,
        example_inputs=[
            "My LinkedIn is https://linkedin.com/in/johnsmith",
            "Here's my profile: linkedin.com/in/sarah-johnson",
            "I don't have LinkedIn"
        ],
        min_entries=0,
        max_entries=1,
        data_type="url"
    ),
    
    "phone": BucketDefinition(
        id="phone",
        name="Phone Number",
        description="Contact phone number (optional)",
        required=False,
        validation=validate_non_empty_string,
        example_inputs=[
            "My phone is 555-123-4567",
            "Call me at +1 (555) 987-6543",
            "I prefer email only"
        ],
        min_entries=0,
        max_entries=1,
        data_type="text"
    ),
    
    "website": BucketDefinition(
        id="website",
        name="Website",
        description="Personal or company website",
        required=False,
        validation=validate_url,
        example_inputs=[
            "My website is https://example.com",
            "Check out www.mycompany.com",
            "I don't have a website yet"
        ],
        min_entries=0,
        max_entries=1,
        data_type="url"
    ),
    
    "social_media": BucketDefinition(
        id="social_media",
        name="Social Media Profiles",
        description="Other social media profiles (Twitter, Instagram, etc.)",
        required=False,
        validation=validate_social_media_list,
        example_inputs=[
            "I'm @johnsmith on Twitter",
            "Follow me on Instagram @sarah_creates",
            "My YouTube is youtube.com/c/miketeaches"
        ],
        min_entries=0,
        max_entries=5,
        allow_multiple=True,
        data_type="list"
    ),
    
    # Professional Background
    "current_role": BucketDefinition(
        id="current_role",
        name="Current Role",
        description="Current job title and role",
        required=True,
        validation=validate_non_empty_string,
        example_inputs=[
            "I'm the CEO of TechStartup Inc",
            "I work as a Senior Marketing Manager",
            "I'm a freelance consultant"
        ],
        min_entries=1,
        max_entries=1,
        data_type="text"
    ),
    
    "company": BucketDefinition(
        id="company",
        name="Company/Organization",
        description="Current company or organization",
        required=False,
        validation=validate_non_empty_string,
        example_inputs=[
            "I work at Google",
            "I'm with Stanford University",
            "I run my own consulting firm"
        ],
        min_entries=0,
        max_entries=1,
        data_type="text"
    ),
    
    "professional_bio": BucketDefinition(
        id="professional_bio",
        name="Professional Background",
        description="Overview of professional experience and what they do",
        required=True,
        validation=validate_non_empty_string,
        example_inputs=[
            "I help companies transform their digital marketing strategies",
            "I've been teaching computer science for 10 years",
            "I specialize in helping startups scale their operations"
        ],
        min_entries=1,
        max_entries=1,
        data_type="text"
    ),
    
    "years_experience": BucketDefinition(
        id="years_experience",
        name="Years of Experience",
        description="Total years of professional experience",
        required=False,
        validation=validate_years_experience,
        example_inputs=[
            "I have 15 years of experience",
            "I've been doing this for 5 years",
            "Started my career in 2010"
        ],
        min_entries=0,
        max_entries=1,
        data_type="number"
    ),
    
    # Expertise & Achievements
    "expertise_keywords": BucketDefinition(
        id="expertise_keywords",
        name="Areas of Expertise",
        description="Key areas of expertise (3-5 keywords)",
        required=True,
        validation=lambda x: validate_string_list(x) and len(x) >= 3,
        example_inputs=[
            "Digital marketing, SEO, and content strategy",
            "Machine learning, AI ethics, data science",
            "Leadership development, team building, organizational culture"
        ],
        min_entries=3,
        max_entries=10,
        allow_multiple=True,
        data_type="list"
    ),
    
    "success_stories": BucketDefinition(
        id="success_stories",
        name="Success Stories",
        description="Specific examples of impact with measurable results",
        required=True,
        validation=validate_story,
        example_inputs=[
            "I helped a startup increase revenue by 300% in one year",
            "Led a team that reduced customer churn by 45%",
            "Developed a system that saved $2M annually"
        ],
        min_entries=1,
        max_entries=5,
        allow_multiple=True,
        data_type="list"
    ),
    
    "achievements": BucketDefinition(
        id="achievements",
        name="Key Achievements",
        description="Notable achievements with metrics",
        required=False,
        validation=validate_achievement,
        example_inputs=[
            "Won the 2023 Innovation Award",
            "Published 3 bestselling books",
            "Generated $10M in new business"
        ],
        min_entries=0,
        max_entries=5,
        allow_multiple=True,
        data_type="list"
    ),
    
    "unique_perspective": BucketDefinition(
        id="unique_perspective",
        name="Unique Value/Perspective",
        description="What makes their approach or perspective unique",
        required=True,
        validation=validate_non_empty_string,
        example_inputs=[
            "I combine psychology with data science for better insights",
            "My military background brings unique leadership perspectives",
            "I approach problems from both technical and creative angles"
        ],
        min_entries=1,
        max_entries=1,
        data_type="text"
    ),
    
    # Media/Podcast Focus
    "podcast_topics": BucketDefinition(
        id="podcast_topics",
        name="Podcast Topics",
        description="Specific topics they want to discuss on podcasts",
        required=True,
        validation=lambda x: validate_string_list(x) and len(x) >= 2,
        example_inputs=[
            "Leadership in remote teams",
            "The future of AI in healthcare",
            "Building sustainable businesses"
        ],
        min_entries=2,
        max_entries=5,
        allow_multiple=True,
        data_type="list"
    ),
    
    "target_audience": BucketDefinition(
        id="target_audience",
        name="Target Audience",
        description="Who would benefit most from their insights",
        required=True,
        validation=validate_non_empty_string,
        example_inputs=[
            "Startup founders and entrepreneurs",
            "HR professionals and team leaders",
            "Anyone interested in personal development"
        ],
        min_entries=1,
        max_entries=1,
        data_type="text"
    ),
    
    "key_message": BucketDefinition(
        id="key_message",
        name="Key Message/Transformation",
        description="Main message or transformation for listeners",
        required=True,
        validation=validate_non_empty_string,
        example_inputs=[
            "Success comes from consistent small improvements",
            "Technology should enhance human connection, not replace it",
            "Every challenge is an opportunity for growth"
        ],
        min_entries=1,
        max_entries=1,
        data_type="text"
    ),
    
    "speaking_experience": BucketDefinition(
        id="speaking_experience",
        name="Previous Speaking/Podcast Experience",
        description="Previous podcasts or speaking engagements",
        required=False,
        validation=validate_string_list_optional,
        example_inputs=[
            "I was on the Tim Ferriss Show",
            "Spoke at TEDx Boston",
            "Regular guest on Marketing Over Coffee"
        ],
        min_entries=0,
        max_entries=10,
        allow_multiple=True,
        data_type="list"
    ),
    
    # Additional Information
    "promotion_items": BucketDefinition(
        id="promotion_items",
        name="Items to Promote",
        description="Books, courses, services, or products to promote",
        required=False,
        validation=validate_string_list_optional,
        example_inputs=[
            "My new book 'Leadership Reimagined'",
            "Online course on digital marketing",
            "Consulting services for startups"
        ],
        min_entries=0,
        max_entries=5,
        allow_multiple=True,
        data_type="list"
    ),
    
    "scheduling_preference": BucketDefinition(
        id="scheduling_preference",
        name="Scheduling Preferences",
        description="Best way for podcast hosts to schedule with them",
        required=False,
        validation=validate_non_empty_string,
        example_inputs=[
            "Email me directly to coordinate",
            "Use my Calendly link: calendly.com/john",
            "My assistant handles scheduling at assistant@company.com"
        ],
        min_entries=0,
        max_entries=1,
        data_type="text"
    ),
    
    "ideal_podcast": BucketDefinition(
        id="ideal_podcast",
        name="Ideal Podcast Description",
        description="Description of the ideal podcast shows they want to appear on",
        required=False,
        validation=validate_non_empty_string,
        example_inputs=[
            "I'm looking for business podcasts that focus on entrepreneurship and startup growth",
            "Educational podcasts for teachers and educators, especially those discussing innovative teaching methods",
            "Interview-style shows with engaged audiences interested in personal development and mindfulness",
            "Tech podcasts that dive deep into AI and machine learning applications"
        ],
        min_entries=0,
        max_entries=1,
        data_type="text"
    )
}

def get_required_buckets() -> List[str]:
    """Get list of required bucket IDs"""
    return [bucket_id for bucket_id, bucket in INFORMATION_BUCKETS.items() if bucket.required]

def get_optional_buckets() -> List[str]:
    """Get list of optional bucket IDs"""
    return [bucket_id for bucket_id, bucket in INFORMATION_BUCKETS.items() if not bucket.required]

def validate_bucket_data(bucket_id: str, data: Any) -> bool:
    """Validate data for a specific bucket"""
    if bucket_id not in INFORMATION_BUCKETS:
        return False
    return INFORMATION_BUCKETS[bucket_id].validate(data)