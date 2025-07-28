# podcast_outreach/services/chatbot/agentic/graph_builder.py

from typing import Literal
from langgraph.graph import StateGraph, END

from .graph_state import GraphState
from .graph_nodes import (
    classification_node,
    bucket_update_node,
    response_generation_node,
    verification_node,
    completion_check_node,
    error_handling_node
)

def build_conversation_graph() -> StateGraph:
    """
    Build the LangGraph for conversation orchestration
    
    The graph manages the flow of conversation through different nodes:
    - Classification: Understand user input
    - Bucket Update: Store extracted information
    - Response Generation: Create contextual responses
    - Verification: Handle ambiguous input
    - Completion Check: Validate and finalize
    - Error Handling: Graceful error recovery
    
    Returns:
        Configured StateGraph ready for compilation
    """
    # Create the graph
    graph = StateGraph(GraphState)
    
    # Add nodes
    graph.add_node("classify", classification_node)
    graph.add_node("update_buckets", bucket_update_node)
    graph.add_node("generate_response", response_generation_node)
    graph.add_node("verify", verification_node)
    graph.add_node("check_completion", completion_check_node)
    graph.add_node("handle_error", error_handling_node)
    
    # Define routing functions
    def route_after_classification(state: GraphState) -> Literal["verify", "check_completion", "update_buckets", "generate_response", "handle_error"]:
        """Determine next node after classification"""
        next_action = state.get('next_action', 'generate_response')
        
        if next_action == 'error':
            return "handle_error"
        elif next_action == 'verify':
            return "verify"
        elif next_action == 'check_completion':
            return "check_completion"
        elif next_action == 'update':
            return "update_buckets"
        else:
            return "generate_response"
    
    def route_after_update(state: GraphState) -> Literal["generate_response", "handle_error"]:
        """Determine next node after bucket update"""
        if state.get('next_action') == 'error':
            return "handle_error"
        else:
            return "generate_response"
    
    def route_after_response(state: GraphState) -> Literal["end"]:
        """After generating response, end this interaction cycle"""
        return END
    
    def route_after_verification(state: GraphState) -> Literal["end"]:
        """After verification, end to wait for user response"""
        return END
    
    def route_after_completion_check(state: GraphState) -> Literal["end"]:
        """After completion check, end this cycle"""
        return END
    
    def route_after_error(state: GraphState) -> Literal["end"]:
        """After error handling, end this cycle"""
        return END
    
    # Set entry point
    graph.set_entry_point("classify")
    
    # Add edges with conditions
    graph.add_conditional_edges(
        "classify",
        route_after_classification,
        {
            "verify": "verify",
            "check_completion": "check_completion",
            "update_buckets": "update_buckets",
            "generate_response": "generate_response",
            "handle_error": "handle_error"
        }
    )
    
    graph.add_conditional_edges(
        "update_buckets",
        route_after_update,
        {
            "generate_response": "generate_response",
            "handle_error": "handle_error"
        }
    )
    
    # Add conditional routing for response generation
    def route_after_response_generation(state: GraphState) -> Literal["handle_error", END]:
        """Route after response generation"""
        if state.get('next_action') == 'error':
            return "handle_error"
        return END
    
    graph.add_conditional_edges(
        "generate_response",
        route_after_response_generation,
        {
            "handle_error": "handle_error",
            END: END
        }
    )
    
    # Direct edges to END
    graph.add_edge("verify", END)
    graph.add_edge("check_completion", END)
    graph.add_edge("handle_error", END)
    
    return graph


def compile_conversation_graph():
    """
    Compile the conversation graph for execution
    
    Returns:
        Compiled graph ready to process messages
    """
    graph = build_conversation_graph()
    return graph.compile()


# Example usage and visualization
if __name__ == "__main__":
    # Build and compile the graph
    app = compile_conversation_graph()
    
    # Print graph structure
    print("Conversation Graph Structure:")
    print("=" * 50)
    
    # The graph flow:
    # 1. Start -> Classify
    # 2. Classify -> {Verify, Check Completion, Update Buckets, Generate Response, Handle Error}
    # 3. Update Buckets -> {Generate Response, Handle Error}
    # 4. All paths -> END
    
    print("""
    Entry: classify
    
    Nodes:
    - classify: Understand user input and intent
    - update_buckets: Store extracted information
    - generate_response: Create contextual response
    - verify: Handle ambiguous input
    - check_completion: Validate completion request
    - handle_error: Graceful error recovery
    
    Flow:
    classify -> {verify|check_completion|update_buckets|generate_response|handle_error}
    update_buckets -> {generate_response|handle_error}
    {generate_response|verify|check_completion|handle_error} -> END
    """)