# podcast_outreach/services/chatbot/agentic/data_models.py

from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass
from enum import Enum
import re

class SocialMediaPlatform(Enum):
    """Known social media platforms"""
    TWITTER = "twitter"
    INSTAGRAM = "instagram"
    LINKEDIN = "linkedin"
    FACEBOOK = "facebook"
    YOUTUBE = "youtube"
    TIKTOK = "tiktok"
    GITHUB = "github"
    MEDIUM = "medium"
    SUBSTACK = "substack"
    OTHER = "other"

@dataclass
class SocialMediaProfile:
    """Structured representation of a social media profile"""
    platform: str  # Platform name (twitter, instagram, etc.)
    handle: Optional[str] = None  # Username/handle (without @)
    url: Optional[str] = None  # Full URL
    display_format: Optional[str] = None  # How user originally wrote it
    
    def to_string(self) -> str:
        """Convert to a user-friendly string format"""
        if self.display_format:
            return self.display_format
        elif self.url:
            return f"{self.platform.title()}: {self.url}"
        elif self.handle:
            return f"{self.platform.title()}: @{self.handle}"
        else:
            return f"{self.platform.title()} profile"
    
    def to_dict(self) -> Dict[str, str]:
        """Convert to dictionary for storage"""
        return {
            'platform': self.platform,
            'handle': self.handle,
            'url': self.url,
            'display_format': self.display_format or self.to_string()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, str]) -> 'SocialMediaProfile':
        """Create from dictionary"""
        return cls(
            platform=data.get('platform', 'other'),
            handle=data.get('handle'),
            url=data.get('url'),
            display_format=data.get('display_format')
        )

class SocialMediaExtractor:
    """Extract and normalize social media information from various formats"""
    
    # Platform URL patterns
    PLATFORM_PATTERNS = {
        'twitter': [
            r'(?:https?://)?(?:www\.)?twitter\.com/(\w+)',
            r'(?:https?://)?(?:www\.)?x\.com/(\w+)',
            r'@(\w+).*twitter',
            r'twitter.*@(\w+)'
        ],
        'instagram': [
            r'(?:https?://)?(?:www\.)?instagram\.com/(\w+)',
            r'@(\w+).*instagram',
            r'instagram.*@(\w+)'
        ],
        'linkedin': [
            r'(?:https?://)?(?:www\.)?linkedin\.com/in/([\w-]+)',
            r'linkedin.*/in/([\w-]+)'
        ],
        'youtube': [
            r'(?:https?://)?(?:www\.)?youtube\.com/(?:c|channel|user)/([\w-]+)',
            r'youtube.*/([\w-]+)'
        ],
        'facebook': [
            r'(?:https?://)?(?:www\.)?facebook\.com/([\w.]+)',
            r'fb\.com/([\w.]+)'
        ],
        'tiktok': [
            r'(?:https?://)?(?:www\.)?tiktok\.com/@([\w.]+)',
            r'@(\w+).*tiktok',
            r'tiktok.*@(\w+)'
        ],
        'github': [
            r'(?:https?://)?(?:www\.)?github\.com/([\w-]+)',
            r'github.*/([\w-]+)'
        ],
        'medium': [
            r'(?:https?://)?(?:www\.)?medium\.com/@([\w.]+)',
            r'medium.*@([\w.]+)'
        ],
        'substack': [
            r'(?:https?://)?([\w-]+)\.substack\.com',
            r'substack.*/([\w-]+)'
        ]
    }
    
    @classmethod
    def extract_from_text(cls, text: str) -> List[SocialMediaProfile]:
        """Extract social media profiles from free-form text"""
        profiles = []
        lines = text.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # Try to extract structured info
            profile = cls._extract_single_profile(line)
            if profile:
                profiles.append(profile)
        
        return profiles
    
    @classmethod
    def _extract_single_profile(cls, text: str) -> Optional[SocialMediaProfile]:
        """Extract a single social media profile from text"""
        text = text.strip()
        
        # Check each platform's patterns
        for platform, patterns in cls.PLATFORM_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    handle = match.group(1) if match.groups() else None
                    
                    # Extract full URL if present
                    url_match = re.search(r'https?://[^\s]+', text)
                    url = url_match.group(0) if url_match else None
                    
                    return SocialMediaProfile(
                        platform=platform,
                        handle=handle,
                        url=url,
                        display_format=text
                    )
        
        # If no specific platform matched, check for generic patterns
        # Handle format: "Platform: @handle" or "Platform: URL"
        generic_pattern = r'^(\w+):\s*(.+)$'
        match = re.match(generic_pattern, text)
        if match:
            platform = match.group(1).lower()
            value = match.group(2).strip()
            
            # Check if it's a handle or URL
            handle = None
            url = None
            if value.startswith('@'):
                handle = value[1:]
            elif value.startswith('http'):
                url = value
            else:
                # Could be either
                handle = value.replace('@', '')
            
            return SocialMediaProfile(
                platform=platform,
                handle=handle,
                url=url,
                display_format=text
            )
        
        # Last resort: treat the whole text as a social media reference
        # if it contains common social media keywords
        social_keywords = ['twitter', 'instagram', 'linkedin', 'facebook', 
                          'youtube', 'tiktok', 'github', 'medium', 'substack']
        
        text_lower = text.lower()
        for keyword in social_keywords:
            if keyword in text_lower:
                return SocialMediaProfile(
                    platform=keyword,
                    handle=None,
                    url=None,
                    display_format=text
                )
        
        return None

def validate_social_media_list(value: Any) -> bool:
    """Validate social media list - accepts various formats"""
    # Accept the special "none" marker
    if value == "none":
        return True
    
    # Accept empty list
    if isinstance(value, list) and len(value) == 0:
        return True
    
    # Accept list of strings (will be parsed later)
    if isinstance(value, list):
        return all(isinstance(item, str) for item in value)
    
    # Accept single string (will be parsed as multi-line)
    if isinstance(value, str):
        return True
    
    return False

def process_social_media_value(value: Any) -> List[str]:
    """Process social media value into standardized format"""
    if value == "none":
        return []
    
    if isinstance(value, list):
        # Process each item
        all_profiles = []
        for item in value:
            if isinstance(item, str):
                profiles = SocialMediaExtractor.extract_from_text(item)
                all_profiles.extend([p.to_string() for p in profiles])
        return all_profiles
    
    if isinstance(value, str):
        # Multi-line string
        profiles = SocialMediaExtractor.extract_from_text(value)
        return [p.to_string() for p in profiles]
    
    return []