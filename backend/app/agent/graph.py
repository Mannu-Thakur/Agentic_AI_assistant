from langgraph.graph import StateGraph, END
from app.agent.state import AgentState
from app.agent.nodes import retrieve_context_node, generate_response_node, execute_tools_node

def should_continue(state: AgentState) -> str:
    """
    Decides whether to branch to the tool executor node or finish execution.
    """
    tool_calls = state.get("tool_calls", [])
    if tool_calls:
        return "execute_tools"
    return END

# Compile LangGraph State Machine
workflow = StateGraph(AgentState)

# Add Node definitions
workflow.add_node("retrieve_context", retrieve_context_node)
workflow.add_node("generate_response", generate_response_node)
workflow.add_node("execute_tools", execute_tools_node)

# Set Entry Point
workflow.set_entry_point("retrieve_context")

# Link static edge
workflow.add_edge("retrieve_context", "generate_response")

# Link conditional edge
workflow.add_conditional_edges(
    "generate_response",
    should_continue,
    {
        "execute_tools": "execute_tools",
        END: END
    }
)

# Loop back to generate response after tool execution
workflow.add_edge("execute_tools", "generate_response")

# Export compiled graph
agent_graph = workflow.compile()
