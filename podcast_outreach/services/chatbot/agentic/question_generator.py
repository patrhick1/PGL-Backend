# podcast_outreach/services/chatbot/agentic/question_generator.py

from typing import List, Dict, Optional, Any
from dataclasses import dataclass
import random

from .response_strategies import ConversationStyle, StrategyContext
from .bucket_definitions import INFORMATION_BUCKETS
from .state_manager import StateManager

@dataclass
class GeneratedQuestion:
    """A generated question with metadata"""
    question_text: str
    target_buckets: List[str]
    question_type: str  # 'single', 'multi', 'follow_up', 'clarification'
    includes_examples: bool
    personalized: bool

class IntelligentQuestionGenerator:
    """
    Generates intelligent, context-aware questions that avoid repetition
    and create natural conversation flow
    """
    
    def __init__(self):
        # Question templates by bucket and style
        self.single_questions = {
            'full_name': {
                ConversationStyle.FORMAL: "May I have your full name, please?",
                ConversationStyle.CASUAL: "What's your name?",
                ConversationStyle.UNCERTAIN: "Let's start with your name. What should I call you?",
                'default': "What's your full name?"
            },
            'email': {
                ConversationStyle.FORMAL: "What email address should podcast hosts use to contact you?",
                ConversationStyle.CASUAL: "What's the best email to reach you at?",
                ConversationStyle.TECHNICAL: "Primary contact email?",
                'default': "What's your email address?"
            },
            'current_role': {
                ConversationStyle.FORMAL: "What is your current professional role?",
                ConversationStyle.CASUAL: "What do you do for work?",
                ConversationStyle.VERBOSE: "Could you tell me about your current role and what it involves?",
                'default': "What's your current role?"
            },
            'company': {
                ConversationStyle.FORMAL: "Which organization are you currently with?",
                ConversationStyle.CASUAL: "Where do you work?",
                'default': "What company do you work for?"
            },
            'professional_bio': {
                ConversationStyle.FORMAL: "Please provide a brief professional biography (2-3 sentences).",
                ConversationStyle.CASUAL: "Tell me a bit about yourself professionally - just 2-3 sentences.",
                ConversationStyle.UNCERTAIN: "Could you share a short bio about what you do? Just a few sentences about your professional background.",
                'default': "Please share a brief professional bio (2-3 sentences)."
            },
            'expertise_keywords': {
                ConversationStyle.TECHNICAL: "List your core competencies and areas of expertise (one per line).",
                ConversationStyle.CASUAL: "What topics are you an expert in? List a few, one per line!",
                ConversationStyle.UNCERTAIN: "What subjects could you speak about on a podcast? List 3-5 topics you know well, one per line.",
                'default': "What are your main areas of expertise? (3-5 topics, one per line)"
            },
            'podcast_topics': {
                ConversationStyle.FORMAL: "Which topics would you be interested in discussing on podcasts? Please list them, one per line.",
                ConversationStyle.CASUAL: "What would you want to talk about on podcasts? List a few topics!",
                'default': "What topics would you like to discuss on podcasts? (list 2-5, one per line)"
            },
            'success_stories': {
                ConversationStyle.FORMAL: "Please share 1-2 significant professional achievements or success stories (one per line).",
                ConversationStyle.CASUAL: "What are you most proud of in your career? Share a few wins!",
                ConversationStyle.TECHNICAL: "Key achievements or case studies? List them separately.",
                'default': "Can you share 1-2 success stories or achievements? (one per line)"
            },
            'unique_perspective': {
                ConversationStyle.CASUAL: "What unique insight or perspective do you bring to your field?",
                ConversationStyle.FORMAL: "What distinguishes your perspective in your area of expertise?",
                'default': "What unique perspective do you bring to your field?"
            },
            'phone': {
                ConversationStyle.FORMAL: "Would you be comfortable sharing a phone number for urgent podcast inquiries?",
                ConversationStyle.CASUAL: "Do you have a phone number for podcast hosts who need to reach you quickly?",
                'default': "What's a good phone number for podcast-related calls? (optional)"
            },
            'years_experience': {
                ConversationStyle.FORMAL: "How many years of professional experience do you have in your field?",
                ConversationStyle.CASUAL: "How long have you been doing what you do?",
                'default': "How many years of experience do you have?"
            },
            'speaking_experience': {
                ConversationStyle.FORMAL: "Have you been a guest on podcasts or done public speaking before? Please list any appearances.",
                ConversationStyle.CASUAL: "Have you been on podcasts or done any speaking gigs before? List any you remember!",
                ConversationStyle.VERBOSE: "Tell me about your experience with podcasts, public speaking, or media appearances. List each one on a separate line.",
                'default': "Do you have any previous podcast or speaking experience? (list any, one per line)"
            },
            'media_experience': {
                ConversationStyle.FORMAL: "Have you had any media appearances or been featured in publications?",
                ConversationStyle.CASUAL: "Have you been featured in any media outlets or publications?",
                'default': "Any media appearances or features we should know about?"
            },
            'achievements': {
                ConversationStyle.FORMAL: "What are some specific achievements or metrics you're proud of? List them one per line.",
                ConversationStyle.CASUAL: "What specific wins or results have you achieved? Share a few!",
                'default': "Can you share some specific achievements with numbers or results? (one per line)"
            },
            'interesting_hooks': {
                ConversationStyle.FORMAL: "What interesting stories or insights could you share that would captivate an audience?",
                ConversationStyle.CASUAL: "What fascinating stories or 'aha moments' could you share on a podcast?",
                ConversationStyle.VERBOSE: "What's a story or insight you have that would make listeners lean in?",
                'default': "What interesting hooks or stories would make great podcast content?"
            },
            'controversial_takes': {
                ConversationStyle.FORMAL: "Do you have any thought-provoking or contrarian views in your field?",
                ConversationStyle.CASUAL: "Any hot takes or controversial opinions that might spark interesting discussions?",
                ConversationStyle.VERBOSE: "What's something you believe that most people in your field would disagree with?",
                'default': "Do you have any controversial or thought-provoking perspectives to share?"
            },
            'fun_fact': {
                ConversationStyle.FORMAL: "Is there an interesting personal fact that might help audiences connect with you?",
                ConversationStyle.CASUAL: "What's something fun or unexpected about you that people might not know?",
                ConversationStyle.CONCISE: "Fun fact about you?",
                'default': "What's a fun fact about you?"
            },
            'website': {
                ConversationStyle.FORMAL: "Do you have a personal or professional website you'd like to share?",
                ConversationStyle.CASUAL: "Got a website where people can learn more about you?",
                'default': "Do you have a website? (optional)"
            },
            'scheduling_preference': {
                ConversationStyle.FORMAL: "What's your preferred method for scheduling podcast interviews?",
                ConversationStyle.CASUAL: "How do you prefer to schedule podcast recordings?",
                'default': "What's the best way for hosts to schedule time with you?"
            },
            'promotion_items': {
                ConversationStyle.FORMAL: "Do you have any books, courses, or services you'd like to promote? List each one.",
                ConversationStyle.CASUAL: "Anything you're promoting right now - book, course, product? List them out!",
                'default': "What would you like to promote on podcasts? (list items, one per line)"
            },
            'social_media': {
                ConversationStyle.FORMAL: "Which social media platforms are you active on? You can share handles, URLs, or usernames in any format.",
                ConversationStyle.CASUAL: "Where can people find you on social media? Drop your profiles in any format you like!",
                ConversationStyle.VERBOSE: "Let's make it easy for podcast listeners to connect with you! Share your social media profiles - Instagram, Twitter/X, LinkedIn, TikTok, or any others. You can provide URLs, handles with @, or just platform and username.",
                'default': "What are your social media profiles? (share in any format - URLs, @handles, or platform: username)"
            },
            'ideal_podcast': {
                ConversationStyle.FORMAL: "Could you describe the type of podcasts you'd be most interested in appearing on? Consider the audience, topics, and format.",
                ConversationStyle.CASUAL: "What kind of podcasts are you looking to be on? Think about the vibe, audience, topics - paint me a picture!",
                ConversationStyle.VERBOSE: "Help me understand your ideal podcast appearance. What type of shows are you hoping to get on? Think about the audience demographics, the topics they cover, the interview style, and what would make a podcast a perfect fit for you.",
                ConversationStyle.CONCISE: "Describe your ideal podcast appearance.",
                'default': "What type of podcasts would be ideal for you? Describe the audience, topics, and format you're looking for."
            }
        }
        
        # Multi-bucket question templates
        self.multi_questions = {
            ('email', 'phone', 'linkedin_url'): {
                ConversationStyle.FORMAL: "How would you prefer podcast hosts contact you? Please share your email and any other contact methods (phone, LinkedIn) you're comfortable with.",
                ConversationStyle.CASUAL: "What's the best way for podcast hosts to reach you? Email, phone, LinkedIn - whatever works for you!",
                ConversationStyle.CONCISE: "Contact info? (email required, phone/LinkedIn optional)",
                'default': "How can podcast hosts best reach you? Please share your email and any other preferred contact methods."
            },
            ('current_role', 'company'): {
                ConversationStyle.FORMAL: "Could you tell me about your current position and organization?",
                ConversationStyle.CASUAL: "What do you do and where do you work?",
                ConversationStyle.VERBOSE: "I'd love to hear about your current role - what you do and which company you're with.",
                'default': "What's your current role and company?"
            },
            ('expertise_keywords', 'podcast_topics'): {
                ConversationStyle.FORMAL: "What are your areas of expertise and which topics would you like to discuss on podcasts? Please list them separately.",
                ConversationStyle.CASUAL: "What are you an expert in and what would you want to talk about on shows? List a few of each!",
                'default': "What are your areas of expertise and what topics interest you for podcast discussions? (list multiple)"
            },
            ('success_stories', 'achievements'): {
                ConversationStyle.FORMAL: "Could you share some of your professional achievements or success stories? List each one on a new line.",
                ConversationStyle.CASUAL: "What accomplishments are you most proud of? Share a few!",
                'default': "What are some of your key achievements or success stories? (one per line)"
            }
        }
        
        # Follow-up question templates based on context
        self.follow_up_templates = {
            'years_mentioned': [
                "You mentioned {years} years of experience - what's been the highlight?",
                "With {years} years in the field, what key insights have you gained?",
                "{years} years is impressive! What's changed most in your industry?"
            ],
            'role_mentioned': [
                "As a {role}, what unique perspectives do you bring to podcasts?",
                "What challenges do {role}s face that listeners might find interesting?",
                "What's the most misunderstood aspect of being a {role}?"
            ],
            'company_mentioned': [
                "What's innovative about what {company} is doing?",
                "How has working at {company} shaped your expertise?",
                "What can you share about {company}'s approach that others could learn from?"
            ]
        }
        
        # Transition phrases for smooth flow
        self.transitions = {
            'acknowledge': [
                "Great!",
                "Perfect!",
                "Excellent!",
                "Got it!",
                "Thanks!"
            ],
            'progress': [
                "We're making good progress.",
                "This is really helpful.",
                "You're providing great information.",
                "This is exactly what podcast hosts need to know."
            ],
            'continue': [
                "Now,",
                "Next,",
                "Also,",
                "One more thing -",
                "Additionally,"
            ]
        }
    
    def generate_question(
        self,
        strategy_context: StrategyContext,
        state_manager: StateManager,
        bucket_contexts: List[Dict[str, Any]]
    ) -> GeneratedQuestion:
        """
        Generate an appropriate question based on strategy and context
        
        Args:
            strategy_context: The response strategy context
            state_manager: Current conversation state
            bucket_contexts: Context for target buckets
            
        Returns:
            GeneratedQuestion with the question and metadata
        """
        if not bucket_contexts or not strategy_context.priority_buckets:
            return self._generate_completion_question(strategy_context)
        
        # Check if we should generate multi-bucket question
        if strategy_context.group_questions and len(bucket_contexts) > 1:
            return self._generate_multi_bucket_question(
                bucket_contexts,
                strategy_context.style_adjustment or ConversationStyle.CASUAL
            )
        
        # Check for follow-up opportunity
        follow_up = self._check_follow_up_opportunity(state_manager, bucket_contexts[0])
        if follow_up:
            return follow_up
        
        # Generate single bucket question
        return self._generate_single_bucket_question(
            bucket_contexts[0],
            strategy_context.style_adjustment or ConversationStyle.CASUAL,
            strategy_context.offer_examples
        )
    
    def _generate_single_bucket_question(
        self,
        bucket_context: Dict[str, Any],
        style: ConversationStyle,
        include_examples: bool
    ) -> GeneratedQuestion:
        """Generate question for a single bucket"""
        
        bucket_id = bucket_context['bucket_id']
        
        # Get appropriate template
        templates = self.single_questions.get(bucket_id, {})
        question = templates.get(style, templates.get('default', f"Could you provide your {bucket_context['bucket_name'].lower()}?"))
        
        # Add examples if needed
        if include_examples and bucket_context.get('examples'):
            examples = bucket_context['examples'][:2]
            if len(examples) == 1:
                question += f" (for example: {examples[0]})"
            else:
                question += f" (for example: {examples[0]} or {examples[1]})"
        
        return GeneratedQuestion(
            question_text=question,
            target_buckets=[bucket_id],
            question_type='single',
            includes_examples=include_examples,
            personalized=False
        )
    
    def _generate_multi_bucket_question(
        self,
        bucket_contexts: List[Dict[str, Any]],
        style: ConversationStyle
    ) -> GeneratedQuestion:
        """Generate question for multiple buckets"""
        
        bucket_ids = tuple(context['bucket_id'] for context in bucket_contexts)
        
        # Check for predefined multi-question template
        for template_buckets, templates in self.multi_questions.items():
            if all(bid in template_buckets for bid in bucket_ids):
                question = templates.get(style, templates.get('default', ''))
                if question:
                    return GeneratedQuestion(
                        question_text=question,
                        target_buckets=list(bucket_ids),
                        question_type='multi',
                        includes_examples=False,
                        personalized=False
                    )
        
        # Build custom multi-question
        if len(bucket_ids) == 2:
            names = [ctx['bucket_name'].lower() for ctx in bucket_contexts]
            question = f"Could you share your {names[0]} and {names[1]}?"
        else:
            names = [ctx['bucket_name'].lower() for ctx in bucket_contexts[:-1]]
            last_name = bucket_contexts[-1]['bucket_name'].lower()
            question = f"Could you share your {', '.join(names)}, and {last_name}?"
        
        return GeneratedQuestion(
            question_text=question,
            target_buckets=list(bucket_ids),
            question_type='multi',
            includes_examples=False,
            personalized=False
        )
    
    def _check_follow_up_opportunity(
        self,
        state_manager: StateManager,
        bucket_context: Dict[str, Any]
    ) -> Optional[GeneratedQuestion]:
        """Check if we can generate a contextual follow-up question"""
        
        filled = state_manager.get_filled_buckets()
        target_bucket = bucket_context['bucket_id']
        
        # Years experience follow-up
        if target_bucket in ['achievements', 'success_stories'] and 'years_experience' in filled:
            years = filled['years_experience']
            if isinstance(years, (int, str)) and int(str(years)) > 5:
                template = random.choice(self.follow_up_templates['years_mentioned'])
                question = template.format(years=years)
                
                return GeneratedQuestion(
                    question_text=question,
                    target_buckets=[target_bucket],
                    question_type='follow_up',
                    includes_examples=False,
                    personalized=True
                )
        
        # Role-based follow-up
        if target_bucket in ['unique_perspective', 'podcast_topics'] and 'current_role' in filled:
            role = filled['current_role']
            if role and len(str(role)) > 3:
                template = random.choice(self.follow_up_templates['role_mentioned'])
                question = template.format(role=role)
                
                return GeneratedQuestion(
                    question_text=question,
                    target_buckets=[target_bucket],
                    question_type='follow_up',
                    includes_examples=False,
                    personalized=True
                )
        
        return None
    
    def _generate_completion_question(
        self,
        strategy_context: StrategyContext
    ) -> GeneratedQuestion:
        """Generate completion-related question"""
        
        if strategy_context.style_adjustment == ConversationStyle.FORMAL:
            question = "Is there anything else you would like to add to your profile?"
        elif strategy_context.style_adjustment == ConversationStyle.CASUAL:
            question = "Anything else you'd like to share?"
        else:
            question = "Would you like to add anything else?"
        
        return GeneratedQuestion(
            question_text=question,
            target_buckets=[],
            question_type='completion',
            includes_examples=False,
            personalized=False
        )
    
    def add_transition(
        self,
        question: GeneratedQuestion,
        acknowledge_previous: bool,
        show_progress: bool
    ) -> str:
        """Add appropriate transition to question"""
        
        parts = []
        
        # Acknowledgment
        if acknowledge_previous:
            parts.append(random.choice(self.transitions['acknowledge']))
        
        # Progress indicator
        if show_progress:
            parts.append(random.choice(self.transitions['progress']))
        
        # Continuation phrase
        if parts:  # If we have acknowledgment or progress
            parts.append(random.choice(self.transitions['continue']).lower())
        
        # Add the question
        parts.append(question.question_text)
        
        return ' '.join(parts)
    
    def personalize_with_name(
        self,
        question_text: str,
        state_manager: StateManager
    ) -> str:
        """Add user's name to question if appropriate"""
        
        filled = state_manager.get_filled_buckets()
        if 'full_name' in filled:
            name = filled['full_name']
            # Extract first name
            first_name = str(name).split()[0] if name else None
            
            if first_name and len(state_manager.state['messages']) > 6:
                # Only personalize after some rapport
                if random.random() < 0.3:  # 30% chance
                    return f"{first_name}, {question_text.lower()}"
        
        return question_text