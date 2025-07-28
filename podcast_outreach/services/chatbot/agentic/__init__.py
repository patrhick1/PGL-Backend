# Agentic Chatbot System
"""
This module implements an agentic chatbot system using LangGraph for intelligent
conversation management with bucket-based information collection.
"""

# Phase 1: Foundation
from .bucket_definitions import INFORMATION_BUCKETS, BucketDefinition
from .state_manager import ChatbotState, StateManager

# Phase 2: Classification
from .message_classifier import MessageClassifier, ClassificationResult
from .bucket_manager import BucketManager, UpdateResult

# Phase 3: LangGraph Integration
from .graph_state import GraphState, GraphStateManager, create_initial_graph_state
from .graph_builder import build_conversation_graph, compile_conversation_graph
from .conversation_orchestrator import ConversationOrchestrator

# Phase 4: Intelligent Response Generation
from .response_strategies import ResponseStrategyEngine, ConversationStyle, ResponseStrategy
from .question_generator import IntelligentQuestionGenerator
from .response_templates import ResponseTemplates
from .response_builder import ResponseBuilder
from .context_manager import ContextCompressionManager

# Phase 5: Integration Layer
from .agentic_adapter import AgenticChatbotAdapter
from .state_converter import StateConverter
from .fallback_handler import FallbackHandler
from .migration_manager import MigrationManager

__all__ = [
    # Phase 1
    'INFORMATION_BUCKETS',
    'BucketDefinition', 
    'ChatbotState',
    'StateManager',
    # Phase 2
    'MessageClassifier',
    'ClassificationResult',
    'BucketManager',
    'UpdateResult',
    # Phase 3
    'GraphState',
    'GraphStateManager',
    'create_initial_graph_state',
    'build_conversation_graph',
    'compile_conversation_graph',
    'ConversationOrchestrator',
    # Phase 4
    'ResponseStrategyEngine',
    'ConversationStyle',
    'ResponseStrategy',
    'IntelligentQuestionGenerator',
    'ResponseTemplates',
    'ResponseBuilder',
    'ContextCompressionManager',
    # Phase 5
    'AgenticChatbotAdapter',
    'StateConverter',
    'FallbackHandler',
    'MigrationManager'
]