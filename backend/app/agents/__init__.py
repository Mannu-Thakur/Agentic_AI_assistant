"""
app/agents/__init__.py — Multi-Agent Workspace package.

Exports the agent registry singleton, base types, and artifact store
so all other modules can import from a single location:

    from app.agents import agent_registry, BaseAgent, artifact_store
"""
from app.agents.registry import agent_registry, BaseAgent, AgentTask, AgentResult
from app.agents.artifacts import artifact_store

__all__ = ["agent_registry", "BaseAgent", "AgentTask", "AgentResult", "artifact_store"]

