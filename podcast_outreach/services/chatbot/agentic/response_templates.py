# podcast_outreach/services/chatbot/agentic/response_templates.py

from typing import Dict, List, Optional
import random
from dataclasses import dataclass

from .response_strategies import ConversationStyle, ResponseStrategy

@dataclass
class ResponseTemplate:
    """A response template with variations"""
    template_id: str
    strategy: ResponseStrategy
    templates: Dict[ConversationStyle, List[str]]
    default_templates: List[str]

class ResponseTemplates:
    """
    Professional yet conversational response templates for various scenarios
    """
    
    def __init__(self):
        self.templates = self._initialize_templates()
        
    def _initialize_templates(self) -> Dict[str, ResponseTemplate]:
        """Initialize all response templates"""
        
        return {
            # Welcome templates
            'warm_welcome': ResponseTemplate(
                template_id='warm_welcome',
                strategy=ResponseStrategy.WARM_WELCOME,
                templates={
                    ConversationStyle.FORMAL: [
                        "Welcome! I'm here to help you create a compelling profile for podcast appearances. Let's begin with your name.",
                        "Good to meet you! I'll be gathering information to help podcast hosts learn about you. May we start with your name?"
                    ],
                    ConversationStyle.CASUAL: [
                        "Hey there! I'll help you create an awesome podcast guest profile. Let's start with your name!",
                        "Hi! Ready to get you on some great podcasts? First up - what's your name?"
                    ],
                    ConversationStyle.UNCERTAIN: [
                        "Hello! I'm here to help you create a profile for podcast opportunities. Don't worry, I'll guide you through everything. Let's start simple - what's your name?"
                    ]
                },
                default_templates=[
                    "Welcome! I'll help you create your podcast guest profile. Let's start with your name."
                ]
            ),
            
            # Acknowledgment templates
            'acknowledge_single': ResponseTemplate(
                template_id='acknowledge_single',
                strategy=ResponseStrategy.ACKNOWLEDGE_PROGRESS,
                templates={
                    ConversationStyle.FORMAL: [
                        "Thank you, I've recorded that.",
                        "Excellent, I have that information."
                    ],
                    ConversationStyle.CASUAL: [
                        "Got it!",
                        "Perfect!",
                        "Awesome!"
                    ],
                    ConversationStyle.TECHNICAL: [
                        "Noted.",
                        "Recorded.",
                        "Confirmed."
                    ]
                },
                default_templates=[
                    "Great, I've got that.",
                    "Thanks, I've saved that information."
                ]
            ),
            
            # Multi-info acknowledgment
            'acknowledge_multiple': ResponseTemplate(
                template_id='acknowledge_multiple',
                strategy=ResponseStrategy.ACKNOWLEDGE_PROGRESS,
                templates={
                    ConversationStyle.VERBOSE: [
                        "Excellent! I've captured all of that information. You've provided {items}.",
                        "Wonderful! I've recorded {items}. This is very helpful."
                    ],
                    ConversationStyle.CONCISE: [
                        "Got {items}.",
                        "Saved {items}."
                    ]
                },
                default_templates=[
                    "Perfect! I've saved {items}.",
                    "Great! I've recorded {items}."
                ]
            ),
            
            # Correction acknowledgment
            'acknowledge_correction': ResponseTemplate(
                template_id='acknowledge_correction',
                strategy=ResponseStrategy.ACKNOWLEDGE_PROGRESS,
                templates={
                    ConversationStyle.FORMAL: [
                        "I've updated that information. Thank you for the correction.",
                        "I've made that correction. The information has been updated."
                    ],
                    ConversationStyle.CASUAL: [
                        "No problem! I've fixed that.",
                        "Got it - I've updated that for you.",
                        "All good! I've made that change."
                    ]
                },
                default_templates=[
                    "Thanks for the correction - I've updated that.",
                    "I've corrected that information."
                ]
            ),
            
            # Progress updates
            'progress_update': ResponseTemplate(
                template_id='progress_update',
                strategy=ResponseStrategy.ACKNOWLEDGE_PROGRESS,
                templates={
                    ConversationStyle.FORMAL: [
                        "We're making excellent progress. You've provided {percent}% of the required information.",
                        "Thank you for your detailed responses. We have {percent}% of what podcast hosts need."
                    ],
                    ConversationStyle.CASUAL: [
                        "We're {percent}% done - you're doing great!",
                        "Nice! We're about {percent}% complete."
                    ]
                },
                default_templates=[
                    "Great progress! We're about {percent}% complete.",
                    "We're making good progress - {percent}% done."
                ]
            ),
            
            # Clarification needed
            'need_clarification': ResponseTemplate(
                template_id='need_clarification',
                strategy=ResponseStrategy.CLARIFY_AMBIGUOUS,
                templates={
                    ConversationStyle.FORMAL: [
                        "I want to ensure I understand correctly. {clarification}",
                        "Could you please clarify? {clarification}"
                    ],
                    ConversationStyle.CASUAL: [
                        "Just to make sure I get this right - {clarification}",
                        "Quick question - {clarification}"
                    ]
                },
                default_templates=[
                    "I want to make sure I understand - {clarification}",
                    "Could you clarify - {clarification}"
                ]
            ),
            
            # Completion blocked
            'completion_blocked': ResponseTemplate(
                template_id='completion_blocked',
                strategy=ResponseStrategy.COMPLETION_BLOCKED,
                templates={
                    ConversationStyle.FORMAL: [
                        "I appreciate your eagerness to complete. However, I still need: {missing}. Would you mind providing this information?",
                        "Before we can submit, I need a few more details: {missing}. Could you help me with these?"
                    ],
                    ConversationStyle.CASUAL: [
                        "Almost there! I just need: {missing}. Can you help me out with these?",
                        "We're so close! Just need: {missing}. Want to knock these out quickly?"
                    ]
                },
                default_templates=[
                    "I'd love to submit your profile, but I still need: {missing}. Can you provide these?",
                    "We're nearly done! I just need: {missing} to complete your profile."
                ]
            ),
            
            # Completion ready
            'completion_ready': ResponseTemplate(
                template_id='completion_ready',
                strategy=ResponseStrategy.COMPLETION_READY,
                templates={
                    ConversationStyle.FORMAL: [
                        "Excellent! I have all the required information. Here's a summary:\n\n{summary}\n\nIs everything correct?",
                        "Thank you! Your profile is complete. Please review:\n\n{summary}\n\nShall I submit this?"
                    ],
                    ConversationStyle.CASUAL: [
                        "Awesome! We've got everything. Here's what I have:\n\n{summary}\n\nLook good?",
                        "All done! Quick review:\n\n{summary}\n\nReady to submit?"
                    ]
                },
                default_templates=[
                    "Great! I have all your information. Here's a summary:\n\n{summary}\n\nIs this correct?",
                    "Perfect! Your profile is ready. Please review:\n\n{summary}\n\nShall I submit?"
                ]
            ),
            
            # Error recovery
            'error_recovery': ResponseTemplate(
                template_id='error_recovery',
                strategy=ResponseStrategy.ERROR_RECOVERY,
                templates={
                    ConversationStyle.FORMAL: [
                        "I apologize, I didn't quite understand that. Could you please rephrase?",
                        "I'm having trouble processing that. Would you mind saying it differently?"
                    ],
                    ConversationStyle.CASUAL: [
                        "Hmm, I didn't catch that. Can you try saying it another way?",
                        "Sorry, I'm a bit confused. Could you rephrase that?"
                    ]
                },
                default_templates=[
                    "I didn't quite understand that. Could you rephrase?",
                    "Sorry, I missed that. Can you say it differently?"
                ]
            ),
            
            # Conversation rescue
            'conversation_rescue': ResponseTemplate(
                template_id='conversation_rescue',
                strategy=ResponseStrategy.CONVERSATION_RESCUE,
                templates={
                    ConversationStyle.FORMAL: [
                        "I sense we may be having some difficulty. Would you prefer if I guide you through this step by step?",
                        "Let me help make this easier. I can ask specific questions one at a time. Would that be better?"
                    ],
                    ConversationStyle.CASUAL: [
                        "Hey, looks like we're getting a bit stuck. Want me to just ask you simple questions one by one?",
                        "No worries! Let's take this step by step. I'll keep it simple. Sound good?"
                    ]
                },
                default_templates=[
                    "I notice we're having some trouble. Let me guide you through this step by step, okay?",
                    "Let's simplify this. I'll ask you one thing at a time. How does that sound?"
                ]
            ),
            
            # Optional info invitation
            'invite_optional': ResponseTemplate(
                template_id='invite_optional',
                strategy=ResponseStrategy.GATHER_OPTIONAL,
                templates={
                    ConversationStyle.FORMAL: [
                        "You've provided all the required information. Would you like to add any optional details such as {optional}?",
                        "The required fields are complete. You may also add {optional} if you'd like."
                    ],
                    ConversationStyle.CASUAL: [
                        "That's all the must-haves! Want to add {optional}? Totally up to you!",
                        "Got all the required stuff! You can also add {optional} if you want - no pressure!"
                    ]
                },
                default_templates=[
                    "Great! All required info is complete. You can also add {optional} if you'd like.",
                    "Perfect! The required fields are done. Optionally, you can share {optional}."
                ]
            )
        }
    
    def get_template(
        self,
        template_id: str,
        style: Optional[ConversationStyle] = None,
        **kwargs
    ) -> str:
        """
        Get a response template and format it with provided values
        
        Args:
            template_id: ID of the template to retrieve
            style: Conversation style for template selection
            **kwargs: Values to format into the template
            
        Returns:
            Formatted response string
        """
        template_obj = self.templates.get(template_id)
        if not template_obj:
            return "I'm not sure how to respond to that."
        
        # Get appropriate template list
        if style and style in template_obj.templates:
            template_list = template_obj.templates[style]
        else:
            template_list = template_obj.default_templates
        
        # Select random template
        template = random.choice(template_list)
        
        # Format with provided values
        try:
            return template.format(**kwargs)
        except KeyError:
            # Return template without formatting if keys missing
            return template
    
    def format_bucket_list(
        self,
        bucket_names: List[str],
        style: ConversationStyle = ConversationStyle.CASUAL
    ) -> str:
        """Format a list of bucket names nicely"""
        
        if not bucket_names:
            return ""
        
        if len(bucket_names) == 1:
            return bucket_names[0]
        
        if style == ConversationStyle.CONCISE:
            return ", ".join(bucket_names)
        
        if len(bucket_names) == 2:
            return f"{bucket_names[0]} and {bucket_names[1]}"
        
        # More than 2 items
        if style == ConversationStyle.FORMAL:
            return ", ".join(bucket_names[:-1]) + f", and {bucket_names[-1]}"
        else:
            return ", ".join(bucket_names[:-1]) + f" and {bucket_names[-1]}"
    
    def format_summary(
        self,
        filled_buckets: Dict[str, any],
        style: ConversationStyle = ConversationStyle.CASUAL
    ) -> str:
        """Format a summary of collected information"""
        
        lines = []
        
        # Priority order for summary
        priority_order = [
            'full_name', 'email', 'current_role', 'company',
            'professional_bio', 'expertise_keywords', 'podcast_topics'
        ]
        
        for bucket_id in priority_order:
            if bucket_id in filled_buckets:
                value = filled_buckets[bucket_id]
                
                # Format based on bucket type
                if bucket_id == 'full_name':
                    lines.append(f"• Name: {value}")
                elif bucket_id == 'email':
                    lines.append(f"• Email: {value}")
                elif bucket_id == 'current_role':
                    company = filled_buckets.get('company', '')
                    if company:
                        lines.append(f"• Role: {value} at {company}")
                    else:
                        lines.append(f"• Role: {value}")
                elif bucket_id == 'company' and 'current_role' not in filled_buckets:
                    lines.append(f"• Company: {value}")
                elif bucket_id == 'professional_bio':
                    # Truncate long bios
                    bio = str(value)
                    if len(bio) > 100:
                        bio = bio[:97] + "..."
                    lines.append(f"• Bio: {bio}")
                elif bucket_id == 'expertise_keywords':
                    if isinstance(value, list):
                        expertise = ", ".join(value[:3])
                    else:
                        expertise = str(value)
                    lines.append(f"• Expertise: {expertise}")
        
        # Limit summary length
        if len(lines) > 7:
            lines = lines[:7]
            lines.append("• ... and more")
        
        return "\n".join(lines)