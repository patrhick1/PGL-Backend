"""
Chatbot-specific schemas to handle formatting
"""

from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

class ChatbotMessageResponse(BaseModel):
    bot_message: str
    bot_message_html: Optional[str] = Field(None, description="HTML formatted version of bot_message")
    extracted_data: Dict[str, Any]
    progress: int
    phase: str
    keywords_found: int
    quick_replies: Optional[List[str]] = []
    ready_for_completion: bool = False
    awaiting_confirmation: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    
    class Config:
        schema_extra = {
            "example": {
                "bot_message": "Here's your profile:\n\nName: John Doe",
                "bot_message_html": "Here's your profile:<br><br>Name: John Doe",
                "extracted_data": {"name": "John Doe"},
                "progress": 50,
                "phase": "gathering",
                "keywords_found": 1,
                "quick_replies": ["Yes", "No"]
            }
        }